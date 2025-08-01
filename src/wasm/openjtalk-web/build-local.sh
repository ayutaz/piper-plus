#!/bin/bash
set -eu

echo "=== OpenJTalk WebAssembly Local Build Script ==="
echo "This script builds OpenJTalk for WebAssembly without Docker"
echo ""

# Check if Emscripten is installed
if ! command -v emcc &> /dev/null; then
    echo "Error: Emscripten (emcc) not found!"
    echo "Please install Emscripten first:"
    echo "  git clone https://github.com/emscripten-core/emsdk.git"
    echo "  cd emsdk"
    echo "  ./emsdk install latest"
    echo "  ./emsdk activate latest"
    echo "  source ./emsdk_env.sh"
    exit 1
fi

echo "Emscripten version:"
emcc --version
echo ""

# Run the build script
cd "$(dirname "$0")"
./build/build.sh

echo ""
echo "Build complete! Check the dist/ directory for output files."