#include <iostream>
#include <map>
#include <sstream>
#include <vector>

#include <espeak-ng/speak_lib.h>

#include "phoneme_ids.hpp"
#include "phonemize.hpp"
#include "tashkeel.hpp"
#include "uni_algo.h"

std::string idString(const std::vector<std::vector<piper::Phoneme>> &phonemes,
                     piper::PhonemeIdConfig &idConfig) {
  std::map<piper::Phoneme, std::size_t> missingPhonemes;
  std::stringstream idStr;
  for (auto sentPhonemes : phonemes) {
    std::vector<piper::PhonemeId> sentIds;
    piper::phonemes_to_ids(sentPhonemes, idConfig, sentIds, missingPhonemes);

    for (auto id : sentIds) {
      idStr << id << " ";
    }
  }

  return idStr.str();
}

std::string
phonemeString(const std::vector<std::vector<piper::Phoneme>> &phonemes) {
  std::stringstream phonemeStr;
  for (auto &sentencePhonemes : phonemes) {
    for (auto phoneme : sentencePhonemes) {
      // Convert to UTF-8 string
      std::u32string phonemeU32Str;
      phonemeU32Str += phoneme;

      phonemeStr << una::utf32to8(phonemeU32Str);
    }

    phonemeStr << "\n";
  }

  return phonemeStr.str();
}

int main(int argc, char *argv[]) {

  if (argc < 2) {
    std::cerr << "Need espeak-ng-data path" << std::endl;
    return 1;
  }

  if (argc < 3) {
    std::cerr << "Need tashkeel model path" << std::endl;
    return 1;
  }

  int result = espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, argv[1], 0);
  if (result < 0) {
    std::cerr << "Failed to initialize eSpeak" << std::endl;
    return 1;
  }

  piper::eSpeakPhonemeConfig phonemeConfig;
  piper::PhonemeIdConfig idConfig;

  // Check "licht" in German
  phonemeConfig.voice = "de";
  std::vector<std::vector<piper::Phoneme>> phonemes;

  // Should be "lˈɪçt!" where "ç" is decomposed into two codepoints
  piper::phonemize_eSpeak("licht!", phonemeConfig, phonemes);

  // 0 = pad
  // 1 = bos
  // 2 = eos
  // 4 = !
  std::string idStr = idString(phonemes, idConfig);
  if (idStr != "1 0 24 0 120 0 74 0 16 0 140 0 32 0 4 0 2 ") {
    std::cerr << "licht: " << idStr << std::endl;
    return 1;
  }

  // Check whitespace around punctuation
  phonemeConfig.voice = "en-us";
  phonemes.clear();

  piper::phonemize_eSpeak("this, is: a; test.", phonemeConfig, phonemes);

  std::string phonemeStr = phonemeString(phonemes);
  if (phonemeStr != "ðˈɪs, ɪz: ˈeɪ; tˈɛst.\n") {
    std::cerr << "punctuation test: " << phonemeStr << std::endl;
    return 1;
  }

  // Check sentence splitting.
  phonemes.clear();

  // Capitalization is required to get espeak to split the sentences.
  piper::phonemize_eSpeak("Test 1. Test 2.", phonemeConfig, phonemes);

   phonemeStr = phonemeString(phonemes);
  if (phonemeStr != "tˈɛst wˈʌn.\ntˈɛst tˈuː.\n") {
    std::cerr << "sentence split: " << phonemeStr << std::endl;
    return 1;
  }

  // Check "ВЕСЕ́ЛКА" in Ukrainian
  piper::CodepointsPhonemeConfig codepointsConfig;
  phonemes.clear();

  piper::phonemize_codepoints("ВЕСЕ́ЛКА", codepointsConfig, phonemes);

  // Case folded and NFD normalized
  std::vector<piper::Phoneme> expectedPhonemes = {U'в', U'е', U'с', U'е',
                                                  U'́',  U'л', U'к', U'а'};

  if (phonemes[0] != expectedPhonemes) {
    std::cerr << "Весе́лка: ";
    for (auto phoneme : phonemes[0]) {
      std::cerr << phoneme << " ";
    }

    std::cerr << std::endl;
    return 1;
  }

  idConfig.phonemeIdMap =
      std::make_shared<piper::PhonemeIdMap>(piper::DEFAULT_ALPHABET["uk"]);
  idStr = idString(phonemes, idConfig);
  if (idStr != "1 0 14 0 18 0 33 0 18 0 45 0 27 0 26 0 12 0 2 ") {
    std::cerr << "Весе́лка: " << idStr << std::endl;
    return 1;
  }

  // --------------------------------------------------------------------------

  // Check missing phoneme
  phonemes.clear();
  phonemes.emplace_back();
  phonemes[0].push_back(0);
  phonemes[0].push_back(0);
  phonemes[0].push_back(0);

  std::vector<piper::PhonemeId> missingIds;
  std::map<piper::Phoneme, std::size_t> missingPhonemes;
  piper::phonemes_to_ids(phonemes[0], idConfig, missingIds, missingPhonemes);

  if (missingPhonemes.size() != 1) {
    std::cerr << "Expected 1 missing phoneme, got " << missingPhonemes.size()
              << std::endl;
    return 1;
  }

  if (missingPhonemes.count(0) < 1) {
    std::cerr << "Expected '0' to be a missing phoneme" << std::endl;
    return 1;
  }

  if (missingPhonemes[0] != 3) {
    std::cerr << "Missing count for '0' phoneme: " << missingPhonemes[0]
              << " != 3" << std::endl;
    return 1;
  }

  // --------------------------------------------------------------------------

  // Test Arabic with libtashkeel (https://github.com/mush42/libtashkeel)
  tashkeel::State tashkeelState;
  tashkeel::tashkeel_load(argv[2], tashkeelState);

  std::string expectedText = "مَرْحَبًا";
  std::string actualText = tashkeel::tashkeel_run("مرحبا", tashkeelState);
  if (expectedText != actualText) {
    std::cerr << "Expected '" << expectedText << "', got '" << actualText << "'"
              << std::endl;
    return 1;
  }

  // --------------------------------------------------------------------------

  std::cout << "OK" << std::endl;

  espeak_Terminate();

  return 0;
}
