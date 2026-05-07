# cmake/PiperCommon.cmake
# piper_common STATIC library definition
#
# NOTE: include directories and compile definitions are configured AFTER
# ExternalDeps.cmake and OnnxRuntime.cmake are included, because those files
# set the variables (FMT_DIR, SPDLOG_DIR, etc.) that we reference here.
# See the piper_common configuration block in the root CMakeLists.txt.
#
# Why STATIC (not OBJECT) — issue #377:
# OBJECT libraries combined with $<TARGET_OBJECTS:>/target_link_libraries fail
# to integrate object files into iOS STATIC archives produced via Apple's
# xcrun libtool (CMake issues #17457, #22415). Switching to STATIC produces
# a real libpiper_common.a, and we use post-build `libtool -static` (iOS) or
# implicit linker behavior (Linux/macOS/Windows/Android SHARED) to consolidate
# it into the consumer artifact. Same pattern as sherpa-onnx / whisper.cpp.

# ---- piper_common STATIC library (shared between piper, test_piper, piper_plus) ----
#
# Source list is split into core sources (compiled on every platform including
# iOS) and desktop-only sources (excluded on iOS because they call std::system /
# popen / fork — all unavailable in the iOS App Sandbox).
#
# Desktop-only file inventory:
#   model_manager.cpp                   std::system → curl/wget for HF auto-download
#   openjtalk_wrapper.c                 popen + system → locate / invoke legacy openjtalk binary
#   openjtalk_optimized.c               fork + execvp + popen → spawn legacy openjtalk binary
#   openjtalk_dictionary_manager.c      popen → sha256 verify + tar extract for dict download
#
# Verified that none of the above are referenced by the piper-plus C API
# (piper_plus_c_api.cpp) nor by the synthesis pipeline (piper.cpp); they are
# only consumed by main.cpp (CLI entry, not built on iOS) and by tests
# (already excluded on iOS via `if(BUILD_TESTS AND NOT iOS)`).
set(PIPER_COMMON_SOURCES
  src/cpp/piper.cpp
  src/cpp/phoneme_parser.cpp
  src/cpp/custom_dictionary.cpp
  src/cpp/language_detector.cpp
  src/cpp/english_phonemize.cpp
  src/cpp/chinese_phonemize.cpp
  src/cpp/chinese_loanword.cpp
  src/cpp/korean_phonemize.cpp
  src/cpp/spanish_phonemize.cpp
  src/cpp/french_phonemize.cpp
  src/cpp/portuguese_phonemize.cpp
  src/cpp/swedish_phonemize.cpp
  src/cpp/openjtalk_phonemize.cpp
  src/cpp/openjtalk_phonemize_utils.cpp
  src/cpp/openjtalk_error.c
  src/cpp/openjtalk_security.c
  src/cpp/openjtalk_api.c
  src/cpp/library_path.c
)

# Desktop-only sources (std::system / popen / fork unavailable on Apple
# embedded platforms — iOS / tvOS / watchOS / visionOS). On those targets,
# openjtalk_ios_stub.c provides minimal stand-ins for the symbols referenced
# by openjtalk_phonemize.cpp / openjtalk_api.c (which remain in the build),
# so libpiper_plus.a links cleanly in consumer Xcode projects.
if(PIPER_APPLE_EMBEDDED)
  list(APPEND PIPER_COMMON_SOURCES
    src/cpp/openjtalk_ios_stub.c
  )
else()
  list(APPEND PIPER_COMMON_SOURCES
    src/cpp/model_manager.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_optimized.c
    src/cpp/openjtalk_dictionary_manager.c
  )
endif()

# Add NEON optimized audio processing for ARM64
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  list(APPEND PIPER_COMMON_SOURCES src/cpp/audio_neon.cpp)
endif()

# =============================================================================
# ZH-EN code-switching loanword data (TICKET-05 P5, Issue #384)
#
# Desktop (Linux / macOS / Windows): the JSON is installed under
# share/piper/dicts/ and loaded at runtime from <exe-dir>/data/.
# Apple-embedded (iOS / tvOS / watchOS / visionOS) and Android: the JSON is
# converted into a C unsigned-char array at configure time via
# `file(READ HEX)`, so libpiper_plus.a / .aar are self-contained — no xxd /
# bin2c host tool required, no runtime file dependency.
# =============================================================================

# Convert a JSON file to a C array header.
#
# Output (text-mode `${VAR_NAME}` C/C++ header):
#   static const unsigned char <var_name>[] = { 0x..., 0x..., ... };
#   static const std::size_t <var_name>_len = sizeof(<var_name>);
#
# Two important behaviors:
#   1. Generation is wired through `add_custom_command(DEPENDS ${INPUT_JSON})`
#      so editing the JSON triggers a re-build. (Plain `file(WRITE)` only fires
#      at configure-time and would silently miss source edits — review note
#      Cpp-H3.)
#   2. CRLF is normalized to LF before hashing. Without this, a Windows
#      checkout with `core.autocrlf=true` produces an embedded payload that
#      differs byte-for-byte from a Linux checkout — breaking the
#      cross-runtime byte-equal sync gate (review note Cpp-C1).
function(piper_embed_json_as_header INPUT_JSON OUTPUT_HEADER VAR_NAME)
  if(NOT EXISTS "${INPUT_JSON}")
    message(FATAL_ERROR "piper_embed_json_as_header: input file not found: ${INPUT_JSON}")
  endif()
  if(NOT DEFINED PIPER_EMBED_JSON_SCRIPT)
    set(PIPER_EMBED_JSON_SCRIPT "${CMAKE_SOURCE_DIR}/cmake/EmbedJson.cmake"
        CACHE INTERNAL "Path to the file embedding script driver")
  endif()
  add_custom_command(
    OUTPUT  "${OUTPUT_HEADER}"
    COMMAND ${CMAKE_COMMAND}
            -DINPUT_JSON=${INPUT_JSON}
            -DOUTPUT_HEADER=${OUTPUT_HEADER}
            -DVAR_NAME=${VAR_NAME}
            -P ${PIPER_EMBED_JSON_SCRIPT}
    DEPENDS "${INPUT_JSON}" "${PIPER_EMBED_JSON_SCRIPT}"
    COMMENT "Embedding ${INPUT_JSON} -> ${OUTPUT_HEADER}"
    VERBATIM
  )
endfunction()

if(PIPER_APPLE_EMBEDDED OR ANDROID)
  set(PIPER_LOANWORD_HEADER ${CMAKE_CURRENT_BINARY_DIR}/zh_en_loanword_data.h)
  piper_embed_json_as_header(
    "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/data/zh_en_loanword.json"
    "${PIPER_LOANWORD_HEADER}"
    zh_en_loanword_json
  )
  list(APPEND PIPER_COMMON_SOURCES "${PIPER_LOANWORD_HEADER}")
endif()

add_library(piper_common STATIC ${PIPER_COMMON_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(PIPER_APPLE_EMBEDDED OR ANDROID)
  # Activate the embedded-data branch in chinese_loanword.cpp +
  # makes the generated header discoverable via #include "zh_en_loanword_data.h".
  target_compile_definitions(piper_common PRIVATE PIPER_PLUS_EMBEDDED_LOANWORD)
  target_include_directories(piper_common PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
else()
  # Desktop install: ship the JSON next to the binary so
  # piper_plus_get_exe_dir() can resolve <exe-dir>/data/zh_en_loanword.json.
  install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/data/zh_en_loanword.json"
          DESTINATION share/piper/dicts)
endif()
