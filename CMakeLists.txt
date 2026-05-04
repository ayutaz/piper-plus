cmake_minimum_required(VERSION 3.15)

# Set runtime library BEFORE project() to ensure it's applied globally
if(MSVC)
  # Use dynamic runtime library to match ONNX Runtime
  # This is required for compatibility with pre-built ONNX Runtime binaries
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL$<$<CONFIG:Debug>:Debug>" CACHE STRING "MSVC Runtime Library" FORCE)
  # Ensure new CMake policy for MSVC runtime library selection
  cmake_policy(SET CMP0091 NEW)
endif()

project(piper C CXX)

file(READ "${CMAKE_CURRENT_LIST_DIR}/VERSION" piper_version)
string(STRIP "${piper_version}" piper_version)

option(USE_CUDA "Enable CUDA support for GPU acceleration" OFF)

# Detect Apple "embedded" / sandboxed platforms (iOS / iPadOS / tvOS / watchOS
# / visionOS) where std::system / popen / fork are unavailable in the App
# Sandbox. Used throughout the cmake/ tree to exclude the desktop-only
# OpenJTalk / model-manager pipeline and toggle install / EXPORT generation.
# Mac Catalyst (CMAKE_SYSTEM_NAME == "Darwin" with iOS deployment target) is
# NOT covered here — Catalyst projects can spawn helper tools, so they take
# the desktop path. Future Catalyst-specific issues should be handled
# separately.
if(CMAKE_SYSTEM_NAME MATCHES "^(iOS|tvOS|watchOS|visionOS)$")
  set(PIPER_APPLE_EMBEDDED ON)
else()
  set(PIPER_APPLE_EMBEDDED OFF)
endif()

# ==== Compiler flags, C/C++ standards, Android/ARM64 settings ====
include(cmake/CompilerSettings.cmake)

# ==== Google Test FetchContent (option BUILD_TESTS) ====
include(cmake/Testing.cmake)

# ==== piper_common OBJECT library (sources only, no includes yet) ====
include(cmake/PiperCommon.cmake)

# ==== piper / test_piper executables (creation + RPATH, no linking yet) ====
include(cmake/PiperExecutable.cmake)

# ==== External dependencies: fmt, spdlog, HTS Engine, OpenJTalk ====
include(cmake/ExternalDeps.cmake)

# ==== ONNX Runtime download / detection ====
include(cmake/OnnxRuntime.cmake)

# ---- piper_common include directories and compile definitions ----
# Configured here because ExternalDeps.cmake and OnnxRuntime.cmake
# set the directory variables (FMT_DIR, SPDLOG_DIR, OPENJTALK_DIR, etc.).
target_include_directories(piper_common PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
  ${OPENJTALK_DIR}/include
  ${OPENJTALK_DIR}/include/openjtalk
  ${HTS_STUB_DIR}/include
)
add_dependencies(piper_common hts_engine_stub)
target_compile_definitions(piper_common PUBLIC
  _PIPER_VERSION=${piper_version}
  SPDLOG_FMT_EXTERNAL=1
  FMT_HEADER_ONLY=1
)
if(WIN32 AND ONNXRUNTIME_INCLUDE_DIR)
  target_include_directories(piper_common PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
endif()

# ==== piper / test_piper linking, includes, compile defs ====
include(cmake/PiperLink.cmake)

# ==== piper_plus SHARED library (C API) ====
include(cmake/PiperPlusShared.cmake)

# ==== Add test subdirectory (after all ExternalProject targets are defined) ====
if(BUILD_TESTS AND NOT ANDROID AND NOT PIPER_APPLE_EMBEDDED)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/tests")
    add_subdirectory(src/cpp/tests)
  endif()
endif()

# ==== Install rules + Windows DLL handling ====
include(cmake/Install.cmake)
