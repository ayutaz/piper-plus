// Python bindings for piper-phonemize using pybind11
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <map>
#include <string>
#include <vector>

#include "phonemize.hpp"
#include "phoneme_ids.hpp"
#include "tashkeel.hpp"

namespace py = pybind11;

// Main module definition
PYBIND11_MODULE(_cpp, m) {
    m.doc() = "Python bindings for piper-phonemize";

    // phonemize_espeak function
    m.def("phonemize_espeak",
        [](const std::string& text, const std::string& voice) -> std::vector<std::string> {
            std::vector<std::string> phonemes;
            piper::phonemize_espeak(text, voice, phonemes);
            return phonemes;
        },
        py::arg("text"),
        py::arg("voice") = "en-us",
        "Phonemize text using eSpeak-ng"
    );

    // phonemize_codepoints function
    m.def("phonemize_codepoints",
        [](const std::string& text) -> std::vector<int> {
            std::vector<int> codepoints;
            piper::phonemize_codepoints(text, codepoints);
            return codepoints;
        },
        py::arg("text"),
        "Convert text to codepoint IDs"
    );

    // phoneme_ids_espeak function (renamed from phoneme_to_ids)
    m.def("phoneme_ids_espeak",
        [](const std::vector<std::string>& phonemes) -> std::vector<int> {
            std::vector<int> ids;
            piper::phoneme_to_ids(phonemes, ids);
            return ids;
        },
        py::arg("phonemes"),
        "Convert phonemes to IDs"
    );

    // tashkeel_run function (for Arabic)
    m.def("tashkeel_run",
        [](const std::string& text) -> std::string {
            return piper::tashkeel_remove(text);
        },
        py::arg("text"),
        "Remove Arabic tashkeel (diacritics) from text"
    );

    // DEFAULT_PHONEME_ID_MAP constant
    // Create a default phoneme ID map
    std::map<std::string, int> default_map;
    // Initialize with some default values (this would normally come from the library)
    m.attr("DEFAULT_PHONEME_ID_MAP") = py::dict();

    // Version information
    #ifdef VERSION_INFO
    m.attr("__version__") = VERSION_INFO;
    #else
    m.attr("__version__") = "dev";
    #endif
}