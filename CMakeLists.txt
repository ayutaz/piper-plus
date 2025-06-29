cmake_minimum_required(VERSION 3.13)

# Set policy for DOWNLOAD_EXTRACT_TIMESTAMP to avoid warnings
if(POLICY CMP0135)
  cmake_policy(SET CMP0135 NEW)
endif()

project(piper C CXX)

file(READ "${CMAKE_CURRENT_LIST_DIR}/VERSION" piper_version)
string(STRIP "${piper_version}" piper_version)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MSVC)
  # Force compiler to use UTF-8 for IPA constants
  add_compile_options("$<$<C_COMPILER_ID:MSVC>:/utf-8>")
  add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/utf-8>")
  
  # Use static runtime library to avoid DLL dependencies
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /MT")
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /MTd")
  set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS_RELEASE} /MT")
  set(CMAKE_C_FLAGS_DEBUG "${CMAKE_C_FLAGS_DEBUG} /MTd")
  
  # Additional Windows-specific flags for better compatibility
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
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra -Wl,-rpath,'$ORIGIN'")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
endif()

add_executable(piper src/cpp/main.cpp src/cpp/piper.cpp)
add_executable(test_piper src/cpp/test.cpp src/cpp/piper.cpp)

# Set runtime library for executables on Windows
if(MSVC)
  set_property(TARGET piper PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  set_property(TARGET test_piper PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
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
  
  add_subdirectory(src/cpp/tests)
endif()

# Add OpenJTalk support 
if(NOT WIN32 AND NOT MSVC)
  # Unix platforms: use native OpenJTalk
  target_sources(piper PRIVATE
    src/cpp/openjtalk_phonemize.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_dictionary_manager.c
  )
  target_sources(test_piper PRIVATE
    src/cpp/openjtalk_phonemize.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_dictionary_manager.c
  )
else()
  # Windows: use wrapper implementation
  target_sources(piper PRIVATE
    src/cpp/openjtalk_phonemize.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_dictionary_manager.c
  )
  target_sources(test_piper PRIVATE
    src/cpp/openjtalk_phonemize.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_dictionary_manager.c
  )
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
  if(APPLE AND CMAKE_OSX_ARCHITECTURES)
    set(EXTERNAL_CMAKE_ARGS -DCMAKE_OSX_ARCHITECTURES=${CMAKE_OSX_ARCHITECTURES})
  elseif(MSVC)
    # Pass static runtime library settings to external projects
    set(EXTERNAL_CMAKE_ARGS 
      -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>
      -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
      -DCMAKE_CXX_FLAGS_RELEASE="/MT /O2"
      -DCMAKE_C_FLAGS_RELEASE="/MT /O2"
      -DCMAKE_CXX_FLAGS_DEBUG="/MTd /Od /Zi"
      -DCMAKE_C_FLAGS_DEBUG="/MTd /Od /Zi"
      -DCMAKE_CXX_FLAGS="/EHsc /W3"
      -DCMAKE_C_FLAGS="/W3"
      -DCMAKE_BUILD_TYPE=Release
    )
  else()
    set(EXTERNAL_CMAKE_ARGS "")
  endif()

  ExternalProject_Add(
    fmt_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/f"
    URL "https://github.com/fmtlib/fmt/archive/refs/tags/${FMT_VERSION}.zip"
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${FMT_DIR}
    CMAKE_ARGS -DFMT_TEST:BOOL=OFF  # Don't build all the tests
    CMAKE_ARGS -DBUILD_SHARED_LIBS:BOOL=OFF  # Build static libraries
    CMAKE_ARGS -DFMT_USE_CPP11:BOOL=ON
    CMAKE_ARGS ${EXTERNAL_CMAKE_ARGS}
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
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${SPDLOG_DIR}
    CMAKE_ARGS -DSPDLOG_BUILD_SHARED:BOOL=OFF  # Build static libraries
    CMAKE_ARGS -DSPDLOG_ENABLE_PCH:BOOL=OFF
    CMAKE_ARGS -DSPDLOG_FMT_EXTERNAL:BOOL=OFF
    CMAKE_ARGS ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(piper spdlog_external)
  add_dependencies(test_piper spdlog_external)
endif()

# ---- ONNX Runtime for Windows ---
# Include this early to ensure ONNXRUNTIME_INCLUDE_DIR is set before targets are defined
if(MSVC)
  include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/find_onnxruntime_windows.cmake)
  
  # For CI builds, ensure we have ONNX Runtime headers
  if((DEFINED ENV{GITHUB_ACTIONS} OR USE_PREBUILT_PIPER_PHONEMIZE) AND NOT ONNXRUNTIME_INCLUDE_DIR)
    message(STATUS "CI build: Setting up ONNX Runtime headers")
    # Download just the headers if needed
    set(ONNXRUNTIME_VERSION "1.15.1")
    set(ONNX_ARCH "x64")
    set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}.zip")
    set(ONNXRUNTIME_DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/onnxruntime-ci")
    set(ONNXRUNTIME_ZIP "${ONNXRUNTIME_DOWNLOAD_DIR}/onnxruntime.zip")
    
    file(MAKE_DIRECTORY ${ONNXRUNTIME_DOWNLOAD_DIR})
    
    if(NOT EXISTS "${ONNXRUNTIME_ZIP}")
      message(STATUS "Downloading ONNX Runtime headers for CI...")
      file(DOWNLOAD
        ${ONNXRUNTIME_URL}
        ${ONNXRUNTIME_ZIP}
        SHOW_PROGRESS
        STATUS download_status
        TIMEOUT 300
      )
    endif()
    
    if(EXISTS "${ONNXRUNTIME_ZIP}")
      message(STATUS "Extracting ONNX Runtime headers...")
      execute_process(
        COMMAND ${CMAKE_COMMAND} -E tar xf "${ONNXRUNTIME_ZIP}"
        WORKING_DIRECTORY "${ONNXRUNTIME_DOWNLOAD_DIR}"
        RESULT_VARIABLE extract_result
      )
      
      if(extract_result EQUAL 0)
        set(ONNXRUNTIME_INCLUDE_DIR "${ONNXRUNTIME_DOWNLOAD_DIR}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}/include")
        set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_DOWNLOAD_DIR}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}/lib")
        message(STATUS "ONNX Runtime headers available at: ${ONNXRUNTIME_INCLUDE_DIR}")
      endif()
    endif()
  endif()
endif()

# ---- piper-phonemize ---

option(USE_PREBUILT_PIPER_PHONEMIZE "Use prebuilt piper-phonemize instead of building from source" OFF)

if(NOT DEFINED PIPER_PHONEMIZE_DIR)
  set(PIPER_PHONEMIZE_DIR "${CMAKE_CURRENT_BINARY_DIR}/pi")
  set(PIPER_PHONEMIZE_VERSION "2023.11.14-3")
  
  if(MSVC)
    message(STATUS "Windows build detected")
    
    # For Windows CI, create stub libraries
    if(DEFINED ENV{GITHUB_ACTIONS} OR USE_PREBUILT_PIPER_PHONEMIZE)
      message(STATUS "Windows CI/Quick build - creating stub piper-phonemize")
      
      # Create necessary directories
      file(MAKE_DIRECTORY "${PIPER_PHONEMIZE_DIR}/include")
      file(MAKE_DIRECTORY "${PIPER_PHONEMIZE_DIR}/include/piper-phonemize")
      file(MAKE_DIRECTORY "${PIPER_PHONEMIZE_DIR}/lib")
      
      # Create stub headers
      file(WRITE "${PIPER_PHONEMIZE_DIR}/include/piper-phonemize/phoneme_ids.hpp" 
        "#pragma once\n// Stub header for Windows CI\nnamespace piper { using PhonemeId = int; using Phoneme = char32_t; }\n")
      file(WRITE "${PIPER_PHONEMIZE_DIR}/include/piper-phonemize/phonemize.hpp" 
        "#pragma once\n// Stub header for Windows CI\n")
      file(WRITE "${PIPER_PHONEMIZE_DIR}/include/piper-phonemize/tashkeel.hpp" 
        "#pragma once\n// Stub header for Windows CI\nnamespace tashkeel { struct State {}; }\n")
      
      # Create dummy target
      add_custom_target(piper_phonemize_external
        COMMAND ${CMAKE_COMMAND} -E echo "Using stub piper-phonemize for Windows CI"
      )
    else()
      message(STATUS "Building piper-phonemize from source")
      ExternalProject_Add(
        piper_phonemize_external
        PREFIX "${CMAKE_CURRENT_BINARY_DIR}/p"
        URL "https://github.com/rhasspy/piper-phonemize/archive/refs/tags/${PIPER_PHONEMIZE_VERSION}.zip"
        CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${PIPER_PHONEMIZE_DIR}
        CMAKE_ARGS -DBUILD_SHARED_LIBS:BOOL=OFF
        CMAKE_ARGS -DPIPER_PHONEMIZE_BUILD_TESTS:BOOL=OFF
        CMAKE_ARGS -DPIPER_PHONEMIZE_BUILD_PROGRAMS:BOOL=OFF
        CMAKE_ARGS ${EXTERNAL_CMAKE_ARGS}
      )
    endif()
  else()
    # On Unix platforms, use static libraries for easier deployment
    ExternalProject_Add(
      piper_phonemize_external
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/p"
      URL "https://github.com/rhasspy/piper-phonemize/archive/refs/tags/${PIPER_PHONEMIZE_VERSION}.zip"
      CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${PIPER_PHONEMIZE_DIR}
      CMAKE_ARGS -DBUILD_SHARED_LIBS:BOOL=OFF  # Build static libraries
      CMAKE_ARGS -DPIPER_PHONEMIZE_BUILD_TESTS:BOOL=OFF
      CMAKE_ARGS -DPIPER_PHONEMIZE_BUILD_PROGRAMS:BOOL=OFF
      CMAKE_ARGS ${EXTERNAL_CMAKE_ARGS}
    )
  endif()
  add_dependencies(piper piper_phonemize_external)
  add_dependencies(test_piper piper_phonemize_external)
endif()

# ---- HTSEngine ---

if(NOT DEFINED HTS_ENGINE_DIR)
  set(HTS_ENGINE_DIR "${CMAKE_CURRENT_BINARY_DIR}/he")
  set(HTS_ENGINE_VERSION "1.10")

  if(MSVC)
    # Windows: Build HTSEngine with our simplified audio implementation
    ExternalProject_Add(
      hts_engine_external
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/h"
      URL "https://downloads.sourceforge.net/project/hts-engine/hts_engine%20API/hts_engine_API-${HTS_ENGINE_VERSION}/hts_engine_API-${HTS_ENGINE_VERSION}.tar.gz"
      PATCH_COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_CMakeLists.txt <SOURCE_DIR>/CMakeLists.txt
        COMMAND ${CMAKE_COMMAND} -E remove <SOURCE_DIR>/lib/HTS_audio.c
        COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_audio_windows.c <SOURCE_DIR>/lib/HTS_audio.c
        COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/include ${HTS_ENGINE_DIR}/include
      CMAKE_ARGS 
        -DCMAKE_INSTALL_PREFIX:PATH=${HTS_ENGINE_DIR}
        -DBUILD_SHARED_LIBS:BOOL=OFF
        -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
        -DCMAKE_C_FLAGS="/MT /D_CRT_SECURE_NO_WARNINGS /DWIN32_LEAN_AND_MEAN"
        -DCMAKE_C_FLAGS_DEBUG="/MTd /D_CRT_SECURE_NO_WARNINGS /DWIN32_LEAN_AND_MEAN"
        -DCMAKE_C_FLAGS_RELEASE="/MT /D_CRT_SECURE_NO_WARNINGS /DWIN32_LEAN_AND_MEAN"
        -DCMAKE_BUILD_TYPE:STRING=Release
      BUILD_BYPRODUCTS ${HTS_ENGINE_DIR}/lib/HTSEngine.lib
    )
  else()
    # Unix platforms: Use configure script
    # Set architecture flags for configure scripts
    if(APPLE AND CMAKE_OSX_ARCHITECTURES)
      if(CMAKE_OSX_ARCHITECTURES STREQUAL "x86_64")
        set(CONFIGURE_HOST "--host=x86_64-apple-darwin")
      elseif(CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
        set(CONFIGURE_HOST "--host=aarch64-apple-darwin")
      else()
        set(CONFIGURE_HOST "")
      endif()
      set(CONFIGURE_ENV "CFLAGS=-arch ${CMAKE_OSX_ARCHITECTURES}" "CXXFLAGS=-arch ${CMAKE_OSX_ARCHITECTURES}" "LDFLAGS=-arch ${CMAKE_OSX_ARCHITECTURES}")
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

  if(MSVC)
    # Windows: Build OpenJTalk using GitHub Actions artifacts or fail
    file(MAKE_DIRECTORY ${OPENJTALK_DIR}/bin)
    
    # Try to use OpenJTalk binary from GitHub Actions artifacts
    # This should be built automatically by CI/CD
    set(OPENJTALK_WINDOWS_URL "$ENV{OPENJTALK_WINDOWS_URL}")
    if(NOT OPENJTALK_WINDOWS_URL)
      # Use the latest release from automated builds
      # Download from the unified binary release
      # This should be updated to point to your own repository
      set(OPENJTALK_WINDOWS_URL "https://github.com/ayutaz/piper-plus/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe")
    endif()
    
    set(OPENJTALK_WINDOWS_EXE "${OPENJTALK_DIR}/bin/open_jtalk.exe")
    
    if(NOT EXISTS ${OPENJTALK_WINDOWS_EXE})
      message(STATUS "Downloading pre-built OpenJTalk binary for Windows...")
      message(STATUS "URL: ${OPENJTALK_WINDOWS_URL}")
      
      file(DOWNLOAD
        ${OPENJTALK_WINDOWS_URL}
        ${OPENJTALK_WINDOWS_EXE}
        STATUS download_status
        SHOW_PROGRESS
        TIMEOUT 60
      )
      
      list(GET download_status 0 status_code)
      list(GET download_status 1 error_message)
      
      if(NOT status_code EQUAL 0)
        message(WARNING 
          "Failed to download OpenJTalk binary for Windows.\n"
          "Error: ${error_message}\n"
          "URL: ${OPENJTALK_WINDOWS_URL}\n\n"
          "Japanese TTS support will be limited without the OpenJTalk binary.\n"
          "The binary will be available after the build-openjtalk-windows GitHub Action runs on the master branch.\n"
          "Creating a placeholder wrapper instead..."
        )
        
        # Create a minimal wrapper as fallback
        configure_file(
          "${CMAKE_CURRENT_SOURCE_DIR}/cmake/open_jtalk_windows_wrapper.cpp.in"
          "${CMAKE_CURRENT_BINARY_DIR}/open_jtalk_windows_wrapper.cpp"
          @ONLY
        )
        
        add_executable(open_jtalk_fallback "${CMAKE_CURRENT_BINARY_DIR}/open_jtalk_windows_wrapper.cpp")
        set_target_properties(open_jtalk_fallback PROPERTIES
          OUTPUT_NAME "open_jtalk"
          RUNTIME_OUTPUT_DIRECTORY "${OPENJTALK_DIR}/bin"
        )
        
        # Ensure the fallback is built
        add_custom_command(TARGET open_jtalk_fallback POST_BUILD
          COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:open_jtalk_fallback> "${OPENJTALK_WINDOWS_EXE}"
        )
        
        # Make openjtalk_external depend on the fallback
        add_custom_target(openjtalk_external ALL
          DEPENDS hts_engine_external open_jtalk_fallback
          COMMENT "OpenJTalk for Windows - using fallback wrapper"
        )
      else()
        message(STATUS "Successfully downloaded OpenJTalk binary")
        add_custom_target(openjtalk_external ALL
          DEPENDS hts_engine_external
          COMMENT "OpenJTalk for Windows - using pre-built binary"
        )
      endif()
    else()
      message(STATUS "Using existing OpenJTalk binary at ${OPENJTALK_WINDOWS_EXE}")
      add_custom_target(openjtalk_external ALL
        DEPENDS hts_engine_external
        COMMENT "OpenJTalk for Windows - using existing binary"
      )
    endif()
  endif()
  
  if(NOT WIN32 AND NOT MSVC)
    # Unix platforms: Use configure script
    ExternalProject_Add(
      openjtalk_external
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/o"
      URL "https://downloads.sourceforge.net/project/open-jtalk/Open%20JTalk/open_jtalk-${OPENJTALK_VERSION}/open_jtalk-${OPENJTALK_VERSION}.tar.gz"
      PATCH_COMMAND ""
      CONFIGURE_COMMAND ${CMAKE_COMMAND} -E env ${CONFIGURE_ENV} ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> ./configure
        --prefix=${OPENJTALK_DIR}
        --with-hts-engine-header-path=${HTS_ENGINE_DIR}/include
        --with-hts-engine-library-path=${HTS_ENGINE_DIR}/lib
        --with-charset=UTF-8
        ${CONFIGURE_HOST}
      BUILD_COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> make
      INSTALL_COMMAND ${CMAKE_COMMAND} -E chdir <SOURCE_DIR> make install
      BUILD_IN_SOURCE 1
      BUILD_BYPRODUCTS
        ${OPENJTALK_DIR}/bin/open_jtalk
      DEPENDS hts_engine_external
    )
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
elseif(MSVC)
  # Windows-specific settings
  set(PIPER_EXTRA_LIBRARIES "")
  # No pthread on Windows, using Windows threads
  # Ensure static linking for Windows
  set(BUILD_SHARED_LIBS OFF)
else()
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra -Wl,-rpath,'$ORIGIN'")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  
  set(PIPER_EXTRA_LIBRARIES "pthread")
endif()

# Link libraries based on platform
if(MSVC)
  # Windows: Try to find libraries with different naming conventions
  find_library(FMT_LIB NAMES fmt fmtd
    PATHS ${FMT_DIR}/lib
    NO_DEFAULT_PATH
  )
  find_library(SPDLOG_LIB NAMES spdlog spdlogd
    PATHS ${SPDLOG_DIR}/lib
    NO_DEFAULT_PATH
  )
  
  # Only look for these libraries if not in CI build
  if(NOT DEFINED ENV{GITHUB_ACTIONS} AND NOT USE_PREBUILT_PIPER_PHONEMIZE)
    find_library(PIPER_PHONEMIZE_LIB NAMES piper_phonemize
      PATHS ${PIPER_PHONEMIZE_DIR}/lib ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/src
      NO_DEFAULT_PATH
    )
    find_library(ESPEAK_NG_LIB NAMES espeak-ng
      PATHS ${PIPER_PHONEMIZE_DIR}/lib ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/espeak_ng-build/src
      NO_DEFAULT_PATH
    )
  endif()
  
  find_library(ONNXRUNTIME_LIB NAMES onnxruntime
    PATHS ${PIPER_PHONEMIZE_DIR}/lib ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/onnxruntime-src/lib ${ONNXRUNTIME_LIB_DIR}
    NO_DEFAULT_PATH
  )
  
  # Link found libraries or use defaults
  if(DEFINED ENV{GITHUB_ACTIONS} OR USE_PREBUILT_PIPER_PHONEMIZE)
    # CI build: skip piper_phonemize and espeak-ng
    target_link_libraries(piper
      $<IF:$<BOOL:${FMT_LIB}>,${FMT_LIB},fmt>
      $<IF:$<BOOL:${SPDLOG_LIB}>,${SPDLOG_LIB},spdlog>
      $<IF:$<BOOL:${ONNXRUNTIME_LIB}>,${ONNXRUNTIME_LIB},onnxruntime>
      ${PIPER_EXTRA_LIBRARIES}
    )
  else()
    # Normal build: include all libraries
    target_link_libraries(piper
      $<IF:$<BOOL:${FMT_LIB}>,${FMT_LIB},fmt>
      $<IF:$<BOOL:${SPDLOG_LIB}>,${SPDLOG_LIB},spdlog>
      $<IF:$<BOOL:${PIPER_PHONEMIZE_LIB}>,${PIPER_PHONEMIZE_LIB},piper_phonemize>
      $<IF:$<BOOL:${ESPEAK_NG_LIB}>,${ESPEAK_NG_LIB},espeak-ng>
      $<IF:$<BOOL:${ONNXRUNTIME_LIB}>,${ONNXRUNTIME_LIB},onnxruntime>
      ${PIPER_EXTRA_LIBRARIES}
    )
  endif()
else()
  # Unix: Use standard library names
  target_link_libraries(piper
    fmt
    spdlog
    piper_phonemize
    espeak-ng
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
endif()

# Add static linking for Linux
if(NOT WIN32 AND NOT APPLE)
  target_link_libraries(piper -static-libgcc -static-libstdc++)
  target_link_libraries(test_piper -static-libgcc -static-libstdc++)
endif()

# Add dependencies for external projects
add_dependencies(piper fmt_external spdlog_external piper_phonemize_external)
add_dependencies(test_piper fmt_external spdlog_external piper_phonemize_external)

# Link OpenJTalk and HTS_Engine libraries
if(MSVC)
  # Windows: Ensure targets are built and link libraries
  add_dependencies(piper hts_engine_external openjtalk_external)
  add_dependencies(test_piper hts_engine_external openjtalk_external)
  
  # Windows uses .lib extension for static libraries
  target_link_libraries(piper
    ${HTS_ENGINE_DIR}/lib/HTSEngine.lib
  )
  target_link_libraries(test_piper
    ${HTS_ENGINE_DIR}/lib/HTSEngine.lib
  )
elseif(NOT WIN32)
  # Unix platforms: Ensure libraries are built before linking
  add_dependencies(piper openjtalk_external hts_engine_external)
  add_dependencies(test_piper openjtalk_external hts_engine_external)

  # Link libraries with absolute paths
  # Note: OpenJTalk doesn't create a single library, we need to link individual components
  target_link_libraries(piper
    ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a
  )
  target_link_libraries(test_piper
    ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a
  )
endif()

target_link_directories(piper PUBLIC
  ${FMT_DIR}/lib
  ${SPDLOG_DIR}/lib
  ${PIPER_PHONEMIZE_DIR}/lib
)

# Windows needs specific library paths
if(MSVC)
  # Add Windows-specific library directories
  target_link_directories(piper PUBLIC
    ${PIPER_PHONEMIZE_DIR}/lib
    ${CMAKE_CURRENT_BINARY_DIR}/pi/lib
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/src/Release
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/src/Debug
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/espeak_ng-build/src/Release
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/espeak_ng-build/src/Debug
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/onnxruntime-src/lib
    ${ONNXRUNTIME_LIB_DIR}
  )
  target_link_directories(test_piper PUBLIC
    ${PIPER_PHONEMIZE_DIR}/lib
    ${CMAKE_CURRENT_BINARY_DIR}/pi/lib
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/src/Release
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/src/Debug
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/espeak_ng-build/src/Release
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/espeak_ng-build/src/Debug
    ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/onnxruntime-src/lib
    ${ONNXRUNTIME_LIB_DIR}
  )
endif()

# Note: We don't need Homebrew paths for espeak-ng on macOS
# because we're using the custom build from piper_phonemize

target_include_directories(piper PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
  ${PIPER_PHONEMIZE_DIR}/include
)

# Add ONNX Runtime include directory early for all platforms
if(ONNXRUNTIME_INCLUDE_DIR)
  target_include_directories(piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
  target_include_directories(test_piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
  message(STATUS "Added ONNX Runtime include directory: ${ONNXRUNTIME_INCLUDE_DIR}")
endif()

if(MSVC)
  # Windows: Include directories for OpenJTalk and HTS_Engine
  target_include_directories(piper PUBLIC
    ${OPENJTALK_DIR}/include
    ${HTS_ENGINE_DIR}/include
  )
  target_include_directories(test_piper PUBLIC
    ${OPENJTALK_DIR}/include
    ${HTS_ENGINE_DIR}/include
  )
elseif(NOT WIN32)
  # Unix platforms: Include directories
  target_include_directories(piper PUBLIC
    ${OPENJTALK_DIR}/include
    ${HTS_ENGINE_DIR}/include
  )
  target_include_directories(test_piper PUBLIC
    ${OPENJTALK_DIR}/include
    ${HTS_ENGINE_DIR}/include
  )
endif()

# OpenJTalk is used via binary execution, includes not needed

target_compile_definitions(piper PUBLIC _PIPER_VERSION=${piper_version})

# Add CI build definition
if(DEFINED ENV{GITHUB_ACTIONS} OR USE_PREBUILT_PIPER_PHONEMIZE)
  target_compile_definitions(piper PUBLIC PIPER_CI_BUILD)
  target_compile_definitions(test_piper PUBLIC PIPER_CI_BUILD)
endif()

# Add OpenJTalk dictionary path definition on Unix platforms
if(NOT WIN32 AND NOT MSVC)
  # Dictionary will be downloaded by CI/CD or provided by user
  # Use relative path from binary location for better portability
  target_compile_definitions(piper PUBLIC OPENJTALK_DIC_PATH="../share/open_jtalk/dic")
  target_compile_definitions(test_piper PUBLIC OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}/naist-jdic")
endif()

# ---- Declare test ----
include(CTest)
enable_testing()
add_test(
  NAME test_piper
  COMMAND test_piper "${CMAKE_SOURCE_DIR}/etc/test_voice.onnx" "${PIPER_PHONEMIZE_DIR}/share/espeak-ng-data" "${CMAKE_CURRENT_BINARY_DIR}/test.wav"
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

# Link libraries for test_piper based on platform
if(MSVC)
  # Windows: Use the same libraries as piper
  if(DEFINED ENV{GITHUB_ACTIONS} OR USE_PREBUILT_PIPER_PHONEMIZE)
    # CI build: skip piper_phonemize and espeak-ng
    target_link_libraries(test_piper
      $<IF:$<BOOL:${FMT_LIB}>,${FMT_LIB},fmt>
      $<IF:$<BOOL:${SPDLOG_LIB}>,${SPDLOG_LIB},spdlog>
      $<IF:$<BOOL:${ONNXRUNTIME_LIB}>,${ONNXRUNTIME_LIB},onnxruntime>
      ${PIPER_EXTRA_LIBRARIES}
    )
  else()
    # Normal build: include all libraries
    target_link_libraries(test_piper
      $<IF:$<BOOL:${FMT_LIB}>,${FMT_LIB},fmt>
      $<IF:$<BOOL:${SPDLOG_LIB}>,${SPDLOG_LIB},spdlog>
      $<IF:$<BOOL:${ESPEAK_NG_LIB}>,${ESPEAK_NG_LIB},espeak-ng>
      $<IF:$<BOOL:${PIPER_PHONEMIZE_LIB}>,${PIPER_PHONEMIZE_LIB},piper_phonemize>
      $<IF:$<BOOL:${ONNXRUNTIME_LIB}>,${ONNXRUNTIME_LIB},onnxruntime>
      ${PIPER_EXTRA_LIBRARIES}
    )
  endif()
else()
  # Unix: Use standard library names
  target_link_libraries(test_piper
    fmt
    spdlog
    espeak-ng
    piper_phonemize
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
endif()

# OpenJTalk is used via binary execution for test_piper, not linked

# ---- Post-build steps for Windows DLL handling ----
if(MSVC)
  # Create a custom target to handle DLL copying after all external projects are built
  add_custom_target(copy_dlls ALL
    DEPENDS piper test_piper piper_phonemize_external
    COMMENT "Ensuring all DLLs are copied..."
  )
  
  # Add DLL copy commands to the custom target
  add_custom_command(TARGET copy_dlls POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying ONNX Runtime and other DLLs..."
    
    # Copy all DLLs to both Release and Debug directories
    COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/Release"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/Debug"
    
    # When using static libraries, DLL copying is minimal
    COMMAND ${CMAKE_COMMAND} -E echo "Static libraries used - minimal DLL copying needed"
    
    COMMENT "Copying DLLs to Release and Debug directories..."
  )
  
  # When using static libraries, only ONNX Runtime needs DLL
  add_custom_command(TARGET piper POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying ONNX Runtime DLL if needed..."
    
    # Only copy onnxruntime DLL if it exists
    COMMAND ${CMAKE_COMMAND} -E $<IF:$<BOOL:${ONNXRUNTIME_DLL}>,copy_if_different,echo>
      $<IF:$<BOOL:${ONNXRUNTIME_DLL}>,${ONNXRUNTIME_DLL},"ONNX Runtime DLL not found - using static library">
      $<IF:$<BOOL:${ONNXRUNTIME_DLL}>,$<TARGET_FILE_DIR:piper>/onnxruntime.dll,"")
    
    # List all files in the output directory for debugging
    COMMAND ${CMAKE_COMMAND} -E echo "Files in output directory:"
    COMMAND ${CMAKE_COMMAND} -E echo "$<TARGET_FILE_DIR:piper>"
    COMMAND dir "$<TARGET_FILE_DIR:piper>"
    
    COMMENT "Copying required DLLs for Windows..."
  )
  
  # Same for test_piper
  add_custom_command(TARGET test_piper POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying ONNX Runtime DLL for tests if needed..."
    
    # Only copy onnxruntime DLL if it exists
    COMMAND ${CMAKE_COMMAND} -E $<IF:$<BOOL:${ONNXRUNTIME_DLL}>,copy_if_different,echo>
      $<IF:$<BOOL:${ONNXRUNTIME_DLL}>,${ONNXRUNTIME_DLL},"ONNX Runtime DLL not found - using static library">
      $<IF:$<BOOL:${ONNXRUNTIME_DLL}>,$<TARGET_FILE_DIR:test_piper>/onnxruntime.dll,"">
    
    COMMENT "Copying required DLLs for test_piper..."
  )
endif()

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
  PATTERN "*.exe"
)

# On Windows, also install DLLs to bin directory for easier PATH management
if(MSVC)
  install(
    DIRECTORY ${PIPER_PHONEMIZE_DIR}/lib/
    DESTINATION bin
    FILES_MATCHING
    PATTERN "*.dll"
  )
  
  # Also install ONNX Runtime DLLs which might be in a different location
  install(
    FILES
      ${PIPER_PHONEMIZE_DIR}/lib/onnxruntime.dll
      ${PIPER_PHONEMIZE_DIR}/bin/onnxruntime.dll
      ${CMAKE_CURRENT_BINARY_DIR}/pi/src/piper_phonemize_external-build/_deps/onnxruntime-src/lib/onnxruntime.dll
      ${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/onnxruntime-src/lib/onnxruntime.dll
    DESTINATION bin
    OPTIONAL  # Don't fail if not found
  )
endif()

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
if(MSVC)
  # Windows: Install OpenJTalk stub binary
  install(
    PROGRAMS ${OPENJTALK_DIR}/bin/open_jtalk.exe
    DESTINATION bin
    OPTIONAL  # Don't fail if not built
  )

  # Install OpenJTalk dictionary (if available)
  install(
    DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/share/open_jtalk
    DESTINATION share
    OPTIONAL  # Don't fail if not present
  )
elseif(NOT WIN32)
  # Unix platforms: Install OpenJTalk binary
  install(
    PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/oj/bin/open_jtalk
    DESTINATION bin
    OPTIONAL  # Don't fail if not built
  )

  # Install OpenJTalk dictionary
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