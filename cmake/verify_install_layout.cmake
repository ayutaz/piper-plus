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

# Summary
if(_errors GREATER 0)
  message(FATAL_ERROR "Install layout verification FAILED with ${_errors} error(s)")
else()
  message(STATUS "Install layout verification PASSED")
endif()
