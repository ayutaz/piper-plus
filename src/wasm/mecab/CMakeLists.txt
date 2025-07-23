cmake_minimum_required(VERSION 3.15)
project(mecab-wasm VERSION 0.996)

# Set C++ standard
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set MeCab source directory
set(MECAB_SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/src/mecab/src)

# Include directories
include_directories(
    ${MECAB_SRC_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# MeCab core source files
set(MECAB_CORE_SOURCES
    ${MECAB_SRC_DIR}/char_property.cpp
    ${MECAB_SRC_DIR}/connector.cpp
    ${MECAB_SRC_DIR}/context_id.cpp
    ${MECAB_SRC_DIR}/dictionary.cpp
    ${MECAB_SRC_DIR}/feature_index.cpp
    ${MECAB_SRC_DIR}/iconv_utils.cpp
    ${MECAB_SRC_DIR}/dictionary_rewriter.cpp
    ${MECAB_SRC_DIR}/libmecab.cpp
    ${MECAB_SRC_DIR}/nbest_generator.cpp
    ${MECAB_SRC_DIR}/param.cpp
    ${MECAB_SRC_DIR}/string_buffer.cpp
    ${MECAB_SRC_DIR}/tagger.cpp
    ${MECAB_SRC_DIR}/tokenizer.cpp
    ${MECAB_SRC_DIR}/utils.cpp
    ${MECAB_SRC_DIR}/viterbi.cpp
    ${MECAB_SRC_DIR}/writer.cpp
)

# Production wrapper
set(MECAB_WRAPPER_SOURCES
    src/mecab_wrapper.cpp
)

# Create MeCab WebAssembly module
add_executable(mecab_wasm ${MECAB_CORE_SOURCES} ${MECAB_WRAPPER_SOURCES})

# Emscripten specific settings
if(EMSCRIPTEN)
    # Common compile options
    set(COMMON_COMPILE_OPTIONS
        -O3
        -fexceptions
        -frtti
        -msimd128  # Enable SIMD for Chrome
        -Wno-deprecated-register  # Allow deprecated register keyword
        -Wno-macro-redefined  # Allow macro redefinitions
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
        -s EXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString','stringToUTF8','allocate','HEAP8','HEAP32','FS'] \
        -s FORCE_FILESYSTEM=1 \
        -s SINGLE_FILE=0 \
        -s DISABLE_EXCEPTION_CATCHING=0 \
        -s ENVIRONMENT=web \
        -s USE_ZLIB=1 \
        -msimd128 \
        --bind \
    ")
    
    # Add preprocessor definitions
    target_compile_definitions(mecab_wasm PRIVATE
        HAVE_CONFIG_H
        DIC_VERSION=102
        VERSION="0.996"
        PACKAGE="mecab"
        MECAB_DEFAULT_RC="/etc/mecabrc"
    )
    
    # Configure WebAssembly build
    target_compile_options(mecab_wasm PRIVATE ${COMMON_COMPILE_OPTIONS})
    set_target_properties(mecab_wasm PROPERTIES
        SUFFIX ".js"
        LINK_FLAGS "${COMMON_LINK_FLAGS} \
            -s EXPORT_NAME='MeCabModule' \
            --preload-file ${CMAKE_SOURCE_DIR}/dict/minimal@/dict \
            --preload-file ${CMAKE_SOURCE_DIR}/dict/mecabrc@/dict/mecabrc \
            -s ASSERTIONS=1 \
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
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy data file if exists
if(EXISTS ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.data)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/mecab_wasm.data
        DESTINATION ${CMAKE_BINARY_DIR}/dist
    )
endif()

# Create build directory for output
file(MAKE_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/build)