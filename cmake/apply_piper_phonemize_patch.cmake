cmake_minimum_required(VERSION 3.15)

# Inputs:
#  - SOURCE_DIR: path to the downloaded piper-phonemize source directory

if(NOT DEFINED SOURCE_DIR)
  message(FATAL_ERROR "apply_piper_phonemize_patch.cmake: SOURCE_DIR is not defined")
endif()

set(src "${SOURCE_DIR}/CMakeLists.txt")
if(NOT EXISTS "${src}")
  message(FATAL_ERROR "apply_piper_phonemize_patch.cmake: CMakeLists.txt not found under ${SOURCE_DIR}")
endif()

# Read file to check if already patched
file(READ "${src}" contents)
string(FIND "${contents}" "/utf-8" already)
if(NOT already EQUAL -1)
  message(STATUS "piper-phonemize already contains /utf-8 settings; skipping patch")
  return()
endif()

message(STATUS "Patching piper-phonemize CMakeLists.txt to force MSVC UTF-8")

set(patch "\n# Injected by piper-plus build: force UTF-8 on MSVC for all subprojects\nif(MSVC)\n  add_compile_options(\"$<$<COMPILE_LANGUAGE:C>:/utf-8>\" \"$<$<COMPILE_LANGUAGE:CXX>:/utf-8>\")\nendif()\n")

file(APPEND "${src}" "${patch}")

message(STATUS "Applied UTF-8 compile options to ${src}")

