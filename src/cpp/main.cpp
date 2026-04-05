#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <cstdlib>
#include <locale>

#ifdef _MSC_VER
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#include <shellapi.h>  // CommandLineToArgvW
#endif

#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

#include <onnxruntime_cxx_api.h>

#include "json.hpp"
#include "piper.hpp"
#include "phoneme_parser.hpp"
#include "custom_dictionary.hpp"
#include "model_manager.hpp"

using namespace std;
using json = nlohmann::json;

enum OutputType { OUTPUT_FILE, OUTPUT_DIRECTORY, OUTPUT_STDOUT, OUTPUT_RAW };

struct RunConfig {
  // Path to .onnx voice file
  filesystem::path modelPath;

  // Path to JSON voice config file
  filesystem::path modelConfigPath;

  // Test mode - skip ONNX runtime for CI testing
  bool testMode = false;

  // Skip model warmup (faster startup, slower first inference)
  bool noWarmup = false;

  // Type of output to produce.
  // Default is to write a WAV file in the current directory.
  OutputType outputType = OUTPUT_DIRECTORY;

  // Path for output
  optional<filesystem::path> outputPath = filesystem::path(".");

  // Numerical id of the default speaker (multi-speaker voices)
  optional<piper::SpeakerId> speakerId;

  // Language code or numerical id (multi-language voices)
  optional<string> language;

  // Amount of noise to add during audio generation
  optional<float> noiseScale;

  // Speed of speaking (1 = normal, < 1 is faster, > 1 is slower)
  optional<float> lengthScale;

  // Variation in phoneme lengths
  optional<float> noiseW;

  // Seconds of silence to add after each sentence
  optional<float> sentenceSilenceSeconds;

  // stdin input is lines of JSON instead of text with format:
  // {
  //   "text": str,               (required)
  //   "speaker_id": int,         (optional)
  //   "speaker": str,            (optional)
  //   "output_file": str,        (optional)
  //   "prosody_features": [[a1,a2,a3], ...],  (optional)
  // }
  bool jsonInput = false;

  // Seconds of extra silence to insert after a single phoneme
  optional<std::map<piper::Phoneme, float>> phonemeSilenceSeconds;

  // true to use CUDA execution provider
  bool useCuda = false;

  // GPU device ID for CUDA execution provider (default: 0)
  int gpuDeviceId = 0;

  // true to interpret input as raw phonemes instead of text
  bool rawPhonemes = false;

  // true to use streaming mode for reduced latency
  bool streamingMode = false;

  // Path for outputting phoneme timing information
  optional<filesystem::path> outputTimingPath;

  // Format for timing output (json or tsv)
  string timingFormat = "json";

  // Format constants
  static const string FORMAT_JSON;
  static const string FORMAT_TSV;

  // Paths to custom dictionary files
  vector<filesystem::path> customDictPaths;

  // Direct text input (no stdin required)
  optional<string> textInput;

  // Model management
  bool listModels = false;
  optional<string> listModelsLanguage;
  optional<string> downloadModelName;
  optional<filesystem::path> modelDir;
};

// Define static constants
const string RunConfig::FORMAT_JSON = "json";
const string RunConfig::FORMAT_TSV = "tsv";

void parseArgs(int argc, char *argv[], RunConfig &runConfig);
void rawOutputProc(vector<int16_t> &sharedAudioBuffer, mutex &mutAudio,
                   condition_variable &cvAudio, bool &audioReady,
                   bool &audioFinished);
void processLine(string line, RunConfig &runConfig, piper::PiperConfig &piperConfig,
                 piper::Voice &voice, piper::SynthesisResult &result,
                 bool jsonInput, std::unique_ptr<piper::CustomDictionary> &customDict);

// ----------------------------------------------------------------------------

int main(int argc, char *argv[]) {

#ifdef _WIN32
  // On Windows, argv is in the system ANSI code page (e.g. CP932 for Japanese).
  // Re-read arguments as UTF-16 via GetCommandLineW() and convert to UTF-8
  // so that --text "日本語" works correctly.
  std::vector<std::string> utf8Args;
  std::vector<char*> utf8Argv;
  {
    int wargc = 0;
    LPWSTR* wargv = CommandLineToArgvW(GetCommandLineW(), &wargc);
    if (wargv) {
      utf8Args.reserve(wargc);
      for (int i = 0; i < wargc; i++) {
        int len = WideCharToMultiByte(CP_UTF8, 0, wargv[i], -1, nullptr, 0, nullptr, nullptr);
        std::string s(len - 1, '\0');
        WideCharToMultiByte(CP_UTF8, 0, wargv[i], -1, &s[0], len, nullptr, nullptr);
        utf8Args.push_back(std::move(s));
      }
      LocalFree(wargv);
      utf8Argv.reserve(wargc + 1);
      for (auto& s : utf8Args) {
        utf8Argv.push_back(&s[0]);
      }
      utf8Argv.push_back(nullptr);
      argc = wargc;
      argv = utf8Argv.data();
    }
  }
#endif

  spdlog::set_default_logger(spdlog::stderr_color_st("piper"));

  // Set locale for proper UTF-8 handling
  try {
    std::locale utf8_locale("en_US.UTF-8");
    std::locale::global(utf8_locale);
    std::cin.imbue(utf8_locale);
    std::cout.imbue(utf8_locale);
  } catch (const std::runtime_error& e) {
    spdlog::warn("Unable to set UTF-8 locale: {}", e.what());
    // Fallback to default locale
    std::locale::global(std::locale());
    std::cin.imbue(std::locale());
    std::cout.imbue(std::locale());
  }

#ifdef _WIN32
  // Initialize Windows subsystems early
  SetConsoleCP(CP_UTF8);       // Set input console to UTF-8
  SetConsoleOutputCP(CP_UTF8);
  
  // Enhanced DLL loading for Windows
  wchar_t exePathW[MAX_PATH];
  GetModuleFileNameW(nullptr, exePathW, MAX_PATH);
  std::filesystem::path exeDir = std::filesystem::path(exePathW).parent_path();
  
  // Try multiple DLL search paths
  std::vector<std::filesystem::path> dllPaths = {
    exeDir,                          // Same directory as exe
    exeDir / "lib",                  // lib subdirectory
    exeDir.parent_path() / "lib",    // ../lib relative to exe
    exeDir / "bin"                   // bin subdirectory (for CI/CD)
  };
  
  // Use AddDllDirectory for Windows 7+ if available
  typedef DLL_DIRECTORY_COOKIE (WINAPI *AddDllDirectoryFunc)(PCWSTR);
  typedef BOOL (WINAPI *SetDefaultDllDirectoriesFunc)(DWORD);
  
  HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
  auto pAddDllDirectory = (AddDllDirectoryFunc)GetProcAddress(kernel32, "AddDllDirectory");
  auto pSetDefaultDllDirectories = (SetDefaultDllDirectoriesFunc)GetProcAddress(kernel32, "SetDefaultDllDirectories");
  
  if (pAddDllDirectory && pSetDefaultDllDirectories) {
    // Windows 7+ approach: Use AddDllDirectory for multiple paths
    pSetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_USER_DIRS);
    
    for (const auto& path : dllPaths) {
      if (std::filesystem::exists(path)) {
        pAddDllDirectory(path.c_str());
        spdlog::debug("Added DLL directory: {}", path.string());
      }
    }
  } else {
    // Windows XP/Vista fallback: Use SetDllDirectory
    for (const auto& path : dllPaths) {
      if (std::filesystem::exists(path)) {
        SetDllDirectoryW(path.c_str());
        spdlog::debug("Set DLL directory: {}", path.string());
        break;  // SetDllDirectory only supports one path
      }
    }
  }
  
  // Pre-load critical DLLs to ensure proper loading order
  std::vector<std::wstring> criticalDlls = {
    L"onnxruntime.dll",
    L"onnxruntime_providers_shared.dll"
  };
  
  for (const auto& dllName : criticalDlls) {
    HMODULE hDll = LoadLibraryW(dllName.c_str());
    if (hDll) {
      spdlog::debug("Pre-loaded DLL: {}", std::string(dllName.begin(), dllName.end()));
    } else {
      DWORD error = GetLastError();
      spdlog::warn("Failed to pre-load DLL: {} (error: {})", 
                   std::string(dllName.begin(), dllName.end()), error);
    }
  }
#endif

  RunConfig runConfig;
  parseArgs(argc, argv, runConfig);

  // Handle --list-models (early exit, no model loading needed)
  if (runConfig.listModels) {
    piper::listModels(runConfig.listModelsLanguage.value_or(""));
    return EXIT_SUCCESS;
  }

  // Handle --download-model (early exit, no model loading needed)
  if (runConfig.downloadModelName) {
    auto modelDir = runConfig.modelDir.value_or(piper::getDefaultModelDir());
    bool success = piper::downloadModel(runConfig.downloadModelName.value(), modelDir);
    return success ? EXIT_SUCCESS : EXIT_FAILURE;
  }

  piper::PiperConfig piperConfig;
  piper::Voice voice;

  spdlog::debug("Model path: {}", runConfig.modelPath.string());
  spdlog::debug("Model config path: {}", runConfig.modelConfigPath.string());
  spdlog::debug("Loading voice from {} (config={})",
                runConfig.modelPath.string(),
                runConfig.modelConfigPath.string());

  auto startTime = chrono::steady_clock::now();
  std::string provider = runConfig.useCuda ? "cuda" : "cpu";
  loadVoice(piperConfig, runConfig.modelPath.string(),
            runConfig.modelConfigPath.string(), voice, runConfig.speakerId,
            provider, runConfig.gpuDeviceId);
  auto endTime = chrono::steady_clock::now();
  spdlog::info("Loaded voice in {} second(s)",
               chrono::duration<double>(endTime - startTime).count());

  // Warmup
  if (!runConfig.noWarmup && !runConfig.testMode) {
      piper::warmupModel(voice.session);
  }

  // Resolve --language to a numeric language ID
  if (runConfig.language) {
    std::string langStr = runConfig.language.value();

    // Try as a numeric ID first
    try {
      piper::LanguageId lid = std::stol(langStr);
      if (lid < 0 || lid >= voice.modelConfig.numLanguages) {
        spdlog::warn("Language ID {} out of range [0, {}), using default (0)",
                     lid, voice.modelConfig.numLanguages);
        voice.synthesisConfig.languageId = 0;
      } else {
        voice.synthesisConfig.languageId = lid;
        spdlog::info("Using language ID: {}", lid);
      }
    } catch (const std::exception&) {
      // Try as a language code (e.g. "ja", "en")
      if (voice.modelConfig.languageIdMap &&
          voice.modelConfig.languageIdMap->count(langStr) > 0) {
        voice.synthesisConfig.languageId =
            (*voice.modelConfig.languageIdMap)[langStr];
        spdlog::info("Resolved language '{}' to ID {}",
                     langStr, voice.synthesisConfig.languageId.value());
      } else {
        spdlog::warn("Unknown language '{}', using default (0)", langStr);
        voice.synthesisConfig.languageId = 0;
      }
    }
  }

  // Warn if languageId is set but model has no lid input
  if (voice.synthesisConfig.languageId.has_value() &&
      voice.synthesisConfig.languageId.value() != 0 &&
      !voice.session.hasLidInput) {
    spdlog::warn("Model does not support language selection (no lid input), "
                 "language_id={} will be ignored",
                 voice.synthesisConfig.languageId.value());
  }

  try {
    piper::initialize(piperConfig);
  } catch (const std::exception& e) {
    spdlog::error("Failed to initialize piper: {}", e.what());
    return EXIT_FAILURE;
  }

  // Scales
  if (runConfig.noiseScale) {
    voice.synthesisConfig.noiseScale = runConfig.noiseScale.value();
  }

  if (runConfig.lengthScale) {
    voice.synthesisConfig.lengthScale = runConfig.lengthScale.value();
  }

  if (runConfig.noiseW) {
    voice.synthesisConfig.noiseW = runConfig.noiseW.value();
  }

  if (runConfig.sentenceSilenceSeconds) {
    voice.synthesisConfig.sentenceSilenceSeconds =
        runConfig.sentenceSilenceSeconds.value();
  }

  if (runConfig.phonemeSilenceSeconds) {
    if (!voice.synthesisConfig.phonemeSilenceSeconds) {
      // Overwrite
      voice.synthesisConfig.phonemeSilenceSeconds =
          runConfig.phonemeSilenceSeconds;
    } else {
      // Merge
      for (const auto &[phoneme, silenceSeconds] :
           *runConfig.phonemeSilenceSeconds) {
        voice.synthesisConfig.phonemeSilenceSeconds->try_emplace(
            phoneme, silenceSeconds);
      }
    }

  } // if phonemeSilenceSeconds

  // カスタム辞書の初期化
  std::unique_ptr<piper::CustomDictionary> customDict;
  if (!runConfig.customDictPaths.empty()) {
    customDict = std::make_unique<piper::CustomDictionary>();
    for (const auto& dictPath : runConfig.customDictPaths) {
      try {
        customDict->loadDictionary(dictPath.string());
        spdlog::info("Loaded custom dictionary: {}", dictPath.string());
      } catch (const std::exception& e) {
        spdlog::error("Failed to load custom dictionary {}: {}", 
                      dictPath.string(), e.what());
      }
    }
  }

  if (runConfig.outputType == OUTPUT_DIRECTORY) {
    runConfig.outputPath = filesystem::absolute(runConfig.outputPath.value());
    spdlog::info("Output directory: {}", runConfig.outputPath.value().string());
  }

  string line;
  piper::SynthesisResult result;

  if (runConfig.textInput) {
    // Single-shot mode: process text from --text and exit
    line = runConfig.textInput.value();
    processLine(line, runConfig, piperConfig, voice, result, false, customDict);
  } else {
    // Interactive mode: read lines from stdin
    while (getline(cin, line)) {
      processLine(line, runConfig, piperConfig, voice, result, runConfig.jsonInput, customDict);
    }
  }

  piper::terminate(piperConfig);

  return EXIT_SUCCESS;
}

// ----------------------------------------------------------------------------

void rawOutputProc(vector<int16_t> &sharedAudioBuffer, mutex &mutAudio,
                   condition_variable &cvAudio, bool &audioReady,
                   bool &audioFinished) {
  vector<int16_t> internalAudioBuffer;
  while (true) {
    {
      unique_lock lockAudio{mutAudio};
      cvAudio.wait(lockAudio, [&audioReady] { return audioReady; });

      if (sharedAudioBuffer.empty() && audioFinished) {
        break;
      }

      copy(sharedAudioBuffer.begin(), sharedAudioBuffer.end(),
           back_inserter(internalAudioBuffer));

      sharedAudioBuffer.clear();

      if (!audioFinished) {
        audioReady = false;
      }
    }

    cout.write((const char *)internalAudioBuffer.data(),
               sizeof(int16_t) * internalAudioBuffer.size());
    cout.flush();
    internalAudioBuffer.clear();
  }

} // rawOutputProc

// ----------------------------------------------------------------------------

void processLine(string line, RunConfig &runConfig, piper::PiperConfig &piperConfig,
                 piper::Voice &voice, piper::SynthesisResult &result,
                 bool jsonInput, std::unique_ptr<piper::CustomDictionary> &customDict) {
  auto outputType = runConfig.outputType;
  auto speakerId = voice.synthesisConfig.speakerId;
  auto languageId = voice.synthesisConfig.languageId;
  std::optional<filesystem::path> maybeOutputPath = runConfig.outputPath;

  // External prosody features (from JSON input)
  std::vector<piper::ProsodyFeature> externalProsody;
  const std::vector<piper::ProsodyFeature> *externalProsodyPtr = nullptr;

  if (jsonInput) {
    // Each line is a JSON object
    json lineRoot = json::parse(line);

    // Text is required
    line = lineRoot["text"].get<std::string>();

    if (lineRoot.contains("output_file")) {
      // Override output WAV file path
      outputType = OUTPUT_FILE;
      maybeOutputPath =
          filesystem::path(lineRoot["output_file"].get<std::string>());
    }

    if (lineRoot.contains("speaker_id")) {
      // Override speaker id
      voice.synthesisConfig.speakerId =
          lineRoot["speaker_id"].get<piper::SpeakerId>();
    } else if (lineRoot.contains("speaker")) {
      // Resolve to id using speaker id map
      auto speakerName = lineRoot["speaker"].get<std::string>();
      if ((voice.modelConfig.speakerIdMap) &&
          (voice.modelConfig.speakerIdMap->count(speakerName) > 0)) {
        voice.synthesisConfig.speakerId =
            (*voice.modelConfig.speakerIdMap)[speakerName];
      } else {
        spdlog::warn("No speaker named: {}", speakerName);
      }
    }

    if (lineRoot.contains("language_id")) {
      auto lid = lineRoot["language_id"].get<piper::LanguageId>();
      if (lid < 0 || lid >= voice.modelConfig.numLanguages) {
        spdlog::warn("JSON language_id {} out of range [0, {}), using default (0)",
                     lid, voice.modelConfig.numLanguages);
        voice.synthesisConfig.languageId = 0;
      } else {
        voice.synthesisConfig.languageId = lid;
      }
    } else if (lineRoot.contains("language")) {
      auto langCode = lineRoot["language"].get<std::string>();
      if (voice.modelConfig.languageIdMap &&
          voice.modelConfig.languageIdMap->count(langCode) > 0) {
        voice.synthesisConfig.languageId =
            (*voice.modelConfig.languageIdMap)[langCode];
      } else {
        spdlog::warn("Unknown language code in JSON: '{}', using default (0)", langCode);
        voice.synthesisConfig.languageId = 0;
      }
    }

    if (lineRoot.contains("prosody_features")) {
      for (const auto& item : lineRoot["prosody_features"]) {
        piper::ProsodyFeature pf;
        pf.a1 = item[0].get<int>();
        pf.a2 = item[1].get<int>();
        pf.a3 = item[2].get<int>();
        externalProsody.push_back(pf);
      }
      externalProsodyPtr = &externalProsody;
    }
  }

  // Apply custom dictionary
  if (customDict && !line.empty()) {
    line = customDict->applyToText(line);
  }

  // Timestamp is used for path to output WAV file
  const auto now = chrono::system_clock::now();
  const auto timestamp =
      chrono::duration_cast<chrono::nanoseconds>(now.time_since_epoch())
          .count();

  if (outputType == OUTPUT_DIRECTORY) {
    // In --text mode, use "output.wav" instead of timestamp
    stringstream outputName;
    if (runConfig.textInput) {
      outputName << "output.wav";
    } else {
      outputName << timestamp << ".wav";
    }
    filesystem::path outputPath = runConfig.outputPath.value();
    outputPath.append(outputName.str());

    // Output audio to automatically-named WAV file in a directory
    ofstream audioFile(outputPath.string(), ios::binary);
    if (runConfig.rawPhonemes) {
      // Parse raw phonemes from input
      auto phonemeType = static_cast<piper::PhonemeTypeInt>(voice.phonemizeConfig.phonemeType);
      auto phonemes = piper::parsePhonemeString(line, phonemeType);
      piper::phonemesToWavFile(piperConfig, voice, phonemes, audioFile, result);
    } else {
      piper::textToWavFile(piperConfig, voice, line, audioFile, result, externalProsodyPtr);
    }
    cout << outputPath.string() << endl;
  } else if (outputType == OUTPUT_FILE) {
    if (!maybeOutputPath || maybeOutputPath->empty()) {
      throw runtime_error("No output path provided");
    }

    filesystem::path outputPath = maybeOutputPath.value();

    if (!jsonInput && !runConfig.textInput) {
      // Read all of standard input before synthesizing.
      // Otherwise, we would overwrite the output file for each line.
      stringstream text;
      text << line;
      while (getline(cin, line)) {
        text << " " << line;
      }

      line = text.str();
    }

    // Output audio to WAV file
    ofstream audioFile(outputPath.string(), ios::binary);
    if (runConfig.rawPhonemes) {
      // Parse raw phonemes from input
      auto phonemeType = static_cast<piper::PhonemeTypeInt>(voice.phonemizeConfig.phonemeType);
      auto phonemes = piper::parsePhonemeString(line, phonemeType);
      piper::phonemesToWavFile(piperConfig, voice, phonemes, audioFile, result);
    } else {
      piper::textToWavFile(piperConfig, voice, line, audioFile, result, externalProsodyPtr);
    }
    cout << outputPath.string() << endl;
  } else if (outputType == OUTPUT_STDOUT) {
    // Output WAV to stdout
    if (runConfig.rawPhonemes) {
      // Parse raw phonemes from input
      auto phonemeType = static_cast<piper::PhonemeTypeInt>(voice.phonemizeConfig.phonemeType);
      auto phonemes = piper::parsePhonemeString(line, phonemeType);
      piper::phonemesToWavFile(piperConfig, voice, phonemes, cout, result);
    } else {
      piper::textToWavFile(piperConfig, voice, line, cout, result, externalProsodyPtr);
    }
  } else if (outputType == OUTPUT_RAW) {
    // Raw output to stdout
    mutex mutAudio;
    condition_variable cvAudio;
    bool audioReady = false;
    bool audioFinished = false;
    vector<int16_t> audioBuffer;
    vector<int16_t> sharedAudioBuffer;

#ifdef _WIN32
    // Needed on Windows to avoid terminal conversions
    setmode(fileno(stdout), O_BINARY);
    setmode(fileno(stdin), O_BINARY);
#endif

    thread rawOutputThread(rawOutputProc, ref(sharedAudioBuffer),
                           ref(mutAudio), ref(cvAudio), ref(audioReady),
                           ref(audioFinished));
    if (runConfig.streamingMode) {
      // Streaming mode - use chunk callback
      spdlog::info("Using streaming mode for synthesis");
      auto chunkCallback = [&sharedAudioBuffer, &mutAudio, &cvAudio, &audioReady](const std::vector<int16_t>& chunk) {
        // Signal thread that audio chunk is ready
        {
          unique_lock lockAudio(mutAudio);
          copy(chunk.begin(), chunk.end(), back_inserter(sharedAudioBuffer));
          audioReady = true;
          cvAudio.notify_one();
        }
      };

      if (runConfig.rawPhonemes) {
        // Use streaming synthesis for raw phonemes
        auto phonemeType = static_cast<piper::PhonemeTypeInt>(voice.phonemizeConfig.phonemeType);
        auto phonemes = piper::parsePhonemeString(line, phonemeType);
        piper::phonemesToAudioStreaming(piperConfig, voice, phonemes, audioBuffer, result, chunkCallback);
      } else {
        // Use streaming synthesis for text
        piper::textToAudioStreaming(piperConfig, voice, line, audioBuffer, result, chunkCallback);
      }
    } else {
      // Regular mode - buffer all audio before output
      auto audioCallback = [&audioBuffer, &sharedAudioBuffer, &mutAudio,
                            &cvAudio, &audioReady]() {
        // Signal thread that audio is ready
        {
          unique_lock lockAudio(mutAudio);
          copy(audioBuffer.begin(), audioBuffer.end(),
               back_inserter(sharedAudioBuffer));
          audioReady = true;
          cvAudio.notify_one();
        }
      };

      if (runConfig.rawPhonemes) {
        // Parse raw phonemes from input
        auto phonemeType = static_cast<piper::PhonemeTypeInt>(voice.phonemizeConfig.phonemeType);
        auto phonemes = piper::parsePhonemeString(line, phonemeType);
        piper::phonemesToAudio(piperConfig, voice, phonemes, audioBuffer, result, audioCallback);
      } else {
        piper::textToAudio(piperConfig, voice, line, audioBuffer, result,
                           audioCallback, externalProsodyPtr);
      }
    }

    // Signal thread that there is no more audio
    {
      unique_lock lockAudio(mutAudio);
      audioReady = true;
      audioFinished = true;
      cvAudio.notify_one();
    }

    // Wait for audio output to finish
    spdlog::info("Waiting for audio to finish playing...");
    rawOutputThread.join();
  }

  spdlog::info("Real-time factor: {} (infer={} sec, audio={} sec)",
               result.realTimeFactor, result.inferSeconds,
               result.audioSeconds);

  // Output phoneme timing information if requested
  if (runConfig.outputTimingPath && result.hasTimingInfo) {
    ofstream timingFile(runConfig.outputTimingPath.value());
    if (timingFile.is_open()) {
      if (runConfig.timingFormat == RunConfig::FORMAT_JSON) {
        piper::outputTimingsAsJSON(result.phonemeTimings, timingFile, line,
                                   voice.synthesisConfig.sampleRate);
      } else if (runConfig.timingFormat == RunConfig::FORMAT_TSV) {
        piper::outputTimingsAsTSV(result.phonemeTimings, timingFile);
      }
      timingFile.close();
      spdlog::info("Wrote phoneme timing to {}", runConfig.outputTimingPath.value().string());
    } else {
      spdlog::error("Failed to open timing output file: {}",
                    runConfig.outputTimingPath.value().string());
    }
  }

  // Restore config (--json-input)
  voice.synthesisConfig.speakerId = speakerId;
  voice.synthesisConfig.languageId = languageId;

} // processLine

// ----------------------------------------------------------------------------

void printUsage(char *argv[]) {
  cerr << endl;
  cerr << "usage: " << argv[0] << " [options]" << endl;
  cerr << endl;
  cerr << "options:" << endl;
  cerr << "   -h        --help              show this message and exit" << endl;
  cerr << "   -m  FILE  --model       FILE  path to onnx model file" << endl;
  cerr << "   -c  FILE  --config      FILE  path to model config file "
          "(default: model path + .json, fallback: config.json in model dir)"
       << endl;
  cerr << "   -t  TEXT  --text        TEXT  text to synthesize (no stdin required)" << endl;
  cerr << "   -f  FILE  --output_file FILE  path to output WAV file ('-' for "
          "stdout)"
       << endl;
  cerr << "   -d  DIR   --output_dir  DIR   path to output directory (default: "
          "cwd)"
       << endl;
  cerr << "   --output_raw                  output raw audio to stdout as it "
          "becomes available"
       << endl;
  cerr << "   -s  NUM   --speaker     NUM   id of speaker (default: 0)" << endl;
  cerr << "   -l  CODE  --language    CODE  language code or id (default: auto)" << endl;
  cerr << "   --noise_scale           NUM   generator noise (default: 0.667)"
       << endl;
  cerr << "   --length_scale          NUM   phoneme length (default: 1.0)"
       << endl;
  cerr << "   --noise_w               NUM   phoneme width noise (default: 0.8)"
       << endl;
  cerr << "   --sentence_silence      NUM   seconds of silence after each "
          "sentence (default: 0.2)"
       << endl;
  cerr << "   --phoneme_silence <phoneme> <seconds>  Set silence for a specific phoneme" << endl;
  cerr << "   --custom-dict       FILE       path to custom dictionary file(s), "
          "comma-separated"
       << endl;
  cerr << endl;
  cerr << "   Phoneme input: Use [[ phonemes ]] notation to specify exact pronunciation" << endl;
  cerr << "                  Example: echo \"Hello [[ h ə l oʊ ]] world\" | piper ..." << endl;
  cerr << endl;
  cerr << "   --json-input                  stdin input is lines of JSON "
          "instead of plain text"
       << endl;
  cerr << "   --use-cuda                    use CUDA execution provider"
       << endl;
  cerr << "   --gpu-device-id         NUM   GPU device ID for CUDA (default: 0)"
       << endl;
  cerr << "   --raw-phonemes                interpret input as raw phonemes (space-separated)"
       << endl;
  cerr << "   --streaming                   use streaming mode for reduced latency"
       << endl;
  cerr << "   --output-timing         FILE  output phoneme timing to FILE"
       << endl;
  cerr << "   --timing-format         FMT   timing output format: json|tsv (default: json)"
       << endl;
  cerr << "   --list-models      [LANG]     list available voice models" << endl;
  cerr << "   --download-model   NAME       download a voice model" << endl;
  cerr << "   --model-dir        DIR        directory for downloaded models" << endl;
  cerr << endl;
  cerr << "   --no-warmup                   skip model warmup (faster startup, slower "
          "first inference)"
       << endl;
  cerr << "   --debug                       print DEBUG messages to the console"
       << endl;
  cerr << "   -q       --quiet              disable logging" << endl;
  cerr << endl;
  cerr << "environment variables:" << endl;
  cerr << "   PIPER_DEFAULT_MODEL           default model path (if --model not specified)" << endl;
  cerr << "   PIPER_DEFAULT_CONFIG          default config file path" << endl;
  cerr << "   PIPER_MODEL_DIR               default model directory (if --model-dir not specified)" << endl;
  cerr << "   PIPER_GPU_DEVICE_ID           GPU device ID for CUDA" << endl;
  cerr << endl;
}

void ensureArg(int argc, char *argv[], int argi) {
  if ((argi + 1) >= argc) {
    printUsage(argv);
    exit(EXIT_FAILURE);
  }
}

// Parse command-line arguments
void parseArgs(int argc, char *argv[], RunConfig &runConfig) {
  optional<filesystem::path> modelConfigPath;

  // Check for GPU device ID environment variable
  const char* gpuDeviceEnv = std::getenv("PIPER_GPU_DEVICE_ID");
  if (gpuDeviceEnv != nullptr) {
    try {
      runConfig.gpuDeviceId = std::stoi(gpuDeviceEnv);
      spdlog::debug("GPU device ID set from environment: {}", runConfig.gpuDeviceId);
    } catch (const std::exception& e) {
      spdlog::warn("Invalid PIPER_GPU_DEVICE_ID environment variable: {}", gpuDeviceEnv);
    }
  }

  // Check for default model path environment variable
  const char* defaultModelEnv = std::getenv("PIPER_DEFAULT_MODEL");
  if (defaultModelEnv != nullptr) {
    runConfig.modelPath = filesystem::path(defaultModelEnv);
    spdlog::debug("Default model path set from environment: {}", runConfig.modelPath.string());
  }

  // Check for default config path environment variable
  const char* defaultConfigEnv = std::getenv("PIPER_DEFAULT_CONFIG");
  if (defaultConfigEnv != nullptr) {
    modelConfigPath = filesystem::path(defaultConfigEnv);
    spdlog::debug("Default config path set from environment: {}", modelConfigPath.value().string());
  }

  // Check for model directory environment variable
  const char* modelDirEnv = std::getenv("PIPER_MODEL_DIR");
  if (modelDirEnv != nullptr) {
    runConfig.modelDir = filesystem::path(modelDirEnv);
    spdlog::debug("Model directory set from environment: {}", runConfig.modelDir.value().string());
  }

  for (int i = 1; i < argc; i++) {
    std::string arg = argv[i];

    if (arg == "-m" || arg == "--model") {
      ensureArg(argc, argv, i);
      runConfig.modelPath = filesystem::path(argv[++i]);
    } else if (arg == "-c" || arg == "--config") {
      ensureArg(argc, argv, i);
      modelConfigPath = filesystem::path(argv[++i]);
    } else if (arg == "-f" || arg == "--output_file" ||
               arg == "--output-file") {
      ensureArg(argc, argv, i);
      std::string filePath = argv[++i];
      if (filePath == "-") {
        runConfig.outputType = OUTPUT_STDOUT;
        runConfig.outputPath = nullopt;
      } else {
        runConfig.outputType = OUTPUT_FILE;
        runConfig.outputPath = filesystem::path(filePath);
      }
    } else if (arg == "-d" || arg == "--output_dir" || arg == "output-dir") {
      ensureArg(argc, argv, i);
      runConfig.outputType = OUTPUT_DIRECTORY;
      runConfig.outputPath = filesystem::path(argv[++i]);
    } else if (arg == "--output_raw" || arg == "--output-raw") {
      runConfig.outputType = OUTPUT_RAW;
    } else if (arg == "-s" || arg == "--speaker") {
      ensureArg(argc, argv, i);
      runConfig.speakerId = (piper::SpeakerId)stol(argv[++i]);
    } else if (arg == "-l" || arg == "--language") {
      ensureArg(argc, argv, i);
      runConfig.language = argv[++i];
    } else if (arg == "--noise_scale" || arg == "--noise-scale") {
      ensureArg(argc, argv, i);
      runConfig.noiseScale = stof(argv[++i]);
    } else if (arg == "--length_scale" || arg == "--length-scale") {
      ensureArg(argc, argv, i);
      runConfig.lengthScale = stof(argv[++i]);
    } else if (arg == "--noise_w" || arg == "--noise-w") {
      ensureArg(argc, argv, i);
      runConfig.noiseW = stof(argv[++i]);
    } else if (arg == "--sentence_silence" || arg == "--sentence-silence") {
      ensureArg(argc, argv, i);
      runConfig.sentenceSilenceSeconds = stof(argv[++i]);
    } else if (arg == "--phoneme_silence" || arg == "--phoneme-silence") {
      ensureArg(argc, argv, i);
      ensureArg(argc, argv, i + 1);
      auto phonemeStr = std::string(argv[++i]);
      if (!piper::isSingleCodepoint(phonemeStr)) {
        std::cerr << "Phoneme '" << phonemeStr
                  << "' is not a single codepoint (--phoneme_silence)"
                  << std::endl;
        exit(1);
      }

      if (!runConfig.phonemeSilenceSeconds) {
        runConfig.phonemeSilenceSeconds.emplace();
      }

      auto phoneme = piper::getCodepoint(phonemeStr);
      (*runConfig.phonemeSilenceSeconds)[phoneme] = stof(argv[++i]);
    } else if (arg == "--json_input" || arg == "--json-input") {
      runConfig.jsonInput = true;
    } else if (arg == "--use_cuda" || arg == "--use-cuda") {
      runConfig.useCuda = true;
    } else if (arg == "--gpu-device-id" || arg == "--gpu_device_id") {
      ensureArg(argc, argv, i);
      runConfig.gpuDeviceId = stoi(argv[++i]);
    } else if (arg == "--raw-phonemes" || arg == "--raw_phonemes") {
      runConfig.rawPhonemes = true;
    } else if (arg == "--streaming") {
      runConfig.streamingMode = true;
    } else if (arg == "--output-timing" || arg == "--output_timing") {
      ensureArg(argc, argv, i);
      runConfig.outputTimingPath = filesystem::path(argv[++i]);
    } else if (arg == "--timing-format" || arg == "--timing_format") {
      ensureArg(argc, argv, i);
      runConfig.timingFormat = argv[++i];
      if (runConfig.timingFormat != RunConfig::FORMAT_JSON && runConfig.timingFormat != RunConfig::FORMAT_TSV) {
        cerr << "Invalid timing format: " << runConfig.timingFormat << " (must be json or tsv)" << endl;
        exit(1);
      }
    } else if (arg == "--custom-dict" || arg == "--custom_dict") {
      ensureArg(argc, argv, i);
      string dictPaths = argv[++i];
      // カンマ区切りで複数の辞書パスを分割
      stringstream ss(dictPaths);
      string path;
      while (getline(ss, path, ',')) {
        runConfig.customDictPaths.push_back(filesystem::path(path));
      }
    } else if (arg == "-t" || arg == "--text") {
      ensureArg(argc, argv, i);
      runConfig.textInput = argv[++i];
    } else if (arg == "--list-models") {
      runConfig.listModels = true;
      // Optional language filter (next arg if not starting with --)
      if (i + 1 < argc && argv[i + 1][0] != '-') {
        runConfig.listModelsLanguage = argv[++i];
      }
    } else if (arg == "--download-model") {
      ensureArg(argc, argv, i);
      runConfig.downloadModelName = argv[++i];
    } else if (arg == "--model-dir" || arg == "--model_dir") {
      ensureArg(argc, argv, i);
      runConfig.modelDir = filesystem::path(argv[++i]);
    } else if (arg == "--version") {
      std::cout << piper::getVersion() << std::endl;
      exit(0);
    } else if (arg == "--test-mode") {
      runConfig.testMode = true;
      spdlog::info("Test mode enabled - ONNX runtime will be skipped");
    } else if (arg == "--no-warmup" || arg == "--no_warmup") {
      runConfig.noWarmup = true;
    } else if (arg == "--debug") {
      // Set DEBUG logging
      spdlog::set_level(spdlog::level::debug);
    } else if (arg == "-q" || arg == "--quiet") {
      // diable logging
      spdlog::set_level(spdlog::level::off);
    } else if (arg == "-h" || arg == "--help") {
      printUsage(argv);
      exit(0);
    } else if (arg.rfind("--", 0) == 0) {
      // Unknown flag starting with "--": suggest closest match
      static const vector<string> knownFlags = {
        "--model", "--config", "--output_file", "--output-file",
        "--output_dir", "--output-dir", "--output_raw", "--output-raw",
        "--speaker", "--language", "--noise-scale", "--noise_scale",
        "--length-scale", "--length_scale", "--noise-w", "--noise_w",
        "--sentence-silence", "--sentence_silence",
        "--phoneme-silence", "--phoneme_silence",
        "--json-input", "--json_input", "--use-cuda", "--use_cuda",
        "--gpu-device-id", "--gpu_device_id",
        "--raw-phonemes", "--raw_phonemes", "--streaming",
        "--output-timing", "--output_timing",
        "--timing-format", "--timing_format",
        "--custom-dict", "--custom_dict", "--text",
        "--list-models", "--download-model", "--model-dir", "--model_dir",
        "--version", "--test-mode", "--debug", "--quiet", "--help",
        "--no-stochastic", "--no-warmup", "--no_warmup",
      };
      // Find best match by edit distance (simple Levenshtein)
      string bestMatch;
      size_t bestDist = string::npos;
      for (const auto& flag : knownFlags) {
        // Simple distance: count differing chars after common prefix
        size_t maxLen = max(arg.size(), flag.size());
        size_t minLen = min(arg.size(), flag.size());
        size_t dist = maxLen - minLen;
        for (size_t j = 0; j < minLen; ++j) {
          if (arg[j] != flag[j]) ++dist;
        }
        if (dist < bestDist) {
          bestDist = dist;
          bestMatch = flag;
        }
      }
      cerr << "Unknown option: " << arg << endl;
      if (bestDist <= 3 && !bestMatch.empty()) {
        cerr << "Did you mean: " << bestMatch << " ?" << endl;
      }
      cerr << "Use --help for usage information." << endl;
      exit(1);
    }
  }

  // Validate --text and --json-input are mutually exclusive
  if (runConfig.textInput && runConfig.jsonInput) {
    throw runtime_error("--text and --json-input are mutually exclusive");
  }

  // --list-models and --download-model don't require a model file
  if (runConfig.listModels || runConfig.downloadModelName) {
    return;
  }

  // Verify model file exists; if not, try resolving as a model name/alias
  ifstream modelFile(runConfig.modelPath.c_str(), ios::binary);
  if (!modelFile.good()) {
    auto modelDir = runConfig.modelDir.value_or(piper::getDefaultModelDir());
    auto resolved = piper::resolveModelPath(runConfig.modelPath.string(), modelDir);
    if (resolved) {
      spdlog::info("Resolved model name '{}' to {}", runConfig.modelPath.string(), resolved->string());
      runConfig.modelPath = resolved.value();
      modelFile.open(runConfig.modelPath.c_str(), ios::binary);
    }
    if (!modelFile.good()) {
      // Check if it looks like a model name (no path separators or extension)
      auto pathStr = runConfig.modelPath.string();
      bool looksLikeName = pathStr.find('/') == string::npos &&
                           pathStr.find('\\') == string::npos &&
                           pathStr.find('.') == string::npos;
      if (looksLikeName) {
        auto voice = piper::findVoice(pathStr);
        if (voice) {
          cerr << "Model '" << pathStr << "' was found in the catalog but is not downloaded yet." << endl;
          cerr << "Run:  --download-model " << pathStr << endl;
        } else {
          cerr << "Model '" << pathStr << "' not found." << endl;
          cerr << "Use --list-models to see available models, "
               << "or specify a file path with --model /path/to/model.onnx" << endl;
        }
      } else {
        cerr << "Model file not found: " << pathStr << endl;
      }
      exit(1);
    }
  }

  if (!modelConfigPath) {
    runConfig.modelConfigPath =
        filesystem::path(runConfig.modelPath.string() + ".json");
    if (!filesystem::exists(runConfig.modelConfigPath)) {
      auto fallback = runConfig.modelPath.parent_path() / "config.json";
      if (filesystem::exists(fallback)) {
        runConfig.modelConfigPath = fallback;
      }
    }
  } else {
    runConfig.modelConfigPath = modelConfigPath.value();
  }

  // Verify model config exists
  ifstream modelConfigFile(runConfig.modelConfigPath.c_str());
  if (!modelConfigFile.good()) {
    throw runtime_error("Model config doesn't exist");
  }
}
