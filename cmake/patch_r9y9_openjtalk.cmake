# Patch pyopenjtalk-plus's open_jtalk CMakeLists.txt for piper-plus integration
#
# Issues addressed:
# 1. install() is guarded by if(NOT MSVC) -> need install on all platforms
# 2. C++17 compatibility for MeCab's deprecated std::binary_function
#
# Note on install patch: The CMakeLists.txt uses cmake_minimum_required(VERSION 3.5),
# so CMP0012 is OLD and if(TRUE) is treated as a variable lookup (evaluates to false!).
# We use if(1) instead, which is always true regardless of CMP0012 policy.
#
# Note on C++17: GCC 11+ defaults to C++17 where std::binary_function is deprecated
# but still present. We use _GLIBCXX_USE_DEPRECATED=1 for GCC and _HAS_AUTO_PTR_ETC=1
# for MSVC to keep it available, avoiding the need for source polyfills.
#
# This script is called as PATCH_COMMAND with -D SOURCE_DIR=<SOURCE_DIR>

if(NOT DEFINED SOURCE_DIR)
  message(FATAL_ERROR "SOURCE_DIR must be defined")
endif()

set(CMAKELISTS_PATH "${SOURCE_DIR}/lib/open_jtalk/src/CMakeLists.txt")

if(NOT EXISTS "${CMAKELISTS_PATH}")
  message(FATAL_ERROR "CMakeLists.txt not found at ${CMAKELISTS_PATH}")
endif()

file(READ "${CMAKELISTS_PATH}" content)

# 1. Enable install on all platforms
#    The CMakeLists.txt guards install() with if(NOT MSVC).
#    Use if(1) because cmake_minimum_required may have CMP0012 OLD,
#    where if(TRUE) is treated as a variable lookup and evaluates to false.
string(REPLACE "if(NOT MSVC)" "if(1)  # Patched: install on all platforms" content "${content}")

# 2. Add C++17 compatibility definitions after project() call
#    MeCab uses std::binary_function which is deprecated in C++17.
#    These definitions keep it available without needing source changes.
string(REPLACE
  "project(openjtalk)"
  "project(openjtalk)\n\n# C++17 compatibility for MeCab std::binary_function (piper-plus patch)\nadd_compile_definitions(_GLIBCXX_USE_DEPRECATED=1)\nif(MSVC)\n  add_compile_definitions(_SILENCE_CXX17_ITERATOR_BASE_CLASS_DEPRECATION_WARNING)\n  add_compile_definitions(_HAS_AUTO_PTR_ETC=1)\nendif()"
  content "${content}"
)

file(WRITE "${CMAKELISTS_PATH}" "${content}")
message(STATUS "Successfully patched pyopenjtalk-plus's open_jtalk CMakeLists.txt")
