cmake_minimum_required(VERSION 3.14)

set(CMAKE_VERBOSE_MAKEFILE off)

project(
    piper_phonemize
    VERSION 1.2.0
    DESCRIPTION "Phonemization library for Piper text to speech system"
    HOMEPAGE_URL "https://github.com/rhasspy/piper-phonemize"
    LANGUAGES CXX
)

if(MSVC)
    # Force compiler to use UTF-8 for IPA constants
    add_compile_options("$<$<C_COMPILER_ID:MSVC>:/utf-8>")
    add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/utf-8>")

elseif(NOT APPLE)
    # Linux flags
    string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra -Wl,-rpath,'$ORIGIN'")
    string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
endif()

add_library(
    piper_phonemize SHARED
    src/phonemize.cpp
    src/phoneme_ids.cpp
    src/tashkeel.cpp
    src/shared.cpp
)

set_target_properties(piper_phonemize PROPERTIES
    VERSION ${PROJECT_VERSION}
    SOVERSION ${PROJECT_VERSION_MAJOR}
)

# ---- onnxruntime ---

# Look for onnxruntime files in <root>/lib
if(NOT DEFINED ONNXRUNTIME_DIR)
    if(NOT DEFINED ONNXRUNTIME_VERSION)
        set(ONNXRUNTIME_VERSION "1.14.1")
    endif()

    if(WIN32)
        # Windows x86-64
        set(ONNXRUNTIME_PREFIX "onnxruntime-win-x64-${ONNXRUNTIME_VERSION}")
        set(ONNXRUNTIME_EXT "zip")
    elseif (APPLE)
        if(CMAKE_SYSTEM_PROCESSOR STREQUAL x86_64)
            # MacOS x86-64
            set(ONNXRUNTIME_PREFIX "onnxruntime-osx-x86_64-${ONNXRUNTIME_VERSION}")
        elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL arm64)
            # MacOS Apple Silicon
            set(ONNXRUNTIME_PREFIX "onnxruntime-osx-arm64-${ONNXRUNTIME_VERSION}")
        else()
            message(FATAL_ERROR "Unsupported architecture for onnxruntime")
        endif()

        set(ONNXRUNTIME_EXT "tgz")
    else()
        if(CMAKE_SYSTEM_PROCESSOR STREQUAL x86_64)
            # Linux x86-64
            set(ONNXRUNTIME_PREFIX "onnxruntime-linux-x64-${ONNXRUNTIME_VERSION}")
        elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL aarch64)
            # Linux ARM 64-bit
            set(ONNXRUNTIME_PREFIX "onnxruntime-linux-aarch64-${ONNXRUNTIME_VERSION}")
        elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL armv7l)
            # Linux ARM 32-bit
            set(ONNXRUNTIME_PREFIX "onnxruntime-linux-arm32-${ONNXRUNTIME_VERSION}")
            set(ONNXRUNTIME_URL "https://github.com/synesthesiam/prebuilt-apps/releases/download/v1.0/onnxruntime-linux-arm32-${ONNXRUNTIME_VERSION}.tgz")
        else()
            message(FATAL_ERROR "Unsupported architecture for onnxruntime")
        endif()

        set(ONNXRUNTIME_EXT "tgz")
    endif()

    if(NOT DEFINED ONNXRUNTIME_URL)
        set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/${ONNXRUNTIME_PREFIX}.${ONNXRUNTIME_EXT}")
    endif()

    set(ONNXRUNTIME_FILENAME "${ONNXRUNTIME_PREFIX}.${ONNXRUNTIME_EXT}")
    set(ONNXRUNTIME_DIR "${CMAKE_CURRENT_LIST_DIR}/lib/${ONNXRUNTIME_PREFIX}")

    if(NOT EXISTS "${ONNXRUNTIME_DIR}")
        if(NOT EXISTS "download/${ONNXRUNTIME_FILENAME}")
            # Download onnxruntime release
            message("Downloading ${ONNXRUNTIME_URL}")
            file(DOWNLOAD "${ONNXRUNTIME_URL}" "download/${ONNXRUNTIME_FILENAME}")
        endif()

        # Extract .zip or .tgz to a directory like lib/onnxruntime-linux-x64-1.14.1/
        file(ARCHIVE_EXTRACT INPUT "download/${ONNXRUNTIME_FILENAME}" DESTINATION "${CMAKE_CURRENT_LIST_DIR}/lib")
    endif()
endif()

# ---- espeak-ng ---

if(NOT DEFINED ESPEAK_NG_DIR)
    set(ESPEAK_NG_DIR "${CMAKE_CURRENT_BINARY_DIR}/ei")

    include(ExternalProject)
    ExternalProject_Add(
        espeak_ng_external
        PREFIX "${CMAKE_CURRENT_BINARY_DIR}/e"
        URL "https://github.com/rhasspy/espeak-ng/archive/0f65aa301e0d6bae5e172cc74197d32a6182200f.zip"
        CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${ESPEAK_NG_DIR}
        CMAKE_ARGS -DUSE_ASYNC:BOOL=OFF
        CMAKE_ARGS -DBUILD_SHARED_LIBS:BOOL=ON
        CMAKE_ARGS -DUSE_MBROLA:BOOL=OFF
        CMAKE_ARGS -DUSE_LIBSONIC:BOOL=OFF
        CMAKE_ARGS -DUSE_LIBPCAUDIO:BOOL=OFF
        CMAKE_ARGS -DUSE_KLATT:BOOL=OFF
        CMAKE_ARGS -DUSE_SPEECHPLAYER:BOOL=OFF
        CMAKE_ARGS -DEXTRA_cmn:BOOL=ON
        CMAKE_ARGS -DEXTRA_ru:BOOL=ON
        CMAKE_ARGS -DCMAKE_C_FLAGS="-D_FILE_OFFSET_BITS=64"
    )
    add_dependencies(piper_phonemize espeak_ng_external)
endif()


# ---- Declare library ----

target_include_directories(
    piper_phonemize PUBLIC
    "$<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/src>"
    ${ESPEAK_NG_DIR}/include
    ${ONNXRUNTIME_DIR}/include
)

target_link_directories(
    piper_phonemize PUBLIC
    ${ESPEAK_NG_DIR}/lib
    ${ONNXRUNTIME_DIR}/lib
)

target_link_libraries(
    piper_phonemize
    espeak-ng
    onnxruntime
)

target_compile_features(piper_phonemize PUBLIC cxx_std_17)

# ---- Declare executable ----

add_executable(piper_phonemize_exe src/main.cpp src/phoneme_ids.cpp)

if(NOT WIN32)
    set_property(TARGET piper_phonemize_exe PROPERTY OUTPUT_NAME piper_phonemize)
endif()

target_compile_features(piper_phonemize_exe PUBLIC cxx_std_17)

target_include_directories(
    piper_phonemize_exe PUBLIC
    "$<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/src>"
    ${ESPEAK_NG_DIR}/include
)

target_link_directories(
    piper_phonemize_exe PUBLIC
    ${ESPEAK_NG_DIR}/lib
)

target_link_libraries(piper_phonemize_exe PUBLIC
    piper_phonemize
    espeak-ng
)

# ---- Declare test ----

include(CTest)
enable_testing()
add_executable(test_piper_phonemize src/test.cpp src/phoneme_ids.cpp)
add_test(
    NAME test_piper_phonemize
    COMMAND test_piper_phonemize "${ESPEAK_NG_DIR}/share/espeak-ng-data" "${CMAKE_SOURCE_DIR}/etc/libtashkeel_model.ort"
)

target_compile_features(test_piper_phonemize PUBLIC cxx_std_17)

target_include_directories(
    test_piper_phonemize PUBLIC
    "$<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/src>"
    ${ESPEAK_NG_DIR}/include
)

target_link_directories(
    test_piper_phonemize PUBLIC
    ${ESPEAK_NG_DIR}/lib
)

target_link_libraries(test_piper_phonemize PUBLIC
    piper_phonemize
    espeak-ng
)

# ---- Declare install targets ----

include(GNUInstallDirs)

install(
    TARGETS piper_phonemize
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})

install(
    DIRECTORY ${CMAKE_SOURCE_DIR}/src/
    DESTINATION include/piper-phonemize
    FILES_MATCHING
    PATTERN "*.h"
    PATTERN "*.hpp")

install(
    TARGETS piper_phonemize_exe
    ARCHIVE DESTINATION ${CMAKE_INSTALL_BINDIR})

install(
    FILES ${CMAKE_SOURCE_DIR}/etc/libtashkeel_model.ort
    TYPE DATA)

# Dependencies
install(
    DIRECTORY ${ESPEAK_NG_DIR}/
    DESTINATION ${CMAKE_INSTALL_PREFIX})

install(
    DIRECTORY ${ONNXRUNTIME_DIR}/include/
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

install(
    DIRECTORY ${ONNXRUNTIME_DIR}/lib/
    DESTINATION ${CMAKE_INSTALL_LIBDIR})
