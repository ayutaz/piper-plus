cmake_minimum_required(VERSION 3.15)
project(mecab-wasm VERSION 0.1.0)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MeCab source files - prototype version
set(MECAB_PROTOTYPE_SOURCES
    src/mecab.cpp
    src/tokenizer.cpp
    src/dictionary.cpp
)

# MeCab source files - core version
set(MECAB_CORE_SOURCES
    src/mecab_core.cpp
)

# Create MeCab WebAssembly module - prototype
add_executable(mecab_wasm ${MECAB_PROTOTYPE_SOURCES})

# Create MeCab WebAssembly module - core version
add_executable(mecab_core_wasm ${MECAB_CORE_SOURCES})

# Emscripten specific settings
if(EMSCRIPTEN)
    # Common compile options
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
        -s INITIAL_MEMORY=64MB \
        -s ALLOW_MEMORY_GROWTH=1 \
        -s MAXIMUM_MEMORY=256MB \
        -s EXPORTED_FUNCTIONS=['_malloc','_free'] \
        -s EXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString','stringToUTF8','allocate','HEAP8','HEAP32'] \
        -s FORCE_FILESYSTEM=1 \
        -s SINGLE_FILE=0 \
        -s DISABLE_EXCEPTION_CATCHING=0 \
        -s ENVIRONMENT=web \
        -s USE_ZLIB=1 \
        -msimd128 \
        --bind \
    ")
    
    # Configure prototype version
    target_compile_options(mecab_wasm PRIVATE ${COMMON_COMPILE_OPTIONS})
    set_target_properties(mecab_wasm PROPERTIES
        SUFFIX ".js"
        LINK_FLAGS "${COMMON_LINK_FLAGS} \
            -s EXPORT_NAME='MeCabModule' \
            --preload-file ${CMAKE_SOURCE_DIR}/dict/minimal@/dict \
        "
    )
    
    # Configure core version
    target_compile_options(mecab_core_wasm PRIVATE ${COMMON_COMPILE_OPTIONS})
    set_target_properties(mecab_core_wasm PROPERTIES
        SUFFIX ".js"
        LINK_FLAGS "${COMMON_LINK_FLAGS} \
            -s EXPORT_NAME='MeCabCoreModule' \
        "
    )
endif()

# Install targets
install(TARGETS mecab_wasm mecab_core_wasm
    RUNTIME DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy generated files for prototype
install(FILES 
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.js
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.wasm
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy generated files for core
install(FILES 
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_core_wasm.js
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_core_wasm.wasm
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy data file if exists
if(EXISTS ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.data)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.data
        DESTINATION ${CMAKE_BINARY_DIR}/dist
    )
endif()