# C++ Tests CMake configuration

# Test sources
set(TEST_SOURCES
    test_phonemize.cpp
    test_piper_core.cpp
    test_openjtalk_security.cpp
    test_openjtalk_error_handling.cpp
    test_openjtalk_optimized.cpp
    test_gpu_device_id.cpp
    test_phoneme_parser.cpp
    test_streaming_simple.cpp
)

# Add dictionary manager test for Unix platforms
if(NOT WIN32 AND NOT MSVC)
    list(APPEND TEST_SOURCES test_dictionary_manager.cpp)
endif()

# Create test executables
foreach(test_source ${TEST_SOURCES})
    get_filename_component(test_name ${test_source} NAME_WE)
    add_executable(${test_name} ${test_source})

    target_link_libraries(${test_name}
        gtest
        gtest_main
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
    
    # Link additional dependencies for security test
    if(${test_name} STREQUAL "test_openjtalk_security")
        target_sources(${test_name} PRIVATE
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            # ../openjtalk_api.c  # Temporarily disabled - requires OpenJTalk static libs
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name}
            Threads::Threads
        )
    endif()
    
    # Link additional dependencies for error handling test
    if(${test_name} STREQUAL "test_openjtalk_error_handling")
        target_sources(${test_name} PRIVATE
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            # ../openjtalk_api.c  # Temporarily disabled - requires OpenJTalk static libs
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name}
            Threads::Threads
        )
    endif()
    
    # Link additional dependencies for optimized test
    if(${test_name} STREQUAL "test_openjtalk_optimized")
        target_sources(${test_name} PRIVATE
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_optimized.c
            # ../openjtalk_api.c  # Temporarily disabled - requires OpenJTalk static libs
        )
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
        )
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name}
            Threads::Threads
        )
    endif()

    # Link additional dependencies for streaming test
    if(${test_name} STREQUAL "test_streaming_simple")
        target_sources(${test_name} PRIVATE
            ../piper.cpp
            ../phoneme_parser.cpp
            ../openjtalk_phonemize.cpp
            ../openjtalk_wrapper.c
            ../openjtalk_dictionary_manager.c
            ../openjtalk_error.c
            ../openjtalk_security.c
            ../openjtalk_optimized.c
        )
        # Set SPDLOG_DIR if not defined
        if(NOT DEFINED SPDLOG_DIR)
            set(SPDLOG_DIR "${CMAKE_BINARY_DIR}/si")
        endif()
        # Set espeak-ng include path
        set(ESPEAK_NG_DIR "${CMAKE_BINARY_DIR}/p/src/piper_phonemize_external-build/ei")
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/pi/include
            ${CMAKE_BINARY_DIR}/e/include
            ${CMAKE_BINARY_DIR}/o/include
            ${SPDLOG_DIR}/include
            ${ESPEAK_NG_DIR}/include
        )
        # Link against piper_phonemize library with platform-specific extension
        if(WIN32)
            set(PIPER_PHONEMIZE_LIB "${CMAKE_BINARY_DIR}/p/src/piper_phonemize_external-build/piper_phonemize.dll")
        elseif(APPLE)
            set(PIPER_PHONEMIZE_LIB "${CMAKE_BINARY_DIR}/p/src/piper_phonemize_external-build/libpiper_phonemize.dylib")
        else()
            set(PIPER_PHONEMIZE_LIB "${CMAKE_BINARY_DIR}/p/src/piper_phonemize_external-build/libpiper_phonemize.so")
        endif()
        
        # Set espeak-ng library path
        if(WIN32)
            set(ESPEAK_NG_LIB "${ESPEAK_NG_DIR}/lib/espeak-ng.dll")
        elseif(APPLE)
            set(ESPEAK_NG_LIB "${ESPEAK_NG_DIR}/lib/libespeak-ng.dylib")
        else()
            set(ESPEAK_NG_LIB "${ESPEAK_NG_DIR}/lib/libespeak-ng.so")
        endif()
        
        if(EXISTS ${PIPER_PHONEMIZE_LIB})
            target_link_libraries(${test_name}
                ${PIPER_PHONEMIZE_LIB}
            )
        else()
            # Fallback to library name
            target_link_libraries(${test_name}
                piper_phonemize
            )
        endif()
        
        if(EXISTS ${ESPEAK_NG_LIB})
            target_link_libraries(${test_name}
                ${ESPEAK_NG_LIB}
            )
        else()
            target_link_libraries(${test_name}
                espeak-ng
            )
        endif()
        
        # Set onnxruntime library path
        if(WIN32)
            set(ONNXRUNTIME_LIB "${CMAKE_BINARY_DIR}/pi/lib/onnxruntime.dll")
        elseif(APPLE)
            set(ONNXRUNTIME_LIB "${CMAKE_BINARY_DIR}/pi/lib/libonnxruntime.dylib")
        else()
            set(ONNXRUNTIME_LIB "${CMAKE_BINARY_DIR}/pi/lib/libonnxruntime.so")
        endif()
        
        if(EXISTS ${ONNXRUNTIME_LIB})
            target_link_libraries(${test_name}
                ${ONNXRUNTIME_LIB}
            )
        else()
            target_link_libraries(${test_name}
                onnxruntime
            )
        endif()
        # Link spdlog
        if(WIN32)
            target_link_libraries(${test_name}
                optimized ${SPDLOG_DIR}/lib/spdlog.lib
                debug ${SPDLOG_DIR}/lib/spdlogd.lib
            )
        else()
            target_link_libraries(${test_name}
                ${SPDLOG_DIR}/lib/libspdlog.a
            )
        endif()
        if(UNIX AND NOT APPLE)
            find_package(Threads REQUIRED)
            target_link_libraries(${test_name} Threads::Threads)
        endif()
        # Add dependency on spdlog_external to ensure headers are available
        if(TARGET spdlog_external)
            add_dependencies(${test_name} spdlog_external)
        endif()
        # Add dependency on espeak-ng to ensure headers are available
        if(TARGET espeak_ng_external)
            add_dependencies(${test_name} espeak_ng_external)
        endif()
    endif()
    
    # Link additional dependencies for phoneme parser test
    if(${test_name} STREQUAL "test_phoneme_parser")
        target_sources(${test_name} PRIVATE
            ../phoneme_parser.cpp
        )
        # Set SPDLOG_DIR if not defined
        if(NOT DEFINED SPDLOG_DIR)
            set(SPDLOG_DIR "${CMAKE_BINARY_DIR}/si")
        endif()
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${SPDLOG_DIR}/include
        )
        if(WIN32)
            target_link_libraries(${test_name}
                optimized ${SPDLOG_DIR}/lib/spdlog.lib
                debug ${SPDLOG_DIR}/lib/spdlogd.lib
            )
        else()
            target_link_libraries(${test_name}
                ${SPDLOG_DIR}/lib/libspdlog.a
            )
        endif()
        # Add dependency on spdlog_external to ensure headers are available
        if(TARGET spdlog_external)
            add_dependencies(${test_name} spdlog_external)
        endif()
    endif()

    add_test(NAME ${test_name} COMMAND ${test_name})
endforeach()