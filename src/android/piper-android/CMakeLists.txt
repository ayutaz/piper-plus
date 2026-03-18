# =============================================================================
# Piper Android JNI — CMake build configuration
# =============================================================================
#
# This CMakeLists.txt builds the native JNI shared library (libpiper_jni.so)
# for Android. It is intended as a local build reference; the actual Android
# build is driven by Gradle + AGP (externalNativeBuild) which invokes this
# file through the NDK toolchain.
#
# Directory layout (relative to this file):
#
#   src/main/cpp/
#       piper_jni.cpp              JNI entry point (NativeBridge <-> piper core)
#       piper_engine.hpp / .cpp    High-level wrapper around piper core
#       piper_jni_utils.h          JNI utility macros and helpers
#
#   <project-root>/src/cpp/        Piper core C++ sources (piper.cpp, etc.)
#
# External dependencies (pre-built for Android):
#   - ONNX Runtime Android AAR  (headers + libonnxruntime.so per ABI)
#   - OpenJTalk static library   (libopenjtalk.a, built for each Android ABI)
#   - spdlog + fmt (header-only)
#
# Usage (standalone, for reference only):
#   cmake -B build -G Ninja \
#       -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
#       -DANDROID_ABI=arm64-v8a \
#       -DANDROID_PLATFORM=android-24 \
#       -DBUILD_ANDROID_JNI=ON \
#       -DONNXRUNTIME_DIR=/path/to/onnxruntime-android \
#       -DOPENJTALK_DIR=/path/to/openjtalk-android \
#       -DSPDLOG_DIR=/path/to/spdlog \
#       -DFMT_DIR=/path/to/fmt \
#       src/android/piper-android
#   cmake --build build
# =============================================================================

cmake_minimum_required(VERSION 3.22)

project(piper_jni C CXX)

# ---------------------------------------------------------------------------
# C/C++ standard — match the top-level project
# ---------------------------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# Build option
# ---------------------------------------------------------------------------
option(BUILD_ANDROID_JNI "Build Android JNI shared library" ON)

# ---------------------------------------------------------------------------
# Project root (three levels up from this CMakeLists.txt)
# ---------------------------------------------------------------------------
get_filename_component(PIPER_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

# ---------------------------------------------------------------------------
# JNI shared library target — JNI layer + piper engine wrapper
# ---------------------------------------------------------------------------
add_library(piper_jni SHARED
    src/main/cpp/piper_jni.cpp
    src/main/cpp/piper_engine.cpp
)

# ---------------------------------------------------------------------------
# Piper core sources (reused from the desktop build)
#
# Includes:
#   - piper.cpp              Main synthesis pipeline
#   - phoneme_parser.cpp     Raw phoneme string parser
#   - language_detector.cpp  Unicode-based language detection
#   - *_phonemize.cpp        Per-language G2P (EN/ZH/KO/ES/FR/PT)
#   - openjtalk_*.cpp/.c     Japanese phonemizer + OpenJTalk C wrappers
#
# Excluded (desktop-only):
#   - main.cpp               CLI entry point
#   - test.cpp               Test entry point
#   - model_manager.cpp      Model downloading / exe-relative path lookup
#   - custom_dictionary.cpp  Custom dictionary loading (exe-relative paths)
#   - audio_neon.cpp         ARM64 NEON audio processing (optional)
# ---------------------------------------------------------------------------
target_sources(piper_jni PRIVATE
    # Core synthesis
    ${PIPER_ROOT}/src/cpp/piper.cpp
    ${PIPER_ROOT}/src/cpp/phoneme_parser.cpp
    ${PIPER_ROOT}/src/cpp/language_detector.cpp

    # Per-language phonemizers (GPL-free)
    ${PIPER_ROOT}/src/cpp/english_phonemize.cpp
    ${PIPER_ROOT}/src/cpp/chinese_phonemize.cpp
    ${PIPER_ROOT}/src/cpp/korean_phonemize.cpp
    ${PIPER_ROOT}/src/cpp/spanish_phonemize.cpp
    ${PIPER_ROOT}/src/cpp/french_phonemize.cpp
    ${PIPER_ROOT}/src/cpp/portuguese_phonemize.cpp

    # OpenJTalk Japanese phonemizer (C++ + C wrappers)
    ${PIPER_ROOT}/src/cpp/openjtalk_phonemize.cpp
    ${PIPER_ROOT}/src/cpp/openjtalk_phonemize_utils.cpp
    ${PIPER_ROOT}/src/cpp/openjtalk_wrapper.c
    ${PIPER_ROOT}/src/cpp/openjtalk_dictionary_manager.c
    ${PIPER_ROOT}/src/cpp/openjtalk_error.c
    ${PIPER_ROOT}/src/cpp/openjtalk_security.c
    ${PIPER_ROOT}/src/cpp/openjtalk_optimized.c
    ${PIPER_ROOT}/src/cpp/openjtalk_api.c
)

# ---------------------------------------------------------------------------
# Include paths
# ---------------------------------------------------------------------------
target_include_directories(piper_jni PRIVATE
    # Piper core headers (piper.hpp, json.hpp, phoneme_ids.hpp, utf8.h, etc.)
    ${PIPER_ROOT}/src/cpp

    # JNI utility headers (piper_jni_utils.h)
    ${CMAKE_CURRENT_SOURCE_DIR}/src/main/cpp
)

# ---------------------------------------------------------------------------
# Compile definitions — match the top-level project
# ---------------------------------------------------------------------------
target_compile_definitions(piper_jni PRIVATE
    SPDLOG_FMT_EXTERNAL=1
    FMT_HEADER_ONLY=1
    BUILD_ANDROID_JNI=1
)

# ---------------------------------------------------------------------------
# ONNX Runtime for Android
# ---------------------------------------------------------------------------
# Expects ONNXRUNTIME_DIR to point to the extracted ONNX Runtime Android
# package containing:
#   include/          onnxruntime_cxx_api.h, etc.
#   jni/<ABI>/        libonnxruntime.so
#
# When built through Gradle, the AAR dependency (onnxruntime-android) handles
# this automatically. For standalone CMake builds, set -DONNXRUNTIME_DIR=...
# ---------------------------------------------------------------------------
if(DEFINED ONNXRUNTIME_DIR)
    add_library(onnxruntime SHARED IMPORTED)
    set_target_properties(onnxruntime PROPERTIES
        IMPORTED_LOCATION "${ONNXRUNTIME_DIR}/jni/${ANDROID_ABI}/libonnxruntime.so"
        INTERFACE_INCLUDE_DIRECTORIES "${ONNXRUNTIME_DIR}/include"
    )
    target_link_libraries(piper_jni PRIVATE onnxruntime)
else()
    message(STATUS "ONNXRUNTIME_DIR not set -- assuming Gradle AAR provides ONNX Runtime")
endif()

# ---------------------------------------------------------------------------
# OpenJTalk for Android (static library, built per ABI)
# ---------------------------------------------------------------------------
# Expects OPENJTALK_DIR to contain:
#   include/            openjtalk headers
#   include/openjtalk/  additional headers (mecab.h, njd.h, jpcommon.h, etc.)
#   lib/                libopenjtalk.a (for the current ANDROID_ABI)
# ---------------------------------------------------------------------------
if(DEFINED OPENJTALK_DIR)
    add_library(openjtalk STATIC IMPORTED)
    set_target_properties(openjtalk PROPERTIES
        IMPORTED_LOCATION "${OPENJTALK_DIR}/lib/libopenjtalk.a"
        INTERFACE_INCLUDE_DIRECTORIES "${OPENJTALK_DIR}/include;${OPENJTALK_DIR}/include/openjtalk"
    )
    target_link_libraries(piper_jni PRIVATE openjtalk)
else()
    message(FATAL_ERROR "OPENJTALK_DIR is required for Android JNI build. "
            "Set -DOPENJTALK_DIR=/path/to/openjtalk-android")
endif()

# ---------------------------------------------------------------------------
# spdlog (header-only or pre-built for Android)
# ---------------------------------------------------------------------------
# piper.cpp, phoneme_parser.cpp, openjtalk_phonemize.cpp use spdlog for logging.
# On Android, spdlog is typically used in header-only mode.
# ---------------------------------------------------------------------------
if(DEFINED SPDLOG_DIR)
    target_include_directories(piper_jni PRIVATE "${SPDLOG_DIR}/include")
else()
    message(FATAL_ERROR "SPDLOG_DIR is required. "
            "Set -DSPDLOG_DIR=/path/to/spdlog (must contain include/spdlog/spdlog.h)")
endif()

# ---------------------------------------------------------------------------
# fmt (header-only, required by spdlog with SPDLOG_FMT_EXTERNAL)
# ---------------------------------------------------------------------------
if(DEFINED FMT_DIR)
    target_include_directories(piper_jni PRIVATE "${FMT_DIR}/include")
else()
    message(FATAL_ERROR "FMT_DIR is required. "
            "Set -DFMT_DIR=/path/to/fmt (must contain include/fmt/format.h)")
endif()

# ---------------------------------------------------------------------------
# Android system libraries
# ---------------------------------------------------------------------------
find_library(ANDROID_LOG_LIB log)
target_link_libraries(piper_jni PRIVATE
    ${ANDROID_LOG_LIB}
)

# ---------------------------------------------------------------------------
# Compiler flags
# ---------------------------------------------------------------------------
target_compile_options(piper_jni PRIVATE
    -Wall
    -Wextra
    -fvisibility=hidden     # Only export JNI_OnLoad and Java_* symbols
)

# ---------------------------------------------------------------------------
# Strip debug symbols in release builds for smaller .so
# ---------------------------------------------------------------------------
set_target_properties(piper_jni PROPERTIES
    # Let AGP / NDK handle stripping via CMAKE_BUILD_TYPE
    LINK_FLAGS_RELEASE "-s"
)
