# C++ Tests CMake configuration

# Resolve ONNX Runtime paths (Windows uses ONNXRUNTIME_INCLUDE_DIR/ONNXRUNTIME_LIB, Linux/macOS uses ort/ prefix)
if(ONNXRUNTIME_INCLUDE_DIR)
    set(ORT_INCLUDE_DIR ${ONNXRUNTIME_INCLUDE_DIR})
else()
    set(ORT_INCLUDE_DIR ${CMAKE_BINARY_DIR}/ort/include)
endif()

if(ONNXRUNTIME_LIB)
    get_filename_component(ORT_LIB_DIR ${ONNXRUNTIME_LIB} DIRECTORY)
else()
    set(ORT_LIB_DIR ${CMAKE_BINARY_DIR}/ort/lib)
endif()

# Add global compile definitions for all tests
add_compile_definitions(SPDLOG_FMT_EXTERNAL=1)
add_compile_definitions(FMT_HEADER_ONLY=1)

# Macro: Link OpenJTalk static library and dependencies to a test target
macro(link_openjtalk_to_test target_name)
    target_include_directories(${target_name} PRIVATE
        ${CMAKE_BINARY_DIR}/oj/include
        ${CMAKE_BINARY_DIR}/oj/include/openjtalk
        # hts_stub/include: OpenJTalk ヘッダーの HTS_engine.h 依存を満たす互換シム
        ${CMAKE_BINARY_DIR}/hts_stub/include
    )
    if(WIN32)
        target_link_libraries(${target_name} ${CMAKE_BINARY_DIR}/oj/lib/openjtalk.lib)
    else()
        target_link_libraries(${target_name} ${CMAKE_BINARY_DIR}/oj/lib/libopenjtalk.a)
    endif()
    # hts_engine_stub: HTS 合成は不使用。OpenJTalk のリンク時シンボル解決にのみ必要。
    if(TARGET hts_engine_stub)
        target_link_libraries(${target_name} hts_engine_stub)
    endif()
    if(TARGET openjtalk_external)
        add_dependencies(${target_name} openjtalk_external)
    endif()
endmacro()

# Test sources
set(TEST_SOURCES
    test_phonemize.cpp
    test_piper_core.cpp
    test_openjtalk_security.cpp
    test_openjtalk_error_handling.cpp
    test_gpu_device_id.cpp
    test_phoneme_parser.cpp
    test_streaming.cpp
    test_streaming_simple.cpp
    test_streaming_raw_phonemes.cpp
    test_n_variants.cpp
    test_question_markers.cpp
    test_model_speaker_detection.cpp
    test_custom_dictionary.cpp
    test_text_input.cpp
    test_model_manager.cpp
    test_download_utils.cpp
    test_multilingual_g2p.cpp
    test_swedish_phonemize.cpp
    test_short_text_mitigation.cpp
    test_split_sentences.cpp
)

# Add Unix-only tests (require open_jtalk binary or Unix APIs)
if(NOT WIN32 AND NOT MSVC)
    list(APPEND TEST_SOURCES
        test_dictionary_manager.cpp
        test_openjtalk_optimized.cpp
    )
endif()

# Add prosody inference test only when ONNX Runtime headers are available
if(EXISTS "${ORT_INCLUDE_DIR}/onnxruntime_cxx_api.h" OR EXISTS "${CMAKE_BINARY_DIR}/pi/include/onnxruntime_cxx_api.h")
    list(APPEND TEST_SOURCES test_prosody_inference.cpp)
endif()

# Create test executables
foreach(test_source ${TEST_SOURCES})
    get_filename_component(test_name ${test_source} NAME_WE)
    add_executable(${test_name} ${test_source})

    # Base libraries
    target_link_libraries(${test_name}
        gtest
        gtest_main
    )
    
    # Add Windows-specific library directories for all tests
    if(WIN32)
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/fi/lib
            ${CMAKE_BINARY_DIR}/si/lib
        )
    endif()
    
    # Add spdlog/fmt dependencies for all tests
    if(TARGET spdlog_external)
        add_dependencies(${test_name} spdlog_external)
    endif()
    if(TARGET fmt_external)
        add_dependencies(${test_name} fmt_external)
    endif()
    
    # Add include directories for spdlog/fmt
    target_include_directories(${test_name} PRIVATE
        ${CMAKE_BINARY_DIR}/si/include
        ${CMAKE_BINARY_DIR}/fi/include
    )
    
    # Link additional dependencies for dictionary manager test
    if(${test_name} STREQUAL "test_dictionary_manager" AND NOT WIN32 AND NOT MSVC)
        target_sources(${test_name} PRIVATE
            ../openjtalk_dictionary_manager.c
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        target_compile_definitions(${test_name} PRIVATE
            OPENJTALK_DIC_PATH="../share/open_jtalk/dic"
        )
    endif()
    
    # Link utf8_utils.hpp include path for split sentences test
    if(${test_name} STREQUAL "test_split_sentences")
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
    endif()

    # Link additional dependencies for custom dictionary test
    if(${test_name} STREQUAL "test_custom_dictionary")
        target_sources(${test_name} PRIVATE
            ../custom_dictionary.cpp
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
    endif()

    # Link additional dependencies for model manager test
    if(${test_name} STREQUAL "test_model_manager")
        target_sources(${test_name} PRIVATE
            ../model_manager.cpp
            ../library_path.c
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        # model_manager.cpp uses spdlog for logging
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/si/lib
            ${CMAKE_BINARY_DIR}/fi/lib
        )
        if(WIN32)
            target_link_libraries(${test_name}
                optimized spdlog.lib
                debug spdlogd.lib
                optimized fmt.lib
                debug fmtd.lib
            )
        else()
            target_link_libraries(${test_name} spdlog fmt)
            # library_path.c uses dladdr which requires libdl on Linux
            if(UNIX AND NOT APPLE)
                target_link_libraries(${test_name} dl)
            endif()
        endif()
    endif()

    # Link additional dependencies for security test
    if(${test_name} STREQUAL "test_openjtalk_security")
        target_sources(${test_name} PRIVATE
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_api.c
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name}
            Threads::Threads
        )
        link_openjtalk_to_test(${test_name})
    endif()

    # Link additional dependencies for error handling test
    if(${test_name} STREQUAL "test_openjtalk_error_handling")
        target_sources(${test_name} PRIVATE
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_api.c
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name}
            Threads::Threads
        )
        link_openjtalk_to_test(${test_name})
    endif()

    # Link additional dependencies for optimized test
    if(${test_name} STREQUAL "test_openjtalk_optimized")
        target_sources(${test_name} PRIVATE
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_optimized.c
            ../openjtalk_api.c
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name}
            Threads::Threads
        )
        link_openjtalk_to_test(${test_name})
    endif()

    # Link additional dependencies for streaming test
    if(${test_name} STREQUAL "test_streaming")
        target_sources(${test_name} PRIVATE
            ../piper.cpp
            ../phoneme_parser.cpp
            ../custom_dictionary.cpp
            ../model_manager.cpp
            ../library_path.c
            ../language_detector.cpp
            ../english_phonemize.cpp
            ../chinese_phonemize.cpp
            ../korean_phonemize.cpp
            ../spanish_phonemize.cpp
            ../french_phonemize.cpp
            ../portuguese_phonemize.cpp
            ../swedish_phonemize.cpp
            ../openjtalk_phonemize.cpp
            ../openjtalk_phonemize_utils.cpp
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_optimized.c
            ../openjtalk_api.c
        )

        # Include directories
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/fi/include
            ${CMAKE_BINARY_DIR}/si/include
            ${ORT_INCLUDE_DIR}
            ${CMAKE_BINARY_DIR}/oj/include
            ${CMAKE_BINARY_DIR}/oj/include/openjtalk
        )

        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/fi/lib
            ${CMAKE_BINARY_DIR}/si/lib
            ${ORT_LIB_DIR}
        )

        # Platform-specific library linking (same as main piper)
        if(WIN32)
            # Windows: Link libraries directly
            target_link_libraries(${test_name}
                optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
                debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
                optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
                debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
                ${ORT_LIB_DIR}/onnxruntime.lib
            )
        else()
            # Unix: Use library names and let CMake find them in link directories
            target_link_libraries(${test_name}
                fmt
                spdlog
                onnxruntime
            )
        endif()

        # Platform-specific linking
        if(UNIX)
            find_package(Threads REQUIRED)
            target_link_libraries(${test_name} Threads::Threads)
            # library_path.c uses dladdr which requires libdl on Linux
            if(NOT APPLE)
                target_link_libraries(${test_name} dl)
            endif()
        endif()

        # Link OpenJTalk static library
        link_openjtalk_to_test(${test_name})

        # Add dependencies to ensure build order
        add_dependencies(${test_name}
            fmt_external
            spdlog_external
        )
    endif()

    # Link additional dependencies for streaming test - using same approach as test_piper
    if(${test_name} STREQUAL "test_streaming_simple")
        target_sources(${test_name} PRIVATE
            ../piper.cpp
            ../phoneme_parser.cpp
            ../custom_dictionary.cpp
            ../model_manager.cpp
            ../library_path.c
            ../language_detector.cpp
            ../english_phonemize.cpp
            ../chinese_phonemize.cpp
            ../korean_phonemize.cpp
            ../spanish_phonemize.cpp
            ../french_phonemize.cpp
            ../portuguese_phonemize.cpp
            ../swedish_phonemize.cpp
            ../openjtalk_phonemize.cpp
            ../openjtalk_phonemize_utils.cpp
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_optimized.c
            ../openjtalk_api.c
        )

        # Include directories
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/fi/include
            ${CMAKE_BINARY_DIR}/si/include
            ${ORT_INCLUDE_DIR}
            ${CMAKE_BINARY_DIR}/oj/include
            ${CMAKE_BINARY_DIR}/oj/include/openjtalk
        )

        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/fi/lib
            ${CMAKE_BINARY_DIR}/si/lib
            ${ORT_LIB_DIR}
        )

        # Platform-specific library linking (same as main piper)
        if(WIN32)
            # Windows: Link libraries directly
            target_link_libraries(${test_name}
                optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
                debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
                optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
                debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
                ${ORT_LIB_DIR}/onnxruntime.lib
            )
        else()
            # Unix: Use library names and let CMake find them in link directories
            target_link_libraries(${test_name}
                fmt
                spdlog
                onnxruntime
            )
        endif()

        # Platform-specific linking
        if(UNIX)
            find_package(Threads REQUIRED)
            target_link_libraries(${test_name} Threads::Threads)
            # library_path.c uses dladdr which requires libdl on Linux
            if(NOT APPLE)
                target_link_libraries(${test_name} dl)
            endif()
        endif()

        # Link OpenJTalk static library
        link_openjtalk_to_test(${test_name})

        # Add dependencies to ensure build order
        add_dependencies(${test_name}
            fmt_external
            spdlog_external
        )
    endif()

    # Link additional dependencies for prosody inference test
    if(${test_name} STREQUAL "test_prosody_inference")
        # Test-only: No additional source files needed (pure unit tests)
        # Just needs ONNX Runtime headers and libraries

        # Include directories
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/fi/include
            ${CMAKE_BINARY_DIR}/si/include
            ${ORT_INCLUDE_DIR}
        )

        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/fi/lib
            ${CMAKE_BINARY_DIR}/si/lib
            ${ORT_LIB_DIR}
        )

        # Platform-specific library linking
        if(WIN32)
            target_link_libraries(${test_name}
                ${ORT_LIB_DIR}/onnxruntime.lib
            )
        else()
            target_link_libraries(${test_name}
                onnxruntime
            )
        endif()

        # Platform-specific linking
        if(UNIX)
            find_package(Threads REQUIRED)
            target_link_libraries(${test_name} Threads::Threads)
        endif()
    endif()

    # Link additional dependencies for streaming raw phonemes test
    if(${test_name} STREQUAL "test_streaming_raw_phonemes")
        target_sources(${test_name} PRIVATE
            ../piper.cpp
            ../phoneme_parser.cpp
            ../custom_dictionary.cpp
            ../model_manager.cpp
            ../library_path.c
            ../language_detector.cpp
            ../english_phonemize.cpp
            ../chinese_phonemize.cpp
            ../korean_phonemize.cpp
            ../spanish_phonemize.cpp
            ../french_phonemize.cpp
            ../portuguese_phonemize.cpp
            ../swedish_phonemize.cpp
            ../openjtalk_phonemize.cpp
            ../openjtalk_phonemize_utils.cpp
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_optimized.c
            ../openjtalk_api.c
        )

        # Include directories
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/fi/include
            ${CMAKE_BINARY_DIR}/si/include
            ${ORT_INCLUDE_DIR}
            ${CMAKE_BINARY_DIR}/oj/include
            ${CMAKE_BINARY_DIR}/oj/include/openjtalk
        )

        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/fi/lib
            ${CMAKE_BINARY_DIR}/si/lib
            ${ORT_LIB_DIR}
        )

        # Platform-specific library linking (same as main piper)
        if(WIN32)
            # Windows: Link libraries directly
            target_link_libraries(${test_name}
                optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
                debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
                optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
                debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
                ${ORT_LIB_DIR}/onnxruntime.lib
            )
        else()
            # Unix: Use library names and let CMake find them in link directories
            target_link_libraries(${test_name}
                fmt
                spdlog
                onnxruntime
            )
        endif()

        # Platform-specific linking
        if(UNIX)
            find_package(Threads REQUIRED)
            target_link_libraries(${test_name} Threads::Threads)
            # library_path.c uses dladdr which requires libdl on Linux
            if(NOT APPLE)
                target_link_libraries(${test_name} dl)
            endif()
        endif()

        # Link OpenJTalk static library
        link_openjtalk_to_test(${test_name})

        # Add dependencies to ensure build order
        add_dependencies(${test_name}
            fmt_external
            spdlog_external
        )
    endif()

    # Link additional dependencies for phoneme parser test
    if(${test_name} STREQUAL "test_phoneme_parser")
        target_sources(${test_name} PRIVATE
            ../phoneme_parser.cpp
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/si/include
            ${CMAKE_BINARY_DIR}/fi/include
        )
        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/si/lib
            ${CMAKE_BINARY_DIR}/fi/lib
        )
        if(WIN32)
            target_link_libraries(${test_name}
                optimized spdlog.lib
                debug spdlogd.lib
                optimized fmt.lib
                debug fmtd.lib
            )
        else()
            target_link_libraries(${test_name}
                spdlog
                fmt
            )
        endif()
        # Ensure dependencies are built first
        add_dependencies(${test_name} spdlog_external fmt_external)
    endif()

    # Link utils source for N variants and question markers tests
    if(${test_name} STREQUAL "test_n_variants" OR ${test_name} STREQUAL "test_question_markers")
        target_sources(${test_name} PRIVATE
            ../openjtalk_phonemize_utils.cpp
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
    endif()

    # Link additional dependencies for multilingual G2P test
    if(${test_name} STREQUAL "test_multilingual_g2p")
        target_sources(${test_name} PRIVATE
            ../language_detector.cpp
            ../english_phonemize.cpp
            ../chinese_phonemize.cpp
            ../spanish_phonemize.cpp
            ../french_phonemize.cpp
            ../portuguese_phonemize.cpp
            ../swedish_phonemize.cpp
            ../korean_phonemize.cpp
            ../phoneme_parser.cpp
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/si/include
            ${CMAKE_BINARY_DIR}/fi/include
            ${ORT_INCLUDE_DIR}
        )
        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/si/lib
            ${CMAKE_BINARY_DIR}/fi/lib
        )
        if(WIN32)
            target_link_libraries(${test_name}
                optimized spdlog.lib
                debug spdlogd.lib
                optimized fmt.lib
                debug fmtd.lib
            )
        else()
            target_link_libraries(${test_name}
                spdlog
                fmt
            )
        endif()
        # Ensure dependencies are built first
        add_dependencies(${test_name} spdlog_external fmt_external)
    endif()

    # Link additional dependencies for Swedish phonemize test
    if(${test_name} STREQUAL "test_swedish_phonemize")
        target_sources(${test_name} PRIVATE
            ../swedish_phonemize.cpp
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
    endif()

    add_test(NAME ${test_name} COMMAND ${test_name})
    set_tests_properties(${test_name} PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    )
endforeach()

# Add test_phoneme_timing - only uses gtest and json.hpp (no spdlog/fmt)
add_executable(test_phoneme_timing test_phoneme_timing.cpp)
target_include_directories(test_phoneme_timing PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../
    ${CMAKE_CURRENT_SOURCE_DIR}/../../
)
target_link_libraries(test_phoneme_timing
    gtest_main
)

add_test(NAME test_phoneme_timing COMMAND test_phoneme_timing)

# ---- test_library_path: library_path.c unit tests ----
add_executable(test_library_path
    test_library_path.cpp
    ../library_path.c
)

target_link_libraries(test_library_path
    gtest
    gtest_main
)

target_include_directories(test_library_path PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/..
)

# library_path.c uses dladdr which requires libdl on Linux
if(UNIX AND NOT APPLE)
    target_link_libraries(test_library_path dl)
endif()

add_test(NAME test_library_path COMMAND test_library_path)

# ---- test_c_api: C API shared library unit tests ----
# Compiles piper_plus_c_api.cpp directly with piper_common static library.
# piper_plus_c_api.cpp wraps the full piper:: namespace, so it needs
# the same dependencies as the streaming tests (onnxruntime, openjtalk, etc.).
# (issue #377: piper_common is STATIC since iOS toolchain regression.)
add_executable(test_c_api
    test_c_api.cpp
    ../piper_plus_c_api.cpp
)

target_link_libraries(test_c_api PRIVATE
    piper_common
    gtest
    gtest_main
)

target_compile_definitions(test_c_api PRIVATE
    PIPER_PLUS_BUILDING_DLL
    _PIPER_VERSION=${piper_version}
)

# Include directories: piper_plus.h lives in src/cpp/
target_include_directories(test_c_api PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/..
    ${CMAKE_BINARY_DIR}/fi/include
    ${CMAKE_BINARY_DIR}/si/include
    ${ORT_INCLUDE_DIR}
    ${CMAKE_BINARY_DIR}/oj/include
    ${CMAKE_BINARY_DIR}/oj/include/openjtalk
)

# Library directories
target_link_directories(test_c_api PRIVATE
    ${CMAKE_BINARY_DIR}/fi/lib
    ${CMAKE_BINARY_DIR}/si/lib
    ${ORT_LIB_DIR}
)

# Platform-specific library linking
if(WIN32)
    target_link_libraries(test_c_api PRIVATE
        optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
        debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
        optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
        debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
        ${ORT_LIB_DIR}/onnxruntime.lib
    )
    target_link_libraries(test_c_api PRIVATE ${CMAKE_BINARY_DIR}/oj/lib/openjtalk.lib)
else()
    target_link_libraries(test_c_api PRIVATE
        fmt
        spdlog
        onnxruntime
    )
    target_link_libraries(test_c_api PRIVATE ${CMAKE_BINARY_DIR}/oj/lib/libopenjtalk.a)
endif()

# HTS Engine stub
if(TARGET hts_engine_stub)
    target_link_libraries(test_c_api PRIVATE hts_engine_stub)
endif()

# Platform-specific threading
if(UNIX)
    find_package(Threads REQUIRED)
    target_link_libraries(test_c_api PRIVATE Threads::Threads)
    # library_path.c uses dladdr which requires libdl on Linux
    if(NOT APPLE)
        target_link_libraries(test_c_api PRIVATE dl)
    endif()
endif()

# Build order dependencies
if(TARGET fmt_external)
    add_dependencies(test_c_api fmt_external)
endif()
if(TARGET spdlog_external)
    add_dependencies(test_c_api spdlog_external)
endif()
if(TARGET openjtalk_external)
    add_dependencies(test_c_api openjtalk_external)
endif()

add_test(NAME test_c_api COMMAND test_c_api)
set_tests_properties(test_c_api PROPERTIES TIMEOUT 60)

# ---- test_c_api_integration: C API integration tests (model required) ----
# Links against the piper_plus shared library (or static lib for embedded build).
# Uses piper_common static library for the full piper engine. (issue #377)
add_executable(test_c_api_integration
    test_c_api_integration.cpp
    ../piper_plus_c_api.cpp
)

target_link_libraries(test_c_api_integration PRIVATE
    piper_common
    gtest
    gtest_main
)

target_compile_definitions(test_c_api_integration PRIVATE
    PIPER_PLUS_BUILDING_DLL
    _PIPER_VERSION=${piper_version}
)

target_include_directories(test_c_api_integration PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/..
    ${CMAKE_BINARY_DIR}/fi/include
    ${CMAKE_BINARY_DIR}/si/include
    ${ORT_INCLUDE_DIR}
    ${CMAKE_BINARY_DIR}/oj/include
    ${CMAKE_BINARY_DIR}/oj/include/openjtalk
)

target_link_directories(test_c_api_integration PRIVATE
    ${CMAKE_BINARY_DIR}/fi/lib
    ${CMAKE_BINARY_DIR}/si/lib
    ${ORT_LIB_DIR}
)

if(WIN32)
    target_link_libraries(test_c_api_integration PRIVATE
        optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
        debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
        optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
        debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
        ${ORT_LIB_DIR}/onnxruntime.lib
    )
    target_link_libraries(test_c_api_integration PRIVATE ${CMAKE_BINARY_DIR}/oj/lib/openjtalk.lib)
else()
    target_link_libraries(test_c_api_integration PRIVATE
        fmt
        spdlog
        onnxruntime
    )
    target_link_libraries(test_c_api_integration PRIVATE ${CMAKE_BINARY_DIR}/oj/lib/libopenjtalk.a)
endif()

if(TARGET hts_engine_stub)
    target_link_libraries(test_c_api_integration PRIVATE hts_engine_stub)
endif()

if(UNIX)
    find_package(Threads REQUIRED)
    target_link_libraries(test_c_api_integration PRIVATE Threads::Threads)
    # library_path.c uses dladdr which requires libdl on Linux
    if(NOT APPLE)
        target_link_libraries(test_c_api_integration PRIVATE dl)
    endif()
endif()

if(TARGET fmt_external)
    add_dependencies(test_c_api_integration fmt_external)
endif()
if(TARGET spdlog_external)
    add_dependencies(test_c_api_integration spdlog_external)
endif()
if(TARGET openjtalk_external)
    add_dependencies(test_c_api_integration openjtalk_external)
endif()

add_test(NAME test_c_api_integration COMMAND test_c_api_integration)

# Set working directory to project root for model path resolution
set_tests_properties(test_c_api_integration PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    TIMEOUT 300
)

# ---- test_c_api_audio_regression: Audio regression tests (M5-21, model required) ----
# Near-deterministic synthesis output checked for sample count range + RMS energy.
add_executable(test_c_api_audio_regression
    test_c_api_audio_regression.cpp
    ../piper_plus_c_api.cpp
)

target_link_libraries(test_c_api_audio_regression PRIVATE
    piper_common
    gtest
    gtest_main
)

target_compile_definitions(test_c_api_audio_regression PRIVATE
    PIPER_PLUS_BUILDING_DLL
    _PIPER_VERSION=${piper_version}
)

target_include_directories(test_c_api_audio_regression PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/..
    ${CMAKE_BINARY_DIR}/fi/include
    ${CMAKE_BINARY_DIR}/si/include
    ${ORT_INCLUDE_DIR}
    ${CMAKE_BINARY_DIR}/oj/include
    ${CMAKE_BINARY_DIR}/oj/include/openjtalk
)

target_link_directories(test_c_api_audio_regression PRIVATE
    ${CMAKE_BINARY_DIR}/fi/lib
    ${CMAKE_BINARY_DIR}/si/lib
    ${ORT_LIB_DIR}
)

if(WIN32)
    target_link_libraries(test_c_api_audio_regression PRIVATE
        optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
        debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
        optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
        debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
        ${ORT_LIB_DIR}/onnxruntime.lib
    )
    target_link_libraries(test_c_api_audio_regression PRIVATE ${CMAKE_BINARY_DIR}/oj/lib/openjtalk.lib)
else()
    target_link_libraries(test_c_api_audio_regression PRIVATE
        fmt
        spdlog
        onnxruntime
    )
    target_link_libraries(test_c_api_audio_regression PRIVATE ${CMAKE_BINARY_DIR}/oj/lib/libopenjtalk.a)
endif()

if(TARGET hts_engine_stub)
    target_link_libraries(test_c_api_audio_regression PRIVATE hts_engine_stub)
endif()

if(UNIX)
    find_package(Threads REQUIRED)
    target_link_libraries(test_c_api_audio_regression PRIVATE Threads::Threads)
    # library_path.c uses dladdr which requires libdl on Linux
    if(NOT APPLE)
        target_link_libraries(test_c_api_audio_regression PRIVATE dl)
    endif()
endif()

if(TARGET fmt_external)
    add_dependencies(test_c_api_audio_regression fmt_external)
endif()
if(TARGET spdlog_external)
    add_dependencies(test_c_api_audio_regression spdlog_external)
endif()
if(TARGET openjtalk_external)
    add_dependencies(test_c_api_audio_regression openjtalk_external)
endif()

add_test(NAME test_c_api_audio_regression COMMAND test_c_api_audio_regression)

# Set working directory to project root for model path resolution
set_tests_properties(test_c_api_audio_regression PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    TIMEOUT 300
)