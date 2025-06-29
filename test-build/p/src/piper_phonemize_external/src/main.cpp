#include <filesystem>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <vector>

#include <espeak-ng/speak_lib.h>

#ifdef _MSC_VER
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

#include "json.hpp"
#include "phoneme_ids.hpp"
#include "phonemize.hpp"
#include "tashkeel.hpp"
#include "uni_algo.h"

using json = nlohmann::json;

enum PhonemeType { eSpeakPhonemes, TextPhonemes };

struct RunConfig {
  std::string language = "";
  PhonemeType phonemeType = eSpeakPhonemes;
  std::optional<std::filesystem::path> eSpeakDataPath;
  std::optional<std::filesystem::path> tashkeelModelPath;
  std::function<std::string(std::string)> processText = [](std::string text) {
    return text;
  };
  std::optional<std::function<void(std::string,
                                   std::vector<std::vector<piper::Phoneme>> &)>>
      textToPhonemes;
  bool jsonInput = false;
  bool allowMissingPhonemes = false;
};

void parseArgs(int argc, char *argv[], RunConfig &runConfig);

// ----------------------------------------------------------------------------

int main(int argc, char *argv[]) {
  RunConfig runConfig;
  parseArgs(argc, argv, runConfig);

#ifdef _WIN32
  // Required on Windows to show IPA symbols
  SetConsoleOutputCP(CP_UTF8);
#endif

  piper::eSpeakPhonemeConfig eSpeakConfig;
  piper::CodepointsPhonemeConfig codepointsConfig;
  piper::PhonemeIdConfig idConfig;
  tashkeel::State tashkeelState;

  if (runConfig.phonemeType == eSpeakPhonemes) {
    // Need to initialize eSpeak
    if (!runConfig.eSpeakDataPath) {
      throw std::runtime_error(
          "--espeak_data is required with path to espeak-ng-data directory");
    }

    eSpeakConfig.voice = runConfig.language;

    int result =
        espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0,
                          runConfig.eSpeakDataPath->string().c_str(), 0);
    if (result < 0) {
      throw std::runtime_error("Failed to initialize eSpeak");
    }

    runConfig.textToPhonemes =
        [&eSpeakConfig](std::string text,
                        std::vector<std::vector<piper::Phoneme>> &phonemes) {
          piper::phonemize_eSpeak(text, eSpeakConfig, phonemes);
        };
  } else {
    // Text "phonemes"
    if (piper::DEFAULT_ALPHABET.count(runConfig.language) < 1) {
      throw std::runtime_error("Language is not supported for text phonemes");
    }

    idConfig.phonemeIdMap = std::make_shared<piper::PhonemeIdMap>(
        piper::DEFAULT_ALPHABET[runConfig.language]);
  }

  // Special handling for Arabic
  if (runConfig.language == "ar") {
    if (runConfig.tashkeelModelPath) {
      // Load tashkeel
      tashkeel::tashkeel_load(runConfig.tashkeelModelPath->string(),
                              tashkeelState);

      // Text will be diacritized with libtashkeel.
      // https://github.com/mush42/libtashkeel
      runConfig.processText = [&tashkeelState](std::string text) {
        return tashkeel::tashkeel_run(text, tashkeelState);
      };
    } else {
      std::cerr << "WARNING: --tashkeel_model is not set, so text cannot be "
                   "diacritized!"
                << std::endl;
    }
  }

  // Count of missing phonemes from phoneme/id map
  std::map<piper::Phoneme, std::size_t> missingPhonemes;

  // Process each line as a JSON object, adding phonemes and phoneme ids.
  std::string line;
  while (std::getline(std::cin, line)) {
    json lineObj;
    if (runConfig.jsonInput) {
      // Each line is JSON object with:
      // {
      //   "text": "Text to phonemize"
      // }
      lineObj = json::parse(line);
    } else {
      // Each line is plain text
      lineObj["text"] = line;
    }

    auto text = lineObj["text"].get<std::string>();
    std::string processedText;

    if (lineObj.contains("processed_text")) {
      processedText = lineObj["processed_text"].get<std::string>();
    } else {
      processedText = runConfig.processText(text);
      lineObj["processed_text"] = processedText;
    }

    std::vector<std::vector<piper::Phoneme>> phonemes;
    if (!lineObj.contains("phonemes")) {
      // Phonemize text
      if (!runConfig.textToPhonemes) {
        throw std::runtime_error("Text to phonemes function was not set.");
      }

      (*runConfig.textToPhonemes)(processedText, phonemes);

      // Copy to JSON object
      std::vector<std::string> linePhonemes;
      for (auto &sentencePhonemes : phonemes) {
        for (auto phoneme : sentencePhonemes) {
          // Convert to UTF-8 string
          std::u32string phonemeU32Str;
          phonemeU32Str += phoneme;
          linePhonemes.push_back(una::utf32to8(phonemeU32Str));
        }
      }

      lineObj["phonemes"] = linePhonemes;
    }

    if (!lineObj.contains("phonemes_ids")) {
      // Add ids for phonenmes
      std::vector<json::number_unsigned_t> phonemeIds;

      for (auto &sentencePhonemes : phonemes) {
        std::vector<piper::PhonemeId> sentIds;
        piper::phonemes_to_ids(sentencePhonemes, idConfig, sentIds,
                               missingPhonemes);
        std::copy(sentIds.begin(), sentIds.end(),
                  std::back_inserter(phonemeIds));
      }

      lineObj["phoneme_ids"] = phonemeIds;
    }

    if ((missingPhonemes.size() > 0) && !runConfig.allowMissingPhonemes) {
      // Fail early if there are any missing phonemes from the phoneme/id map.
      for (auto phonemeAndCount : missingPhonemes) {
        std::cerr << "Missing phoneme: \\u" << std::setw(4) << std::setfill('0')
                  << std::hex << static_cast<uint32_t>(phonemeAndCount.first)
                  << " for: " << lineObj.dump() << std::endl;
      }
      return 1;
    }

    std::cout << lineObj.dump() << std::endl;
  }

  if (missingPhonemes.size() > 0) {
    // Print missing phonemes.
    // We'll only get here if --allow_missing_phonemes is set
    std::cerr << "WARNING: There were " << missingPhonemes.size()
              << " missing phonemes:" << std::endl;

    for (auto phonemeAndCount : missingPhonemes) {
      std::cerr << "\\u" << std::setw(4) << std::setfill('0') << std::hex
                << static_cast<uint32_t>(phonemeAndCount.first)
                << " (count=" << phonemeAndCount.second << ")" << std::endl;
    }
  }

  if (runConfig.phonemeType == eSpeakPhonemes) {
    // Terminate eSpeak
    espeak_Terminate();
  }

  return 0;
}

// ----------------------------------------------------------------------------

void printUsage(char *argv[]) {
  std::cerr << std::endl;
  std::cerr << "usage: " << argv[0] << " [options]" << std::endl;
  std::cerr << std::endl;
  std::cerr << "options:" << std::endl;
  std::cerr << "   -h        --help              show this message and exit"
            << std::endl;
  std::cerr
      << "   -l  LANG  --language     LANG  language of input text (required)"
      << std::endl;
  std::cerr
      << "   --espeak_data           DIR   path to espeak-ng data directory"
      << std::endl;
  std::cerr
      << "   --tashkeel_model        FILE  path to libtashkeel onnx model "
         "(arabic)"
      << std::endl;
  std::cerr
      << "   -j        --json_input        input is JSONL instead of plain text"
      << std::endl;
  std::cerr
      << "   --allow_missing_phonemes      don't fail when phonemes are not "
         "recognized"
      << std::endl;
  std::cerr << std::endl;
}

void ensureArg(int argc, char *argv[], int argi) {
  if ((argi + 1) >= argc) {
    printUsage(argv);
    exit(0);
  }
}

// Parse command-line arguments
void parseArgs(int argc, char *argv[], RunConfig &runConfig) {
  std::optional<std::filesystem::path> modelConfigPath;

  for (int i = 1; i < argc; i++) {
    std::string arg = argv[i];

    if (arg == "-l" || arg == "--language") {
      ensureArg(argc, argv, i);
      runConfig.language = std::string(argv[++i]);
    } else if (arg == "--espeak_data" || arg == "--espeak-data") {
      ensureArg(argc, argv, i);
      runConfig.eSpeakDataPath = std::filesystem::path(argv[++i]);
    } else if (arg == "--tashkeel_model" || arg == "--tashkeel-model") {
      ensureArg(argc, argv, i);
      runConfig.tashkeelModelPath = std::filesystem::path(argv[++i]);
    } else if (arg == "-j" || arg == "--json_input" || arg == "--json-input") {
      runConfig.jsonInput = true;
    } else if (arg == "--allow_missing_phonemes" ||
               arg == "--allow-missing-phonemes") {
      runConfig.allowMissingPhonemes = true;
    } else if (arg == "-h" || arg == "--help") {
      printUsage(argv);
      exit(0);
    }
  }

  if (runConfig.language.empty()) {
    std::cerr << "--language is required" << std::endl;
    printUsage(argv);
    exit(1);
  }
}
