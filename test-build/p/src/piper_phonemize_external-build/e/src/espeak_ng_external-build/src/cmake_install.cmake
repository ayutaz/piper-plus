# Install script for directory: /Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external/src

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/ei")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external-build/src/espeak-ng")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/espeak-ng" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/espeak-ng")
    execute_process(COMMAND /usr/bin/install_name_tool
      -delete_rpath "/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external-build/src/libespeak-ng"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/espeak-ng")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" -u -r "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/espeak-ng")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE DIRECTORY FILES
    "/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external/src/include/espeak"
    "/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external/src/include/espeak-ng"
    )
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external-build/src/ucd-tools/cmake_install.cmake")
  include("/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external-build/src/speechPlayer/cmake_install.cmake")
  include("/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external-build/src/libespeak-ng/cmake_install.cmake")

endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/s19447/Desktop/piper/test-build/p/src/piper_phonemize_external-build/e/src/espeak_ng_external-build/src/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
