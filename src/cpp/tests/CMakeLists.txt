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

    # Link additional dependencies for streaming test - using same approach as test_piper
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
        
        # Include directories
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/fi/include
            ${CMAKE_BINARY_DIR}/si/include
            ${CMAKE_BINARY_DIR}/pi/include
        )
        
        # Add library directories
        target_link_directories(${test_name} PRIVATE
            ${CMAKE_BINARY_DIR}/fi/lib
            ${CMAKE_BINARY_DIR}/si/lib
            ${CMAKE_BINARY_DIR}/pi/lib
        )
        
        # Platform-specific library linking (same as main piper)
        if(WIN32)
            # Windows: Link libraries directly
            target_link_libraries(${test_name}
                optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
                debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
                optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
                debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
                ${CMAKE_BINARY_DIR}/pi/lib/piper_phonemize.lib
                ${CMAKE_BINARY_DIR}/pi/lib/espeak-ng.lib
                ${CMAKE_BINARY_DIR}/pi/lib/onnxruntime.lib
            )
        else()
            # Unix: Use library names and let CMake find them in link directories
            target_link_libraries(${test_name}
                fmt
                spdlog
                piper_phonemize
                espeak-ng
                onnxruntime
            )
        endif()
        
        # Platform-specific linking
        if(UNIX)
            find_package(Threads REQUIRED)
            target_link_libraries(${test_name} Threads::Threads)
        endif()
        
        # Add dependencies to ensure build order
        add_dependencies(${test_name} 
            piper_phonemize_external 
            fmt_external 
            spdlog_external
        )
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