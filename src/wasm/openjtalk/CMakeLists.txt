cmake_minimum_required(VERSION 3.15)
project(openjtalk-wasm VERSION 0.1.0)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# OpenJTalk source files
set(OPENJTALK_SOURCES
    src/openjtalk_core.cpp
    src/text_analyzer.cpp
    src/phoneme_converter.cpp
    src/njd.cpp
)

# Create OpenJTalk WebAssembly module
add_executable(openjtalk_wasm ${OPENJTALK_SOURCES})

# Emscripten specific settings
if(EMSCRIPTEN)
    # Common compile options with MeCab
    set(COMMON_COMPILE_OPTIONS
        -O3
        -fexceptions
        -frtti
        -msimd128  # Enable SIMD for Chrome
    )
    
    # Common link flags
    set(COMMON_LINK_FLAGS "\
        -s WASM=1 \
        -s MODULARIZE=1 \
        -s EXPORT_ES6=1 \
        -s EXPORT_NAME='OpenJTalkModule' \
        -s INITIAL_MEMORY=64MB \
        -s ALLOW_MEMORY_GROWTH=1 \
        -s MAXIMUM_MEMORY=256MB \
        -s EXPORTED_FUNCTIONS=['_malloc','_free'] \
        -s EXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString','stringToUTF8','allocate','HEAP8','HEAP32'] \
        -s FORCE_FILESYSTEM=1 \
        -s SINGLE_FILE=0 \
        -s DISABLE_EXCEPTION_CATCHING=0 \
        -s ENVIRONMENT=web \
        -msimd128 \
        --bind \
    ")
    
    target_compile_options(openjtalk_wasm PRIVATE ${COMMON_COMPILE_OPTIONS})
    set_target_properties(openjtalk_wasm PROPERTIES
        SUFFIX ".js"
        LINK_FLAGS "${COMMON_LINK_FLAGS}"
    )
    
    # Include directories
    target_include_directories(openjtalk_wasm PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../mecab/src  # For MeCab integration
    )
endif()

# Install targets
install(TARGETS openjtalk_wasm
    RUNTIME DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy generated files
install(FILES 
    ${CMAKE_CURRENT_BINARY_DIR}/openjtalk_wasm.js
    ${CMAKE_CURRENT_BINARY_DIR}/openjtalk_wasm.wasm
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)