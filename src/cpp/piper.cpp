#include <array>
#include <chrono>
#include <cmath>
#include <fstream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <filesystem>
#include <unordered_map>
#include <regex>

#include <onnxruntime_cxx_api.h>
#include <spdlog/spdlog.h>

// Self-contained phoneme ID conversion
#include "phoneme_ids.hpp"

#include "json.hpp"
#include "piper.hpp"
#include "utf8.h"
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

#ifdef USE_ARM64_NEON
#include "audio_neon.hpp"
#endif

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
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
      GraphOptimizationLevel::ORT_ENABLE_ALL);

  // CPU memory arena and memory pattern are enabled by default (ORT defaults).
  // This trades higher memory usage for ~10-15% faster inference.
  // To reduce memory in constrained environments, uncomment:
  // session.options.DisableCpuMemArena();
  // session.options.DisableMemPattern();

  // Slows down performance very slightly
  // session.options.SetExecutionMode(ExecutionMode::ORT_PARALLEL);
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
  // Dictionary files are expected next to the model file
  std::string modelDir = std::filesystem::path(modelPath).parent_path().string();

  // English: CMU dictionary
  std::string cmuPath = modelDir + "/cmudict_data.json";
  if (std::filesystem::exists(cmuPath)) {
    if (loadCmuDict(cmuPath, voice.cmuDict)) {
      spdlog::info("Loaded CMU dictionary ({} entries) from {}", voice.cmuDict.size(), cmuPath);
    }
  }

  // Chinese: pypinyin dictionaries
  std::string pinyinSinglePath = modelDir + "/pinyin_single.json";
  std::string pinyinPhrasePath = modelDir + "/pinyin_phrases.json";
  if (std::filesystem::exists(pinyinSinglePath)) {
    if (loadPinyinDicts(pinyinSinglePath, pinyinPhrasePath,
                        voice.pinyinSingleDict, voice.pinyinPhraseDict)) {
      spdlog::info("Loaded pinyin dictionaries (single={}, phrases={}) from {}",
                   voice.pinyinSingleDict.size(), voice.pinyinPhraseDict.size(), modelDir);
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

  // Add language id for multilingual models
  // ONNX input order: ... -> sid -> lid -> prosody_features
  // NOTE: Must be declared outside "if" to prevent deallocation before Run().
  auto lid = synthesisConfig.languageId.value_or(0);
  if (voice && (lid < 0 || lid >= voice->modelConfig.numLanguages)) {
    spdlog::warn("Language ID {} out of range [0, {}), using 0",
                 lid, voice->modelConfig.numLanguages);
    lid = 0;
  }
  std::vector<int64_t> languageId{(int64_t)lid};
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

  // Save the original language ID to detect if the user explicitly set it.
  // This prevents dominant-language auto-detection from overwriting an
  // explicit user choice (M3 fix).
  auto originalLanguageId = voice.synthesisConfig.languageId;

  std::size_t sentenceSilenceSamples = 0;
  if (voice.synthesisConfig.sentenceSilenceSeconds > 0) {
    sentenceSilenceSamples = (std::size_t)(
        voice.synthesisConfig.sentenceSilenceSeconds *
        voice.synthesisConfig.sampleRate * voice.synthesisConfig.channels);
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

        // Determine default Latin language
        std::string defaultLatin = "en";
        for (const auto& lang : {"en", "es", "pt", "fr"}) {
          if (std::find(multiLangs.begin(), multiLangs.end(), lang) != multiLangs.end()) {
            defaultLatin = lang;
            break;
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
          } else if (langSeg.lang == "en" && !voice.cmuDict.empty()) {
            // English: CMU dictionary-based G2P
            phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
            // Check if CMU dict produced any phonemes
            bool hasAnyPhonemes = false;
            for (const auto& s : langPhonemes) {
              if (!s.empty()) { hasAnyPhonemes = true; break; }
            }
            if (!hasAnyPhonemes) {
              spdlog::debug("English segment '{}' has no CMU dict matches; skipping", langSeg.text);
            }
          } else if (langSeg.lang == "zh" && !voice.pinyinSingleDict.empty()) {
            // Chinese: pypinyin-based G2P
            phonemize_chinese(langSeg.text, langPhonemes,
                              voice.pinyinSingleDict, voice.pinyinPhraseDict);
          } else if (langSeg.lang == "ko") {
            // Korean: Hangul decomposition (no external data needed)
            phonemize_korean(langSeg.text, langPhonemes);
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

        // Set dominant language for lid, but only if the user did not
        // explicitly set a language ID before this call (M3 fix).
        // originalLanguageId was captured at the start of textToAudio().
        // If the current value still matches the original, auto-detect is safe.
        if (!langSegments.empty() &&
            voice.synthesisConfig.languageId == originalLanguageId) {
          auto dominantLang = detectDominantLanguage(segment.text, detector);
          if (voice.modelConfig.languageIdMap &&
              voice.modelConfig.languageIdMap->count(dominantLang) > 0) {
            voice.synthesisConfig.languageId =
                (*voice.modelConfig.languageIdMap)[dominantLang];
            spdlog::debug("Multilingual: auto-detected dominant language '{}' (lid={})",
                          dominantLang, voice.synthesisConfig.languageId.value());
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

    if (usesOpenJTalk(voice.phonemizeConfig.phonemeType)) {
      // Japanese/Multilingual OpenJTalk phonemizer
      if (useProsody) {
        phonemize_openjtalk_with_prosody(chunk, chunkSentences, chunkProsody);
      } else {
        phonemize_openjtalk(chunk, chunkSentences);
      }
    } else if (voice.phonemizeConfig.phonemeType == MultilingualPhonemes) {
      // TODO: Implement proper multilingual streaming dispatch
      // For now, fall back to OpenJTalk for multilingual streaming
      spdlog::warn("Multilingual streaming not yet implemented; falling back to OpenJTalk for chunk");
      phonemize_openjtalk(chunk, chunkSentences);
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
    result.realTimeFactor = result.inferSeconds / result.audioSeconds;
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
