#!/usr/bin/env python3
"""
Create a basic python.cpp stub file for pybind11 binding
"""

import sys
from pathlib import Path


def create_python_cpp():
    """Create a python.cpp file with pybind11 bindings"""
    src_dir = Path(__file__).parent
    cpp_dir = src_dir / "piper_phonemize" / "cpp" / "src"
    cpp_dir.mkdir(parents=True, exist_ok=True)

    python_cpp_path = cpp_dir / "python.cpp"

    # Check if phonemize.hpp exists to include it properly
    phonemize_header = cpp_dir / "phonemize.hpp"
    if not phonemize_header.exists():
        print(f"Warning: {phonemize_header} not found")

    python_cpp_content = """#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

#include "phonemize.hpp"
#include "phoneme_ids.hpp"
#include "tashkeel.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_cpp, m) {
    m.doc() = "Piper phonemization library";

    // Main phonemization function
    m.def("phonemize_espeak",
        [](const std::string& text, const std::string& voice) {
            std::vector<std::string> phonemes;
            piper::phonemize_espeak(text, voice, phonemes);
            return phonemes;
        },
        py::arg("text"),
        py::arg("voice") = "en-us",
        "Phonemize text using espeak-ng"
    );

    // Phoneme to IDs conversion
    m.def("phoneme_ids_espeak",
        [](const std::vector<std::string>& phonemes) {
            std::vector<int> ids;
            piper::phonemes_to_ids(phonemes, ids);
            return ids;
        },
        py::arg("phonemes"),
        "Convert phonemes to IDs"
    );

    // Codepoint phonemization
    m.def("phonemize_codepoints",
        [](const std::string& text) {
            std::vector<int> codepoints;
            piper::phonemize_codepoints(text, codepoints);
            return codepoints;
        },
        py::arg("text"),
        "Convert text to codepoint IDs"
    );

    // Arabic tashkeel
    m.def("tashkeel_run",
        [](const std::string& text) {
            std::string result;
            piper::tashkeel_run(text, result);
            return result;
        },
        py::arg("text"),
        "Add Arabic diacritics (tashkeel)"
    );

    // Constants
    m.attr("DEFAULT_PHONEME_ID_MAP") = py::dict();
}
"""

    # Write the file
    with open(python_cpp_path, "w", encoding="utf-8") as f:
        f.write(python_cpp_content)

    print(f"Created {python_cpp_path}")
    return True


if __name__ == "__main__":
    if create_python_cpp():
        print("Successfully created python.cpp")
        sys.exit(0)
    else:
        print("Failed to create python.cpp")
        sys.exit(1)
