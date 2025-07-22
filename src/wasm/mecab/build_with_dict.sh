#!/bin/bash

# MeCab WebAssembly build script with NAIST-JDIC dictionary
set -e

echo "=== Building MeCab WASM with NAIST-JDIC Dictionary ==="

# Check if dictionary exists
if [ ! -d "dict/naist-jdic" ]; then
    echo "Error: NAIST-JDIC dictionary not found. Run setup_naist_jdic.sh first."
    exit 1
fi

# Create build directory
mkdir -p build
cd build

# Configure with CMake
echo "Configuring build..."
emcmake cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS="-O3 -flto"

# Build
echo "Building..."
emmake make -j$(nproc)

# Create output directory
mkdir -p ../dist

# Package with dictionary files
echo "Packaging with dictionary..."
emcc mecab_wasm.o -o ../dist/mecab_wasm_dict.js \
    -s WASM=1 \
    -s MODULARIZE=1 \
    -s EXPORT_NAME="'MeCabModule'" \
    -s EXPORTED_FUNCTIONS="['_malloc', '_free']" \
    -s EXPORTED_RUNTIME_METHODS="['ccall', 'cwrap', 'UTF8ToString', 'stringToUTF8']" \
    -s ALLOW_MEMORY_GROWTH=1 \
    -s INITIAL_MEMORY=134217728 \
    -s MAXIMUM_MEMORY=268435456 \
    -s ENVIRONMENT='web,worker' \
    -s SINGLE_FILE=0 \
    --preload-file ../dict/naist-jdic@/dict \
    --use-preload-plugins \
    -O3 \
    -flto \
    --closure 0

# Copy original files too
cp ../dist/mecab_wasm.js ../dist/mecab_wasm_original.js
cp ../dist/mecab_wasm.wasm ../dist/mecab_wasm_original.wasm

echo "Build complete! Dictionary-enabled version at dist/mecab_wasm_dict.js"
echo "Dictionary will be available at /dict in the virtual filesystem"