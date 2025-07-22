#!/bin/bash

# OpenJTalk WebAssembly build script

set -e

echo "Building OpenJTalk WebAssembly module..."

# Create build directory
mkdir -p build
cd build

# Configure with Emscripten
emcmake cmake ..

# Build
emmake make -j$(nproc)

echo "Build complete!"