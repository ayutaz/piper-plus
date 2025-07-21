#!/bin/bash
# MeCab WebAssembly build script

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}MeCab WebAssembly Build Script${NC}"
echo "================================"

# Setup environment
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check for Emscripten
if [ -f "../setup_env.sh" ]; then
    echo -e "${YELLOW}Setting up Emscripten environment...${NC}"
    source ../setup_env.sh
else
    echo -e "${RED}Error: setup_env.sh not found${NC}"
    echo "Please ensure Emscripten is installed"
    exit 1
fi

# Clean build directory if requested
if [ "$1" == "--clean" ]; then
    echo -e "${YELLOW}Cleaning build directory...${NC}"
    rm -rf build
fi

# Create build directory
mkdir -p build
cd build

# Configure
echo -e "${YELLOW}Configuring with CMake...${NC}"
emcmake cmake ..

# Build
echo -e "${YELLOW}Building...${NC}"
emmake make

# Check results
echo -e "${GREEN}Build complete! Checking artifacts...${NC}"
if [ -f "mecab_wasm.js" ] && [ -f "mecab_wasm.wasm" ]; then
    echo -e "${GREEN}✓ WebAssembly files generated successfully${NC}"
    ls -lh mecab_wasm.*
    
    # Create dist directory
    mkdir -p ../dist
    cp mecab_wasm.* ../dist/
    echo -e "${GREEN}✓ Files copied to dist/${NC}"
else
    echo -e "${RED}✗ Build failed - WebAssembly files not found${NC}"
    exit 1
fi

echo -e "${GREEN}Build successful!${NC}"