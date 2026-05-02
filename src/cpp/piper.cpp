#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <fstream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <filesystem>
#include <thread>
#include <unordered_map>

#include <onnxruntime_cxx_api.h>
#ifdef __APPLE__
#include <coreml_provider_factory.h>
#endif
#ifdef _WIN32
#if __has_include(<dml_provider_factory.h>)
#include <dml_provider_factory.h>
#define PIPER_HAS_DIRECTML 1
#endif
#endif
#include <spdlog/spdlog.h>

// Self-contained phoneme ID conversion
#include "phoneme_ids.hpp"

#include "json.hpp"
#include "piper.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"
#include "wavfile.hpp"
#include "openjtalk_phonemize.hpp"
#include "phoneme_parser.hpp"
#include "language_detector.hpp"
#include "spanish_phonemize.hpp"
#include "french_phonemize.hpp"
#include "portuguese_phonemize.hpp"
#include "english_phonemize.hpp"
#include "chinese_phonemize.hpp"
#include "korean_phonemize.hpp"
#include "swedish_phonemize.hpp"

#ifdef USE_ARM64_NEON
#include "audio_neon.hpp"
#endif

#include "library_path.h"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

using json = nlohmann::json;


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

// Upper bound for intra-op threads, matching Rust/C#/Python convention.
// Beyond 4 threads VITS sees diminishing returns and increased contention.
constexpr int MAX_INTRA_THREADS = 4;

// Short-text mitigation constants (keep in sync with other runtimes —
// docs/spec/short-text-contract.toml).
//
// Issue #356: MIN_PHONEME_IDS was 40 but tsukuyomi 6lang testing shows
// synthesis is stable down to ~8 IDs. 40 caused Strategy A to fire on
// already-stable inputs and leak padding artifacts. 15 keeps Strategy A
// active for genuinely tiny inputs only. MIN_BODY_FOR_STRATEGY_A = 3
// additionally bypasses Strategy A when the body (= phoneme IDs minus
// BOS/EOS) is too small for padding to outweigh content (e.g. 「あ。」).
constexpr int MIN_PHONEME_IDS = 15;
constexpr int MIN_BODY_FOR_STRATEGY_A = 3;
constexpr float TRIM_THRESHOLD_RMS = 0.01f;
constexpr int TRIM_MIN_SAMPLES = 2205;  // 22050 Hz * 0.1 s
constexpr int TRIM_WINDOW_SIZE = 256;
// Maximum EOS frames retained by the durations-based Strategy A trim.
// VITS predicts an inflated EOS under the padded context that emits an
// audible artifact otherwise. 0 = drop the entire EOS region.
constexpr int TRIM_EOS_MAX_FRAMES = 0;

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
    {0xE019, "N_m"}, {0xE01A, "N_n"}, {0xE01B, "N_ng"}, {0xE01C, "N_uvular"},
    // Multilingual phoneme tokens
    {0xE01D, "rr"}, {0xE01E, "y_vowel"}
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
  //     "phoneme_type": "<openjtalk or multilingual>",
  //     "phoneme_map": {
  //         "<from phoneme>": ["<to phoneme 1>", "<to phoneme 2>", ...]
  //     },
  //     "phoneme_id_map": {
  //         "<phoneme>": [<id1>, <id2>, ...]
  //     }
  // }

  if (configRoot.contains("phoneme_type")) {
    auto phonemeTypeStr = configRoot["phoneme_type"].get<std::string>();
    if (phonemeTypeStr == "openjtalk") {
      phonemizeConfig.phonemeType = OpenJTalkPhonemes;
      // OpenJTalk models don't use padding between phonemes
      phonemizeConfig.interspersePad = false;
    } else if (phonemeTypeStr == "multilingual" || phonemeTypeStr == "bilingual") {
      phonemizeConfig.phonemeType = MultilingualPhonemes;
      // Multilingual models use padding between phonemes
      phonemizeConfig.interspersePad = true;
    } else {
      spdlog::warn("Unknown phoneme_type '{}', defaulting to MultilingualPhonemes", phonemeTypeStr);
      phonemizeConfig.phonemeType = MultilingualPhonemes;
      phonemizeConfig.interspersePad = true;
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

  // Parse num_languages (default: 1 for monolingual models)
  if (configRoot.contains("num_languages")) {
    modelConfig.numLanguages = configRoot["num_languages"].get<int>();
  }

  // Parse language_id_map: {"ja": 0, "en": 1, ...}
  if (configRoot.contains("language_id_map")) {
    if (!modelConfig.languageIdMap) {
      modelConfig.languageIdMap.emplace();
    }

    auto languageIdMapValue = configRoot["language_id_map"];
    for (auto &langItem : languageIdMapValue.items()) {
      std::string langCode = langItem.key();
      (*modelConfig.languageIdMap)[langCode] =
          langItem.value().get<LanguageId>();
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
    
    // Build reverse map from phoneme ID to UTF-8 string.
    // idMap key is Phoneme (char32_t); encode it properly so isSingleCodepoint()
    // and the utf8-checked functions never see invalid byte sequences.
    std::unordered_map<PhonemeId, std::string> phonemeIdToStringMap;
    for (const auto& [phonemeChar, ids] : idMap) {
        if (!ids.empty()) {
            std::string phonemeUtf8;
            utf8::append(static_cast<uint32_t>(phonemeChar),
                         std::back_inserter(phonemeUtf8));
            phonemeIdToStringMap[ids[0]] = std::move(phonemeUtf8);
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
            if (id > 2 && id < 128) {
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
            if (isSingleCodepoint(timings[i].phoneme)) {
                // Get the first codepoint (handles multi-byte UTF-8, e.g. PUA U+E000+)
                Phoneme ph = getCodepoint(timings[i].phoneme);
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

void initialize(PiperConfig &config) {
  spdlog::info("Initialized piper");
}

void terminate(PiperConfig &config) {
  spdlog::info("Terminated piper");
}

void loadModel(std::string modelPath, ModelSession &session,
               const std::string &provider, int gpuDeviceId = 0,
               int numThreads = 0) {
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

  // Execution provider selection
  if (provider == "cuda") {
    // Use CUDA provider
    OrtCUDAProviderOptions cuda_options{};
    cuda_options.device_id = gpuDeviceId;
    cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic;
    session.options.AppendExecutionProvider_CUDA(cuda_options);
    spdlog::info("Using CUDA execution provider with GPU device ID: {}", gpuDeviceId);
  } else if (provider == "coreml") {
#ifdef __APPLE__
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_CoreML(session.options, 0));
    spdlog::info("Using CoreML execution provider");
#else
    throw std::runtime_error("CoreML is only available on macOS/iOS");
#endif
  } else if (provider == "directml") {
#ifdef PIPER_HAS_DIRECTML
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_DML(session.options, gpuDeviceId));
    spdlog::info("Using DirectML execution provider with device ID: {}", gpuDeviceId);
#elif defined(_WIN32)
    throw std::runtime_error("DirectML support requires the DirectML ONNX Runtime package");
#else
    throw std::runtime_error("DirectML is only available on Windows");
#endif
  } else if (!provider.empty() && provider != "cpu") {
    throw std::runtime_error("Unknown provider: " + provider);
  }

  // Compute effective intra-op thread count.
  // Formula: min(logical_cores / 2, MAX_INTRA_THREADS) — matches Rust/C#/Python.
  int effectiveThreads = numThreads;
  if (effectiveThreads <= 0) {
    unsigned int hwThreads = std::thread::hardware_concurrency();
    if (hwThreads == 0) hwThreads = 2;  // fallback when detection fails
    effectiveThreads = std::min(static_cast<int>(hwThreads / 2),
                                MAX_INTRA_THREADS);
    if (effectiveThreads < 1) effectiveThreads = 1;
  }
  effectiveThreads = std::min(effectiveThreads, MAX_INTRA_THREADS);
  session.options.SetIntraOpNumThreads(effectiveThreads);
  spdlog::info("Set IntraOpNumThreads to {} (requested={}, hw_concurrency={})",
               effectiveThreads, numThreads,
               std::thread::hardware_concurrency());

  // Roughly doubles load time for no visible inference benefit
  // session.options.SetGraphOptimizationLevel(
  //     GraphOptimizationLevel::ORT_ENABLE_EXTENDED);

  session.options.SetGraphOptimizationLevel(
      GraphOptimizationLevel::ORT_ENABLE_ALL);

  // CPU memory arena and memory pattern are enabled by default (ORT defaults).
  // This trades higher memory usage for ~10-15% faster inference.
  // To reduce memory in constrained environments, uncomment:
  // session.options.DisableCpuMemArena();
  // session.options.DisableMemPattern();

  // VITS は単一グラフで並列サブグラフがない — Sequential が最適
  session.options.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
  session.options.SetInterOpNumThreads(1);

  // 動的ブロックサイズ: intra-op スレッドの作業分割を細粒度化しレイテンシ分散を低減
  session.options.AddConfigEntry("session.dynamic_block_base", "4");

  session.options.DisableProfiling();

  auto startTime = std::chrono::steady_clock::now();

#ifdef _WIN32
  auto modelPathW = std::filesystem::path(modelPath).wstring();
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

// Get the directory containing the running executable.
// Delegates to piper_plus_get_exe_dir() in library_path.c.
// Returns empty path on failure.
static std::filesystem::path getExeDir() {
  char buf[4096];
  if (piper_plus_get_exe_dir(buf, sizeof(buf)) == 0) {
    return std::filesystem::path(buf);
  }
  return {};
}

// Search for a dictionary file in multiple locations:
//   1. modelDir/<filename>              (model-local)
//   2. <exe_dir>/../share/piper/dicts/<filename>  (installed)
//   3. PIPER_DICTIONARIES_PATH/<filename>          (env override)
// Returns the first path that exists, or empty string if not found.
static std::string findDictionaryFile(const std::string &filename,
                                      const std::string &modelDir) {
  namespace fs = std::filesystem;

  // 1. Model directory
  fs::path p1 = fs::path(modelDir) / filename;
  if (fs::exists(p1)) {
    spdlog::debug("Dictionary '{}' found in model dir: {}", filename, p1.string());
    return p1.string();
  }

  // 2. Exe-relative path: <exe_dir>/../share/piper/dicts/<filename>
  auto exeDir = getExeDir();
  if (!exeDir.empty()) {
    fs::path p2 = exeDir / ".." / "share" / "piper" / "dicts" / filename;
    if (fs::exists(p2)) {
      std::error_code ec;
      auto resolved = fs::weakly_canonical(p2, ec);
      std::string checkPath = ec ? p2.string() : resolved.string();
      spdlog::debug("Dictionary '{}' found in exe-relative dir: {}", filename, checkPath);
      return checkPath;
    }
  }

  // 3. Environment variable PIPER_DICTIONARIES_PATH
  const char *envPath = std::getenv("PIPER_DICTIONARIES_PATH");
  if (envPath && envPath[0] != '\0') {
    fs::path p3 = fs::path(envPath) / filename;
    if (fs::exists(p3)) {
      spdlog::debug("Dictionary '{}' found via PIPER_DICTIONARIES_PATH: {}", filename, p3.string());
      return p3.string();
    }
  }

  spdlog::debug("Dictionary '{}' not found in any search path", filename);
  return {};
}

// Load Onnx model and JSON config file
void loadVoice(PiperConfig &config, std::string modelPath,
               std::string modelConfigPath, Voice &voice,
               std::optional<SpeakerId> &speakerId,
               const std::string &provider,
               int gpuDeviceId, int numThreads) {
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

  // Multi-language model: set default language to 0
  if (voice.modelConfig.numLanguages > 1) {
    if (!voice.synthesisConfig.languageId) {
      voice.synthesisConfig.languageId = 0;
    }
    spdlog::debug("Voice contains {} language(s)", voice.modelConfig.numLanguages);
  }

  // Validate language_id_map for multilingual models
  if (voice.phonemizeConfig.phonemeType == MultilingualPhonemes) {
    if (!voice.modelConfig.languageIdMap || voice.modelConfig.languageIdMap->empty()) {
      spdlog::warn("Multilingual model missing language_id_map, defaulting to ja+en");
    }
  }

  // Load language-specific dictionaries for multilingual models
  // Search order: model dir -> exe-relative -> PIPER_DICTIONARIES_PATH
  std::string modelDir = std::filesystem::path(modelPath).parent_path().string();

  // English: CMU dictionary
  std::string cmuPath = findDictionaryFile("cmudict_data.json", modelDir);
  if (!cmuPath.empty()) {
    if (loadCmuDict(cmuPath, voice.cmuDict)) {
      spdlog::info("Loaded CMU dictionary ({} entries) from {}", voice.cmuDict.size(), cmuPath);
    }
  }

  // Chinese: pypinyin dictionaries
  std::string pinyinSinglePath = findDictionaryFile("pinyin_single.json", modelDir);
  std::string pinyinPhrasePath = findDictionaryFile("pinyin_phrases.json", modelDir);
  if (!pinyinSinglePath.empty()) {
    if (pinyinPhrasePath.empty()) {
      spdlog::warn("pinyin_single.json found but pinyin_phrases.json is missing; "
                   "Chinese phrase-level G2P will be degraded");
    }
    if (loadPinyinDicts(pinyinSinglePath, pinyinPhrasePath,
                        voice.pinyinSingleDict, voice.pinyinPhraseDict)) {
      spdlog::info("Loaded pinyin dictionaries (single={}, phrases={}) from {}",
                   voice.pinyinSingleDict.size(), voice.pinyinPhraseDict.size(),
                   std::filesystem::path(pinyinSinglePath).parent_path().string());
    }
  }

  spdlog::debug("Voice contains {} speaker(s)", voice.modelConfig.numSpeakers);

  loadModel(modelPath, voice.session, provider, gpuDeviceId, numThreads);

} /* loadVoice */

// ---------------------------------------------------------------------------
// Short-text mitigation: Strategy A helpers
// ---------------------------------------------------------------------------

// Pad short phoneme ID sequences with silence tokens (pause ID = 0) after BOS
// and before EOS to reach MIN_PHONEME_IDS length. Returns true if padding was
// applied. Strategy A is also skipped when the body (= phoneme IDs minus
// BOS/EOS) is shorter than MIN_BODY_FOR_STRATEGY_A — see issue #356.
//
// When padding is applied, *frontPadOut and *backPadOut (when non-null)
// receive the number of pad tokens inserted after BOS and before EOS
// respectively, so the durations-based trim can locate them precisely.
static bool padPhonemeIds(std::vector<PhonemeId> &phonemeIds,
                          PhonemeId padId = 0,
                          int *frontPadOut = nullptr,
                          int *backPadOut = nullptr) {
  if (frontPadOut) *frontPadOut = 0;
  if (backPadOut) *backPadOut = 0;
  const auto len = static_cast<int>(phonemeIds.size());
  const int bodyLen = len - 2; // exclude BOS / EOS
  if (bodyLen < MIN_BODY_FOR_STRATEGY_A) {
    return false;
  }
  if (len >= MIN_PHONEME_IDS) {
    return false;
  }

  const int needed = MIN_PHONEME_IDS - len;
  const int front = needed / 2;
  const int back = needed - front;

  // phonemeIds layout: [BOS, ...body..., EOS]
  // We need at least 2 elements (BOS + EOS) to split safely.
  if (phonemeIds.size() < 2) {
    // Degenerate case: just pad at the end
    phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(needed), padId);
    if (frontPadOut) *frontPadOut = front;
    if (backPadOut) *backPadOut = back;
    return true;
  }

  // Split: bos = first element, body = middle, eos = last element
  PhonemeId bos = phonemeIds.front();
  PhonemeId eos = phonemeIds.back();
  std::vector<PhonemeId> body(phonemeIds.begin() + 1, phonemeIds.end() - 1);

  // Reconstruct: BOS + front_pad + body + back_pad + EOS
  phonemeIds.clear();
  phonemeIds.reserve(static_cast<size_t>(MIN_PHONEME_IDS));
  phonemeIds.push_back(bos);
  phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(front), padId);
  phonemeIds.insert(phonemeIds.end(), body.begin(), body.end());
  phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(back), padId);
  phonemeIds.push_back(eos);

  spdlog::debug("Short-text padding: {} -> {} phoneme IDs ({} pad tokens added)",
                len, phonemeIds.size(), needed);
  if (frontPadOut) *frontPadOut = front;
  if (backPadOut) *backPadOut = back;
  return true;
}

// Strategy A precise post-trim using the model's duration output.
// Mirrors the Python reference (src/python_run/piper/voice.py
// _trim_padding_by_durations) so all runtimes produce byte-equal output for
// the same inputs (issue #356, cross-runtime contract).
//
// Layout: [BOS, pad×frontPad, ...body..., pad×backPad, EOS]
//
// Trimming policy:
//   - BOS + front padding: stripped completely
//   - Back padding: stripped completely
//   - EOS: keep only `eosMaxFrames` frames (default TRIM_EOS_MAX_FRAMES = 0)
//
// All frame→sample conversions use static_cast<int>(...) on a float product
// (truncation toward zero), matching int() in the Python implementation.
//
// Falls through unchanged when arguments are inconsistent.
static void trimPaddingByDurations(std::vector<int16_t> &audioBuffer,
                                   const std::vector<float> &durations,
                                   int frontPad,
                                   int backPad,
                                   int hopSize,
                                   int eosMaxFrames = TRIM_EOS_MAX_FRAMES) {
  if (frontPad <= 0 && backPad <= 0) return;
  if (durations.empty() || hopSize <= 0) return;
  const int expectedLen = 1 + frontPad + backPad + 1; // BOS + pads + EOS
  if (static_cast<int>(durations.size()) < expectedLen) return;

  // Front: BOS + front padding samples (truncated).
  float frontSum = 0.0f;
  for (int i = 0; i < 1 + frontPad; i++) {
    frontSum += durations[i];
  }
  const int frontSamples = static_cast<int>(frontSum * static_cast<float>(hopSize));

  // Back: back padding samples + EOS excess (over eosMaxFrames).
  float backPadSum = 0.0f;
  if (backPad > 0) {
    // durations[-(1+backPad) : -1] in Python = [size-1-backPad, size-1)
    const int start = static_cast<int>(durations.size()) - 1 - backPad;
    for (int i = start; i < static_cast<int>(durations.size()) - 1; i++) {
      backPadSum += durations[i];
    }
  }
  const int backPadSamples =
      static_cast<int>(backPadSum * static_cast<float>(hopSize));
  const float eosFrames = durations.back();
  float eosExcess = eosFrames - static_cast<float>(eosMaxFrames);
  if (eosExcess < 0.0f) eosExcess = 0.0f;
  const int backSamples =
      backPadSamples +
      static_cast<int>(eosExcess * static_cast<float>(hopSize));

  const int totalSamples = static_cast<int>(audioBuffer.size());
  int start = frontSamples < 0 ? 0 : frontSamples;
  int end = totalSamples - backSamples;
  if (end < start) end = start;
  if (start >= totalSamples || end <= 0 || start >= end) return;

  if (start > 0 || end < totalSamples) {
    std::vector<int16_t> trimmed(audioBuffer.begin() + start,
                                 audioBuffer.begin() + end);
    audioBuffer = std::move(trimmed);
  }
}

// Float32 variant of trimPaddingByDurations. Identical sample-count logic;
// only the buffer element type differs.
static void trimPaddingByDurationsFloat(std::vector<float> &audioBuffer,
                                        const std::vector<float> &durations,
                                        int frontPad,
                                        int backPad,
                                        int hopSize,
                                        int eosMaxFrames = TRIM_EOS_MAX_FRAMES) {
  if (frontPad <= 0 && backPad <= 0) return;
  if (durations.empty() || hopSize <= 0) return;
  const int expectedLen = 1 + frontPad + backPad + 1;
  if (static_cast<int>(durations.size()) < expectedLen) return;

  float frontSum = 0.0f;
  for (int i = 0; i < 1 + frontPad; i++) {
    frontSum += durations[i];
  }
  const int frontSamples = static_cast<int>(frontSum * static_cast<float>(hopSize));

  float backPadSum = 0.0f;
  if (backPad > 0) {
    const int start = static_cast<int>(durations.size()) - 1 - backPad;
    for (int i = start; i < static_cast<int>(durations.size()) - 1; i++) {
      backPadSum += durations[i];
    }
  }
  const int backPadSamples =
      static_cast<int>(backPadSum * static_cast<float>(hopSize));
  const float eosFrames = durations.back();
  float eosExcess = eosFrames - static_cast<float>(eosMaxFrames);
  if (eosExcess < 0.0f) eosExcess = 0.0f;
  const int backSamples =
      backPadSamples +
      static_cast<int>(eosExcess * static_cast<float>(hopSize));

  const int totalSamples = static_cast<int>(audioBuffer.size());
  int start = frontSamples < 0 ? 0 : frontSamples;
  int end = totalSamples - backSamples;
  if (end < start) end = start;
  if (start >= totalSamples || end <= 0 || start >= end) return;

  if (start > 0 || end < totalSamples) {
    std::vector<float> trimmed(audioBuffer.begin() + start,
                               audioBuffer.begin() + end);
    audioBuffer = std::move(trimmed);
  }
}

// Trim leading/trailing silence from int16 audio using windowed RMS.
// Preserves at least TRIM_MIN_SAMPLES samples.
static void trimSilenceInt16(std::vector<int16_t> &audioBuffer) {
  const auto totalSamples = static_cast<int>(audioBuffer.size());
  if (totalSamples <= TRIM_MIN_SAMPLES) {
    return;
  }

  const int nWindows = totalSamples / TRIM_WINDOW_SIZE;
  if (nWindows == 0) {
    return;
  }

  // Find first and last window above RMS threshold
  int firstAbove = -1;
  int lastAbove = -1;

  for (int w = 0; w < nWindows; w++) {
    float sumSq = 0.0f;
    const int offset = w * TRIM_WINDOW_SIZE;
    for (int s = 0; s < TRIM_WINDOW_SIZE; s++) {
      float sample = static_cast<float>(audioBuffer[offset + s]) / 32767.0f;
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(TRIM_WINDOW_SIZE));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = w;
      }
      lastAbove = w;
    }
  }

  // Check partial window (remainder samples after the last full window)
  const int remainder = totalSamples % TRIM_WINDOW_SIZE;
  if (remainder > 0) {
    float sumSq = 0.0f;
    const int offset = nWindows * TRIM_WINDOW_SIZE;
    for (int s = 0; s < remainder; s++) {
      float sample = static_cast<float>(audioBuffer[offset + s]) / 32767.0f;
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(remainder));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = nWindows;  // virtual window index for the partial
      }
      lastAbove = nWindows;
    }
  }

  if (firstAbove < 0) {
    // All silence -- keep minimum
    audioBuffer.resize(std::min(totalSamples, TRIM_MIN_SAMPLES));
    return;
  }

  int startSample = firstAbove * TRIM_WINDOW_SIZE;
  int endSample = std::min((lastAbove + 1) * TRIM_WINDOW_SIZE, totalSamples);

  // Ensure minimum length
  int length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    int center = (startSample + endSample) / 2;
    startSample = std::max(0, center - TRIM_MIN_SAMPLES / 2);
    endSample = std::min(totalSamples, startSample + TRIM_MIN_SAMPLES);
    startSample = std::max(0, endSample - TRIM_MIN_SAMPLES);
  }

  if (startSample > 0 || endSample < totalSamples) {
    spdlog::debug("Trimming silence: [{}, {}) from {} samples",
                  startSample, endSample, totalSamples);
    std::vector<int16_t> trimmed(audioBuffer.begin() + startSample,
                                 audioBuffer.begin() + endSample);
    audioBuffer = std::move(trimmed);
  }
}

// Trim leading/trailing silence from float32 audio using windowed RMS.
// Audio is assumed normalized to [-1.0, 1.0].
// Preserves at least TRIM_MIN_SAMPLES samples.
static void trimSilenceFloat(std::vector<float> &audioBuffer) {
  const auto totalSamples = static_cast<int>(audioBuffer.size());
  if (totalSamples <= TRIM_MIN_SAMPLES) {
    return;
  }

  const int nWindows = totalSamples / TRIM_WINDOW_SIZE;
  if (nWindows == 0) {
    return;
  }

  int firstAbove = -1;
  int lastAbove = -1;

  for (int w = 0; w < nWindows; w++) {
    float sumSq = 0.0f;
    const int offset = w * TRIM_WINDOW_SIZE;
    for (int s = 0; s < TRIM_WINDOW_SIZE; s++) {
      float sample = audioBuffer[offset + s];
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(TRIM_WINDOW_SIZE));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = w;
      }
      lastAbove = w;
    }
  }

  // Check partial window (remainder samples after the last full window)
  const int remainder = totalSamples % TRIM_WINDOW_SIZE;
  if (remainder > 0) {
    float sumSq = 0.0f;
    const int offset = nWindows * TRIM_WINDOW_SIZE;
    for (int s = 0; s < remainder; s++) {
      float sample = audioBuffer[offset + s];
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(remainder));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = nWindows;
      }
      lastAbove = nWindows;
    }
  }

  if (firstAbove < 0) {
    audioBuffer.resize(std::min(totalSamples, TRIM_MIN_SAMPLES));
    return;
  }

  int startSample = firstAbove * TRIM_WINDOW_SIZE;
  int endSample = std::min((lastAbove + 1) * TRIM_WINDOW_SIZE, totalSamples);

  int length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    int center = (startSample + endSample) / 2;
    startSample = std::max(0, center - TRIM_MIN_SAMPLES / 2);
    endSample = std::min(totalSamples, startSample + TRIM_MIN_SAMPLES);
    startSample = std::max(0, endSample - TRIM_MIN_SAMPLES);
  }

  if (startSample > 0 || endSample < totalSamples) {
    spdlog::debug("Trimming silence (float): [{}, {}) from {} samples",
                  startSample, endSample, totalSamples);
    std::vector<float> trimmed(audioBuffer.begin() + startSample,
                               audioBuffer.begin() + endSample);
    audioBuffer = std::move(trimmed);
  }
}

// ---------------------------------------------------------------------------
// buildInputTensors — shared tensor construction for synthesize / warmupModel
// ---------------------------------------------------------------------------
// Buffers (phonemeIdsBuf, etc.) are written by this function and MUST remain
// alive until after session.onnx.Run() returns, because Ort::Value::CreateTensor
// holds a raw pointer into them.
//
// Returns: { vector<Ort::Value>, vector<const char*> inputNames }
static std::pair<std::vector<Ort::Value>, std::vector<const char *>>
buildInputTensors(
    const InferenceInputs &inputs,
    const ModelSession &session,
    Ort::MemoryInfo &memoryInfo,
    // Caller-owned buffers — kept alive until Run() completes
    std::vector<int64_t> &phonemeIdsBuf,
    std::vector<int64_t> &phonemeIdLengthsBuf,
    std::vector<float>   &scalesBuf,
    std::vector<int64_t> &sidBuf,
    std::vector<int64_t> &lidBuf,
    std::vector<int64_t> &prosodyBuf) {

  // ---- phoneme ids ----
  phonemeIdsBuf = inputs.phonemeIds;  // copy
  const int64_t numPhonemes = static_cast<int64_t>(phonemeIdsBuf.size());

  phonemeIdLengthsBuf = {numPhonemes};
  scalesBuf = {inputs.noiseScale, inputs.lengthScale, inputs.noiseW};

  std::vector<Ort::Value> tensors;
  std::vector<const char *> names;

  // input (phoneme ids)
  std::vector<int64_t> phonemeIdsShape{1, numPhonemes};
  names.push_back("input");
  tensors.push_back(Ort::Value::CreateTensor<int64_t>(
      memoryInfo, phonemeIdsBuf.data(), phonemeIdsBuf.size(),
      phonemeIdsShape.data(), phonemeIdsShape.size()));

  // input_lengths
  std::vector<int64_t> phonemeIdLengthsShape{
      static_cast<int64_t>(phonemeIdLengthsBuf.size())};
  names.push_back("input_lengths");
  tensors.push_back(Ort::Value::CreateTensor<int64_t>(
      memoryInfo, phonemeIdLengthsBuf.data(), phonemeIdLengthsBuf.size(),
      phonemeIdLengthsShape.data(), phonemeIdLengthsShape.size()));

  // scales
  std::vector<int64_t> scalesShape{static_cast<int64_t>(scalesBuf.size())};
  names.push_back("scales");
  tensors.push_back(Ort::Value::CreateTensor<float>(
      memoryInfo, scalesBuf.data(), scalesBuf.size(),
      scalesShape.data(), scalesShape.size()));

  // sid (speaker id)
  if (session.hasMultiSpeaker) {
    sidBuf = {inputs.speakerId.value_or(0)};
    std::vector<int64_t> sidShape{static_cast<int64_t>(sidBuf.size())};
    names.push_back("sid");
    tensors.push_back(Ort::Value::CreateTensor<int64_t>(
        memoryInfo, sidBuf.data(), sidBuf.size(),
        sidShape.data(), sidShape.size()));
  }

  // lid (language id)
  if (session.hasLidInput) {
    lidBuf = {inputs.languageId.value_or(0)};
    std::vector<int64_t> lidShape{static_cast<int64_t>(lidBuf.size())};
    names.push_back("lid");
    tensors.push_back(Ort::Value::CreateTensor<int64_t>(
        memoryInfo, lidBuf.data(), lidBuf.size(),
        lidShape.data(), lidShape.size()));
  }

  // prosody_features
  if (session.hasProsodyInput) {
    std::vector<int64_t> prosodyShape{1, numPhonemes, 3};
    const auto expectedSize = static_cast<size_t>(numPhonemes) * 3;
    if (!inputs.prosodyFeatures.empty() &&
        inputs.prosodyFeatures.size() == expectedSize) {
      prosodyBuf = inputs.prosodyFeatures;  // copy
    } else {
      prosodyBuf.assign(expectedSize, 0);
    }
    names.push_back("prosody_features");
    tensors.push_back(Ort::Value::CreateTensor<int64_t>(
        memoryInfo, prosodyBuf.data(), prosodyBuf.size(),
        prosodyShape.data(), prosodyShape.size()));
  }

  return {std::move(tensors), std::move(names)};
}

// Phoneme ids to WAV audio
void synthesize(std::vector<PhonemeId> &phonemeIds,
                SynthesisConfig &synthesisConfig, ModelSession &session,
                std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                Voice *voice = nullptr,
                std::vector<int64_t> *prosodyFeatures = nullptr) {
  spdlog::debug("Synthesizing audio for {} phoneme id(s)", phonemeIds.size());

  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  // Validate & clamp language ID before building tensors
  auto lid = synthesisConfig.languageId.value_or(0);
  if (voice && (lid < 0 || lid >= voice->modelConfig.numLanguages)) {
    spdlog::warn("Language ID {} out of range [0, {}), using 0",
                 lid, voice->modelConfig.numLanguages);
    lid = 0;
  }

  // --- Strategy A+B: Short-text mitigation ---
  const auto originalLen = static_cast<int>(phonemeIds.size());
  // Save original (pre-padding) phoneme IDs for timing extraction.
  // Duration output corresponds to the original sequence, not padded.
  const std::vector<PhonemeId> originalPhonemeIds(phonemeIds);
  int frontPad = 0;
  int backPad = 0;
  bool wasPadded = padPhonemeIds(phonemeIds, /*padId=*/0, &frontPad, &backPad);

  // Strategy B: Dynamic Scales Adjustment
  float effectiveNoiseScale = synthesisConfig.noiseScale;
  float effectiveNoiseW = synthesisConfig.noiseW;
  if (originalLen < MIN_PHONEME_IDS) {
    float ratio = std::clamp(static_cast<float>(originalLen) /
                                 static_cast<float>(MIN_PHONEME_IDS),
                             0.0f, 1.0f);
    effectiveNoiseScale *= std::max(0.5f, ratio);
    effectiveNoiseW *= std::max(0.4f, ratio);
    spdlog::debug("Short-text dynamic scales: ratio={:.3f}, "
                  "noiseScale={:.4f}, noiseW={:.4f}",
                  ratio, effectiveNoiseScale, effectiveNoiseW);
  }

  // Populate InferenceInputs from the existing parameters
  InferenceInputs inputs;
  inputs.phonemeIds.assign(phonemeIds.begin(), phonemeIds.end());
  inputs.noiseScale  = effectiveNoiseScale;
  inputs.lengthScale = synthesisConfig.lengthScale;
  inputs.noiseW      = effectiveNoiseW;
  inputs.speakerId   = static_cast<int64_t>(synthesisConfig.speakerId.value_or(0));
  inputs.languageId  = static_cast<int64_t>(lid);
  if (prosodyFeatures) {
    inputs.prosodyFeatures = *prosodyFeatures;
  }

  // Buffers must outlive the Run() call
  std::vector<int64_t> phonemeIdsBuf, phonemeIdLengthsBuf, sidBuf, lidBuf, prosodyBuf;
  std::vector<float> scalesBuf;

  auto [inputTensors, inputNamesVec] = buildInputTensors(
      inputs, session, memoryInfo,
      phonemeIdsBuf, phonemeIdLengthsBuf, scalesBuf,
      sidBuf, lidBuf, prosodyBuf);

  // Output names
  std::vector<const char *> outputNamesVec;
  outputNamesVec.push_back("output");
  if (session.hasDurationOutput) {
    outputNamesVec.push_back("durations");
  }

  // Resolve hop_size for durations-based Strategy A trim. Falls back to
  // DEFAULT_HOP_SIZE when the config is missing or the field is absent.
  int hopSize = DEFAULT_HOP_SIZE;
  if (voice && voice->configRoot.contains("audio") &&
      voice->configRoot["audio"].contains("hop_size")) {
    hopSize = voice->configRoot["audio"]["hop_size"];
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
    float audioValue = std::abs(audio[i]);
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

  // Extract durations BEFORE post-trim so the precise trimmer can use them.
  std::vector<float> paddedDurations;
  bool haveDurations = false;
  if (session.hasDurationOutput && outputTensors.size() >= 2) {
    auto& durationTensor = outputTensors[1];
    if (durationTensor.IsTensor()) {
      const float *dPtr = durationTensor.GetTensorData<float>();
      auto durationShape = durationTensor.GetTensorTypeAndShapeInfo().GetShape();
      size_t durationCount = 1;
      for (auto dim : durationShape) {
        durationCount *= dim;
      }
      paddedDurations.assign(dPtr, dPtr + durationCount);
      haveDurations = true;
    }
  }

  // --- Strategy A post-trim: remove padding-induced audio ---
  // Prefer the durations-based precise trim when the model exposes
  // durations (issue #356). Falls back to the legacy RMS trim only when
  // durations are unavailable.
  if (wasPadded) {
    if (haveDurations) {
      trimPaddingByDurations(audioBuffer, paddedDurations, frontPad, backPad,
                             hopSize, TRIM_EOS_MAX_FRAMES);
    } else {
      trimSilenceInt16(audioBuffer);
    }
    result.audioSeconds =
        static_cast<double>(audioBuffer.size()) /
        static_cast<double>(synthesisConfig.sampleRate);
    if (result.audioSeconds > 0) {
      result.realTimeFactor = result.inferSeconds / result.audioSeconds;
    }
  }

  // Extract phoneme timing information using the original (pre-padding)
  // sequence so callers see indices aligned with their input.
  if (haveDurations && voice != nullptr) {
    result.phonemeTimings = extractTimingsFromDurations(
        paddedDurations, originalPhonemeIds,
        voice->phonemizeConfig.phonemeIdMap,
        hopSize,
        voice->synthesisConfig.sampleRate,
        voice->phonemizeConfig.phonemeType);
    result.hasTimingInfo = true;
    spdlog::debug("Extracted timing for {} phonemes",
                  result.phonemeTimings.size());
  }

  // Clean up
  for (std::size_t i = 0; i < outputTensors.size(); i++) {
    Ort::detail::OrtRelease(outputTensors[i].release());
  }

  for (std::size_t i = 0; i < inputTensors.size(); i++) {
    Ort::detail::OrtRelease(inputTensors[i].release());
  }
}

// Float32 variant of synthesize — outputs normalized [-1.0, 1.0] samples
// instead of converting to int16.
void synthesizeFloat(std::vector<PhonemeId> &phonemeIds,
                     SynthesisConfig &synthesisConfig, ModelSession &session,
                     std::vector<float> &audioBuffer, SynthesisResult &result,
                     Voice *voice = nullptr,
                     std::vector<int64_t> *prosodyFeatures = nullptr) {
  spdlog::debug("Synthesizing audio (float32) for {} phoneme id(s)", phonemeIds.size());

  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  // Validate & clamp language ID before building tensors
  auto lid = synthesisConfig.languageId.value_or(0);
  if (voice && (lid < 0 || lid >= voice->modelConfig.numLanguages)) {
    spdlog::warn("Language ID {} out of range [0, {}), using 0",
                 lid, voice->modelConfig.numLanguages);
    lid = 0;
  }

  // --- Strategy A+B: Short-text mitigation ---
  const auto originalLen = static_cast<int>(phonemeIds.size());
  // Save original (pre-padding) phoneme IDs for timing extraction.
  // Duration output corresponds to the original sequence, not padded.
  const std::vector<PhonemeId> originalPhonemeIds(phonemeIds);
  int frontPad = 0;
  int backPad = 0;
  bool wasPadded = padPhonemeIds(phonemeIds, /*padId=*/0, &frontPad, &backPad);

  // Strategy B: Dynamic Scales Adjustment
  float effectiveNoiseScale = synthesisConfig.noiseScale;
  float effectiveNoiseW = synthesisConfig.noiseW;
  if (originalLen < MIN_PHONEME_IDS) {
    float ratio = std::clamp(static_cast<float>(originalLen) /
                                 static_cast<float>(MIN_PHONEME_IDS),
                             0.0f, 1.0f);
    effectiveNoiseScale *= std::max(0.5f, ratio);
    effectiveNoiseW *= std::max(0.4f, ratio);
    spdlog::debug("Short-text dynamic scales (float): ratio={:.3f}, "
                  "noiseScale={:.4f}, noiseW={:.4f}",
                  ratio, effectiveNoiseScale, effectiveNoiseW);
  }

  // Resolve hop_size for durations-based Strategy A trim.
  int hopSize = DEFAULT_HOP_SIZE;
  if (voice && voice->configRoot.contains("audio") &&
      voice->configRoot["audio"].contains("hop_size")) {
    hopSize = voice->configRoot["audio"]["hop_size"];
  }

  // Populate InferenceInputs from the existing parameters
  InferenceInputs inputs;
  inputs.phonemeIds.assign(phonemeIds.begin(), phonemeIds.end());
  inputs.noiseScale  = effectiveNoiseScale;
  inputs.lengthScale = synthesisConfig.lengthScale;
  inputs.noiseW      = effectiveNoiseW;
  inputs.speakerId   = static_cast<int64_t>(synthesisConfig.speakerId.value_or(0));
  inputs.languageId  = static_cast<int64_t>(lid);
  if (prosodyFeatures) {
    inputs.prosodyFeatures = *prosodyFeatures;
  }

  // Buffers must outlive the Run() call
  std::vector<int64_t> phonemeIdsBuf, phonemeIdLengthsBuf, sidBuf, lidBuf, prosodyBuf;
  std::vector<float> scalesBuf;

  auto [inputTensors, inputNamesVec] = buildInputTensors(
      inputs, session, memoryInfo,
      phonemeIdsBuf, phonemeIdLengthsBuf, scalesBuf,
      sidBuf, lidBuf, prosodyBuf);

  // Output names
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

  // Get max audio value for normalization to [-1.0, 1.0]
  float maxAudioValue = 0.01f;

#ifdef USE_ARM64_NEON
  maxAudioValue = findMaxAudioValueNEON(audio, audioCount);
#else
  for (int64_t i = 0; i < audioCount; i++) {
    float audioValue = std::abs(audio[i]);
    if (audioValue > maxAudioValue) {
      maxAudioValue = audioValue;
    }
  }
#endif

  // We know the size up front
  audioBuffer.reserve(audioBuffer.size() + audioCount);

  // Normalize audio to [-1.0, 1.0] and copy directly as float
  float invMax = 1.0f / std::max(0.01f, maxAudioValue);
  for (int64_t i = 0; i < audioCount; i++) {
    audioBuffer.push_back(
        std::clamp(audio[i] * invMax, -1.0f, 1.0f));
  }

  // Extract durations BEFORE post-trim so the precise trimmer can use them.
  std::vector<float> paddedDurations;
  bool haveDurations = false;
  if (session.hasDurationOutput && outputTensors.size() >= 2) {
    auto& durationTensor = outputTensors[1];
    if (durationTensor.IsTensor()) {
      const float *dPtr = durationTensor.GetTensorData<float>();
      auto durationShape = durationTensor.GetTensorTypeAndShapeInfo().GetShape();
      size_t durationCount = 1;
      for (auto dim : durationShape) {
        durationCount *= dim;
      }
      paddedDurations.assign(dPtr, dPtr + durationCount);
      haveDurations = true;
    }
  }

  // --- Strategy A post-trim: remove padding-induced audio ---
  if (wasPadded) {
    if (haveDurations) {
      trimPaddingByDurationsFloat(audioBuffer, paddedDurations, frontPad,
                                  backPad, hopSize, TRIM_EOS_MAX_FRAMES);
    } else {
      trimSilenceFloat(audioBuffer);
    }
    result.audioSeconds =
        static_cast<double>(audioBuffer.size()) /
        static_cast<double>(synthesisConfig.sampleRate);
    if (result.audioSeconds > 0) {
      result.realTimeFactor = result.inferSeconds / result.audioSeconds;
    }
  }

  // Extract phoneme timing information if available (legacy block kept
  // intact below — it consumes the durationTensor a second time only when
  // we entered this branch).
  if (session.hasDurationOutput && outputTensors.size() >= 2 && voice != nullptr) {
    auto& durationTensor = outputTensors[1];
    if (durationTensor.IsTensor()) {
      const float *durations = durationTensor.GetTensorData<float>();
      auto durationShape = durationTensor.GetTensorTypeAndShapeInfo().GetShape();
      size_t durationCount = 1;
      for (auto dim : durationShape) {
        durationCount *= dim;
      }

      std::vector<float> durationVec(durations, durations + durationCount);

      int hopSize = DEFAULT_HOP_SIZE;
      if (voice->configRoot.contains("audio") &&
          voice->configRoot["audio"].contains("hop_size")) {
        hopSize = voice->configRoot["audio"]["hop_size"];
      }

      result.phonemeTimings = extractTimingsFromDurations(
          durationVec, originalPhonemeIds,
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

// Compute prosody features (a1, a2, a3) for non-JA languages.
// Each language family uses a different prosody extraction strategy:
//   - Chinese (zh):  a1=tone(1-5), a2=syllable position, a3=syllables in word
//   - English/Spanish/Portuguese (en/es/pt): a1=0, a2=stress level, a3=word phoneme count
//   - French (fr):   a1=0, a2=2 for final vowel in word, a3=word phoneme count
//   - Korean (ko) / unknown: all {0,0,0}
static std::vector<ProsodyFeature> computeNonJaProsody(
    const std::vector<Phoneme> &phonemes, const std::string &lang) {

  std::vector<ProsodyFeature> result(phonemes.size(), {0, 0, 0});

  if (phonemes.empty()) return result;

  // --- Vowel-like phoneme detection ---
  auto isVowelLike = [](Phoneme ph) -> bool {
    // Basic Latin vowels
    if (ph == 0x61 || ph == 0x65 || ph == 0x69 ||
        ph == 0x6F || ph == 0x75) return true;
    // IPA vowels
    if (ph == 0x0251 || ph == 0x00E6 || ph == 0x028C ||
        ph == 0x0259 || ph == 0x0254 || ph == 0x025B ||
        ph == 0x025A || ph == 0x025C || ph == 0x026A ||
        ph == 0x028A || ph == 0x00F8 || ph == 0x0153) return true;
    // PUA: y_vowel
    if (ph == 0xE01E) return true;
    // PUA: French nasal vowels
    if (ph >= 0xE056 && ph <= 0xE058) return true;
    return false;
  };

  // Length marker
  constexpr Phoneme LENGTH_MARKER = 0x02D0; // ː

  // --- Word boundary detection ---
  auto isWordBoundary = [](Phoneme ph) -> bool {
    if (ph == 0x20) return true;                        // space
    if (ph == U',' || ph == U'.' || ph == U'!' ||
        ph == U'?' || ph == U';' || ph == U':') return true;
    if (ph == 0x3001 || ph == 0x3002 || ph == 0xFF0C) return true; // CJK punct
    return false;
  };

  // --- Chinese: tone from PUA markers, syllable position in word ---
  if (lang == "zh") {
    constexpr Phoneme PUA_TONE1 = 0xE046;
    constexpr Phoneme PUA_TONE5 = 0xE04A;

    auto isToneMarker = [](Phoneme ph) -> bool {
      return ph >= 0xE046 && ph <= 0xE04A;
    };
    auto getToneFromMarker = [](Phoneme ph) -> int {
      return static_cast<int>(ph - 0xE046 + 1);
    };

    // Two-pass: first identify word boundaries & syllable counts,
    // then assign a1=tone, a2=syllable pos, a3=total syllables.
    // A "word" is delimited by word boundaries.
    // A "syllable" in the Chinese phoneme stream ends at a tone marker.

    size_t wordStart = 0;
    while (wordStart < phonemes.size()) {
      // Find word end
      size_t wordEnd = wordStart;
      while (wordEnd < phonemes.size() && !isWordBoundary(phonemes[wordEnd])) {
        wordEnd++;
      }

      // Count syllables in this word (= number of tone markers)
      int totalSyllables = 0;
      for (size_t i = wordStart; i < wordEnd; i++) {
        if (isToneMarker(phonemes[i])) totalSyllables++;
      }
      if (totalSyllables == 0) totalSyllables = 1; // at least 1

      // Assign prosody: track current syllable position
      int syllablePos = 1;
      int currentTone = 0;
      for (size_t i = wordStart; i < wordEnd; i++) {
        if (isToneMarker(phonemes[i])) {
          currentTone = getToneFromMarker(phonemes[i]);
          result[i] = {currentTone, syllablePos, totalSyllables};
          syllablePos++;
          currentTone = 0; // reset for next syllable
        } else {
          // Non-tone phonemes in the current syllable get a1=0
          result[i] = {0, syllablePos, totalSyllables};
        }
      }

      // Boundary phonemes stay {0,0,0}
      if (wordEnd < phonemes.size()) {
        wordEnd++; // skip the boundary
      }
      wordStart = wordEnd;
    }

    return result;
  }

  // --- English / Spanish / Portuguese: stress-based prosody ---
  if (lang == "en" || lang == "es" || lang == "pt") {
    constexpr Phoneme PRIMARY_STRESS   = 0x02C8; // ˈ
    constexpr Phoneme SECONDARY_STRESS = 0x02CC; // ˌ

    auto isStressMarker = [](Phoneme ph) -> bool {
      return ph == 0x02C8 || ph == 0x02CC;
    };

    // Process word by word
    size_t wordStart = 0;
    while (wordStart < phonemes.size()) {
      // Find word end
      size_t wordEnd = wordStart;
      while (wordEnd < phonemes.size() && !isWordBoundary(phonemes[wordEnd])) {
        wordEnd++;
      }

      // Count phonemes in word excluding stress markers (for a3)
      int wordPhonemeCount = 0;
      for (size_t i = wordStart; i < wordEnd; i++) {
        if (!isStressMarker(phonemes[i])) wordPhonemeCount++;
      }
      if (wordPhonemeCount == 0) wordPhonemeCount = 1;

      // Assign stress: ˈ→2, ˌ→1, applied to the marker itself and
      // following vowel-like phonemes (including ː length marker).
      // Reset to 0 when a non-vowel, non-length-marker phoneme appears
      // after at least one vowel was assigned stress.
      int pendingStress = 0;
      bool vowelAssigned = false;
      for (size_t i = wordStart; i < wordEnd; i++) {
        Phoneme ph = phonemes[i];
        if (ph == PRIMARY_STRESS) {
          pendingStress = 2;
          vowelAssigned = false;
          result[i] = {0, pendingStress, wordPhonemeCount};
        } else if (ph == SECONDARY_STRESS) {
          pendingStress = 1;
          vowelAssigned = false;
          result[i] = {0, pendingStress, wordPhonemeCount};
        } else if (isVowelLike(ph) || (ph == LENGTH_MARKER && vowelAssigned)) {
          // Vowel or length marker after a vowel: assign current stress
          result[i] = {0, pendingStress, wordPhonemeCount};
          if (isVowelLike(ph)) vowelAssigned = true;
        } else {
          // Consonant or other: reset stress if a vowel was already assigned
          if (vowelAssigned) {
            pendingStress = 0;
            vowelAssigned = false;
          }
          result[i] = {0, pendingStress, wordPhonemeCount};
        }
      }

      // Boundary phonemes stay {0,0,0}
      if (wordEnd < phonemes.size()) {
        wordEnd++; // skip boundary
      }
      wordStart = wordEnd;
    }

    return result;
  }

  // --- French: final-syllable stress (a2=2 for last vowel in word) ---
  if (lang == "fr") {
    size_t wordStart = 0;
    while (wordStart < phonemes.size()) {
      // Find word end
      size_t wordEnd = wordStart;
      while (wordEnd < phonemes.size() && !isWordBoundary(phonemes[wordEnd])) {
        wordEnd++;
      }

      // Count phonemes in word (for a3)
      int wordPhonemeCount = static_cast<int>(wordEnd - wordStart);
      if (wordPhonemeCount == 0) wordPhonemeCount = 1;

      // Find the last vowel-like phoneme in this word
      int lastVowelIdx = -1;
      for (size_t i = wordStart; i < wordEnd; i++) {
        if (isVowelLike(phonemes[i])) {
          lastVowelIdx = static_cast<int>(i);
        }
      }

      // Assign: a1=0, a2=2 for last vowel, a2=0 otherwise, a3=word count
      for (size_t i = wordStart; i < wordEnd; i++) {
        int stress = (static_cast<int>(i) == lastVowelIdx) ? 2 : 0;
        result[i] = {0, stress, wordPhonemeCount};
      }

      // Boundary phonemes stay {0,0,0}
      if (wordEnd < phonemes.size()) {
        wordEnd++; // skip boundary
      }
      wordStart = wordEnd;
    }

    return result;
  }

  // --- Korean / unknown: all zeros ---
  // result is already initialized to {0,0,0}
  return result;
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

  // Phonemize text (pure -- does not modify voice).
  PhonemizeResult phonResult;
  phonemizeText(voice, text, phonResult, externalProsody);
  auto &phonemes = phonResult.phonemes;
  auto &allProsodyFeatures = phonResult.prosody;
  bool useProsody = !allProsodyFeatures.empty();

  // Apply auto-detected language only if the caller did not explicitly set one.
  if (!voice.synthesisConfig.languageId.has_value() &&
      phonResult.detectedLanguageId.has_value()) {
    voice.synthesisConfig.languageId = phonResult.detectedLanguageId;
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

    // Multilingual: BOS/EOS + padding (added by phonemes_to_ids)
    // BOS/EOS from individual segments are already stripped
    // Note: MultilingualPhonemes uses interspersePad=true (set in parsePhonemizeConfig)

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

// Float32 output variant — avoids int16 intermediate conversion.
// Audio samples are normalized to [-1.0, 1.0].
void textToAudioFloat(PiperConfig &config, Voice &voice, std::string text,
                      std::vector<float> &audioBuffer, SynthesisResult &result,
                      const std::function<void()> &audioCallback,
                      const std::vector<ProsodyFeature> *externalProsody) {

  std::size_t sentenceSilenceSamples = 0;
  if (voice.synthesisConfig.sentenceSilenceSeconds > 0) {
    sentenceSilenceSamples = (std::size_t)(
        voice.synthesisConfig.sentenceSilenceSeconds *
        voice.synthesisConfig.sampleRate * voice.synthesisConfig.channels);
  }

  // Phonemize text (pure -- does not modify voice).
  PhonemizeResult phonResult;
  phonemizeText(voice, text, phonResult, externalProsody);
  auto &phonemes = phonResult.phonemes;
  auto &allProsodyFeatures = phonResult.prosody;
  bool useProsody = !allProsodyFeatures.empty();

  // Apply auto-detected language only if the caller did not explicitly set one.
  if (!voice.synthesisConfig.languageId.has_value() &&
      phonResult.detectedLanguageId.has_value()) {
    voice.synthesisConfig.languageId = phonResult.detectedLanguageId;
  }

  // Synthesize each sentence independently.
  std::vector<PhonemeId> phonemeIds;
  std::map<Phoneme, std::size_t> missingPhonemes;
  size_t sentenceIdx = 0;
  for (auto phonemesIter = phonemes.begin(); phonemesIter != phonemes.end();
       ++phonemesIter, ++sentenceIdx) {
    std::vector<Phoneme> &sentencePhonemes = *phonemesIter;

    if (spdlog::should_log(spdlog::level::debug)) {
      std::string phonemesStr;
      for (auto phoneme : sentencePhonemes) {
        phonemesStr += phonemeToString(phoneme);
        phonemesStr += " ";
      }
      if (!phonemesStr.empty()) {
        phonemesStr.pop_back();
      }

      spdlog::debug("Converting {} phoneme(s) to ids: {}",
                    sentencePhonemes.size(), phonemesStr);
    }

    std::vector<std::shared_ptr<std::vector<Phoneme>>> phrasePhonemes;
    std::vector<SynthesisResult> phraseResults;
    std::vector<size_t> phraseSilenceSamples;

    PhonemeIdConfig idConfig;
    idConfig.phonemeIdMap =
        std::make_shared<PhonemeIdMap>(voice.phonemizeConfig.phonemeIdMap);
    idConfig.interspersePad = voice.phonemizeConfig.interspersePad;

    if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
        idConfig.addBos = false;
        idConfig.addEos = false;
    }

    if (voice.synthesisConfig.phonemeSilenceSeconds) {
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
          phraseSilenceSamples.push_back(
              (std::size_t)(phonemeSilenceSeconds[currentPhoneme] *
                            voice.synthesisConfig.sampleRate *
                            voice.synthesisConfig.channels));

          currentPhrasePhonemes = std::make_shared<std::vector<Phoneme>>();
          phrasePhonemes.push_back(currentPhrasePhonemes);
        }
      }
    } else {
      phrasePhonemes.push_back(
          std::make_shared<std::vector<Phoneme>>(sentencePhonemes));
    }

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

      phonemes_to_ids(*(phrasePhonemes[phraseIdx]), idConfig, phonemeIds,
                      missingPhonemes);
      if (spdlog::should_log(spdlog::level::debug)) {
        std::stringstream phonemeIdsStr;
        for (auto phonemeId : phonemeIds) {
          phonemeIdsStr << phonemeId << ", ";
        }

        spdlog::debug("Converted {} phoneme(s) to {} phoneme id(s): {}",
                      phrasePhonemes[phraseIdx]->size(), phonemeIds.size(),
                      phonemeIdsStr.str());
      }

      // ids -> audio (float32)
      std::vector<int64_t> *prosodyPtr = nullptr;
      std::vector<int64_t> prosodyFlat;

      if (useProsody && sentenceIdx < allProsodyFeatures.size()) {
        const auto &sentenceProsody = allProsodyFeatures[sentenceIdx];

        size_t numPhonemeIds = phonemeIds.size();
        prosodyFlat.resize(numPhonemeIds * 3, 0);

        spdlog::debug("Prosody mapping: {} phonemeIds, {} prosody features, interspersePad={}",
                      phonemeIds.size(), sentenceProsody.size(),
                      voice.phonemizeConfig.interspersePad);

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
        spdlog::debug("Using prosody features: {} phoneme IDs, {} original prosody values",
                      numPhonemeIds, sentenceProsody.size());
      }

      synthesizeFloat(phonemeIds, voice.synthesisConfig, voice.session, audioBuffer,
                      phraseResults[phraseIdx], &voice, prosodyPtr);

      // Add end of phrase silence (float 0.0)
      for (std::size_t i = 0; i < phraseSilenceSamples[phraseIdx]; i++) {
        audioBuffer.push_back(0.0f);
      }

      result.audioSeconds += phraseResults[phraseIdx].audioSeconds;
      result.inferSeconds += phraseResults[phraseIdx].inferSeconds;

      phonemeIds.clear();
    }

    // Add end of sentence silence (float 0.0)
    if (sentenceSilenceSamples > 0) {
      for (std::size_t i = 0; i < sentenceSilenceSamples; i++) {
        audioBuffer.push_back(0.0f);
      }
    }

    if (audioCallback) {
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

} /* textToAudioFloat */

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

// Helper: is a codepoint a punctuation mark used for density calculation?
static bool isPunctCodepoint(char32_t c) {
  switch (c) {
    case U'\u3002': // 。
    case U'\u3001': // 、
    case U'\uFF01': // ！
    case U'\uFF1F': // ？
    case U'.': case U'!': case U'?': case U',': case U';': case U':':
      return true;
    default:
      return false;
  }
}

// Helper function for calculating dynamic chunk size based on text characteristics.
// Operates on codepoints (not bytes) to correctly handle CJK text.
static size_t calculateDynamicChunkSize(const std::vector<char32_t>& cps,
                                        size_t baseSize = 50) {
  size_t cpLen = cps.size();

  // Short texts should not be chunked
  if (cpLen < baseSize * 2) {
    return cpLen;
  }

  // Calculate punctuation density (codepoint-level)
  size_t punctCount = 0;
  for (char32_t c : cps) {
    if (isPunctCodepoint(c)) {
      punctCount++;
    }
  }

  // Adjust chunk size based on punctuation density
  float punctDensity = static_cast<float>(punctCount) / static_cast<float>(cpLen);
  if (punctDensity > 0.05f) {  // More than 5% punctuation - use smaller chunks
    return baseSize;
  } else if (punctDensity < 0.02f) {  // Less than 2% punctuation - use larger chunks
    return baseSize * 3;
  }
  return baseSize * 2;  // Medium density
}

// Helper: is a codepoint a closing punctuation mark that should be
// consumed after a sentence terminator? (Issue #346)
// Character set (14 chars): all-runtime superset covering 8 supported languages.
// See docs/spec/text-splitter-contract.toml for the canonical definition.
// Includes U+0022 and U+0027 which are ambiguous (open/close), but safe because
// this function is only called after a sentence terminator (hasTerminator guard).
static bool isClosingPunctuation(char32_t c) {
  switch (c) {
    case U')':      // U+0029  Right Parenthesis
    case U']':      // U+005D  Right Square Bracket
    case U'}':      // U+007D  Right Curly Bracket
    case U'"':      // U+0022  Quotation Mark
    case U'\'':     // U+0027  Apostrophe
    case U'\u300D': // 」 Right Corner Bracket
    case U'\u300F': // 』 Right White Corner Bracket
    case U'\uFF09': // ） Fullwidth Right Parenthesis
    case U'\uFF3D': // ］ Fullwidth Right Square Bracket
    case U'\u3011': // 】 Right Black Lenticular Bracket
    case U'\uFF63': // ｣  Halfwidth Right Corner Bracket
    case U'\u201D': // "  Right Double Quotation Mark
    case U'\u2019': // '  Right Single Quotation Mark
    case U'\u00BB': // »  Right-Pointing Double Angle Quotation Mark
      return true;
    default:
      return false;
  }
}

// Split text into sentences at natural boundaries (public API).
// Uses codepoint-level iteration via utf8_utils to correctly handle
// multibyte UTF-8 characters (CJK punctuation, etc.).
// Fixes: https://github.com/ayutaz/piper-plus/issues/343
std::vector<std::string> splitTextToSentences(
    const std::string &text,
    PhonemeType phonemeType,
    size_t maxChunkSize) {

  if (text.empty()) {
    return {};
  }

  // Guard against invalid UTF-8: toCodepoints() uses utf8::unchecked
  // internally and requires well-formed input.
  if (!utf8::is_valid(text.begin(), text.end())) {
    spdlog::warn("splitTextToSentences: invalid UTF-8 input, returning as single chunk");
    return {text};
  }

  using utf8_util::toCodepoints;
  using utf8_util::cpsToUtf8;

  auto cps = toCodepoints(text);
  size_t cpLen = cps.size();

  size_t baseSize = maxChunkSize > 0 ? maxChunkSize : 50;
  size_t dynamicChunkSize = calculateDynamicChunkSize(cps, baseSize);

  // Classify whether a codepoint is a boundary punctuation mark
  auto isBoundaryPunct = [&](char32_t c) -> bool {
    if (phonemeType == MultilingualPhonemes) {
      // Multilingual: CJK fullwidth + ASCII sentence-end + ellipsis
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F' ||
             c == U'\uFF0E' || c == U'.' || c == U'!' || c == U'?' ||
             c == U'\u2026'; // …
    } else if (usesOpenJTalk(phonemeType)) {
      // Japanese: fullwidth sentence-end + ideographic comma
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F' ||
             c == U'\u3001'; // 、
    } else {
      // English/other: ASCII punctuation
      return c == U'.' || c == U'!' || c == U'?' || c == U',' ||
             c == U';' || c == U':';
    }
  };

  // Check if a codepoint is a sentence terminator (triggers immediate split)
  auto isSentenceTerminator = [&](char32_t c) -> bool {
    if (phonemeType == MultilingualPhonemes) {
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F' ||
             c == U'\uFF0E' || c == U'.' || c == U'!' || c == U'?';
    } else if (usesOpenJTalk(phonemeType)) {
      // For Japanese, 、 (comma) is boundary but NOT a terminator
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F';
    } else {
      return c == U'.' || c == U'!' || c == U'?';
    }
  };

  std::vector<std::string> chunks;
  size_t sentenceStart = 0;

  for (size_t i = 0; i < cpLen; ++i) {
    char32_t c = cps[i];

    if (isBoundaryPunct(c)) {
      // Consume the entire run of boundary punctuation
      bool hasTerminator = isSentenceTerminator(c);
      size_t punctEnd = i + 1;
      while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {
        if (isSentenceTerminator(cps[punctEnd])) {
          hasTerminator = true;
        }
        punctEnd++;
      }
      // Issue #346: Consume closing brackets/quotes after sentence terminator
      // so that 「こんにちは。」 stays in one chunk (matches Rust/C# behavior).
      if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
          punctEnd++;
        }
      }
      i = punctEnd - 1; // advance past punctuation run (for-loop will ++)

      // Split if this contains a sentence terminator, or chunk is too long
      size_t chunkLen = punctEnd - sentenceStart;
      if (hasTerminator || chunkLen > dynamicChunkSize) {
        std::string chunk = cpsToUtf8(cps, sentenceStart, chunkLen);
        if (!chunk.empty()) {
          chunks.push_back(chunk);
        }
        sentenceStart = punctEnd;
      }
    }
  }

  // Emit any remaining text
  if (sentenceStart < cpLen) {
    std::string remaining = cpsToUtf8(cps, sentenceStart, cpLen - sentenceStart);
    if (!remaining.empty()) {
      chunks.push_back(remaining);
    }
  }

  return chunks;
}

// Phonemize text into per-sentence phoneme sequences (public API).
// Pure: does not modify voice.  Auto-detected language is returned
// in result.detectedLanguageId.
void phonemizeText(const Voice &voice, const std::string &text,
                   PhonemizeResult &result,
                   const std::vector<ProsodyFeature> *externalProsody) {

  result.phonemes.clear();
  result.prosody.clear();
  result.detectedLanguageId = std::nullopt;

  // Parse text for [[ phonemes ]] notation
  auto textSegments = parsePhonemeNotation(text);

  // Phonemes for each sentence
  spdlog::debug("Phonemizing text: {}", text);

  // Prosody features for each sentence (only used for OpenJTalk with prosody-enabled models)
  bool useProsody = voice.session.hasProsodyInput &&
                    usesOpenJTalk(voice.phonemizeConfig.phonemeType);

  // Process each segment
  for (const auto& segment : textSegments) {
    if (segment.isPhonemes) {
      // Direct phoneme input
      spdlog::debug("Processing direct phoneme input: {}", segment.text);
      auto parsedPhonemes = parsePhonemeString(segment.text, static_cast<int>(voice.phonemizeConfig.phonemeType));

      // Add as a single "sentence"
      result.phonemes.push_back(parsedPhonemes);

      // Add empty prosody features for direct phoneme input
      if (useProsody) {
        std::vector<ProsodyFeature> emptyProsody(parsedPhonemes.size(), {0, 0, 0});
        result.prosody.push_back(std::move(emptyProsody));
      }
    } else {
      // Regular text - phonemize as usual
      std::vector<std::vector<Phoneme>> segmentPhonemes;
      std::vector<std::vector<ProsodyFeature>> segmentProsody;

      if (voice.phonemizeConfig.phonemeType == OpenJTalkPhonemes) {
        // Japanese OpenJTalk phonemizer
        if (useProsody) {
          phonemize_openjtalk_with_prosody(segment.text, segmentPhonemes, segmentProsody);
        } else {
          phonemize_openjtalk(segment.text, segmentPhonemes);
        }

        // If OpenJTalk failed, report error (eSpeak is no longer available)
        if (segmentPhonemes.empty() && !segment.text.empty()) {
          spdlog::error("OpenJTalk failed to process text; skipping segment");
        }
      } else if (voice.phonemizeConfig.phonemeType == MultilingualPhonemes) {
        // Multilingual: segment text by language, phonemize each segment
        // with the appropriate engine, strip BOS/EOS from JA segments.
        std::vector<std::string> multiLangs;
        if (voice.modelConfig.languageIdMap) {
          for (const auto& [code, id] : *voice.modelConfig.languageIdMap) {
            multiLangs.push_back(code);
          }
        } else {
          multiLangs = {"ja", "en"};  // Default bilingual
        }

        // Determine default Latin language.
        // If the user set --language, reverse-lookup the code and prefer it
        // when it is a Latin-script language.
        std::string defaultLatin = "en";
        static const std::set<std::string> latinLangs = {"en", "es", "fr", "pt", "sv"};
        bool defaultLatinSet = false;
        if (voice.synthesisConfig.languageId && voice.modelConfig.languageIdMap) {
          for (const auto& [code, id] : *voice.modelConfig.languageIdMap) {
            if (id == *voice.synthesisConfig.languageId && latinLangs.count(code)) {
              defaultLatin = code;
              defaultLatinSet = true;
              break;
            }
          }
        }
        // Fallback: pick the first available Latin language by priority
        if (!defaultLatinSet) {
          for (const auto& lang : {"en", "es", "fr", "pt", "sv"}) {
            if (std::find(multiLangs.begin(), multiLangs.end(), lang) != multiLangs.end()) {
              defaultLatin = lang;
              break;
            }
          }
        }

        UnicodeLanguageDetector detector(multiLangs, defaultLatin);
        auto langSegments = detector.segmentText(segment.text);

        // BOS/EOS codepoints to strip from JA segments
        std::set<Phoneme> bosEosTokens = {
          0x5E,    // ^ (BOS)
          0x24,    // $ (EOS)
          0x3F,    // ? (question EOS)
          0xE016,  // ?! (emphatic question)
          0xE017,  // ?. (neutral question)
          0xE018   // ?~ (tag question)
        };

        // Track last EOS for dynamic EOS selection
        Phoneme lastEos = 0x24;  // Default: $

        std::vector<Phoneme> allPhonemes;
        std::vector<ProsodyFeature> allProsody;

        for (const auto& langSeg : langSegments) {
          std::vector<std::vector<Phoneme>> langPhonemes;
          std::vector<std::vector<ProsodyFeature>> langProsody;

          if (langSeg.lang == "ja") {
            // Japanese: use OpenJTalk
            if (voice.session.hasProsodyInput) {
              phonemize_openjtalk_with_prosody(langSeg.text, langPhonemes, langProsody);
            } else {
              phonemize_openjtalk(langSeg.text, langPhonemes);
            }

            // Strip BOS/EOS from JA phonemes
            for (size_t s = 0; s < langPhonemes.size(); s++) {
              for (auto ph : langPhonemes[s]) {
                if (bosEosTokens.count(ph)) {
                  if (ph != 0x5E) {  // Not BOS
                    lastEos = ph;    // Track EOS
                  }
                  continue;  // Skip BOS/EOS
                }
                allPhonemes.push_back(ph);
                if (voice.session.hasProsodyInput && s < langProsody.size()) {
                  // Find matching prosody index (approximate)
                  // JA phonemizer produces 1:1 phoneme:prosody
                }
              }
              // Add prosody for JA phonemes (after stripping)
              if (voice.session.hasProsodyInput && s < langProsody.size()) {
                // We need to rebuild prosody without BOS/EOS entries
                for (size_t pi = 0; pi < langPhonemes[s].size(); pi++) {
                  if (!bosEosTokens.count(langPhonemes[s][pi])) {
                    if (pi < langProsody[s].size()) {
                      allProsody.push_back(langProsody[s][pi]);
                    } else {
                      allProsody.push_back({0, 0, 0});
                    }
                  }
                }
              }
            }
          } else if (langSeg.lang == "es") {
            // Spanish: native rule-based phonemizer
            phonemize_spanish(langSeg.text, langPhonemes);
          } else if (langSeg.lang == "fr") {
            // French: native rule-based phonemizer
            phonemize_french(langSeg.text, langPhonemes);
          } else if (langSeg.lang == "pt") {
            // Portuguese: native rule-based phonemizer
            phonemize_portuguese(langSeg.text, langPhonemes);
          } else if (langSeg.lang == "en") {
            // English: CMU dictionary-based G2P
            static bool warnedNoCmuDict = false;
            if (voice.cmuDict.empty() && !warnedNoCmuDict) {
              spdlog::warn("English CMU dictionary not loaded; English text may not be phonemized correctly");
              warnedNoCmuDict = true;
            }
            phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
            // Check if CMU dict produced any phonemes
            bool hasAnyPhonemes = false;
            for (const auto& s : langPhonemes) {
              if (!s.empty()) { hasAnyPhonemes = true; break; }
            }
            if (!hasAnyPhonemes) {
              spdlog::debug("English segment '{}' has no CMU dict matches; skipping", langSeg.text);
            }
          } else if (langSeg.lang == "zh") {
            // Chinese: pypinyin-based G2P
            static bool warnedNoPinyinDict = false;
            if (voice.pinyinSingleDict.empty() && !warnedNoPinyinDict) {
              spdlog::warn("Chinese pinyin dictionary not loaded; Chinese text may not be phonemized correctly");
              warnedNoPinyinDict = true;
            }
            phonemize_chinese(langSeg.text, langPhonemes,
                              voice.pinyinSingleDict, voice.pinyinPhraseDict);
          } else if (langSeg.lang == "ko") {
            // Korean: Hangul decomposition (no external data needed)
            phonemize_korean(langSeg.text, langPhonemes);
          } else if (langSeg.lang == "sv") {
            // Swedish: native rule-based phonemizer
            phonemize_swedish(langSeg.text, langPhonemes);
          } else {
            spdlog::warn("No native phonemizer for language '{}'; skipping segment", langSeg.lang);
          }

          // Add phonemes from non-JA segment with language-specific prosody
          if (langSeg.lang != "ja") {
            for (const auto& sentence : langPhonemes) {
              if (voice.session.hasProsodyInput) {
                auto sentenceProsody = computeNonJaProsody(sentence, langSeg.lang);
                for (size_t pi = 0; pi < sentence.size(); pi++) {
                  allPhonemes.push_back(sentence[pi]);
                  allProsody.push_back(sentenceProsody[pi]);
                }
              } else {
                for (auto ph : sentence) {
                  allPhonemes.push_back(ph);
                }
              }
            }
          }
        }

        // Detect dominant language and store in result (no side effect on voice).
        if (!langSegments.empty()) {
          auto dominantLang = detectDominantLanguage(segment.text, detector);
          if (voice.modelConfig.languageIdMap &&
              voice.modelConfig.languageIdMap->count(dominantLang) > 0) {
            result.detectedLanguageId =
                voice.modelConfig.languageIdMap->at(dominantLang);
            spdlog::debug("Multilingual: auto-detected dominant language '{}' (lid={})",
                          dominantLang, result.detectedLanguageId.value());
          }
        }

        // Add as a single sentence
        if (!allPhonemes.empty()) {
          segmentPhonemes.push_back(std::move(allPhonemes));
          if (voice.session.hasProsodyInput) {
            segmentProsody.push_back(std::move(allProsody));
          }
        }
      }

      // Add all sentences from this segment
      for (size_t i = 0; i < segmentPhonemes.size(); i++) {
        result.phonemes.push_back(std::move(segmentPhonemes[i]));

        if (useProsody) {
          if (i < segmentProsody.size()) {
            result.prosody.push_back(std::move(segmentProsody[i]));
          } else {
            // Fallback: create zero prosody features
            std::vector<ProsodyFeature> zeroProsody(result.phonemes.back().size(), {0, 0, 0});
            result.prosody.push_back(std::move(zeroProsody));
          }
        }
      }
    }
  }

  // Override prosody features with external data if provided
  if (externalProsody && !externalProsody->empty() && useProsody) {
    result.prosody.clear();
    result.prosody.push_back(*externalProsody);
    spdlog::debug("Using {} external prosody features", externalProsody->size());
  }

} /* phonemizeText */

// Streaming text-to-audio synthesis with reduced latency.
// Splits text into sentences via splitTextToSentences(), synthesizes each
// sentence through textToAudio(), and delivers per-sentence audio via
// chunkCallback.  This eliminates the duplicated phonemization logic that
// previously existed here (including the dead MultilingualPhonemes branch).
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

  // Split text into sentences using the shared helper (M2-1 / M5-2)
  auto sentences = splitTextToSentences(text,
                                        voice.phonemizeConfig.phonemeType,
                                        chunkSize > 0 ? chunkSize : 0);

  spdlog::debug("Split text into {} sentence(s)", sentences.size());

  // Synthesize each sentence through the unified textToAudio() path.
  // textToAudio handles all phoneme types (OpenJTalk, MultilingualPhonemes)
  // correctly, including prosody, language detection, and phoneme silence.
  for (size_t i = 0; i < sentences.size(); ++i) {
    const auto &sentence = sentences[i];
    spdlog::debug("Streaming sentence {}/{}: '{}'", i + 1, sentences.size(), sentence);

    std::vector<int16_t> sentenceAudio;
    SynthesisResult sentenceResult;

    // Synthesize via textToAudio with no audioCallback so that the full
    // sentence audio (including sentence silence) is accumulated in
    // sentenceAudio.
    textToAudio(config, voice, sentence, sentenceAudio, sentenceResult,
                nullptr /* audioCallback */);

    // Accumulate into the full output buffer
    audioBuffer.insert(audioBuffer.end(),
                       sentenceAudio.begin(), sentenceAudio.end());

    // Update cumulative timing
    result.inferSeconds += sentenceResult.inferSeconds;
    result.audioSeconds += sentenceResult.audioSeconds;

    // Deliver sentence audio via callback
    if (chunkCallback && !sentenceAudio.empty()) {
      chunkCallback(sentenceAudio);
    }
  }

  // Calculate final real-time factor
  if (result.audioSeconds > 0) {
    result.realTimeFactor = result.inferSeconds / result.audioSeconds;
  }

  spdlog::debug("Streaming synthesis complete: {} sentence(s), {:.2f}s audio, RTF={:.2f}",
                sentences.size(), result.audioSeconds, result.realTimeFactor);

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

void warmupModel(ModelSession &session, int runs) {
    if (runs <= 0) {
        return;
    }

    try {
        auto startTime = std::chrono::steady_clock::now();
        auto memoryInfo = Ort::MemoryInfo::CreateCpu(
            OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

        // Build dummy inputs: BOS(1) + dummy(8)x98 + EOS(2) = 100 tokens
        constexpr int64_t phonemeLength = 100;

        InferenceInputs dummy;
        dummy.phonemeIds.assign(phonemeLength, 8);
        dummy.phonemeIds[0] = 1;                       // BOS
        dummy.phonemeIds[phonemeLength - 1] = 2;       // EOS
        // noiseScale / lengthScale / noiseW use defaults (0.667, 1.0, 0.8)
        if (session.hasMultiSpeaker) dummy.speakerId = 0;
        if (session.hasLidInput)     dummy.languageId = 0;
        if (session.hasProsodyInput) {
            dummy.prosodyFeatures.assign(phonemeLength * 3, 0);
        }

        // Buffers kept alive across all warmup runs
        std::vector<int64_t> phonemeIdsBuf, phonemeIdLengthsBuf, sidBuf, lidBuf, prosodyBuf;
        std::vector<float> scalesBuf;

        auto [inputTensors, inputNames] = buildInputTensors(
            dummy, session, memoryInfo,
            phonemeIdsBuf, phonemeIdLengthsBuf, scalesBuf,
            sidBuf, lidBuf, prosodyBuf);

        // Output names
        std::vector<const char*> outputNames;
        outputNames.push_back("output");
        if (session.hasDurationOutput) {
            outputNames.push_back("durations");
        }

        // Run warmup
        for (int i = 0; i < runs; i++) {
            auto runStart = std::chrono::steady_clock::now();
            session.onnx.Run(Ort::RunOptions{nullptr},
                             inputNames.data(), inputTensors.data(), inputTensors.size(),
                             outputNames.data(), outputNames.size());
            auto runEnd = std::chrono::steady_clock::now();
            spdlog::debug("Warmup run {}/{} completed in {}ms", i + 1, runs,
                          std::chrono::duration<double, std::milli>(runEnd - runStart).count());
        }

        auto endTime = std::chrono::steady_clock::now();
        auto elapsedMs = std::chrono::duration<double, std::milli>(endTime - startTime).count();
        spdlog::info("Warmup completed ({} runs in {:.0f}ms)", runs, elapsedMs);
    } catch (const std::exception &e) {
        spdlog::warn("Warmup failed (non-fatal): {}", e.what());
    } catch (...) {
        spdlog::warn("Warmup failed (non-fatal): unknown error");
    }
}

} // namespace piper
