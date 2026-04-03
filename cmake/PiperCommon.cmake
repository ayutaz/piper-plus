# cmake/PiperCommon.cmake
# piper_common OBJECT library definition
#
# NOTE: include directories and compile definitions are configured AFTER
# ExternalDeps.cmake and OnnxRuntime.cmake are included, because those files
# set the variables (FMT_DIR, SPDLOG_DIR, etc.) that we reference here.
# See the piper_common configuration block in the root CMakeLists.txt.

# ---- piper_common OBJECT library (shared between piper, test_piper, piper_plus) ----
set(PIPER_COMMON_SOURCES
  src/cpp/piper.cpp
  src/cpp/phoneme_parser.cpp
  src/cpp/custom_dictionary.cpp
  src/cpp/model_manager.cpp
  src/cpp/language_detector.cpp
  src/cpp/english_phonemize.cpp
  src/cpp/chinese_phonemize.cpp
  src/cpp/korean_phonemize.cpp
  src/cpp/spanish_phonemize.cpp
  src/cpp/french_phonemize.cpp
  src/cpp/portuguese_phonemize.cpp
  src/cpp/swedish_phonemize.cpp
  src/cpp/openjtalk_phonemize.cpp
  src/cpp/openjtalk_phonemize_utils.cpp
  src/cpp/openjtalk_wrapper.c
  src/cpp/openjtalk_dictionary_manager.c
  src/cpp/openjtalk_error.c
  src/cpp/openjtalk_security.c
  src/cpp/openjtalk_optimized.c
  src/cpp/openjtalk_api.c
  src/cpp/library_path.c
)

# Add NEON optimized audio processing for ARM64
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  list(APPEND PIPER_COMMON_SOURCES src/cpp/audio_neon.cpp)
endif()

add_library(piper_common OBJECT ${PIPER_COMMON_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)
