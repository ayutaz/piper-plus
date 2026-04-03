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

# ---- piper_common OBJECT library (shared between piper, test_piper, piper_plus) ----
set(PIPER_COMMON_SOURCES
  src/cpp/piper.cpp
  src/cpp/phoneme_parser.cpp
  src/cpp/custom_dictionary.cpp
  src/cpp/model_manager.cpp
  src/cpp/language_detector.cpp
  src/cpp/english_phonemize.cpp
  src/cpp/chinese_phonemize.cpp
  src/cpp/korean_phonemize.cpp
  src/cpp/spanish_phonemize.cpp
  src/cpp/french_phonemize.cpp
  src/cpp/portuguese_phonemize.cpp
  src/cpp/swedish_phonemize.cpp
  src/cpp/openjtalk_phonemize.cpp
  src/cpp/openjtalk_phonemize_utils.cpp
  src/cpp/openjtalk_wrapper.c
  src/cpp/openjtalk_dictionary_manager.c
  src/cpp/openjtalk_error.c
  src/cpp/openjtalk_security.c
  src/cpp/openjtalk_optimized.c
  src/cpp/openjtalk_api.c
)

# Add NEON optimized audio processing for ARM64
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  list(APPEND PIPER_COMMON_SOURCES src/cpp/audio_neon.cpp)
endif()

add_library(piper_common OBJECT ${PIPER_COMMON_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_executable(piper src/cpp/main.cpp $<TARGET_OBJECTS:piper_common>)
add_executable(test_piper src/cpp/test.cpp $<TARGET_OBJECTS:piper_common>)

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
  
  # Note: add_subdirectory(src/cpp/tests) is deferred to after all ExternalProject
  # targets are defined, so that if(TARGET openjtalk_external) etc. work correctly.
endif()

# OpenJTalk sources are included in piper_common OBJECT library above

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
    INSTALL_RPATH "@executable_path;@executable_path/../lib;@loader_path/../lib"
    BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR}/ort/lib"
    BUILD_WITH_INSTALL_RPATH FALSE
  )
  set_target_properties(test_piper PROPERTIES
    MACOSX_RPATH TRUE
    INSTALL_RPATH "@executable_path;@executable_path/../lib;@loader_path/../lib"
    BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR}/ort/lib"
    BUILD_WITH_INSTALL_RPATH FALSE
  )
endif()

# NOTE: external project prefix are shortened because of path length restrictions on Windows

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
               -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
               ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(piper_common fmt_external)
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
               -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
               ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(spdlog_external fmt_external)
  add_dependencies(piper_common spdlog_external)
  add_dependencies(piper spdlog_external)
  add_dependencies(test_piper spdlog_external)
endif()

# ---- ONNX Runtime ---
if(WIN32)
  include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/find_onnxruntime_windows.cmake)
elseif(NOT DEFINED ONNXRUNTIME_DIR)
  # Linux/macOS: Download pre-built ONNX Runtime if not already available
  set(ONNXRUNTIME_VERSION "1.14.1")
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    if(APPLE)
      set(ONNXRUNTIME_ARCH "arm64")
    else()
      set(ONNXRUNTIME_ARCH "aarch64")
    endif()
  else()
    set(ONNXRUNTIME_ARCH "x64")
  endif()
  if(APPLE)
    set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-osx-${ONNXRUNTIME_ARCH}-${ONNXRUNTIME_VERSION}.tgz")
  else()
    set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-linux-${ONNXRUNTIME_ARCH}-${ONNXRUNTIME_VERSION}.tgz")
  endif()
  set(ONNXRUNTIME_DIR "${CMAKE_CURRENT_BINARY_DIR}/ort")

  include(ExternalProject)
  ExternalProject_Add(
    onnxruntime_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/ort_dl"
    URL "${ONNXRUNTIME_URL}"
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ""
    INSTALL_COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/lib ${ONNXRUNTIME_DIR}/lib
    COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/include ${ONNXRUNTIME_DIR}/include
  )
  add_dependencies(piper_common onnxruntime_external)
  add_dependencies(piper onnxruntime_external)
  add_dependencies(test_piper onnxruntime_external)

  target_include_directories(piper_common PUBLIC ${ONNXRUNTIME_DIR}/include)
  target_include_directories(piper PUBLIC ${ONNXRUNTIME_DIR}/include)
  target_include_directories(test_piper PUBLIC ${ONNXRUNTIME_DIR}/include)
  target_link_directories(piper PUBLIC ${ONNXRUNTIME_DIR}/lib)
  target_link_directories(test_piper PUBLIC ${ONNXRUNTIME_DIR}/lib)
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
  set_target_properties(hts_engine_stub PROPERTIES POSITION_INDEPENDENT_CODE ON)
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
          -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
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
        set(CONFIGURE_ENV "CFLAGS=-arch arm64 -fPIC" "CXXFLAGS=-arch arm64 -fPIC" "LDFLAGS=-arch arm64")
      elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
        # Linux ARM64 cross-compilation
        set(CONFIGURE_HOST "--host=aarch64-linux-gnu")
        set(CONFIGURE_ENV "CC=aarch64-linux-gnu-gcc" "CXX=aarch64-linux-gnu-g++" "AR=aarch64-linux-gnu-ar" "RANLIB=aarch64-linux-gnu-ranlib" "CFLAGS=-fPIC" "CXXFLAGS=-fPIC")
      else()
        set(CONFIGURE_HOST "")
        set(CONFIGURE_ENV "CFLAGS=-fPIC" "CXXFLAGS=-fPIC")
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
# Using pyopenjtalk-plus's open_jtalk fork for Python/C++ consistency.
# This fork has improved NJD accent phrase rules (Rules 19-22) and accent type fixes
# that produce identical fullcontext labels to the Python training pipeline.
# Both the library and dictionary come from the same pyopenjtalk-plus source.
set(PYOPENJTALK_PLUS_URL "https://files.pythonhosted.org/packages/82/4e/1e2c165b04dd250dbcb1c270df8517681eed5c20b755c72bec2b42853851/pyopenjtalk_plus-0.4.1.post7.tar.gz")

if(NOT DEFINED OPENJTALK_DIR)
    set(OPENJTALK_DIR "${CMAKE_CURRENT_BINARY_DIR}/oj")

    # pyopenjtalk-plus fork: single "openjtalk" library (MeCab + NJD + JPCommon)
    # No HTS_Engine dependency (NJD/MeCab pipeline only)
    set(OPENJTALK_CMAKE_ARGS
      -DCMAKE_INSTALL_PREFIX:PATH=${OPENJTALK_DIR}
      -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
      -DBUILD_SHARED_LIBS:BOOL=OFF
      -DCHARSET:STRING=utf8
      -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
      ${EXTERNAL_CMAKE_ARGS}
    )

    if(WIN32)
      list(APPEND OPENJTALK_CMAKE_ARGS
        -DCMAKE_MSVC_RUNTIME_LIBRARY:STRING=${CMAKE_MSVC_RUNTIME_LIBRARY}
      )
    else()
      # Linux ARM64 cross-compilation settings
      if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
        list(APPEND OPENJTALK_CMAKE_ARGS
          -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
          -DCMAKE_C_COMPILER:FILEPATH=aarch64-linux-gnu-gcc
          -DCMAKE_CXX_COMPILER:FILEPATH=aarch64-linux-gnu-g++
          -DCMAKE_AR:FILEPATH=aarch64-linux-gnu-ar
          -DCMAKE_RANLIB:FILEPATH=aarch64-linux-gnu-ranlib
        )
      endif()
    endif()

    ExternalProject_Add(
      openjtalk_external
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/o"
      URL ${PYOPENJTALK_PLUS_URL}
      URL_HASH SHA256=555fdf86310d6d72f4a37e92beb251cdc2114aafc133d4c77b136a07a4b17119
      DOWNLOAD_NO_PROGRESS TRUE
      TIMEOUT 600
      TLS_VERIFY ON
      DOWNLOAD_TRIES 3
      SOURCE_SUBDIR lib/open_jtalk/src
      CMAKE_ARGS ${OPENJTALK_CMAKE_ARGS}
      PATCH_COMMAND
        ${CMAKE_COMMAND} -D SOURCE_DIR=<SOURCE_DIR> -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/patch_r9y9_openjtalk.cmake
      BUILD_BYPRODUCTS
        ${OPENJTALK_DIR}/lib/libopenjtalk.a      # Unix
        ${OPENJTALK_DIR}/lib/openjtalk.lib        # Windows
    )

    # Note: pyopenjtalk-plus fork doesn't require HTS_Engine for NJD pipeline
    # (no add_dependencies on hts_engine_external needed)

    # Dictionary from pyopenjtalk-plus (same source, same archive)
    # Custom dictionary with improved accent predictions from jpreprocess project.
    # DEPENDS openjtalk_external to avoid parallel download race condition.
    set(OPENJTALK_DIC_DIR "${CMAKE_CURRENT_BINARY_DIR}/share/open_jtalk/dic")
    ExternalProject_Add(
      openjtalk_dic_download
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/od"
      DEPENDS openjtalk_external
      URL ${PYOPENJTALK_PLUS_URL}
      URL_HASH SHA256=555fdf86310d6d72f4a37e92beb251cdc2114aafc133d4c77b136a07a4b17119
      DOWNLOAD_NO_PROGRESS TRUE
      TIMEOUT 600
      TLS_VERIFY ON
      DOWNLOAD_TRIES 3
      CONFIGURE_COMMAND ""
      BUILD_COMMAND ""
      INSTALL_COMMAND
        ${CMAKE_COMMAND} -E make_directory ${OPENJTALK_DIC_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/pyopenjtalk/dictionary ${OPENJTALK_DIC_DIR}
    )
endif()

# ---- Declare executable ----

if(APPLE)
  # macOS-specific settings
  set(PIPER_EXTRA_LIBRARIES "pthread")
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
    ${ONNXRUNTIME_LIB}
    ${PIPER_EXTRA_LIBRARIES}
  )
else()
  # Unix: Use standard library names
  target_link_libraries(piper PRIVATE
    fmt
    spdlog
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
endif()

# Link OpenJTalk libraries
# Ensure OpenJTalk is built before linking
add_dependencies(piper_common openjtalk_external)
add_dependencies(piper openjtalk_external)
add_dependencies(test_piper openjtalk_external)

# Link HTS_Engine (required for OpenJTalk build)
add_dependencies(piper_common hts_engine_external)
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

# ---- piper_common include directories and compile definitions ----
# piper_common needs these at compile time for OBJECT files
target_include_directories(piper_common PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
  ${OPENJTALK_DIR}/include
  ${OPENJTALK_DIR}/include/openjtalk
  ${HTS_ENGINE_DIR}/include
)
target_compile_definitions(piper_common PUBLIC
  _PIPER_VERSION=${piper_version}
  SPDLOG_FMT_EXTERNAL=1
  FMT_HEADER_ONLY=1
)

# Add ONNX Runtime include directory for Windows (piper_common)
if(WIN32 AND ONNXRUNTIME_INCLUDE_DIR)
  target_include_directories(piper_common PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
endif()

# ---- piper / test_piper link directories and include directories ----
target_link_directories(piper PUBLIC
  ${FMT_DIR}/lib
  ${SPDLOG_DIR}/lib
)

target_include_directories(piper PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
)

# Add ONNX Runtime include directory for Windows
if(WIN32 AND ONNXRUNTIME_INCLUDE_DIR)
  target_include_directories(piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
  target_include_directories(test_piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
endif()

# Add ONNX Runtime install path for Linux/macOS
if(NOT WIN32 AND DEFINED ONNXRUNTIME_DIR)
  # Also install ONNX Runtime shared libs
  install(
    DIRECTORY ${ONNXRUNTIME_DIR}/lib/
    DESTINATION lib
    FILES_MATCHING PATTERN "libonnxruntime*"
  )
endif()

# Include OpenJTalk headers (r9y9 fork installs to include/openjtalk/)
target_include_directories(piper PUBLIC
  ${OPENJTALK_DIR}/include
  ${OPENJTALK_DIR}/include/openjtalk
)
target_include_directories(test_piper PUBLIC
  ${OPENJTALK_DIR}/include
  ${OPENJTALK_DIR}/include/openjtalk
)

# Include HTSEngine headers (required for OpenJTalk)
target_include_directories(piper PUBLIC
  ${HTS_ENGINE_DIR}/include
)
target_include_directories(test_piper PUBLIC
  ${HTS_ENGINE_DIR}/include
)

# Link OpenJTalk static library (r9y9 fork: single "openjtalk" lib with MeCab included)
if(WIN32)
  target_link_libraries(piper PRIVATE ${OPENJTALK_DIR}/lib/openjtalk.lib)
  target_link_libraries(test_piper PRIVATE ${OPENJTALK_DIR}/lib/openjtalk.lib)
else()
  target_link_libraries(piper PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
  target_link_libraries(test_piper PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
endif()

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

# Add test subdirectory AFTER all ExternalProject targets are defined
# (tests depend on openjtalk_external, hts_engine_external, etc.)
if(BUILD_TESTS)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/tests")
    add_subdirectory(src/cpp/tests)
  endif()
endif()

# ---- Declare test ----
include(CTest)
enable_testing()
add_test(
  NAME test_piper
  COMMAND test_piper "${CMAKE_SOURCE_DIR}/test/models/multilingual-test-medium.onnx" "${CMAKE_CURRENT_BINARY_DIR}/test.wav"
)
set_tests_properties(test_piper PROPERTIES SKIP_RETURN_CODE 77)

target_compile_features(test_piper PUBLIC cxx_std_17)

target_include_directories(
  test_piper PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
)

target_link_directories(
  test_piper PUBLIC
  ${FMT_DIR}/lib
  ${SPDLOG_DIR}/lib
)

# Platform-specific library linking for test_piper
if(WIN32)
  # Windows: Link libraries directly with generator expressions for debug/release
  target_link_libraries(test_piper PRIVATE
    optimized ${FMT_DIR}/lib/fmt.lib
    debug ${FMT_DIR}/lib/fmtd.lib
    optimized ${SPDLOG_DIR}/lib/spdlog.lib
    debug ${SPDLOG_DIR}/lib/spdlogd.lib
    ${ONNXRUNTIME_LIB}
    ${PIPER_EXTRA_LIBRARIES}
  )
else()
  target_link_libraries(test_piper PRIVATE
    fmt
    spdlog
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
endif()

# OpenJTalk is linked as a static library (r9y9 fork) for direct API access

# ---- piper_plus SHARED library (C API) ----

option(PIPER_PLUS_BUILD_SHARED "Build piper-plus shared library (C API)" OFF)

if(PIPER_PLUS_BUILD_SHARED)
  add_library(piper_plus SHARED
    src/cpp/piper_plus_c_api.cpp
    $<TARGET_OBJECTS:piper_common>
  )

  # Dependencies (same as piper/test_piper)
  add_dependencies(piper_plus fmt_external spdlog_external openjtalk_external hts_engine_external)
  if(TARGET onnxruntime_external)
    add_dependencies(piper_plus onnxruntime_external)
  endif()

  # Include directories (same as piper_common)
  target_include_directories(piper_plus PUBLIC
    ${FMT_DIR}/include
    ${SPDLOG_DIR}/include
    ${OPENJTALK_DIR}/include
    ${OPENJTALK_DIR}/include/openjtalk
    ${HTS_ENGINE_DIR}/include
  )
  if(WIN32 AND ONNXRUNTIME_INCLUDE_DIR)
    target_include_directories(piper_plus PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
  elseif(NOT WIN32 AND DEFINED ONNXRUNTIME_DIR)
    target_include_directories(piper_plus PUBLIC ${ONNXRUNTIME_DIR}/include)
  endif()

  # Compile definitions (same as piper_common, but NO OPENJTALK_DIC_PATH -- C API uses dict_dir)
  target_compile_definitions(piper_plus PRIVATE
    PIPER_PLUS_BUILDING_DLL
    _PIPER_VERSION=${piper_version}
    SPDLOG_FMT_EXTERNAL=1
    FMT_HEADER_ONLY=1
  )

  # Link directories
  target_link_directories(piper_plus PUBLIC
    ${FMT_DIR}/lib
    ${SPDLOG_DIR}/lib
  )
  if(NOT WIN32 AND DEFINED ONNXRUNTIME_DIR)
    target_link_directories(piper_plus PUBLIC ${ONNXRUNTIME_DIR}/lib)
  endif()

  # Link libraries -- NOTE: -static-libstdc++ is intentionally NOT applied (M1-2)
  if(WIN32)
    target_link_libraries(piper_plus PRIVATE
      optimized ${FMT_DIR}/lib/fmt.lib
      debug ${FMT_DIR}/lib/fmtd.lib
      optimized ${SPDLOG_DIR}/lib/spdlog.lib
      debug ${SPDLOG_DIR}/lib/spdlogd.lib
      ${ONNXRUNTIME_LIB}
      ${OPENJTALK_DIR}/lib/openjtalk.lib
    )
  else()
    target_link_libraries(piper_plus PRIVATE
      fmt
      spdlog
      onnxruntime
      ${PIPER_EXTRA_LIBRARIES}
    )
    # Link OpenJTalk static library
    target_link_libraries(piper_plus PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
  endif()

  # Link HTS Engine
  if(USE_HTS_ENGINE_STUB)
    target_link_libraries(piper_plus PRIVATE hts_engine_stub)
  else()
    if(WIN32)
      target_link_libraries(piper_plus PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/he/lib/HTSEngine.lib)
    else()
      target_link_libraries(piper_plus PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a)
    endif()
  endif()

  # Link pthread on Linux
  if(UNIX AND NOT APPLE)
    find_package(Threads REQUIRED)
    target_link_libraries(piper_plus PRIVATE Threads::Threads)
  endif()

  # Visibility and output settings
  set_target_properties(piper_plus PROPERTIES
    C_VISIBILITY_PRESET hidden
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    OUTPUT_NAME "piper_plus"
    VERSION ${piper_version}
    SOVERSION 1
  )

  # RPATH settings
  if(APPLE)
    set_target_properties(piper_plus PROPERTIES
      MACOSX_RPATH TRUE
      INSTALL_RPATH "@loader_path"
    )
  elseif(UNIX)
    set_target_properties(piper_plus PROPERTIES
      INSTALL_RPATH "$ORIGIN"
      BUILD_WITH_INSTALL_RPATH TRUE
    )
  endif()

  # Install targets
  include(GNUInstallDirs)
  install(TARGETS piper_plus
    EXPORT PiperPlusTargets
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
  )
  install(FILES src/cpp/piper_plus.h
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
  )
endif()

# ---- Declare install targets ----

install(
  TARGETS piper
  DESTINATION bin)

# Install OpenJTalk for Japanese TTS support
# r9y9 fork: static library linked directly, no separate binaries needed.
# OpenJTalk binaries (open_jtalk, open_jtalk_phonemizer) are no longer installed
# since C++ now uses the API directly instead of system() calls.
# Install OpenJTalk dictionary
install(
  DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/share/open_jtalk
  DESTINATION share
  OPTIONAL  # Don't fail if not present
)

# Install phonemizer dictionaries (English CMU, Chinese Pinyin)
install(
  FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/cmudict_data.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_single.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_phrases.json
  DESTINATION share/piper/dicts
)

# Install voices.json catalog for model listing/downloading
install(
  FILES ${CMAKE_CURRENT_SOURCE_DIR}/src/python_run/piper/voices.json
  DESTINATION share
  OPTIONAL
)


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
  
  # Apply DLL copying to targets
  copy_dlls_to_target(piper)
  copy_dlls_to_target(test_piper)
  if(PIPER_PLUS_BUILD_SHARED)
    copy_dlls_to_target(piper_plus)
  endif()
  
  # Install ONNX Runtime DLL
  if(ONNXRUNTIME_DLL)
    install(FILES ${ONNXRUNTIME_DLL} DESTINATION bin)
    get_filename_component(ONNX_DIR "${ONNXRUNTIME_DLL}" DIRECTORY)
    file(GLOB ONNX_PROVIDER_DLLS "${ONNX_DIR}/onnxruntime_providers*.dll")
    if(ONNX_PROVIDER_DLLS)
      install(FILES ${ONNX_PROVIDER_DLLS} DESTINATION bin)
    endif()
  endif()
  
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
endif()