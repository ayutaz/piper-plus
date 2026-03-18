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
#       piper_jni.cpp          JNI entry point (NativeBridge <-> piper core)
#
#   <project-root>/src/cpp/    Piper core C++ sources (piper.cpp, etc.)
#
# External dependencies (pre-built for Android):
#   - ONNX Runtime Android AAR  (headers + libonnxruntime.so per ABI)
#   - OpenJTalk static library   (libopenjtalk.a, built for each Android ABI)
#
# Usage (standalone, for reference only):
#   cmake -B build -G Ninja \
#       -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
#       -DANDROID_ABI=arm64-v8a \
#       -DANDROID_PLATFORM=android-24 \
#       -DONNXRUNTIME_DIR=/path/to/onnxruntime-android \
#       -DOPENJTALK_DIR=/path/to/openjtalk-android \
#       src/android/piper-android
#   cmake --build build
# =============================================================================

cmake_minimum_required(VERSION 3.22)

project(piper_jni CXX)

# ---------------------------------------------------------------------------
# C++ standard — match the top-level project
# ---------------------------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# Project root (three levels up from this CMakeLists.txt)
# ---------------------------------------------------------------------------
get_filename_component(PIPER_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

# ---------------------------------------------------------------------------
# JNI shared library target
# ---------------------------------------------------------------------------
add_library(piper_jni SHARED
    src/main/cpp/piper_jni.cpp
)

# ---------------------------------------------------------------------------
# Piper core sources (reused from the desktop build)
# Phase 2 will add these; for now the JNI stub compiles standalone.
# ---------------------------------------------------------------------------
# target_sources(piper_jni PRIVATE
#     ${PIPER_ROOT}/src/cpp/piper.cpp
#     ${PIPER_ROOT}/src/cpp/phoneme_parser.cpp
#     ${PIPER_ROOT}/src/cpp/language_detector.cpp
#     ${PIPER_ROOT}/src/cpp/english_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/chinese_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/korean_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/spanish_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/french_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/portuguese_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/openjtalk_phonemize.cpp
#     ${PIPER_ROOT}/src/cpp/openjtalk_phonemize_utils.cpp
#     ${PIPER_ROOT}/src/cpp/openjtalk_wrapper.c
#     ${PIPER_ROOT}/src/cpp/openjtalk_dictionary_manager.c
#     ${PIPER_ROOT}/src/cpp/openjtalk_error.c
#     ${PIPER_ROOT}/src/cpp/openjtalk_security.c
#     ${PIPER_ROOT}/src/cpp/openjtalk_optimized.c
#     ${PIPER_ROOT}/src/cpp/openjtalk_api.c
# )

# Piper core headers (available when core sources are enabled)
target_include_directories(piper_jni PRIVATE
    ${PIPER_ROOT}/src/cpp
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
    # Create an IMPORTED target for ONNX Runtime
    add_library(onnxruntime SHARED IMPORTED)
    set_target_properties(onnxruntime PROPERTIES
        IMPORTED_LOCATION "${ONNXRUNTIME_DIR}/jni/${ANDROID_ABI}/libonnxruntime.so"
        INTERFACE_INCLUDE_DIRECTORIES "${ONNXRUNTIME_DIR}/include"
    )
    target_link_libraries(piper_jni PRIVATE onnxruntime)
else()
    message(STATUS "ONNXRUNTIME_DIR not set — assuming Gradle AAR provides ONNX Runtime")
endif()

# ---------------------------------------------------------------------------
# OpenJTalk for Android (static library, built per ABI)
# ---------------------------------------------------------------------------
# Expects OPENJTALK_DIR to contain:
#   include/            openjtalk headers
#   include/openjtalk/  additional headers
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
    message(STATUS "OPENJTALK_DIR not set — OpenJTalk linking deferred to Phase 2")
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

# Strip debug symbols in release builds for smaller .so
set_target_properties(piper_jni PROPERTIES
    # Let AGP / NDK handle stripping via CMAKE_BUILD_TYPE
    LINK_FLAGS_RELEASE "-s"
)
