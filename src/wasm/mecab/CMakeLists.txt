cmake_minimum_required(VERSION 3.15)
project(mecab-wasm VERSION 0.1.0)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MeCab source files
set(MECAB_SOURCES
    src/mecab.cpp
    src/tokenizer.cpp
    src/dictionary.cpp
)

# Create MeCab WebAssembly module
add_executable(mecab_wasm ${MECAB_SOURCES})

# Emscripten specific settings
if(EMSCRIPTEN)
    target_compile_options(mecab_wasm PRIVATE
        -O3
        -fexceptions
        -frtti
    )
    
    set_target_properties(mecab_wasm PROPERTIES
        SUFFIX ".js"
        LINK_FLAGS "\
            -s WASM=1 \
            -s MODULARIZE=1 \
            -s EXPORT_ES6=1 \
            -s EXPORT_NAME='MeCabModule' \
            -s INITIAL_MEMORY=32MB \
            -s ALLOW_MEMORY_GROWTH=1 \
            -s MAXIMUM_MEMORY=128MB \
            -s EXPORTED_FUNCTIONS=['_malloc','_free'] \
            -s EXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString','stringToUTF8','allocate','HEAP8','HEAP32'] \
            -s FORCE_FILESYSTEM=1 \
            -s SINGLE_FILE=0 \
            -s DISABLE_EXCEPTION_CATCHING=0 \
            --bind \
            --preload-file ${CMAKE_SOURCE_DIR}/dict/minimal@/dict \
        "
    )
endif()

# Install targets
install(TARGETS mecab_wasm
    RUNTIME DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy generated files
install(FILES 
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.js
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.wasm
    ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.data
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)