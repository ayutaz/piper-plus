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

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set C standard for better compatibility
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(MSVC)
  # Force compiler to use UTF-8 for IPA constants
  add_compile_options("$<$<C_COMPILER_ID:MSVC>:/utf-8>")
  add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/utf-8>")
  
  # Additional Windows-specific flags
  add_compile_options(/EHsc)  # Enable C++ exceptions
  add_compile_options(/W3)    # Warning level 3
  
  # Define Windows version macros
  add_compile_definitions(WIN32_LEAN_AND_MEAN)
  add_compile_definitions(_WIN32_WINNT=0x0601)  # Windows 7 and later
elseif(APPLE)
  # macOS flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
else()
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  # Set RPATH for installed binaries
  set(CMAKE_INSTALL_RPATH "$ORIGIN" "$ORIGIN/../lib")
  set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
  set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
endif()

option(USE_CUDA "Enable CUDA support for GPU acceleration" OFF)

# ARM64-specific optimizations
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  message(STATUS "Detected ARM64 architecture, enabling optimizations")
  
  # Enable NEON SIMD instructions
  if(NOT MSVC)
    # Use compatible ARM64 flags for QEMU
    # Avoid advanced instructions that might not be properly emulated
    set(ARM64_FLAGS "-march=armv8-a -mtune=generic")
    string(APPEND CMAKE_CXX_FLAGS " ${ARM64_FLAGS}")
    string(APPEND CMAKE_C_FLAGS " ${ARM64_FLAGS}")
    
    # Conservative optimization for QEMU compatibility
    set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")
    set(CMAKE_C_FLAGS_RELEASE "-O2 -DNDEBUG")
    
    # Enable Link Time Optimization for release builds
    if(CMAKE_BUILD_TYPE STREQUAL "Release")
      include(CheckIPOSupported)
      check_ipo_supported(RESULT ipo_supported OUTPUT error)
      if(ipo_supported)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
        message(STATUS "Link Time Optimization enabled for ARM64")
      endif()
    endif()
    
    # Strip symbols for smaller binaries
    set(CMAKE_EXE_LINKER_FLAGS_RELEASE "-s")
  endif()
  
  # Temporarily disable NEON for debugging
  # add_compile_definitions(USE_ARM64_NEON)
endif()

add_executable(piper src/cpp/main.cpp src/cpp/piper.cpp src/cpp/phoneme_parser.cpp src/cpp/custom_dictionary.cpp)
add_executable(test_piper src/cpp/test.cpp src/cpp/piper.cpp src/cpp/phoneme_parser.cpp src/cpp/custom_dictionary.cpp)

# Add NEON optimized audio processing for ARM64
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  target_sources(piper PRIVATE src/cpp/audio_neon.cpp)
  target_sources(test_piper PRIVATE src/cpp/audio_neon.cpp)
endif()


# Testing support
option(BUILD_TESTS "Build unit tests" OFF)
if(BUILD_TESTS)
  enable_testing()
  
  # Use FetchContent for Google Test
  include(FetchContent)
  FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
  )
  # For Windows: Prevent overriding the parent project's compiler/linker settings
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)
  
  # Only add tests directory if it exists
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/tests")
    add_subdirectory(src/cpp/tests)
  endif()
endif()

# Add OpenJTalk support on all platforms
target_sources(piper PRIVATE
  src/cpp/openjtalk_phonemize.cpp
  src/cpp/openjtalk_wrapper.c
  src/cpp/openjtalk_dictionary_manager.c
  src/cpp/openjtalk_error.c
  src/cpp/openjtalk_security.c
  src/cpp/openjtalk_optimized.c
  # src/cpp/openjtalk_api.c  # Temporarily disabled - requires OpenJTalk static libs
)
target_sources(test_piper PRIVATE
  src/cpp/openjtalk_phonemize.cpp
  src/cpp/openjtalk_wrapper.c
  src/cpp/openjtalk_dictionary_manager.c
  src/cpp/openjtalk_error.c
  src/cpp/openjtalk_security.c
  src/cpp/openjtalk_optimized.c
  # src/cpp/openjtalk_api.c  # Temporarily disabled - requires OpenJTalk static libs
)

# Link pthread library on Unix systems
if(UNIX AND NOT APPLE)
  find_package(Threads REQUIRED)
  target_link_libraries(piper PRIVATE Threads::Threads)
  target_link_libraries(test_piper PRIVATE Threads::Threads)
endif()

# Configure RPATH for macOS
if(APPLE)
  set_target_properties(piper PROPERTIES
    MACOSX_RPATH TRUE
    INSTALL_RPATH "@executable_path/../lib;@loader_path/../lib;${PIPER_PHONEMIZE_DIR}/lib"
    BUILD_WITH_INSTALL_RPATH FALSE
    BUILD_RPATH "${PIPER_PHONEMIZE_DIR}/lib"
  )
  set_target_properties(test_piper PROPERTIES
    MACOSX_RPATH TRUE
    INSTALL_RPATH "@executable_path/../lib;@loader_path/../lib;${PIPER_PHONEMIZE_DIR}/lib"
    BUILD_WITH_INSTALL_RPATH FALSE
    BUILD_RPATH "${PIPER_PHONEMIZE_DIR}/lib"
  )
endif()

# NOTE: external project prefix are shortened because of path length restrictions on Windows
# NOTE: onnxruntime is pulled from piper-phonemize

# ---- fmt ---

if(NOT DEFINED FMT_DIR)
  set(FMT_VERSION "10.0.0")
  set(FMT_DIR "${CMAKE_CURRENT_BINARY_DIR}/fi")

  include(ExternalProject)
  # Pass architecture settings to external projects
  if(APPLE)
    # Apple Silicon (arm64) only
    set(EXTERNAL_CMAKE_ARGS -DCMAKE_OSX_ARCHITECTURES=arm64)
  else()
    set(EXTERNAL_CMAKE_ARGS "")
  endif()
  
  # Ensure MSVC runtime library is propagated to all external projects
  if(MSVC)
    list(APPEND EXTERNAL_CMAKE_ARGS
      -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
      -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
      -DCMAKE_CXX_FLAGS_RELEASE=/MD
      -DCMAKE_CXX_FLAGS_DEBUG=/MDd
      -DCMAKE_C_FLAGS_RELEASE=/MD
      -DCMAKE_C_FLAGS_DEBUG=/MDd
    )
  endif()

  ExternalProject_Add(
    fmt_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/f"
    URL "https://github.com/fmtlib/fmt/archive/refs/tags/${FMT_VERSION}.zip"
    DOWNLOAD_NO_PROGRESS TRUE
    TIMEOUT 600  # 10 minutes timeout
    TLS_VERIFY ON
    DOWNLOAD_TRIES 3  # Retry download 3 times
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${FMT_DIR}
               -DFMT_TEST:BOOL=OFF  # Don't build all the tests
               -DFMT_HEADER_ONLY:BOOL=ON  # Build as header-only library
               -DBUILD_SHARED_LIBS:BOOL=OFF  # Build static libraries
               ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(piper fmt_external)
  add_dependencies(test_piper fmt_external)
endif()

# ---- spdlog ---

if(NOT DEFINED SPDLOG_DIR)
  set(SPDLOG_DIR "${CMAKE_CURRENT_BINARY_DIR}/si")
  set(SPDLOG_VERSION "1.12.0")
  ExternalProject_Add(
    spdlog_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/s"
    URL "https://github.com/gabime/spdlog/archive/refs/tags/v${SPDLOG_VERSION}.zip"
    DOWNLOAD_NO_PROGRESS TRUE
    TIMEOUT 600  # 10 minutes timeout
    TLS_VERIFY ON
    DOWNLOAD_TRIES 3  # Retry download 3 times
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${SPDLOG_DIR}
               -DSPDLOG_BUILD_SHARED:BOOL=OFF  # Build static libraries
               -DSPDLOG_FMT_EXTERNAL:BOOL=ON  # Use external fmt
               -DCMAKE_PREFIX_PATH:PATH=${FMT_DIR}
               -DFMT_HEADER_ONLY:BOOL=ON  # Use fmt as header-only
               ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(spdlog_external fmt_external)
  add_dependencies(piper spdlog_external)
  add_dependencies(test_piper spdlog_external)
endif()

# ---- piper-phonemize ---

if(NOT DEFINED PIPER_PHONEMIZE_DIR)
  set(PIPER_PHONEMIZE_DIR "${CMAKE_CURRENT_BINARY_DIR}/pi")
  # On Windows, we need espeak-ng as a shared library for proper functioning
  if(WIN32)
    set(PIPER_PHONEMIZE_SHARED_LIBS ON)
  else()
    # Use static linking for ARM64 to avoid QEMU issues
    set(PIPER_PHONEMIZE_SHARED_LIBS OFF)
  endif()
  
  # NOTE: Using master branch HEAD. For reproducible builds, pin to a specific commit:
  # URL "https://github.com/rhasspy/piper-phonemize/archive/<commit-hash>.zip"
  ExternalProject_Add(
    piper_phonemize_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/p"
    URL "https://github.com/rhasspy/piper-phonemize/archive/refs/heads/master.zip"
    DOWNLOAD_NO_PROGRESS TRUE
    TIMEOUT 600  # 10 minutes timeout
    TLS_VERIFY ON
    DOWNLOAD_TRIES 3  # Retry download 3 times
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${PIPER_PHONEMIZE_DIR}
    CMAKE_ARGS -DBUILD_SHARED_LIBS:BOOL=${PIPER_PHONEMIZE_SHARED_LIBS}
    CMAKE_ARGS -DESPEAK_NG_BUILD_SHARED:BOOL=${PIPER_PHONEMIZE_SHARED_LIBS}
    CMAKE_ARGS -DCMAKE_MSVC_RUNTIME_LIBRARY:STRING=${CMAKE_MSVC_RUNTIME_LIBRARY}
    CMAKE_ARGS ${EXTERNAL_CMAKE_ARGS}
    # Patch piper-phonemize sources to force UTF-8 on MSVC for all subprojects
    PATCH_COMMAND
      ${CMAKE_COMMAND} -D SOURCE_DIR=<SOURCE_DIR> -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/apply_piper_phonemize_patch.cmake
    # Ensure nested builds (e.g., espeak-ng) receive MSVC UTF-8 option even if flags are overridden
    BUILD_COMMAND ${CMAKE_COMMAND} -E env CL=/utf-8 ${CMAKE_COMMAND} --build <BINARY_DIR> --config $<CONFIG>
    INSTALL_COMMAND ${CMAKE_COMMAND} -E env CL=/utf-8 ${CMAKE_COMMAND} --build <BINARY_DIR> --target install --config $<CONFIG>
  )
  add_dependencies(piper piper_phonemize_external)
  add_dependencies(test_piper piper_phonemize_external)
endif()

# Runtime library is already set globally via CMAKE_MSVC_RUNTIME_LIBRARY
# No need to set per-target properties

# ---- ONNX Runtime for Windows ---
if(WIN32)
  include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/find_onnxruntime_windows.cmake)
endif()

# ---- HTSEngine ---

# HTSEngine stub for phonemizer-only mode
option(USE_HTS_ENGINE_STUB "Use HTS Engine stub (phonemizer-only mode)" ON)

if(USE_HTS_ENGINE_STUB)
  # Use stub instead of real HTS Engine
  set(HTS_ENGINE_DIR "${CMAKE_CURRENT_BINARY_DIR}/hts_stub")
  file(MAKE_DIRECTORY ${HTS_ENGINE_DIR}/include)
  file(MAKE_DIRECTORY ${HTS_ENGINE_DIR}/lib)
  
  # Copy stub files
  configure_file(${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_stub.h 
                 ${HTS_ENGINE_DIR}/include/HTS_engine.h COPYONLY)
  
  # Build stub library
  add_library(hts_engine_stub STATIC ${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_stub.c)
  target_include_directories(hts_engine_stub PUBLIC ${HTS_ENGINE_DIR}/include)
  if(WIN32)
    set_target_properties(hts_engine_stub PROPERTIES 
      ARCHIVE_OUTPUT_DIRECTORY ${HTS_ENGINE_DIR}/lib
      OUTPUT_NAME HTSEngine
      PREFIX "")
  else()
    set_target_properties(hts_engine_stub PROPERTIES 
      ARCHIVE_OUTPUT_DIRECTORY ${HTS_ENGINE_DIR}/lib
      OUTPUT_NAME HTSEngine
      PREFIX "lib")
  endif()
    
  # Ensure the stub library is built and create a symlink/copy for compatibility
  if(WIN32)
    add_custom_command(TARGET hts_engine_stub POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E make_directory ${HTS_ENGINE_DIR}/lib
      COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:hts_engine_stub> ${HTS_ENGINE_DIR}/lib/HTSEngine.lib
      COMMENT "Ensuring HTS Engine stub library is in expected location (Windows)"
    )
  else()
    add_custom_command(TARGET hts_engine_stub POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E make_directory ${HTS_ENGINE_DIR}/lib
      COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:hts_engine_stub> ${HTS_ENGINE_DIR}/lib/libHTSEngine.a
      COMMENT "Ensuring HTS Engine stub library is in expected location (Unix)"
    )
  endif()
    
  # Create dummy target for dependencies
  add_custom_target(hts_engine_external DEPENDS hts_engine_stub)
  
elseif(NOT DEFINED HTS_ENGINE_DIR)
    set(HTS_ENGINE_DIR "${CMAKE_CURRENT_BINARY_DIR}/he")
    set(HTS_ENGINE_VERSION "1.10")

    if(WIN32)
      # Use CMake build for Windows
      ExternalProject_Add(
        hts_engine_external
        PREFIX "${CMAKE_CURRENT_BINARY_DIR}/h"
        URL "https://downloads.sourceforge.net/project/hts-engine/hts_engine%20API/hts_engine_API-${HTS_ENGINE_VERSION}/hts_engine_API-${HTS_ENGINE_VERSION}.tar.gz"
        CMAKE_ARGS 
          -DCMAKE_INSTALL_PREFIX:PATH=${HTS_ENGINE_DIR}
          -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
          -DBUILD_SHARED_LIBS:BOOL=OFF
          -DHTS_EMBEDDED:BOOL=ON
          -DCMAKE_MSVC_RUNTIME_LIBRARY:STRING=${CMAKE_MSVC_RUNTIME_LIBRARY}
          ${EXTERNAL_CMAKE_ARGS}
        PATCH_COMMAND ${CMAKE_COMMAND} -E copy 
          ${CMAKE_CURRENT_SOURCE_DIR}/cmake/HTSEngine_CMakeLists.txt 
          <SOURCE_DIR>/CMakeLists.txt
        BUILD_BYPRODUCTS ${HTS_ENGINE_DIR}/lib/HTSEngine.lib
      )
    else()
      # Use autotools for Unix platforms
      # Set architecture flags for configure scripts
      if(APPLE)
        # Apple Silicon (arm64) only
        set(CONFIGURE_HOST "--host=aarch64-apple-darwin")
        set(CONFIGURE_ENV "CFLAGS=-arch arm64" "CXXFLAGS=-arch arm64" "LDFLAGS=-arch arm64")
      elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
        # Linux ARM64 cross-compilation
        set(CONFIGURE_HOST "--host=aarch64-linux-gnu")
        set(CONFIGURE_ENV "CC=aarch64-linux-gnu-gcc" "CXX=aarch64-linux-gnu-g++" "AR=aarch64-linux-gnu-ar" "RANLIB=aarch64-linux-gnu-ranlib")
      else()
        set(CONFIGURE_HOST "")
        set(CONFIGURE_ENV "")
      endif()

      ExternalProject_Add(
        hts_engine_external
        PREFIX "${CMAKE_CURRENT_BINARY_DIR}/h"
        URL "https://downloads.sourceforge.net/project/hts-engine/hts_engine%20API/hts_engine_API-${HTS_ENGINE_VERSION}/hts_engine_API-${HTS_ENGINE_VERSION}.tar.gz"
        CONFIGURE_COMMAND ${CMAKE_COMMAND} -E env ${CONFIGURE_ENV} ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> ./configure --prefix=${HTS_ENGINE_DIR} ${CONFIGURE_HOST}
        BUILD_COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> make
        INSTALL_COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> make install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS ${HTS_ENGINE_DIR}/lib/libHTSEngine.a
      )
    endif()
endif()

# ---- OpenJTalk ---

if(NOT DEFINED OPENJTALK_DIR)
    set(OPENJTALK_DIR "${CMAKE_CURRENT_BINARY_DIR}/oj")
    set(OPENJTALK_VERSION "1.11")

    # Use CMake build for Windows and Linux ARM64
    if(WIN32 OR (CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux"))
      # Use CMake build for Windows and Linux ARM64
      set(OPENJTALK_CMAKE_ARGS
        -DCMAKE_INSTALL_PREFIX:PATH=${OPENJTALK_DIR}
        -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
        -DBUILD_SHARED_LIBS:BOOL=OFF
        -DHTS_ENGINE_INCLUDE_DIR:PATH=${HTS_ENGINE_DIR}/include
        ${EXTERNAL_CMAKE_ARGS}
      )
      
      # Platform-specific settings
      if(WIN32)
        list(APPEND OPENJTALK_CMAKE_ARGS
          -DHTS_ENGINE_LIB:FILEPATH=${HTS_ENGINE_DIR}/lib/HTSEngine.lib
          -DCMAKE_MSVC_RUNTIME_LIBRARY:STRING=${CMAKE_MSVC_RUNTIME_LIBRARY}
        )
      else()
        # Linux ARM64
        list(APPEND OPENJTALK_CMAKE_ARGS
          -DHTS_ENGINE_LIB:FILEPATH=${HTS_ENGINE_DIR}/lib/libHTSEngine.a
          -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
          -DCMAKE_C_COMPILER:FILEPATH=aarch64-linux-gnu-gcc
          -DCMAKE_CXX_COMPILER:FILEPATH=aarch64-linux-gnu-g++
          -DCMAKE_AR:FILEPATH=aarch64-linux-gnu-ar
          -DCMAKE_RANLIB:FILEPATH=aarch64-linux-gnu-ranlib
        )
      endif()
      
      if(WIN32)
        ExternalProject_Add(
          openjtalk_external
          PREFIX "${CMAKE_CURRENT_BINARY_DIR}/o"
          URL "https://downloads.sourceforge.net/project/open-jtalk/Open%20JTalk/open_jtalk-${OPENJTALK_VERSION}/open_jtalk-${OPENJTALK_VERSION}.tar.gz"
          CMAKE_ARGS ${OPENJTALK_CMAKE_ARGS}
          PATCH_COMMAND 
            ${CMAKE_COMMAND} -E copy 
              ${CMAKE_CURRENT_SOURCE_DIR}/cmake/OpenJTalk_CMakeLists.txt 
              <SOURCE_DIR>/CMakeLists.txt
            COMMAND ${CMAKE_COMMAND} -E copy
              ${CMAKE_CURRENT_SOURCE_DIR}/cmake/open_jtalk_phonemizer.c
              <SOURCE_DIR>/bin/open_jtalk_phonemizer.c
            COMMAND ${CMAKE_COMMAND} -E copy
              ${CMAKE_CURRENT_SOURCE_DIR}/cmake/apply_openjtalk_patch.ps1
              <SOURCE_DIR>/apply_patch.ps1
            COMMAND powershell -ExecutionPolicy Bypass -File "<SOURCE_DIR>/apply_patch.ps1" -SourceDir "<SOURCE_DIR>"
          BUILD_BYPRODUCTS
            ${OPENJTALK_DIR}/bin/open_jtalk.exe
            ${OPENJTALK_DIR}/bin/open_jtalk_phonemizer.exe
        )
      else()
        # Linux ARM64
        ExternalProject_Add(
          openjtalk_external
          PREFIX "${CMAKE_CURRENT_BINARY_DIR}/o"
          URL "https://downloads.sourceforge.net/project/open-jtalk/Open%20JTalk/open_jtalk-${OPENJTALK_VERSION}/open_jtalk-${OPENJTALK_VERSION}.tar.gz"
          CMAKE_ARGS ${OPENJTALK_CMAKE_ARGS}
          PATCH_COMMAND 
            ${CMAKE_COMMAND} -E copy 
              ${CMAKE_CURRENT_SOURCE_DIR}/cmake/OpenJTalk_CMakeLists.txt 
              <SOURCE_DIR>/CMakeLists.txt
            COMMAND ${CMAKE_COMMAND} -E copy
              ${CMAKE_CURRENT_SOURCE_DIR}/cmake/open_jtalk_phonemizer.c
              <SOURCE_DIR>/bin/open_jtalk_phonemizer.c
            COMMAND ${CMAKE_COMMAND} -E copy
              ${CMAKE_CURRENT_SOURCE_DIR}/cmake/open_jtalk_patch.sh
              <SOURCE_DIR>/apply_patch.sh
            COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> chmod +x apply_patch.sh
            COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> ./apply_patch.sh
          BUILD_BYPRODUCTS
            ${OPENJTALK_DIR}/bin/open_jtalk
            ${OPENJTALK_DIR}/bin/open_jtalk_phonemizer
        )
      endif()
      
      add_dependencies(openjtalk_external hts_engine_external)
    else()
      # Use autotools for Unix platforms
      set(OPENJTALK_CONFIGURE_CMD ${CMAKE_COMMAND} -E env ${CONFIGURE_ENV} ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> ./configure
        --prefix=${OPENJTALK_DIR}
        --with-hts-engine-header-path=${HTS_ENGINE_DIR}/include
        --with-hts-engine-library-path=${HTS_ENGINE_DIR}/lib
        --with-charset=UTF-8
        ${CONFIGURE_HOST})
      
      ExternalProject_Add(
        openjtalk_external
        PREFIX "${CMAKE_CURRENT_BINARY_DIR}/o"
        URL "https://downloads.sourceforge.net/project/open-jtalk/Open%20JTalk/open_jtalk-${OPENJTALK_VERSION}/open_jtalk-${OPENJTALK_VERSION}.tar.gz"
        PATCH_COMMAND 
          ${CMAKE_COMMAND} -E copy 
            ${CMAKE_CURRENT_SOURCE_DIR}/cmake/open_jtalk_phonemizer.c
            <SOURCE_DIR>/bin/open_jtalk_phonemizer.c
        CONFIGURE_COMMAND ${OPENJTALK_CONFIGURE_CMD}
        BUILD_COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> make
        INSTALL_COMMAND 
          ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> make install
          COMMAND ${CMAKE_COMMAND} -E copy
            ${CMAKE_CURRENT_SOURCE_DIR}/cmake/build_openjtalk_phonemizer.sh
            <SOURCE_DIR>/build_phonemizer.sh
          COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> chmod +x build_phonemizer.sh
          COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> ./build_phonemizer.sh
            ${CMAKE_CXX_COMPILER} ${OPENJTALK_DIR} ${HTS_ENGINE_DIR}
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
          ${OPENJTALK_DIR}/bin/open_jtalk
          ${OPENJTALK_DIR}/bin/open_jtalk_phonemizer
      )
      
      add_dependencies(openjtalk_external hts_engine_external)
    endif()
endif()

# ---- Declare executable ----

if(APPLE)
  # macOS-specific settings
  set(PIPER_EXTRA_LIBRARIES "pthread")
  # Find Homebrew-installed espeak-ng
  if(CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
    set(HOMEBREW_PREFIX "/usr/local")
  else()
    set(HOMEBREW_PREFIX "/opt/homebrew")
  endif()
elseif(NOT MSVC)
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra -Wl,-rpath,'$ORIGIN'")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  target_link_libraries(piper PRIVATE -static-libgcc -static-libstdc++)

  set(PIPER_EXTRA_LIBRARIES "pthread")
endif()

# Platform-specific library linking
if(WIN32)
  # Windows: Link libraries directly with generator expressions for debug/release
  target_link_libraries(piper PRIVATE
    optimized ${FMT_DIR}/lib/fmt.lib
    debug ${FMT_DIR}/lib/fmtd.lib
    optimized ${SPDLOG_DIR}/lib/spdlog.lib
    debug ${SPDLOG_DIR}/lib/spdlogd.lib
    ${PIPER_PHONEMIZE_DIR}/lib/piper_phonemize.lib
    ${PIPER_PHONEMIZE_DIR}/lib/espeak-ng.lib
    ${ONNXRUNTIME_LIB}
    ${PIPER_EXTRA_LIBRARIES}
  )
else()
  # Unix: Use standard library names
  target_link_libraries(piper PRIVATE
    fmt
    spdlog
    piper_phonemize
    espeak-ng
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
endif()

# Link OpenJTalk libraries
# Ensure OpenJTalk is built before linking
add_dependencies(piper openjtalk_external)
add_dependencies(test_piper openjtalk_external)

# Link HTS_Engine (required for OpenJTalk build)
add_dependencies(piper hts_engine_external)
add_dependencies(test_piper hts_engine_external)

if(USE_HTS_ENGINE_STUB)
  target_link_libraries(piper PRIVATE hts_engine_stub)
  target_link_libraries(test_piper PRIVATE hts_engine_stub)
else()
  if(WIN32)
    target_link_libraries(piper PRIVATE
      ${CMAKE_CURRENT_BINARY_DIR}/he/lib/HTSEngine.lib
    )
    target_link_libraries(test_piper PRIVATE
      ${CMAKE_CURRENT_BINARY_DIR}/he/lib/HTSEngine.lib
    )
  else()
    target_link_libraries(piper PRIVATE
      ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a
    )
    target_link_libraries(test_piper PRIVATE
      ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a
    )
  endif()
endif()

target_link_directories(piper PUBLIC
  ${FMT_DIR}/lib
  ${SPDLOG_DIR}/lib
  ${PIPER_PHONEMIZE_DIR}/lib
)

# Note: We don't need Homebrew paths for espeak-ng on macOS
# because we're using the custom build from piper_phonemize

target_include_directories(piper PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
  ${PIPER_PHONEMIZE_DIR}/include
)

# Add ONNX Runtime include directory for Windows
if(WIN32 AND ONNXRUNTIME_INCLUDE_DIR)
  target_include_directories(piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
  target_include_directories(test_piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
endif()

# Include OpenJTalk headers
target_include_directories(piper PUBLIC
  ${OPENJTALK_DIR}/include
)
target_include_directories(test_piper PUBLIC
  ${OPENJTALK_DIR}/include
)

# Include HTSEngine headers (required for OpenJTalk)
target_include_directories(piper PUBLIC
  ${HTS_ENGINE_DIR}/include
)
target_include_directories(test_piper PUBLIC
  ${HTS_ENGINE_DIR}/include
)

# OpenJTalk is used via binary execution, includes not needed

target_compile_definitions(piper PUBLIC _PIPER_VERSION=${piper_version})
target_compile_definitions(piper PUBLIC SPDLOG_FMT_EXTERNAL=1)
target_compile_definitions(piper PUBLIC FMT_HEADER_ONLY=1)

# Add OpenJTalk dictionary path definition
if(TRUE)  # HTSEngine and OpenJTalk are built
  # Dictionary will be downloaded by CI/CD or provided by user
  # Use relative path from binary location for better portability
  if(WIN32)
    target_compile_definitions(piper PUBLIC OPENJTALK_DIC_PATH="..\\\\share\\\\open_jtalk\\\\dic")
    target_compile_definitions(test_piper PUBLIC OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}\\\\naist-jdic")
    target_compile_definitions(test_piper PUBLIC SPDLOG_FMT_EXTERNAL=1)
    target_compile_definitions(test_piper PUBLIC FMT_HEADER_ONLY=1)
  else()
    target_compile_definitions(piper PUBLIC OPENJTALK_DIC_PATH="../share/open_jtalk/dic")
    target_compile_definitions(test_piper PUBLIC OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}/naist-jdic")
    target_compile_definitions(test_piper PUBLIC SPDLOG_FMT_EXTERNAL=1)
    target_compile_definitions(test_piper PUBLIC FMT_HEADER_ONLY=1)
  endif()
endif()

# ---- Declare test ----
include(CTest)
enable_testing()
add_test(
  NAME test_piper
  COMMAND test_piper "${CMAKE_SOURCE_DIR}/test/models/test_voice.onnx" "$<TARGET_FILE_DIR:test_piper>/espeak-ng-data" "${CMAKE_CURRENT_BINARY_DIR}/test.wav"
)

target_compile_features(test_piper PUBLIC cxx_std_17)

target_include_directories(
  test_piper PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
  ${PIPER_PHONEMIZE_DIR}/include
)

target_link_directories(
  test_piper PUBLIC
  ${FMT_DIR}/lib
  ${SPDLOG_DIR}/lib
  ${PIPER_PHONEMIZE_DIR}/lib
)

# Platform-specific library linking for test_piper
if(WIN32)
  # Windows: Link libraries directly with generator expressions for debug/release
  target_link_libraries(test_piper PRIVATE
    optimized ${FMT_DIR}/lib/fmt.lib
    debug ${FMT_DIR}/lib/fmtd.lib
    optimized ${SPDLOG_DIR}/lib/spdlog.lib
    debug ${SPDLOG_DIR}/lib/spdlogd.lib
    ${PIPER_PHONEMIZE_DIR}/lib/piper_phonemize.lib
    ${PIPER_PHONEMIZE_DIR}/lib/espeak-ng.lib
    ${ONNXRUNTIME_LIB}
    ${PIPER_EXTRA_LIBRARIES}
  )
else()
  target_link_libraries(test_piper PRIVATE
    fmt
    spdlog
    espeak-ng
    piper_phonemize
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
endif()

# OpenJTalk is used via binary execution for test_piper, not linked

# ---- Declare install targets ----

install(
  TARGETS piper
  DESTINATION bin)

# Dependencies
install(
  DIRECTORY ${PIPER_PHONEMIZE_DIR}/bin/
  DESTINATION bin
  USE_SOURCE_PERMISSIONS  # keep +x
  FILES_MATCHING
  PATTERN "piper_phonemize"
  PATTERN "espeak-ng"
  PATTERN "*.dll"
)

install(
  DIRECTORY ${PIPER_PHONEMIZE_DIR}/lib/
  DESTINATION lib
  FILES_MATCHING
  PATTERN "*.dll"
  PATTERN "*.so*"
  PATTERN "*.dylib"
)

install(
  DIRECTORY ${PIPER_PHONEMIZE_DIR}/share/espeak-ng-data
  DESTINATION share
)

install(
  FILES ${PIPER_PHONEMIZE_DIR}/share/libtashkeel_model.ort
  DESTINATION share
)

# Install OpenJTalk for Japanese TTS support
if(TRUE)  # HTSEngine and OpenJTalk are built
  # Install OpenJTalk binaries
  if(WIN32)
    install(
      PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/oj/bin/open_jtalk.exe
      DESTINATION bin
      OPTIONAL  # Don't fail if not built
    )
    install(
      PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/oj/bin/open_jtalk_phonemizer.exe
      DESTINATION bin
      OPTIONAL  # Don't fail if not built
    )
  else()
    install(
      PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/oj/bin/open_jtalk
      DESTINATION bin
      OPTIONAL  # Don't fail if not built
    )
    install(
      PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/oj/bin/open_jtalk_phonemizer
      DESTINATION bin
      OPTIONAL  # Don't fail if not built
    )
  endif()

  # Install OpenJTalk dictionary
  # The autotools build installs the dictionary under OPENJTALK_DIR (oj/)
  # while the CMake build may place it under the build root's share/
  install(
    DIRECTORY ${OPENJTALK_DIR}/share/open_jtalk
    DESTINATION share
    OPTIONAL  # Don't fail if not present
  )
  # Fallback: also check the build root's share/ (CMake-based builds)
  install(
    DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/share/open_jtalk
    DESTINATION share
    OPTIONAL  # Don't fail if not present
  )
endif()

# Note: We don't need to copy espeak-ng library on macOS separately
# because piper_phonemize builds and installs its own custom fork
# of espeak-ng that includes the required espeak_TextToPhonemesWithTerminator
# function. The library is already installed by the piper_phonemize
# external project.

# ---- Windows-specific DLL handling ----
if(WIN32)
  # Helper function to copy DLLs
  function(copy_dlls_to_target target_name)
    # Create bin and lib subdirectories for better organization
    add_custom_command(TARGET ${target_name} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${target_name}>/lib"
      COMMENT "Creating lib directory for ${target_name}..."
    )
    
    # Copy ONNX Runtime DLLs
    if(ONNXRUNTIME_DLL)
      add_custom_command(TARGET ${target_name} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${ONNXRUNTIME_DLL}"
          "$<TARGET_FILE_DIR:${target_name}>/onnxruntime.dll"
        COMMENT "Copying ONNX Runtime DLL..."
      )
      
      # Also copy ONNX Runtime providers DLL if it exists
      get_filename_component(ONNX_DIR "${ONNXRUNTIME_DLL}" DIRECTORY)
      file(GLOB ONNX_PROVIDER_DLLS "${ONNX_DIR}/onnxruntime_providers*.dll")
      foreach(dll ${ONNX_PROVIDER_DLLS})
        add_custom_command(TARGET ${target_name} POST_BUILD
          COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${dll}"
            "$<TARGET_FILE_DIR:${target_name}>/"
          COMMENT "Copying ONNX Runtime provider DLL: ${dll}..."
        )
      endforeach()
    endif()
  endfunction()
  
  # Apply DLL copying to both targets
  copy_dlls_to_target(piper)
  copy_dlls_to_target(test_piper)
  
  # Install ONNX Runtime DLL
  if(ONNXRUNTIME_DLL)
    install(FILES ${ONNXRUNTIME_DLL} DESTINATION bin)
    get_filename_component(ONNX_DIR "${ONNXRUNTIME_DLL}" DIRECTORY)
    file(GLOB ONNX_PROVIDER_DLLS "${ONNX_DIR}/onnxruntime_providers*.dll")
    if(ONNX_PROVIDER_DLLS)
      install(FILES ${ONNX_PROVIDER_DLLS} DESTINATION bin)
    endif()
  endif()
  
  # Copy piper-phonemize DLLs
  # First, copy specific DLLs we know we need
  set(PIPER_PHONEMIZE_BUILD_DIR "${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build")
  
  # Copy DLLs from installed locations
  # Both espeak-ng.dll and piper_phonemize.dll should be installed to ${PIPER_PHONEMIZE_DIR}/bin
  
  add_custom_command(TARGET piper POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying DLLs for piper..."
    # Copy from installed location
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${PIPER_PHONEMIZE_DIR}/bin"
      "$<TARGET_FILE_DIR:piper>/"
    COMMENT "Copying piper-phonemize DLLs..."
  )
  
  add_custom_command(TARGET test_piper POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying DLLs for test_piper..."
    # Copy from installed location
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${PIPER_PHONEMIZE_DIR}/bin"
      "$<TARGET_FILE_DIR:test_piper>/"
    COMMENT "Copying piper-phonemize DLLs for tests..."
  )
  
  
  # Copy Microsoft C++ runtime redistributables if needed
  # Required for dynamic runtime linking (/MD)
  set(CMAKE_INSTALL_UCRT_LIBRARIES TRUE)
  set(CMAKE_INSTALL_SYSTEM_RUNTIME_DESTINATION bin)
  set(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS_SKIP FALSE)
  include(InstallRequiredSystemLibraries)
  
  # Copy runtime DLLs only for piper target to avoid conflicts
  # test_piper will use the same directory structure in CI
  if(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS)
    foreach(lib ${CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS})
      add_custom_command(TARGET piper POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${lib}"
          "$<TARGET_FILE_DIR:piper>/"
        COMMENT "Copying runtime library ${lib}..."
      )
    endforeach()
  endif()
  
  # Also copy espeak-ng data for test
  add_custom_command(TARGET test_piper POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${PIPER_PHONEMIZE_DIR}/share/espeak-ng-data"
      "$<TARGET_FILE_DIR:test_piper>/espeak-ng-data"
    COMMENT "Copying espeak-ng data for tests..."
  )
endif()