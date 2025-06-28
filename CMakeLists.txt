cmake_minimum_required(VERSION 3.13)

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
      -DCMAKE_CXX_FLAGS_RELEASE="${CMAKE_CXX_FLAGS_RELEASE}"
      -DCMAKE_C_FLAGS_RELEASE="${CMAKE_C_FLAGS_RELEASE}"
      -DCMAKE_CXX_FLAGS_DEBUG="${CMAKE_CXX_FLAGS_DEBUG}"
      -DCMAKE_C_FLAGS_DEBUG="${CMAKE_C_FLAGS_DEBUG}"
      -DCMAKE_CXX_FLAGS="${CMAKE_CXX_FLAGS}"
      -DCMAKE_C_FLAGS="${CMAKE_C_FLAGS}"
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

# ---- piper-phonemize ---

if(NOT DEFINED PIPER_PHONEMIZE_DIR)
  set(PIPER_PHONEMIZE_DIR "${CMAKE_CURRENT_BINARY_DIR}/pi")
  ExternalProject_Add(
    piper_phonemize_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/p"
    URL "https://github.com/rhasspy/piper-phonemize/archive/refs/heads/master.zip"
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${PIPER_PHONEMIZE_DIR}
    CMAKE_ARGS -DBUILD_SHARED_LIBS:BOOL=OFF  # Build static libraries
    CMAKE_ARGS -DPIPER_PHONEMIZE_BUILD_TESTS:BOOL=OFF
    CMAKE_ARGS -DPIPER_PHONEMIZE_BUILD_PROGRAMS:BOOL=OFF
    CMAKE_ARGS ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(piper piper_phonemize_external)
  add_dependencies(test_piper piper_phonemize_external)
endif()

# ---- HTSEngine ---

if(NOT DEFINED HTS_ENGINE_DIR)
  set(HTS_ENGINE_DIR "${CMAKE_CURRENT_BINARY_DIR}/he")
  set(HTS_ENGINE_VERSION "1.10")

  if(MSVC)
    # Windows: Build HTSEngine without audio support
    # Note: We don't actually need HTSEngine on Windows since we use binary execution
    # This is just to satisfy the build dependencies
    file(MAKE_DIRECTORY ${HTS_ENGINE_DIR}/include)
    file(MAKE_DIRECTORY ${HTS_ENGINE_DIR}/lib)
    
    # Create dummy headers
    file(WRITE ${HTS_ENGINE_DIR}/include/HTS_engine.h "/* Dummy HTS_engine.h for Windows */\n")
    
    # Skip HTSEngine build on Windows
    add_custom_target(hts_engine_external ALL
      COMMENT "Skipping HTSEngine build on Windows (not needed for binary execution)"
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
    # Windows: Skip OpenJTalk build
    # OpenJTalk will be provided separately or built manually
    # The wrapper implementation will look for it at runtime
    file(MAKE_DIRECTORY ${OPENJTALK_DIR}/bin)
    file(MAKE_DIRECTORY ${OPENJTALK_DIR}/include)
    
    # Create dummy target
    add_custom_target(openjtalk_external ALL
      DEPENDS hts_engine_external
      COMMENT "OpenJTalk binary should be provided separately on Windows"
    )
  elseif(NOT WIN32)
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
elseif(NOT MSVC)
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra -Wl,-rpath,'$ORIGIN'")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  target_link_libraries(piper -static-libgcc -static-libstdc++)

  set(PIPER_EXTRA_LIBRARIES "pthread")
endif()

target_link_libraries(piper
  fmt
  spdlog
  piper_phonemize
  espeak-ng
  onnxruntime
  ${PIPER_EXTRA_LIBRARIES}
)

# Link OpenJTalk and HTS_Engine libraries
if(MSVC)
  # Windows: Ensure dummy targets are built
  add_dependencies(piper hts_engine_external openjtalk_external)
  add_dependencies(test_piper hts_engine_external openjtalk_external)
  # No linking needed on Windows - we use binary execution
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

# Note: We don't need Homebrew paths for espeak-ng on macOS
# because we're using the custom build from piper_phonemize

target_include_directories(piper PUBLIC
  ${FMT_DIR}/include
  ${SPDLOG_DIR}/include
  ${PIPER_PHONEMIZE_DIR}/include
)

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

target_link_libraries(test_piper
  fmt
  spdlog
  espeak-ng
  piper_phonemize
  onnxruntime
  ${PIPER_EXTRA_LIBRARIES}
)

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
  # Windows: Install OpenJTalk binary that we built
  install(
    PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/oj/bin/open_jtalk.exe
    DESTINATION bin
    OPTIONAL  # Don't fail if not built
  )

  # Install OpenJTalk dictionary (will be downloaded separately)
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