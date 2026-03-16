#include <array>
#include <chrono>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <filesystem>
#include <unordered_map>
#include <regex>

#include <espeak-ng/speak_lib.h>
#include <onnxruntime_cxx_api.h>
#include <spdlog/spdlog.h>

#include "json.hpp"
#include "piper.hpp"
#include "utf8.h"
#include "wavfile.hpp"
#include "openjtalk_phonemize.hpp"
#include "phoneme_parser.hpp"

#ifdef USE_ARM64_NEON
#include "audio_neon.hpp"
#endif

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <io.h>
#define access _access
#define F_OK 0
#else
#include <unistd.h>
#endif

#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif


namespace piper {

#ifdef _PIPER_VERSION
// https://stackoverflow.com/questions/47346133/how-to-use-a-define-inside-a-format-string
#define _STR(x) #x
#define STR(x) _STR(x)
const std::string VERSION = STR(_PIPER_VERSION);
#else
const std::string VERSION = "";
#endif

// Maximum value for 16-bit signed WAV sample
const float MAX_WAV_VALUE = 32767.0f;

// PUA to multi-char phoneme mapping for display
static const std::unordered_map<char32_t, std::string> puaToPhoneme = {
    {0xE000, "a:"}, {0xE001, "i:"}, {0xE002, "u:"}, {0xE003, "e:"}, {0xE004, "o:"},
    {0xE005, "cl"}, {0xE006, "ky"}, {0xE007, "kw"}, {0xE008, "gy"}, {0xE009, "gw"},
    {0xE00A, "ty"}, {0xE00B, "dy"}, {0xE00C, "py"}, {0xE00D, "by"}, {0xE00E, "ch"},
    {0xE00F, "ts"}, {0xE010, "sh"}, {0xE011, "zy"}, {0xE012, "hy"}, {0xE013, "ny"},
    {0xE014, "my"}, {0xE015, "ry"},
    // Question type markers (Issue #204)
    {0xE016, "?!"}, {0xE017, "?."}, {0xE018, "?~"},
    // N phoneme variants (Issue #207)
    {0xE019, "N_m"}, {0xE01A, "N_n"}, {0xE01B, "N_ng"}, {0xE01C, "N_uvular"}
};

// Convert phoneme to readable string for logging
static std::string phonemeToString(Phoneme ph) {
    // Check if it's a PUA character
    if (ph >= 0xE000 && ph <= 0xF8FF) {
        auto it = puaToPhoneme.find(ph);
        if (it != puaToPhoneme.end()) {
            return it->second;
        }
    }
    
    // Convert regular character to string
    std::string result;
    utf8::append(ph, std::back_inserter(result));
    return result;
}

const std::string instanceName{"piper"};

std::string getVersion() { return VERSION; }

// True if the string is a single UTF-8 codepoint
bool isSingleCodepoint(std::string s) {
  return utf8::distance(s.begin(), s.end()) == 1;
}

// Get the first UTF-8 codepoint of a string
Phoneme getCodepoint(std::string s) {
  utf8::iterator character_iter(s.begin(), s.begin(), s.end());
  return *character_iter;
}

// Load JSON config information for phonemization
void parsePhonemizeConfig(json &configRoot, PhonemizeConfig &phonemizeConfig) {
  // {
  //     "espeak": {
  //         "voice": "<language code>"
  //     },
  //     "phoneme_type": "<espeak or text>",
  //     "phoneme_map": {
  //         "<from phoneme>": ["<to phoneme 1>", "<to phoneme 2>", ...]
  //     },
  //     "phoneme_id_map": {
  //         "<phoneme>": [<id1>, <id2>, ...]
  //     }
  // }

  if (configRoot.contains("espeak")) {
    auto espeakValue = configRoot["espeak"];
    if (espeakValue.contains("voice")) {
      phonemizeConfig.eSpeak.voice = espeakValue["voice"].get<std::string>();
    }
  }

  if (configRoot.contains("phoneme_type")) {
    auto phonemeTypeStr = configRoot["phoneme_type"].get<std::string>();
    if (phonemeTypeStr == "text") {
      phonemizeConfig.phonemeType = TextPhonemes;
    } else if (phonemeTypeStr == "openjtalk") {
      phonemizeConfig.phonemeType = OpenJTalkPhonemes;
      // OpenJTalk models don't use padding between phonemes
      phonemizeConfig.interspersePad = false;
    } else if (phonemeTypeStr == "multilingual") {
      phonemizeConfig.phonemeType = MultilingualPhonemes;
      // Multilingual models use OpenJTalk phonemization but WITH intersperse padding
      // (interspersePad defaults to true, so no change needed)
    }
  }

  // phoneme to [id] map
  // Maps phonemes to one or more phoneme ids (required).
  if (configRoot.contains("phoneme_id_map")) {
    auto phonemeIdMapValue = configRoot["phoneme_id_map"];
    for (auto &fromPhonemeItem : phonemeIdMapValue.items()) {
      std::string fromPhoneme = fromPhonemeItem.key();
      if (!isSingleCodepoint(fromPhoneme)) {
        std::stringstream idsStr;
        for (auto &toIdValue : fromPhonemeItem.value()) {
          PhonemeId toId = toIdValue.get<PhonemeId>();
          idsStr << toId << ",";
        }

        spdlog::error("\"{}\" is not a single codepoint (ids={})", fromPhoneme,
                      idsStr.str());
        throw std::runtime_error(
            "Phonemes must be one codepoint (phoneme id map)");
      }

      auto fromCodepoint = getCodepoint(fromPhoneme);
      for (auto &toIdValue : fromPhonemeItem.value()) {
        PhonemeId toId = toIdValue.get<PhonemeId>();
        phonemizeConfig.phonemeIdMap[fromCodepoint].push_back(toId);
      }
    }
  }

  // phoneme to [phoneme] map
  // Maps phonemes to one or more other phonemes (not normally used).
  if (configRoot.contains("phoneme_map")) {
    if (!phonemizeConfig.phonemeMap) {
      phonemizeConfig.phonemeMap.emplace();
    }

    auto phonemeMapValue = configRoot["phoneme_map"];
    for (auto &fromPhonemeItem : phonemeMapValue.items()) {
      std::string fromPhoneme = fromPhonemeItem.key();
      if (!isSingleCodepoint(fromPhoneme)) {
        spdlog::error("\"{}\" is not a single codepoint", fromPhoneme);
        throw std::runtime_error(
            "Phonemes must be one codepoint (phoneme map)");
      }

      auto fromCodepoint = getCodepoint(fromPhoneme);
      for (auto &toPhonemeValue : fromPhonemeItem.value()) {
        std::string toPhoneme = toPhonemeValue.get<std::string>();
        if (!isSingleCodepoint(toPhoneme)) {
          throw std::runtime_error(
              "Phonemes must be one codepoint (phoneme map)");
        }

        auto toCodepoint = getCodepoint(toPhoneme);
        (*phonemizeConfig.phonemeMap)[fromCodepoint].push_back(toCodepoint);
      }
    }
  }

} /* parsePhonemizeConfig */

// Load JSON config for audio synthesis
void parseSynthesisConfig(json &configRoot, SynthesisConfig &synthesisConfig) {
  // {
  //     "audio": {
  //         "sample_rate": 22050
  //     },
  //     "inference": {
  //         "noise_scale": 0.667,
  //         "length_scale": 1,
  //         "noise_w": 0.8,
  //         "phoneme_silence": {
  //           "<phoneme>": <seconds of silence>,
  //           ...
  //         }
  //     }
  // }

  if (configRoot.contains("audio")) {
    auto audioValue = configRoot["audio"];
    if (audioValue.contains("sample_rate")) {
      // Default sample rate is 22050 Hz
      synthesisConfig.sampleRate = audioValue.value("sample_rate", 22050);
    }
  }

  if (configRoot.contains("inference")) {
    // Overrides default inference settings
    auto inferenceValue = configRoot["inference"];
    if (inferenceValue.contains("noise_scale")) {
      synthesisConfig.noiseScale = inferenceValue.value("noise_scale", 0.667f);
    }

    if (inferenceValue.contains("length_scale")) {
      synthesisConfig.lengthScale = inferenceValue.value("length_scale", 1.0f);
    }

    if (inferenceValue.contains("noise_w")) {
      synthesisConfig.noiseW = inferenceValue.value("noise_w", 0.8f);
    }

    if (inferenceValue.contains("phoneme_silence")) {
      // phoneme -> seconds of silence to add after
      synthesisConfig.phonemeSilenceSeconds.emplace();
      auto phonemeSilenceValue = inferenceValue["phoneme_silence"];
      for (auto &phonemeItem : phonemeSilenceValue.items()) {
        std::string phonemeStr = phonemeItem.key();
        if (!isSingleCodepoint(phonemeStr)) {
          spdlog::error("\"{}\" is not a single codepoint", phonemeStr);
          throw std::runtime_error(
              "Phonemes must be one codepoint (phoneme silence)");
        }

        auto phoneme = getCodepoint(phonemeStr);
        (*synthesisConfig.phonemeSilenceSeconds)[phoneme] =
            phonemeItem.value().get<float>();
      }

    } // if phoneme_silence

  } // if inference

} /* parseSynthesisConfig */

void parseModelConfig(json &configRoot, ModelConfig &modelConfig) {

  modelConfig.numSpeakers = configRoot["num_speakers"].get<SpeakerId>();

  if (configRoot.contains("speaker_id_map")) {
    if (!modelConfig.speakerIdMap) {
      modelConfig.speakerIdMap.emplace();
    }

    auto speakerIdMapValue = configRoot["speaker_id_map"];
    for (auto &speakerItem : speakerIdMapValue.items()) {
      std::string speakerName = speakerItem.key();
      (*modelConfig.speakerIdMap)[speakerName] =
          speakerItem.value().get<SpeakerId>();
    }
  }

} /* parseModelConfig */

// Constants for phoneme timing
static const std::string UNKNOWN_PHONEME = "?";
static const float JAPANESE_CL_OVERLAP_RATIO = 0.3f;
static const int DEFAULT_HOP_SIZE = 256;

// Helper function to extract phoneme timings from duration information
std::vector<PhonemeInfo> extractTimingsFromDurations(
    const std::vector<float>& durations,
    const std::vector<PhonemeId>& phonemeIds,
    const PhonemeIdMap& idMap,
    int hopSize,
    int sampleRate,
    PhonemeType phonemeType
) {
    std::vector<PhonemeInfo> timings;
    
    // Build reverse map from phoneme ID to string
    std::unordered_map<PhonemeId, std::string> phonemeIdToStringMap;
    for (const auto& [phonemeStr, ids] : idMap) {
        if (!ids.empty()) {
            // Map phoneme ID to its string representation
            phonemeIdToStringMap[ids[0]] = phonemeStr;
        }
    }
    
    float frameLength = static_cast<float>(hopSize) / sampleRate;
    float currentTime = 0.0f;
    int currentFrame = 0;
    
    for (size_t i = 0; i < phonemeIds.size() && i < durations.size(); ++i) {
        PhonemeId id = phonemeIds[i];
        float duration = durations[i];  // Duration in frames
        
        // Skip special tokens (PAD, BOS, EOS)
        if (id == 0 || id == 1 || id == 2) {
            currentFrame += static_cast<int>(duration);
            currentTime += duration * frameLength;
            continue;
        }
        
        // Get phoneme string
        std::string phonemeStr = UNKNOWN_PHONEME;
        auto it = phonemeIdToStringMap.find(id);
        if (it != phonemeIdToStringMap.end()) {
            phonemeStr = it->second;
        } else {
            // Try to decode single character
            if (id > 2 && id < 256) {
                phonemeStr = std::string(1, static_cast<char>(id));
            }
        }
        
        PhonemeInfo info;
        info.phoneme = phonemeStr;
        info.start_time = currentTime;
        info.start_frame = currentFrame;
        
        currentFrame += static_cast<int>(duration);
        currentTime += duration * frameLength;
        
        info.end_time = currentTime;
        info.end_frame = currentFrame;
        
        timings.push_back(info);
    }
    
    // Adjust timings for Japanese if needed
    if (usesOpenJTalk(phonemeType)) {
        for (size_t i = 0; i < timings.size(); ++i) {
            // Convert PUA mapped phonemes back to original
            if (timings[i].phoneme.size() == 1) {
                // Get the first character as a codepoint
                Phoneme ph = static_cast<Phoneme>(timings[i].phoneme[0]);
                auto it = puaToPhoneme.find(ph);
                if (it != puaToPhoneme.end()) {
                    timings[i].phoneme = it->second;
                }
            }
            
            // Adjust timing for specific phonemes like 'cl' (促音)
            if (timings[i].phoneme == "cl" && i > 0) {
                // Overlap with previous phoneme
                float overlap = (timings[i].end_time - timings[i].start_time) * JAPANESE_CL_OVERLAP_RATIO;
                timings[i-1].end_time += overlap;
                timings[i].start_time += overlap;
            }
        }
    }
    
    return timings;
}

// Helper function to find espeak-ng data directory
std::string findEspeakDataPath() {
    // First, check environment variable
    const char* env_path = getenv("ESPEAK_DATA_PATH");
    if (env_path && access(env_path, F_OK) == 0) {
        spdlog::debug("Using ESPEAK_DATA_PATH from environment: {}", env_path);
        return env_path;
    }
    
    // Try to find data relative to executable
    char exe_path[4096] = {0};
    
#ifdef _WIN32
    // Use wide char API for better Unicode support on Windows
    wchar_t exe_path_w[4096] = {0};
    DWORD size = ::GetModuleFileNameW(NULL, exe_path_w, sizeof(exe_path_w) / sizeof(wchar_t));
    if (size > 0 && size <= (sizeof(exe_path_w) / sizeof(wchar_t) - 1)) {
        // Convert to UTF-8
        int utf8_size = WideCharToMultiByte(CP_UTF8, 0, exe_path_w, -1, nullptr, 0, nullptr, nullptr);
        if (utf8_size > 0 && utf8_size <= sizeof(exe_path)) {
            WideCharToMultiByte(CP_UTF8, 0, exe_path_w, -1, exe_path, utf8_size, nullptr, nullptr);
        }
    }
#elif defined(__APPLE__)
    uint32_t size = sizeof(exe_path);
    if (_NSGetExecutablePath(exe_path, &size) != 0) {
        exe_path[0] = '\0';
    }
#elif defined(__linux__)
    ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len > 0) {
        exe_path[len] = '\0';
    } else {
        exe_path[0] = '\0';
    }
#endif
    
    if (exe_path[0] != '\0') {
        std::filesystem::path exePath(exe_path);
        std::filesystem::path exeDir = exePath.parent_path();
        
        // Try different relative locations
        std::vector<std::filesystem::path> candidates = {
#ifdef _WIN32
            // Windows-specific search paths - prioritize exe directory
            exeDir / "espeak-ng-data",                    // Same directory as exe (highest priority)
            exeDir / ".." / "share" / "espeak-ng-data",   // Standard distribution location
            exeDir / "share" / "espeak-ng-data",          // Alternative share location
            exeDir / ".." / "espeak-ng-data",             // Parent directory
            exeDir / ".." / "lib" / "espeak-ng-data",     // lib directory
            // Try to find in build directories (for development)
            exeDir / ".." / ".." / "share" / "espeak-ng-data",
            // Common installation paths
            "C:\\Program Files\\eSpeak NG\\espeak-ng-data",
            "C:\\Program Files (x86)\\eSpeak NG\\espeak-ng-data",
            "C:\\espeak-ng-data"
#else
            exeDir / "espeak-ng-data",                    // Same directory as exe
            exeDir / ".." / "share" / "espeak-ng-data",   // Installed location
            exeDir / ".." / "espeak-ng-data",             // Alternative location
            exeDir / ".." / "lib" / "espeak-ng-data"      // Another alternative for Unix
#endif
        };
        
        for (const auto& candidate : candidates) {
            try {
                auto absPath = std::filesystem::absolute(candidate);
                // Normalize the path to avoid issues with mixed separators
                auto normalizedPath = absPath.lexically_normal();
                
                if (std::filesystem::exists(normalizedPath)) {
                    // Verify it's actually a directory with expected content
                    auto phontabPath = normalizedPath / "phontab";
                    if (std::filesystem::exists(phontabPath)) {
                        spdlog::info("Found valid espeak-ng-data at: {}", normalizedPath.string());
                        
#ifdef _WIN32
                        // On Windows, convert to native path separators
                        auto nativePath = normalizedPath.make_preferred();
                        return nativePath.string();
#else
                        return normalizedPath.string();
#endif
                    } else {
                        spdlog::debug("Directory {} exists but missing phontab file", normalizedPath.string());
                    }
                }
            } catch (const std::exception& e) {
                spdlog::debug("Error checking path {}: {}", candidate.string(), e.what());
            }
        }
        
        // Log all paths we tried for debugging
        spdlog::warn("Could not find espeak-ng-data directory. Searched in:");
        // Store normalized paths to avoid duplicate operations
        std::vector<std::pair<std::filesystem::path, std::string>> searchedPaths;
        for (const auto& candidate : candidates) {
            try {
                auto absPath = std::filesystem::absolute(candidate).lexically_normal();
                searchedPaths.push_back({candidate, absPath.string()});
                spdlog::warn("  - {}", absPath.string());
            } catch (...) {
                searchedPaths.push_back({candidate, candidate.string() + " (invalid path)"});
                spdlog::warn("  - {} (invalid path)", candidate.string());
            }
        }
    }
    
    // If nothing found, return empty string (espeak will use its default)
    spdlog::warn("espeak-ng will attempt to use its built-in default data");
    return "";
}

void initialize(PiperConfig &config) {
  if (config.useESpeak) {
    // Set up espeak-ng for calling espeak_TextToPhonemesWithTerminator
    // See: https://github.com/rhasspy/espeak-ng
    spdlog::debug("Initializing eSpeak");
    
    // If no path was provided, try to find it automatically
    if (config.eSpeakDataPath.empty()) {
        config.eSpeakDataPath = findEspeakDataPath();
    }
    
#ifdef _WIN32
    // On Windows, normalize the path to use native separators
    if (!config.eSpeakDataPath.empty()) {
        try {
            std::filesystem::path dataPath(config.eSpeakDataPath);
            dataPath = dataPath.lexically_normal().make_preferred();
            config.eSpeakDataPath = dataPath.string();
            spdlog::debug("Normalized espeak-ng-data path: {}", config.eSpeakDataPath);
        } catch (const std::exception& e) {
            spdlog::warn("Failed to normalize espeak-ng-data path: {}", e.what());
        }
    }
#endif
    
    const char* espeak_path = config.eSpeakDataPath.empty() ? nullptr : config.eSpeakDataPath.c_str();
    
    spdlog::info("Calling espeak_Initialize with path: {}", 
                 espeak_path ? espeak_path : "(using built-in default)");
    
#ifdef _WIN32
    // On Windows, add extra debugging for DLL loading issues
    spdlog::debug("Current DLL directory: {}", 
                  []() -> std::string {
                      wchar_t buffer[MAX_PATH] = {0};
                      DWORD result = ::GetDllDirectoryW(MAX_PATH, buffer);
                      if (result > 0 && result < MAX_PATH) {
                          return std::filesystem::path(buffer).string();
                      }
                      return "(not set)";
                  }());
                  
    // Verify espeak-ng.dll is loaded
    HMODULE espeakModule = ::GetModuleHandleA("espeak-ng.dll");
    if (espeakModule) {
        wchar_t dllPath[MAX_PATH] = {0};
        if (::GetModuleFileNameW(espeakModule, dllPath, MAX_PATH) > 0) {
            // Convert once and store the result
            std::string dllPathStr = std::filesystem::path(dllPath).string();
            spdlog::debug("espeak-ng.dll loaded from: {}", dllPathStr);
        }
    } else {
        spdlog::warn("espeak-ng.dll not yet loaded");
    }
#endif
    
    int result = espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS,
                                   /*buflength*/ 0,
                                   /*path*/ espeak_path,
                                   /*options*/ 0);
    if (result < 0) {
      spdlog::error("espeak_Initialize failed with code: {}", result);
      
#ifdef _WIN32
      DWORD lastError = ::GetLastError();
      if (lastError != 0) {
          spdlog::error("Windows last error code: {} (0x{:X})", lastError, lastError);
      }
      
      // Provide helpful error messages based on the error code
      if (result == -1) {
          spdlog::error("eSpeak initialization failed: Unable to access espeak-ng-data directory");
          spdlog::error("Please ensure espeak-ng-data directory is present in one of these locations:");
          spdlog::error("  1. Same directory as piper.exe");
          spdlog::error("  2. ../share/espeak-ng-data relative to piper.exe");
          spdlog::error("  3. Set ESPEAK_DATA_PATH environment variable");
          spdlog::error("  4. Use --espeak_data command line option");
      }
#endif
      
      throw std::runtime_error("Failed to initialize eSpeak-ng. Check logs for details.");
    }

    spdlog::info("Successfully initialized eSpeak with data path: {}", 
                 espeak_path ? espeak_path : "(built-in default)");
  }

  // Load onnx model for libtashkeel
  // https://github.com/mush42/libtashkeel/
  if (config.useTashkeel) {
    spdlog::debug("Using libtashkeel for diacritization");
    if (!config.tashkeelModelPath) {
      throw std::runtime_error("No path to libtashkeel model");
    }

    spdlog::debug("Loading libtashkeel model from {}",
                  config.tashkeelModelPath.value());
    config.tashkeelState = std::make_unique<tashkeel::State>();
    tashkeel::tashkeel_load(config.tashkeelModelPath.value(),
                            *config.tashkeelState);
    spdlog::debug("Initialized libtashkeel");
  }

  spdlog::info("Initialized piper");
}

void terminate(PiperConfig &config) {
  if (config.useESpeak) {
    // Clean up espeak-ng
    spdlog::debug("Terminating eSpeak");
    espeak_Terminate();
    spdlog::debug("Terminated eSpeak");
  }

  spdlog::info("Terminated piper");
}

void loadModel(std::string modelPath, ModelSession &session, bool useCuda, int gpuDeviceId = 0) {
  spdlog::debug("loadModel called with path: {}", modelPath);
  spdlog::debug("Creating ONNX Runtime environment");
  try {
    session.env = Ort::Env(OrtLoggingLevel::ORT_LOGGING_LEVEL_WARNING,
                           instanceName.c_str());
    session.env.DisableTelemetryEvents();
  } catch (const std::exception& e) {
    spdlog::error("Failed to create ONNX Runtime environment: {}", e.what());
    throw;
  }

  if (useCuda) {
    // Use CUDA provider
    OrtCUDAProviderOptions cuda_options{};
    cuda_options.device_id = gpuDeviceId;
    cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic;
    session.options.AppendExecutionProvider_CUDA(cuda_options);
    spdlog::info("Using CUDA execution provider with GPU device ID: {}", gpuDeviceId);
  }

  // Slows down performance by ~2x
  // session.options.SetIntraOpNumThreads(1);

  // Roughly doubles load time for no visible inference benefit
  // session.options.SetGraphOptimizationLevel(
  //     GraphOptimizationLevel::ORT_ENABLE_EXTENDED);

  session.options.SetGraphOptimizationLevel(
      GraphOptimizationLevel::ORT_DISABLE_ALL);

  // Slows down performance very slightly
  // session.options.SetExecutionMode(ExecutionMode::ORT_PARALLEL);

  session.options.DisableCpuMemArena();
  session.options.DisableMemPattern();
  session.options.DisableProfiling();

  auto startTime = std::chrono::steady_clock::now();

#ifdef _WIN32
  auto modelPathW = std::wstring(modelPath.begin(), modelPath.end());
  auto modelPathStr = modelPathW.c_str();
#else
  auto modelPathStr = modelPath.c_str();
#endif

  session.onnx = Ort::Session(session.env, modelPathStr, session.options);

  auto endTime = std::chrono::steady_clock::now();
  spdlog::debug("Loaded onnx model in {} second(s)",
                std::chrono::duration<double>(endTime - startTime).count());
  
  // Check if model has duration output
  size_t numOutputNodes = session.onnx.GetOutputCount();
  if (numOutputNodes >= 2) {
    // Check if second output is named "durations"
    auto outputName = session.onnx.GetOutputNameAllocated(1, session.allocator);
    if (std::string(outputName.get()) == "durations") {
      session.hasDurationOutput = true;
      spdlog::debug("Model supports duration output for phoneme timing");
    }
  }

  // Check model inputs for optional features
  size_t numInputNodes = session.onnx.GetInputCount();
  for (size_t i = 0; i < numInputNodes; i++) {
    auto inputName = session.onnx.GetInputNameAllocated(i, session.allocator);
    std::string name(inputName.get());
    if (name == "prosody_features") {
      session.hasProsodyInput = true;
      spdlog::debug("Model supports prosody features input (A1/A2/A3)");
    } else if (name == "sid") {
      session.hasMultiSpeaker = true;
      spdlog::debug("Model supports multi-speaker (sid input)");
    } else if (name == "lid") {
      session.hasLidInput = true;
      spdlog::debug("Model supports language ID (lid input)");
    }
  }
}

// Load Onnx model and JSON config file
void loadVoice(PiperConfig &config, std::string modelPath,
               std::string modelConfigPath, Voice &voice,
               std::optional<SpeakerId> &speakerId, bool useCuda,
               int gpuDeviceId) {
  spdlog::debug("loadVoice called with modelPath={}, configPath={}", modelPath, modelConfigPath);
  spdlog::debug("Parsing voice config at {}", modelConfigPath);
  std::ifstream modelConfigFile(modelConfigPath);
  if (!modelConfigFile.is_open()) {
    throw std::runtime_error("Failed to open model config file: " + modelConfigPath);
  }
  voice.configRoot = json::parse(modelConfigFile);

  parsePhonemizeConfig(voice.configRoot, voice.phonemizeConfig);
  parseSynthesisConfig(voice.configRoot, voice.synthesisConfig);
  parseModelConfig(voice.configRoot, voice.modelConfig);

  if (voice.modelConfig.numSpeakers > 1) {
    // Multi-speaker model
    if (speakerId) {
      voice.synthesisConfig.speakerId = speakerId;
    } else {
      // Default speaker
      voice.synthesisConfig.speakerId = 0;
    }
  }

  spdlog::debug("Voice contains {} speaker(s)", voice.modelConfig.numSpeakers);

  loadModel(modelPath, voice.session, useCuda, gpuDeviceId);

} /* loadVoice */

// Phoneme ids to WAV audio
void synthesize(std::vector<PhonemeId> &phonemeIds,
                SynthesisConfig &synthesisConfig, ModelSession &session,
                std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                Voice *voice = nullptr,
                std::vector<int64_t> *prosodyFeatures = nullptr) {
  spdlog::debug("Synthesizing audio for {} phoneme id(s)", phonemeIds.size());

  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  // Allocate
  std::vector<int64_t> phonemeIdLengths{(int64_t)phonemeIds.size()};
  std::vector<float> scales{synthesisConfig.noiseScale,
                            synthesisConfig.lengthScale,
                            synthesisConfig.noiseW};

  std::vector<Ort::Value> inputTensors;
  std::vector<int64_t> phonemeIdsShape{1, (int64_t)phonemeIds.size()};
  inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
      memoryInfo, phonemeIds.data(), phonemeIds.size(), phonemeIdsShape.data(),
      phonemeIdsShape.size()));

  std::vector<int64_t> phomemeIdLengthsShape{(int64_t)phonemeIdLengths.size()};
  inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
      memoryInfo, phonemeIdLengths.data(), phonemeIdLengths.size(),
      phomemeIdLengthsShape.data(), phomemeIdLengthsShape.size()));

  std::vector<int64_t> scalesShape{(int64_t)scales.size()};
  inputTensors.push_back(
      Ort::Value::CreateTensor<float>(memoryInfo, scales.data(), scales.size(),
                                      scalesShape.data(), scalesShape.size()));

  // Build input names dynamically based on model capabilities
  std::vector<const char *> inputNamesVec = {"input", "input_lengths", "scales"};

  // Add speaker id only for multi-speaker models
  // NOTE: These must be kept outside the "if" below to avoid being deallocated.
  std::vector<int64_t> speakerId{
      (int64_t)synthesisConfig.speakerId.value_or(0)};
  std::vector<int64_t> speakerIdShape{(int64_t)speakerId.size()};

  if (session.hasMultiSpeaker) {
    inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
        memoryInfo, speakerId.data(), speakerId.size(), speakerIdShape.data(),
        speakerIdShape.size()));
    inputNamesVec.push_back("sid");
  }

  // Add language id for multilingual models (default to 0 = first language)
  std::vector<int64_t> languageId{0};
  std::vector<int64_t> languageIdShape{(int64_t)languageId.size()};

  if (session.hasLidInput) {
    inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
        memoryInfo, languageId.data(), languageId.size(),
        languageIdShape.data(), languageIdShape.size()));
    inputNamesVec.push_back("lid");
  }

  // Add prosody features if model supports them and they are provided
  // prosodyFeatures is a flat array of [a1, a2, a3, a1, a2, a3, ...] for each phoneme
  std::vector<int64_t> zeroProsody;
  if (session.hasProsodyInput) {
    std::vector<int64_t> prosodyShape{1, (int64_t)phonemeIds.size(), 3};
    if (prosodyFeatures && prosodyFeatures->size() == phonemeIds.size() * 3) {
      inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
          memoryInfo, prosodyFeatures->data(), prosodyFeatures->size(),
          prosodyShape.data(), prosodyShape.size()));
    } else {
      // Use zeros if no prosody features provided
      zeroProsody.resize(phonemeIds.size() * 3, 0);
      inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
          memoryInfo, zeroProsody.data(), zeroProsody.size(),
          prosodyShape.data(), prosodyShape.size()));
    }
    inputNamesVec.push_back("prosody_features");
  }
  
  // Check if we should get duration output
  std::vector<const char *> outputNamesVec;
  outputNamesVec.push_back("output");
  if (session.hasDurationOutput) {
    outputNamesVec.push_back("durations");
  }

  // Infer
  auto startTime = std::chrono::steady_clock::now();
  auto outputTensors = session.onnx.Run(
      Ort::RunOptions{nullptr}, inputNamesVec.data(), inputTensors.data(),
      inputTensors.size(), outputNamesVec.data(), outputNamesVec.size());
  auto endTime = std::chrono::steady_clock::now();

  if (outputTensors.empty() || (!outputTensors.front().IsTensor())) {
    throw std::runtime_error("Invalid output tensors");
  }
  auto inferDuration = std::chrono::duration<double>(endTime - startTime);
  result.inferSeconds = inferDuration.count();

  const float *audio = outputTensors.front().GetTensorData<float>();
  auto audioShape =
      outputTensors.front().GetTensorTypeAndShapeInfo().GetShape();
  int64_t audioCount = audioShape[audioShape.size() - 1];

  result.audioSeconds = (double)audioCount / (double)synthesisConfig.sampleRate;
  result.realTimeFactor = 0.0;
  if (result.audioSeconds > 0) {
    result.realTimeFactor = result.inferSeconds / result.audioSeconds;
  }
  spdlog::debug("Synthesized {} second(s) of audio in {} second(s)",
                result.audioSeconds, result.inferSeconds);

  // Get max audio value for scaling
  float maxAudioValue = 0.01f;
  
#ifdef USE_ARM64_NEON
  maxAudioValue = findMaxAudioValueNEON(audio, audioCount);
#else
  for (int64_t i = 0; i < audioCount; i++) {
    float audioValue = abs(audio[i]);
    if (audioValue > maxAudioValue) {
      maxAudioValue = audioValue;
    }
  }
#endif

  // We know the size up front
  audioBuffer.reserve(audioCount);

  // Scale audio to fill range and convert to int16
  float audioScale = (MAX_WAV_VALUE / std::max(0.01f, maxAudioValue));
  
#ifdef USE_ARM64_NEON
  // Resize buffer to final size for NEON implementation
  audioBuffer.resize(audioCount);
  scaleAndConvertAudioNEON(audio, audioBuffer.data(), audioCount, audioScale);
#else
  for (int64_t i = 0; i < audioCount; i++) {
    int16_t intAudioValue = static_cast<int16_t>(
        std::clamp(audio[i] * audioScale,
                   static_cast<float>(std::numeric_limits<int16_t>::min()),
                   static_cast<float>(std::numeric_limits<int16_t>::max())));

    audioBuffer.push_back(intAudioValue);
  }
#endif

  // Extract phoneme timing information if available
  if (session.hasDurationOutput && outputTensors.size() >= 2 && voice != nullptr) {
    auto& durationTensor = outputTensors[1];
    if (durationTensor.IsTensor()) {
      const float *durations = durationTensor.GetTensorData<float>();
      auto durationShape = durationTensor.GetTensorTypeAndShapeInfo().GetShape();
      size_t durationCount = 1;
      for (auto dim : durationShape) {
        durationCount *= dim;
      }
      
      // Convert durations to vector
      std::vector<float> durationVec(durations, durations + durationCount);
      
      // Extract timing information
      // Get hop_size from config
      int hopSize = DEFAULT_HOP_SIZE;
      if (voice->configRoot.contains("audio") && 
          voice->configRoot["audio"].contains("hop_size")) {
        hopSize = voice->configRoot["audio"]["hop_size"];
      }
      
      result.phonemeTimings = extractTimingsFromDurations(
          durationVec, phonemeIds,
          voice->phonemizeConfig.phonemeIdMap,
          hopSize,
          voice->synthesisConfig.sampleRate,
          voice->phonemizeConfig.phonemeType
      );
      result.hasTimingInfo = true;
      
      spdlog::debug("Extracted timing for {} phonemes", result.phonemeTimings.size());
    }
  }

  // Clean up
  for (std::size_t i = 0; i < outputTensors.size(); i++) {
    Ort::detail::OrtRelease(outputTensors[i].release());
  }

  for (std::size_t i = 0; i < inputTensors.size(); i++) {
    Ort::detail::OrtRelease(inputTensors[i].release());
  }
}

// ----------------------------------------------------------------------------

// Phonemize text and synthesize audio
void textToAudio(PiperConfig &config, Voice &voice, std::string text,
                 std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                 const std::function<void()> &audioCallback,
                 const std::vector<ProsodyFeature> *externalProsody) {

  std::size_t sentenceSilenceSamples = 0;
  if (voice.synthesisConfig.sentenceSilenceSeconds > 0) {
    sentenceSilenceSamples = (std::size_t)(
        voice.synthesisConfig.sentenceSilenceSeconds *
        voice.synthesisConfig.sampleRate * voice.synthesisConfig.channels);
  }

  if (config.useTashkeel) {
    if (!config.tashkeelState) {
      throw std::runtime_error("Tashkeel model is not loaded");
    }

    spdlog::debug("Diacritizing text with libtashkeel: {}", text);
    text = tashkeel::tashkeel_run(text, *config.tashkeelState);
  }

  // Parse text for [[ phonemes ]] notation
  auto textSegments = parsePhonemeNotation(text);
  
  // Phonemes for each sentence
  spdlog::debug("Phonemizing text: {}", text);
  std::vector<std::vector<Phoneme>> phonemes;

  // Prosody features for each sentence (only used for OpenJTalk with prosody-enabled models)
  std::vector<std::vector<ProsodyFeature>> allProsodyFeatures;
  bool useProsody = voice.session.hasProsodyInput &&
                    usesOpenJTalk(voice.phonemizeConfig.phonemeType);

  // Process each segment
  for (const auto& segment : textSegments) {
    if (segment.isPhonemes) {
      // Direct phoneme input
      spdlog::debug("Processing direct phoneme input: {}", segment.text);
      auto parsedPhonemes = parsePhonemeString(segment.text, static_cast<int>(voice.phonemizeConfig.phonemeType));

      // Add as a single "sentence"
      phonemes.push_back(parsedPhonemes);

      // Add empty prosody features for direct phoneme input
      if (useProsody) {
        std::vector<ProsodyFeature> emptyProsody(parsedPhonemes.size(), {0, 0, 0});
        allProsodyFeatures.push_back(std::move(emptyProsody));
      }
    } else {
      // Regular text - phonemize as usual
      std::vector<std::vector<Phoneme>> segmentPhonemes;
      std::vector<std::vector<ProsodyFeature>> segmentProsody;

      if (voice.phonemizeConfig.phonemeType == eSpeakPhonemes) {
        // Use espeak-ng for phonemization
        eSpeakPhonemeConfig eSpeakConfig;
        eSpeakConfig.voice = voice.phonemizeConfig.eSpeak.voice;
        phonemize_eSpeak(segment.text, eSpeakConfig, segmentPhonemes);
      } else if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
        // Japanese/Multilingual OpenJTalk phonemizer
        if (useProsody) {
          phonemize_openjtalk_with_prosody(segment.text, segmentPhonemes, segmentProsody);
        } else {
          phonemize_openjtalk(segment.text, segmentPhonemes);
        }

        // If OpenJTalk failed, fall back to eSpeak for multilingual models
        if (segmentPhonemes.empty() && !segment.text.empty()) {
          if (voice.phonemizeConfig.phonemeType == MultilingualPhonemes) {
            spdlog::warn("OpenJTalk unavailable, falling back to eSpeak for multilingual model");
            eSpeakPhonemeConfig eSpeakConfig;
            eSpeakConfig.voice = "en";
            phonemize_eSpeak(segment.text, eSpeakConfig, segmentPhonemes);
          } else {
            throw std::runtime_error("OpenJTalk is not available or failed to process Japanese text. "
                                     "Cannot synthesize Japanese without OpenJTalk.");
          }
        }
      } else {
        // Use UTF-8 codepoints as "phonemes"
        CodepointsPhonemeConfig codepointsConfig;
        phonemize_codepoints(segment.text, codepointsConfig, segmentPhonemes);
      }

      // Add all sentences from this segment
      for (size_t i = 0; i < segmentPhonemes.size(); i++) {
        phonemes.push_back(std::move(segmentPhonemes[i]));

        if (useProsody) {
          if (i < segmentProsody.size()) {
            allProsodyFeatures.push_back(std::move(segmentProsody[i]));
          } else {
            // Fallback: create zero prosody features
            std::vector<ProsodyFeature> zeroProsody(phonemes.back().size(), {0, 0, 0});
            allProsodyFeatures.push_back(std::move(zeroProsody));
          }
        }
      }
    }
  }

  // Override prosody features with external data if provided
  if (externalProsody && !externalProsody->empty() && useProsody) {
    allProsodyFeatures.clear();
    allProsodyFeatures.push_back(*externalProsody);
    spdlog::debug("Using {} external prosody features", externalProsody->size());
  }

  // Synthesize each sentence independently.
  std::vector<PhonemeId> phonemeIds;
  std::map<Phoneme, std::size_t> missingPhonemes;
  size_t sentenceIdx = 0;
  for (auto phonemesIter = phonemes.begin(); phonemesIter != phonemes.end();
       ++phonemesIter, ++sentenceIdx) {
    std::vector<Phoneme> &sentencePhonemes = *phonemesIter;

    if (spdlog::should_log(spdlog::level::debug)) {
      // DEBUG log for phonemes in readable format
      std::string phonemesStr;
      for (auto phoneme : sentencePhonemes) {
        phonemesStr += phonemeToString(phoneme);
        phonemesStr += " ";
      }
      // Remove trailing space
      if (!phonemesStr.empty()) {
        phonemesStr.pop_back();
      }

      spdlog::debug("Converting {} phoneme(s) to ids: {}",
                    sentencePhonemes.size(), phonemesStr);
    }

    std::vector<std::shared_ptr<std::vector<Phoneme>>> phrasePhonemes;
    std::vector<SynthesisResult> phraseResults;
    std::vector<size_t> phraseSilenceSamples;

    // Use phoneme/id map from config
    PhonemeIdConfig idConfig;
    idConfig.phonemeIdMap =
        std::make_shared<PhonemeIdMap>(voice.phonemizeConfig.phonemeIdMap);
    idConfig.interspersePad = voice.phonemizeConfig.interspersePad;

    // OpenJTalk: BOS/EOS are already in the phoneme list from phonemizer
    if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
        idConfig.addBos = false;
        idConfig.addEos = false;
    }

    if (voice.synthesisConfig.phonemeSilenceSeconds) {
      // Split into phrases
      std::map<Phoneme, float> &phonemeSilenceSeconds =
          *voice.synthesisConfig.phonemeSilenceSeconds;

      auto currentPhrasePhonemes = std::make_shared<std::vector<Phoneme>>();
      phrasePhonemes.push_back(currentPhrasePhonemes);

      for (auto sentencePhonemesIter = sentencePhonemes.begin();
           sentencePhonemesIter != sentencePhonemes.end();
           sentencePhonemesIter++) {
        Phoneme &currentPhoneme = *sentencePhonemesIter;
        currentPhrasePhonemes->push_back(currentPhoneme);

        if (phonemeSilenceSeconds.count(currentPhoneme) > 0) {
          // Split at phrase boundary
          phraseSilenceSamples.push_back(
              (std::size_t)(phonemeSilenceSeconds[currentPhoneme] *
                            voice.synthesisConfig.sampleRate *
                            voice.synthesisConfig.channels));

          currentPhrasePhonemes = std::make_shared<std::vector<Phoneme>>();
          phrasePhonemes.push_back(currentPhrasePhonemes);
        }
      }
    } else {
      // Use all phonemes
      phrasePhonemes.push_back(
          std::make_shared<std::vector<Phoneme>>(sentencePhonemes));
    }

    // Ensure results/samples are the same size
    while (phraseResults.size() < phrasePhonemes.size()) {
      phraseResults.emplace_back();
    }

    while (phraseSilenceSamples.size() < phrasePhonemes.size()) {
      phraseSilenceSamples.push_back(0);
    }

    // phonemes -> ids -> audio
    for (size_t phraseIdx = 0; phraseIdx < phrasePhonemes.size(); phraseIdx++) {
      if (phrasePhonemes[phraseIdx]->size() <= 0) {
        continue;
      }

      // phonemes -> ids
      phonemes_to_ids(*(phrasePhonemes[phraseIdx]), idConfig, phonemeIds,
                      missingPhonemes);
      if (spdlog::should_log(spdlog::level::debug)) {
        // DEBUG log for phoneme ids
        std::stringstream phonemeIdsStr;
        for (auto phonemeId : phonemeIds) {
          phonemeIdsStr << phonemeId << ", ";
        }

        spdlog::debug("Converted {} phoneme(s) to {} phoneme id(s): {}",
                      phrasePhonemes[phraseIdx]->size(), phonemeIds.size(),
                      phonemeIdsStr.str());
      }

      // ids -> audio
      std::vector<int64_t> *prosodyPtr = nullptr;
      std::vector<int64_t> prosodyFlat;

      if (useProsody && sentenceIdx < allProsodyFeatures.size()) {
        // Convert prosody features to flat array matching phonemeIds length
        // Format: [a1, a2, a3, a1, a2, a3, ...] for each phoneme ID
        const auto &sentenceProsody = allProsodyFeatures[sentenceIdx];

        // With intersperse padding, phonemeIds has format:
        // PAD, P1, PAD, P2, PAD, ..., PN, PAD
        // So phonemeIds.size() = 2 * num_phonemes + 1 (when interspersePad=true)
        // Prosody features are per original phoneme (before padding)

        size_t numPhonemeIds = phonemeIds.size();
        prosodyFlat.resize(numPhonemeIds * 3, 0);  // Initialize with zeros

        spdlog::debug("Prosody mapping: {} phonemeIds, {} prosody features, interspersePad={}",
                      phonemeIds.size(), sentenceProsody.size(),
                      voice.phonemizeConfig.interspersePad);

        if (voice.phonemizeConfig.interspersePad) {
          // Map prosody to odd positions (1, 3, 5, ...) which are real phonemes
          size_t prosodyIdx = 0;
          for (size_t i = 1; i < numPhonemeIds && prosodyIdx < sentenceProsody.size(); i += 2) {
            prosodyFlat[i * 3 + 0] = sentenceProsody[prosodyIdx].a1;
            prosodyFlat[i * 3 + 1] = sentenceProsody[prosodyIdx].a2;
            prosodyFlat[i * 3 + 2] = sentenceProsody[prosodyIdx].a3;
            prosodyIdx++;
          }
        } else {
          // Direct 1:1 mapping (OpenJTalk)
          // prosodyFeatures are already aligned with phonemes (BOS/EOS/marks have {0,0,0})
          for (size_t i = 0; i < numPhonemeIds && i < sentenceProsody.size(); i++) {
            prosodyFlat[i * 3 + 0] = sentenceProsody[i].a1;
            prosodyFlat[i * 3 + 1] = sentenceProsody[i].a2;
            prosodyFlat[i * 3 + 2] = sentenceProsody[i].a3;
          }
        }

        prosodyPtr = &prosodyFlat;
        spdlog::debug("Using prosody features: {} phoneme IDs, {} original prosody values",
                      numPhonemeIds, sentenceProsody.size());
      }

      synthesize(phonemeIds, voice.synthesisConfig, voice.session, audioBuffer,
                 phraseResults[phraseIdx], &voice, prosodyPtr);

      // Add end of phrase silence
      for (std::size_t i = 0; i < phraseSilenceSamples[phraseIdx]; i++) {
        audioBuffer.push_back(0);
      }

      result.audioSeconds += phraseResults[phraseIdx].audioSeconds;
      result.inferSeconds += phraseResults[phraseIdx].inferSeconds;

      phonemeIds.clear();
    }

    // Add end of sentence silence
    if (sentenceSilenceSamples > 0) {
      for (std::size_t i = 0; i < sentenceSilenceSamples; i++) {
        audioBuffer.push_back(0);
      }
    }

    if (audioCallback) {
      // Call back must copy audio since it is cleared afterwards.
      audioCallback();
      audioBuffer.clear();
    }

    phonemeIds.clear();
  }

  if (missingPhonemes.size() > 0) {
    spdlog::warn("Missing {} phoneme(s) from phoneme/id map!",
                 missingPhonemes.size());

    for (auto phonemeCount : missingPhonemes) {
      std::string phonemeStr;
      utf8::append(phonemeCount.first, std::back_inserter(phonemeStr));
      spdlog::warn("Missing \"{}\" (\\u{:04X}): {} time(s)", phonemeStr,
                   (uint32_t)phonemeCount.first, phonemeCount.second);
    }
  }

  if (result.audioSeconds > 0) {
    result.realTimeFactor = result.inferSeconds / result.audioSeconds;
  }

} /* textToAudio */

// Phonemize text and synthesize audio to WAV file
void textToWavFile(PiperConfig &config, Voice &voice, std::string text,
                   std::ostream &audioFile, SynthesisResult &result,
                   const std::vector<ProsodyFeature> *externalProsody) {

  std::vector<int16_t> audioBuffer;
  textToAudio(config, voice, text, audioBuffer, result, NULL, externalProsody);

  // Write WAV
  auto synthesisConfig = voice.synthesisConfig;
  writeWavHeader(synthesisConfig.sampleRate, synthesisConfig.sampleWidth,
                 synthesisConfig.channels, (int32_t)audioBuffer.size(),
                 audioFile);

  audioFile.write((const char *)audioBuffer.data(),
                  sizeof(int16_t) * audioBuffer.size());

} /* textToWavFile */

// Synthesize audio directly from phonemes
void phonemesToAudio(PiperConfig &config, Voice &voice, 
                     const std::vector<Phoneme> &phonemes,
                     std::vector<int16_t> &audioBuffer, 
                     SynthesisResult &result,
                     const std::function<void()> &audioCallback) {
  
  // Convert phonemes to IDs
  std::vector<PhonemeId> phonemeIds;
  std::map<Phoneme, std::size_t> missingPhonemes;
  
  PhonemeIdConfig idConfig;
  idConfig.phonemeIdMap = 
      std::make_shared<PhonemeIdMap>(voice.phonemizeConfig.phonemeIdMap);
  idConfig.interspersePad = voice.phonemizeConfig.interspersePad;
  
  // OpenJTalk: BOS/EOS are already in the phoneme list from phonemizer
  if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
    idConfig.addBos = false;
    idConfig.addEos = false;
  } else {
    idConfig.addBos = true;
    idConfig.addEos = true;
  }
  
  // Convert phonemes to IDs
  phonemes_to_ids(phonemes, idConfig, phonemeIds, missingPhonemes);
  
  // Report missing phonemes
  if (!missingPhonemes.empty()) {
    for (auto& [phoneme, count] : missingPhonemes) {
      spdlog::warn("Missing phoneme: '{}' ({})", phonemeToString(phoneme), count);
    }
  }
  
  // Synthesize audio
  synthesize(phonemeIds, voice.synthesisConfig, voice.session, audioBuffer, result, &voice);
  
  // Call the audio callback if provided
  if (audioCallback) {
    audioCallback();
  }
  
} /* phonemesToAudio */

// Synthesize audio directly from phonemes to WAV file
void phonemesToWavFile(PiperConfig &config, Voice &voice,
                       const std::vector<Phoneme> &phonemes,
                       std::ostream &audioFile, SynthesisResult &result) {
  
  std::vector<int16_t> audioBuffer;
  phonemesToAudio(config, voice, phonemes, audioBuffer, result, nullptr);
  
  // Write WAV
  auto synthesisConfig = voice.synthesisConfig;
  writeWavHeader(synthesisConfig.sampleRate, synthesisConfig.sampleWidth,
                 synthesisConfig.channels, (int32_t)audioBuffer.size(),
                 audioFile);
  
  audioFile.write((const char *)audioBuffer.data(),
                  sizeof(int16_t) * audioBuffer.size());
                  
} /* phonemesToWavFile */

// Helper function for calculating dynamic chunk size based on text characteristics
static size_t calculateDynamicChunkSize(const std::string& text, size_t baseSize = 50) {
  // Short texts should not be chunked
  if (text.length() < baseSize * 2) {
    return text.length();
  }
  
  // Calculate punctuation density
  size_t punctCount = 0;
  const std::string punctMarks = u8"。、！？.!?,;:";
  for (size_t i = 0; i < text.length(); ++i) {
    if (punctMarks.find(text[i]) != std::string::npos) {
      punctCount++;
    }
  }
  
  // Adjust chunk size based on punctuation density
  float punctDensity = static_cast<float>(punctCount) / text.length();
  if (punctDensity > 0.05f) {  // More than 5% punctuation - use smaller chunks
    return baseSize;
  } else if (punctDensity < 0.02f) {  // Less than 2% punctuation - use larger chunks
    return baseSize * 3;
  }
  return baseSize * 2;  // Medium density
}

// Helper function for audio crossfade to reduce chunk boundary artifacts
static void crossfadeAudioChunks(
    const std::vector<int16_t>& prevChunk,
    const std::vector<int16_t>& newChunk,
    std::vector<int16_t>& output,
    size_t overlapSamples = 220  // 10ms @ 22050Hz
) {
  if (prevChunk.empty() || newChunk.empty() || overlapSamples == 0) {
    // No crossfade possible, just append
    output.insert(output.end(), newChunk.begin(), newChunk.end());
    return;
  }
  
  // Ensure we don't exceed chunk boundaries
  size_t actualOverlap = std::min({overlapSamples, prevChunk.size() / 4, newChunk.size() / 4});
  if (actualOverlap < 44) {  // Less than 2ms - not worth crossfading
    output.insert(output.end(), newChunk.begin(), newChunk.end());
    return;
  }
  
  // Remove the overlap from the output (it was already added with prevChunk)
  if (output.size() >= actualOverlap) {
    output.resize(output.size() - actualOverlap);
  }
  
  // Perform crossfade
  for (size_t i = 0; i < actualOverlap; ++i) {
    float fadeOut = 1.0f - (static_cast<float>(i) / actualOverlap);
    float fadeIn = static_cast<float>(i) / actualOverlap;
    
    size_t prevIdx = prevChunk.size() - actualOverlap + i;
    int16_t mixed = static_cast<int16_t>(
      prevChunk[prevIdx] * fadeOut + newChunk[i] * fadeIn
    );
    output.push_back(mixed);
  }
  
  // Append the rest of the new chunk
  output.insert(output.end(), newChunk.begin() + actualOverlap, newChunk.end());
}

// Streaming text-to-audio synthesis with reduced latency
void textToAudioStreaming(PiperConfig &config, Voice &voice, std::string text,
                          std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                          const std::function<void(const std::vector<int16_t>&)> &chunkCallback,
                          size_t chunkSize) {
  spdlog::debug("textToAudioStreaming: text='{}', chunkSize={}", text, chunkSize);
  
  // Clear result
  result.inferSeconds = 0;
  result.audioSeconds = 0;
  result.realTimeFactor = 0;
  
  // Clear output buffer
  audioBuffer.clear();
  
  if (text.empty()) {
    return;
  }
  
  // Calculate dynamic chunk size based on text characteristics
  size_t dynamicChunkSize = calculateDynamicChunkSize(text, chunkSize > 0 ? chunkSize : 50);
  
  // Static regex patterns for better performance (cached compilation)
  static const std::regex japaneseSentenceBoundary(u8"([。！？、]+)");
  static const std::regex englishSentenceBoundary("([.!?,;:]+|\\s+(?:and|or|but|because|while|when|if|that|which)\\s+)");
  
  // Select appropriate regex based on language
  const std::regex& sentenceBoundary = 
    (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) 
    ? japaneseSentenceBoundary 
    : englishSentenceBoundary;
  
  // Split text into chunks at natural boundaries
  std::vector<std::string> chunks;
  std::sregex_token_iterator iter(text.begin(), text.end(), sentenceBoundary, {-1, 1});
  std::sregex_token_iterator end;
  
  std::string currentChunk;
  for (; iter != end; ++iter) {
    std::string token = *iter;
    if (token.empty()) continue;
    
    // Check if this is a delimiter
    if (std::regex_match(token, sentenceBoundary)) {
      // Add delimiter to current chunk
      currentChunk += token;
      if (!currentChunk.empty() && 
          (token.find_first_of(u8"。！？.!?") != std::string::npos ||
           currentChunk.length() > dynamicChunkSize)) {
        // End of sentence or chunk is getting long
        chunks.push_back(currentChunk);
        currentChunk.clear();
      }
    } else {
      // Regular text
      currentChunk += token;
    }
  }
  
  // Add any remaining text
  if (!currentChunk.empty()) {
    chunks.push_back(currentChunk);
  }
  
  spdlog::debug("Split text into {} chunks with dynamic chunk size: {}", chunks.size(), dynamicChunkSize);
  
  // Track previous chunk for crossfading
  std::vector<int16_t> previousChunkAudio;
  
  // Process each chunk
  for (size_t i = 0; i < chunks.size(); ++i) {
    const auto& chunk = chunks[i];
    spdlog::debug("Processing chunk {}/{}: '{}'", i+1, chunks.size(), chunk);
    
    // Phonemize chunk
    std::vector<std::vector<Phoneme>> chunkSentences;
    std::vector<std::vector<ProsodyFeature>> chunkProsody;

    // Check if model supports prosody input
    bool useProsody = voice.session.hasProsodyInput &&
                      usesOpenJTalk(voice.phonemizeConfig.phonemeType);

    if (voice.phonemizeConfig.phonemeType == eSpeakPhonemes) {
      // Use espeak-ng for phonemization
      eSpeakPhonemeConfig eSpeakConfig;
      eSpeakConfig.voice = voice.phonemizeConfig.eSpeak.voice;
      phonemize_eSpeak(chunk, eSpeakConfig, chunkSentences);
    } else if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
      // Japanese/Multilingual OpenJTalk phonemizer
      if (useProsody) {
        phonemize_openjtalk_with_prosody(chunk, chunkSentences, chunkProsody);
      } else {
        phonemize_openjtalk(chunk, chunkSentences);
      }
      // Fall back to eSpeak for multilingual models when OpenJTalk is unavailable
      if (chunkSentences.empty() && !chunk.empty() &&
          voice.phonemizeConfig.phonemeType == MultilingualPhonemes) {
        spdlog::warn("OpenJTalk unavailable, falling back to eSpeak for multilingual model");
        eSpeakPhonemeConfig eSpeakConfig;
        eSpeakConfig.voice = "en";
        phonemize_eSpeak(chunk, eSpeakConfig, chunkSentences);
      }
    } else {
      // Use UTF-8 codepoints as "phonemes"
      CodepointsPhonemeConfig codepointsConfig;
      phonemize_codepoints(chunk, codepointsConfig, chunkSentences);
    }

    // Process each sentence in the chunk
    for (size_t sentIdx = 0; sentIdx < chunkSentences.size(); sentIdx++) {
      auto& sentencePhonemes = chunkSentences[sentIdx];
      if (sentencePhonemes.empty()) {
        continue;
      }

      // Convert phonemes to IDs
      std::vector<PhonemeId> phonemeIds;
      std::map<Phoneme, std::size_t> missingPhonemes;
      // Create PhonemeIdConfig from voice config
      PhonemeIdConfig idConfig;
      idConfig.phonemeIdMap =
          std::make_shared<PhonemeIdMap>(voice.phonemizeConfig.phonemeIdMap);
      idConfig.interspersePad = voice.phonemizeConfig.interspersePad;
      // OpenJTalk: BOS/EOS are already in the phoneme list from phonemizer
      if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
        idConfig.addBos = false;
        idConfig.addEos = false;
      } else {
        idConfig.addBos = true;
        idConfig.addEos = true;
      }

      phonemes_to_ids(sentencePhonemes, idConfig, phonemeIds,
                      missingPhonemes);

      // Report missing phonemes
      if (!missingPhonemes.empty()) {
        for (auto& [phoneme, count] : missingPhonemes) {
          spdlog::warn("Missing phoneme: '{}' (count={})",
                       phonemeToString(phoneme), count);
        }
      }

      // Prepare prosody features if available
      std::vector<int64_t> *prosodyPtr = nullptr;
      std::vector<int64_t> prosodyFlat;

      if (useProsody && sentIdx < chunkProsody.size()) {
        const auto &sentenceProsody = chunkProsody[sentIdx];
        size_t numPhonemeIds = phonemeIds.size();
        prosodyFlat.resize(numPhonemeIds * 3, 0);

        if (voice.phonemizeConfig.interspersePad) {
          size_t prosodyIdx = 0;
          for (size_t i = 1; i < numPhonemeIds && prosodyIdx < sentenceProsody.size(); i += 2) {
            prosodyFlat[i * 3 + 0] = sentenceProsody[prosodyIdx].a1;
            prosodyFlat[i * 3 + 1] = sentenceProsody[prosodyIdx].a2;
            prosodyFlat[i * 3 + 2] = sentenceProsody[prosodyIdx].a3;
            prosodyIdx++;
          }
        } else {
          for (size_t i = 0; i < numPhonemeIds && i < sentenceProsody.size(); i++) {
            prosodyFlat[i * 3 + 0] = sentenceProsody[i].a1;
            prosodyFlat[i * 3 + 1] = sentenceProsody[i].a2;
            prosodyFlat[i * 3 + 2] = sentenceProsody[i].a3;
          }
        }
        prosodyPtr = &prosodyFlat;
      }

      // Synthesize audio for this chunk
      std::vector<int16_t> chunkAudioBuffer;
      SynthesisResult chunkResult;
      synthesize(phonemeIds, voice.synthesisConfig, voice.session,
                 chunkAudioBuffer, chunkResult, &voice, prosodyPtr);
      
      // Update cumulative result
      result.inferSeconds += chunkResult.inferSeconds;
      result.audioSeconds += chunkResult.audioSeconds;
      
      // Apply crossfade if we have a previous chunk
      if (!previousChunkAudio.empty() && !chunkAudioBuffer.empty()) {
        // Crossfade with previous chunk to reduce boundary artifacts
        crossfadeAudioChunks(previousChunkAudio, chunkAudioBuffer, audioBuffer);
      } else {
        // No previous chunk or empty current chunk - just append
        audioBuffer.insert(audioBuffer.end(), 
                           chunkAudioBuffer.begin(), 
                           chunkAudioBuffer.end());
      }
      
      // Store current chunk for next iteration's crossfade
      previousChunkAudio = chunkAudioBuffer;
      
      // Call chunk callback for all chunks (including empty ones for progress tracking)
      if (chunkCallback) {
        chunkCallback(chunkAudioBuffer);
      }
    }
  }
  
  // Calculate final real-time factor
  if (result.audioSeconds > 0) {
    result.realTimeFactor = result.audioSeconds / result.inferSeconds;
  }
  
  spdlog::debug("Streaming synthesis complete: {} chunks, {:.2f}s audio, RTF={:.2f}",
                chunks.size(), result.audioSeconds, result.realTimeFactor);
  
} /* textToAudioStreaming */

// Streaming phonemes-to-audio synthesis with reduced latency
void phonemesToAudioStreaming(PiperConfig &config, Voice &voice,
                              const std::vector<Phoneme> &phonemes,
                              std::vector<int16_t> &audioBuffer,
                              SynthesisResult &result,
                              const std::function<void(const std::vector<int16_t>&)> &chunkCallback,
                              size_t phonemesPerChunk) {
  spdlog::debug("phonemesToAudioStreaming: {} phonemes, chunk size={}",
                phonemes.size(), phonemesPerChunk);
  
  // Clear result
  result.inferSeconds = 0;
  result.audioSeconds = 0;
  result.realTimeFactor = 0;
  
  // Clear output buffer
  audioBuffer.clear();
  
  if (phonemes.empty()) {
    return;
  }
  
  // Setup phoneme ID configuration
  PhonemeIdConfig idConfig;
  idConfig.phonemeIdMap = 
      std::make_shared<PhonemeIdMap>(voice.phonemizeConfig.phonemeIdMap);
  idConfig.interspersePad = voice.phonemizeConfig.interspersePad;
  // OpenJTalk: BOS/EOS are already in the phoneme list from phonemizer
  if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
    idConfig.addBos = false;
    idConfig.addEos = false;
  } else {
    idConfig.addBos = true;
    idConfig.addEos = false;  // We'll add EOS only to the last chunk
  }

  std::vector<PhonemeId> phonemeIds;
  std::map<Phoneme, std::size_t> missingPhonemes;
  std::vector<int16_t> chunkAudioBuffer;

  // Process phonemes in chunks
  size_t processedPhonemes = 0;
  while (processedPhonemes < phonemes.size()) {
    // Determine chunk boundaries
    size_t chunkStart = processedPhonemes;
    size_t chunkEnd = std::min(processedPhonemes + phonemesPerChunk, phonemes.size());
    bool isLastChunk = (chunkEnd == phonemes.size());

    // Extract chunk phonemes
    std::vector<Phoneme> chunkPhonemes(phonemes.begin() + chunkStart,
                                        phonemes.begin() + chunkEnd);

    // Add EOS only to the last chunk (non-OpenJTalk only)
    if (!usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
      idConfig.addEos = isLastChunk;
    }
    
    // Convert chunk phonemes to IDs
    phonemeIds.clear();
    phonemes_to_ids(chunkPhonemes, idConfig, phonemeIds, missingPhonemes);
    
    // Log phoneme IDs for debugging
    if (spdlog::should_log(spdlog::level::debug)) {
      std::stringstream phonemeIdsStr;
      for (auto phonemeId : phonemeIds) {
        phonemeIdsStr << phonemeId << ", ";
      }
      spdlog::debug("Chunk {}: {} phonemes -> {} IDs: {}", 
                    (processedPhonemes / phonemesPerChunk) + 1,
                    chunkPhonemes.size(), phonemeIds.size(), phonemeIdsStr.str());
    }
    
    // Synthesize chunk
    chunkAudioBuffer.clear();
    SynthesisResult chunkResult;
    synthesize(phonemeIds, voice.synthesisConfig, voice.session, 
               chunkAudioBuffer, chunkResult, &voice);
    
    // Accumulate results
    result.audioSeconds += chunkResult.audioSeconds;
    result.inferSeconds += chunkResult.inferSeconds;
    
    // Append to main buffer
    audioBuffer.insert(audioBuffer.end(), 
                       chunkAudioBuffer.begin(), 
                       chunkAudioBuffer.end());
    
    // Call chunk callback
    if (chunkCallback && !chunkAudioBuffer.empty()) {
      chunkCallback(chunkAudioBuffer);
    }
    
    // Move to next chunk
    processedPhonemes = chunkEnd;
    
    // For subsequent chunks, don't add BOS
    idConfig.addBos = false;
  }
  
  // Report missing phonemes
  if (!missingPhonemes.empty()) {
    spdlog::warn("Missing {} phoneme(s) from phoneme/id map!", missingPhonemes.size());
    for (auto& [phoneme, count] : missingPhonemes) {
      std::string phonemeStr;
      utf8::append(phoneme, std::back_inserter(phonemeStr));
      spdlog::warn("Missing \"{}\" (\\u{:04X}): {} time(s)", phonemeStr,
                   (uint32_t)phoneme, count);
    }
  }
  
  // Calculate final real-time factor
  if (result.audioSeconds > 0) {
    result.realTimeFactor = result.inferSeconds / result.audioSeconds;
  }
  
  spdlog::debug("Streaming phoneme synthesis complete: {} chunks, {:.2f}s audio, RTF={:.2f}",
                (phonemes.size() + phonemesPerChunk - 1) / phonemesPerChunk,
                result.audioSeconds, result.realTimeFactor);
  
} /* phonemesToAudioStreaming */

// Output phoneme timing information as JSON
void outputTimingsAsJSON(const std::vector<PhonemeInfo> &timings,
                         std::ostream &output,
                         const std::string &text,
                         int sampleRate) {
    json result;
    json phonemesArray = json::array();
    
    for (const auto &info : timings) {
        json phonemeObj;
        phonemeObj["phoneme"] = info.phoneme;
        phonemeObj["start"] = info.start_time;
        phonemeObj["end"] = info.end_time;
        phonemeObj["start_frame"] = info.start_frame;
        phonemeObj["end_frame"] = info.end_frame;
        phonemesArray.push_back(phonemeObj);
    }
    
    result["phonemes"] = phonemesArray;
    if (!text.empty()) {
        result["text"] = text;
    }
    result["total_duration"] = timings.empty() ? 0.0 : timings.back().end_time;
    result["sample_rate"] = sampleRate;
    result["frame_shift_ms"] = 256.0 / sampleRate * 1000;  // hop_size in ms
    
    output << result.dump(2) << std::endl;
}

// Output phoneme timing information as TSV
void outputTimingsAsTSV(const std::vector<PhonemeInfo> &timings,
                        std::ostream &output) {
    output << "phoneme\tstart\tend\tstart_frame\tend_frame" << std::endl;
    
    for (const auto &info : timings) {
        output << info.phoneme << "\t"
               << info.start_time << "\t"
               << info.end_time << "\t"
               << info.start_frame << "\t"
               << info.end_frame << std::endl;
    }
}

} // namespace piper
