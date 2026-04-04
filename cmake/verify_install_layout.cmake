# verify_install_layout.cmake — Run with: cmake -DPREFIX=<install_prefix> -P verify_install_layout.cmake
# Verifies the install layout is correct on all platforms.

if(NOT DEFINED PREFIX)
  message(FATAL_ERROR "Usage: cmake -DPREFIX=<install_prefix> -P verify_install_layout.cmake")
endif()

set(_errors 0)

macro(check_exists path description)
  if(NOT EXISTS "${path}")
    message(WARNING "MISSING: ${description} — ${path}")
    math(EXPR _errors "${_errors} + 1")
  else()
    message(STATUS "  OK: ${description}")
  endif()
endmacro()

message(STATUS "Verifying install layout at: ${PREFIX}")

# Header
check_exists("${PREFIX}/include/piper_plus.h" "C API header")

# pkg-config
check_exists("${PREFIX}/lib/pkgconfig/piper_plus.pc" "pkg-config file")

# CMake Config
check_exists("${PREFIX}/lib/cmake/PiperPlus/PiperPlusConfig.cmake" "CMake Config")
check_exists("${PREFIX}/lib/cmake/PiperPlus/PiperPlusTargets.cmake" "CMake Targets")

# Platform-specific library checks
if(WIN32)
  check_exists("${PREFIX}/bin/piper_plus.dll" "Shared library (DLL)")
  check_exists("${PREFIX}/lib/piper_plus.lib" "Import library")
elseif(APPLE)
  file(GLOB _dylibs "${PREFIX}/lib/libpiper_plus*.dylib")
  list(LENGTH _dylibs _count)
  if(_count EQUAL 0)
    message(WARNING "MISSING: libpiper_plus.dylib")
    math(EXPR _errors "${_errors} + 1")
  else()
    message(STATUS "  OK: libpiper_plus.dylib (${_count} files)")
  endif()
else()
  # Linux
  file(GLOB _sos "${PREFIX}/lib/libpiper_plus.so*")
  list(LENGTH _sos _count)
  if(_count EQUAL 0)
    message(WARNING "MISSING: libpiper_plus.so")
    math(EXPR _errors "${_errors} + 1")
  else()
    message(STATUS "  OK: libpiper_plus.so (${_count} files including SOVERSION symlinks)")
  endif()
endif()

# ONNX Runtime shared library
if(WIN32)
  file(GLOB _ort_dlls "${PREFIX}/bin/onnxruntime*.dll")
  list(LENGTH _ort_dlls _ort_count)
  if(_ort_count EQUAL 0)
    message(WARNING "MISSING: ONNX Runtime DLL in bin/")
    math(EXPR _errors "${_errors} + 1")
  else()
    message(STATUS "  OK: ONNX Runtime DLLs (${_ort_count} files)")
  endif()
elseif(APPLE)
  file(GLOB _ort_dylibs "${PREFIX}/lib/libonnxruntime*.dylib")
  list(LENGTH _ort_dylibs _ort_count)
  if(_ort_count EQUAL 0)
    message(WARNING "MISSING: ONNX Runtime dylib in lib/")
    math(EXPR _errors "${_errors} + 1")
  else()
    message(STATUS "  OK: ONNX Runtime dylibs (${_ort_count} files)")
  endif()
else()
  file(GLOB _ort_sos "${PREFIX}/lib/libonnxruntime.so*")
  list(LENGTH _ort_sos _ort_count)
  if(_ort_count EQUAL 0)
    message(WARNING "MISSING: ONNX Runtime .so in lib/")
    math(EXPR _errors "${_errors} + 1")
  else()
    message(STATUS "  OK: ONNX Runtime .so (${_ort_count} files)")
  endif()
endif()

# SOVERSION symlinks (Linux)
if(NOT WIN32 AND NOT APPLE)
  check_exists("${PREFIX}/lib/libpiper_plus.so" "Linker symlink (libpiper_plus.so)")
  check_exists("${PREFIX}/lib/libpiper_plus.so.1" "SOVERSION symlink (libpiper_plus.so.1)")
endif()

# ConfigVersion
check_exists("${PREFIX}/lib/cmake/PiperPlus/PiperPlusConfigVersion.cmake" "CMake ConfigVersion")

# G2P dictionaries
check_exists("${PREFIX}/share/piper/dicts/cmudict_data.json" "CMU English dictionary")

# ONNX Runtime license
if(IS_DIRECTORY "${PREFIX}/share/licenses/onnxruntime")
  message(STATUS "  OK: ONNX Runtime license directory")
else()
  message(STATUS "  INFO: ONNX Runtime license directory not found (optional)")
endif()

# Summary
if(_errors GREATER 0)
  message(FATAL_ERROR "Install layout verification FAILED with ${_errors} error(s)")
else()
  message(STATUS "Install layout verification PASSED")
endif()
