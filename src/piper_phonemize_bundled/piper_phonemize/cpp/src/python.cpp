#include <iostream>
#include <optional>
#include <string>
#include <map>
#include <vector>

#include <espeak-ng/speak_lib.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "phoneme_ids.hpp"
#include "phonemize.hpp"
#include "tashkeel.hpp"

#define STRINGIFY(x) #x
#define MACRO_STRINGIFY(x) STRINGIFY(x)

namespace py = pybind11;

// True when espeak_Initialize has been called
bool eSpeakInitialized = false;

// Loaded when using Arabic
// https://github.com/mush42/libtashkeel/
std::map<std::string, tashkeel::State> tashkeelStates;

// ----------------------------------------------------------------------------

std::vector<std::vector<piper::Phoneme>>
phonemize_espeak(std::string text, std::string voice, std::string dataPath) {
  if (!eSpeakInitialized) {
    int result =
        espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, dataPath.c_str(), 0);
    if (result < 0) {
      throw std::runtime_error("Failed to initialize eSpeak");
    }

    eSpeakInitialized = true;
  }

  piper::eSpeakPhonemeConfig config;
  config.voice = voice;

  std::vector<std::vector<piper::Phoneme>> phonemes;
  piper::phonemize_eSpeak(text, config, phonemes);

  return phonemes;
}

std::vector<std::vector<piper::Phoneme>>
phonemize_codepoints(std::string text, std::string casing) {
  piper::CodepointsPhonemeConfig config;

  if (casing == "ignore") {
    config.casing = piper::CASING_IGNORE;
  } else if (casing == "lower") {
    config.casing = piper::CASING_LOWER;
  } else if (casing == "upper") {
    config.casing = piper::CASING_UPPER;
  } else if (casing == "fold") {
    config.casing = piper::CASING_FOLD;
  }

  std::vector<std::vector<piper::Phoneme>> phonemes;

  piper::phonemize_codepoints(text, config, phonemes);

  return phonemes;
}

std::pair<std::vector<piper::PhonemeId>, std::map<piper::Phoneme, std::size_t>>
phoneme_ids_espeak(std::vector<piper::Phoneme> &phonemes) {
  piper::PhonemeIdConfig config;
  std::vector<piper::PhonemeId> phonemeIds;
  std::map<piper::Phoneme, std::size_t> missingPhonemes;

  phonemes_to_ids(phonemes, config, phonemeIds, missingPhonemes);

  return std::make_pair(phonemeIds, missingPhonemes);
}

std::pair<std::vector<piper::PhonemeId>, std::map<piper::Phoneme, std::size_t>>
phoneme_ids_codepoints(std::string language,
                       std::vector<piper::Phoneme> &phonemes) {
  if (piper::DEFAULT_ALPHABET.count(language) < 1) {
    throw std::runtime_error("No phoneme/id map for language");
  }

  piper::PhonemeIdConfig config;
  config.phonemeIdMap =
      std::make_shared<piper::PhonemeIdMap>(piper::DEFAULT_ALPHABET[language]);
  std::vector<piper::PhonemeId> phonemeIds;
  std::map<piper::Phoneme, std::size_t> missingPhonemes;

  phonemes_to_ids(phonemes, config, phonemeIds, missingPhonemes);

  return std::make_pair(phonemeIds, missingPhonemes);
}

std::size_t get_max_phonemes() { return piper::MAX_PHONEMES; }

piper::PhonemeIdMap get_espeak_map() { return piper::DEFAULT_PHONEME_ID_MAP; }

std::map<std::string, piper::PhonemeIdMap> get_codepoints_map() {
  return piper::DEFAULT_ALPHABET;
}

std::string tashkeel_run(std::string modelPath, std::string text) {
  if (tashkeelStates.count(modelPath) < 1) {
    tashkeel::State newState;
    tashkeel::tashkeel_load(modelPath, newState);
    tashkeelStates[modelPath] = std::move(newState);
  }

  return tashkeel::tashkeel_run(text, tashkeelStates[modelPath]);
}

// ----------------------------------------------------------------------------

PYBIND11_MODULE(piper_phonemize_cpp, m) {
  m.doc() = R"pbdoc(
        Pybind11 example plugin
        -----------------------

        .. currentmodule:: piper_phonemize_cpp

        .. autosummary::
           :toctree: _generate

           phonemize_espeak
           phonemize_codepoints
           phoneme_ids_espeak
           phoneme_ids_codepoints
           get_espeak_map
           get_codepoints_map
           get_max_phonemes
           tashkeel_load
           tashkeel_run
    )pbdoc";

  m.def("phonemize_espeak", &phonemize_espeak, R"pbdoc(
        Phonemize text using espeak-ng
    )pbdoc");

  m.def("phonemize_codepoints", &phonemize_codepoints, R"pbdoc(
        Phonemize text as UTF-8 codepoints
    )pbdoc");

  m.def("phoneme_ids_espeak", &phoneme_ids_espeak, R"pbdoc(
        Get ids for espeak-ng phonemes
    )pbdoc");

  m.def("phoneme_ids_codepoints", &phoneme_ids_codepoints, R"pbdoc(
        Get ids for a language's codepoints
    )pbdoc");

  m.def("get_espeak_map", &get_espeak_map, R"pbdoc(
        Get phoneme/id map for espeak-ng phonemes
    )pbdoc");

  m.def("get_codepoints_map", &get_codepoints_map, R"pbdoc(
        Get codepoint/id map for supported languages
    )pbdoc");

  m.def("get_max_phonemes", &get_max_phonemes, R"pbdoc(
        Get maximum number of phonemes in id maps
    )pbdoc");

  m.def("tashkeel_run", &tashkeel_run, R"pbdoc(
        Add diacritics to Arabic text (must call tashkeel_load first)
    )pbdoc");

#ifdef VERSION_INFO
  m.attr("__version__") = MACRO_STRINGIFY(VERSION_INFO);
#else
  m.attr("__version__") = "dev";
#endif
}
