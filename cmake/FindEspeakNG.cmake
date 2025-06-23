# FindEspeakNG.cmake
# Find the espeak-ng library
#
# This module defines:
#   ESPEAK_NG_FOUND - True if espeak-ng was found
#   ESPEAK_NG_INCLUDE_DIRS - The espeak-ng include directories
#   ESPEAK_NG_LIBRARIES - The libraries needed to use espeak-ng
#   espeak-ng::espeak-ng - Imported target

include(FindPackageHandleStandardArgs)

# Try to find espeak-ng using pkg-config first (for Unix systems)
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND AND NOT MSVC)
  pkg_check_modules(PC_ESPEAK_NG QUIET espeak-ng)
endif()

# Find include directory
find_path(ESPEAK_NG_INCLUDE_DIR
  NAMES espeak-ng/speak_lib.h speak_lib.h
  HINTS
    ${PC_ESPEAK_NG_INCLUDEDIR}
    ${PC_ESPEAK_NG_INCLUDE_DIRS}
    ${ESPEAK_NG_ROOT}/include
    ${ESPEAK_NG_ROOT}
  PATH_SUFFIXES espeak-ng
)

# Find library
if(MSVC)
  find_library(ESPEAK_NG_LIBRARY
    NAMES espeak-ng.lib libespeak-ng.lib espeak-ng libespeak-ng
    HINTS
      ${ESPEAK_NG_ROOT}/lib
      ${ESPEAK_NG_ROOT}/bin
      ${PC_ESPEAK_NG_LIBDIR}
      ${PC_ESPEAK_NG_LIBRARY_DIRS}
  )
else()
  find_library(ESPEAK_NG_LIBRARY
    NAMES espeak-ng
    HINTS
      ${PC_ESPEAK_NG_LIBDIR}
      ${PC_ESPEAK_NG_LIBRARY_DIRS}
      ${ESPEAK_NG_ROOT}/lib
  )
endif()

# Handle the QUIETLY and REQUIRED arguments
find_package_handle_standard_args(EspeakNG
  DEFAULT_MSG
  ESPEAK_NG_LIBRARY
  ESPEAK_NG_INCLUDE_DIR
)

if(ESPEAK_NG_FOUND)
  set(ESPEAK_NG_LIBRARIES ${ESPEAK_NG_LIBRARY})
  set(ESPEAK_NG_INCLUDE_DIRS ${ESPEAK_NG_INCLUDE_DIR})
  
  # Create imported target
  if(NOT TARGET espeak-ng::espeak-ng)
    add_library(espeak-ng::espeak-ng UNKNOWN IMPORTED)
    set_target_properties(espeak-ng::espeak-ng PROPERTIES
      IMPORTED_LOCATION "${ESPEAK_NG_LIBRARY}"
      INTERFACE_INCLUDE_DIRECTORIES "${ESPEAK_NG_INCLUDE_DIR}"
    )
  endif()
endif()

mark_as_advanced(ESPEAK_NG_INCLUDE_DIR ESPEAK_NG_LIBRARY)