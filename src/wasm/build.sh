#!/bin/bash
# Build script for Piper WebAssembly

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Piper WebAssembly Build Script${NC}"
echo "================================"

# Check if we're in the right directory
if [ ! -f "CMakeLists.txt" ]; then
    echo -e "${RED}Error: CMakeLists.txt not found. Please run this script from src/wasm directory${NC}"
    exit 1
fi

# Setup environment
if [ -f "setup_env.sh" ]; then
    echo -e "${YELLOW}Setting up Emscripten environment...${NC}"
    source setup_env.sh
else
    echo -e "${RED}Error: setup_env.sh not found${NC}"
    exit 1
fi

# Parse arguments
BUILD_TYPE="Release"
CLEAN_BUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            BUILD_TYPE="Debug"
            shift
            ;;
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}Build configuration:${NC}"
echo "  Build type: $BUILD_TYPE"
echo "  Clean build: $CLEAN_BUILD"

# Clean if requested
if [ "$CLEAN_BUILD" = true ]; then
    echo -e "${YELLOW}Cleaning build directory...${NC}"
    rm -rf build
fi

# Create build directory
mkdir -p build
cd build

# Configure
echo -e "${YELLOW}Configuring with CMake...${NC}"
emcmake cmake .. -DCMAKE_BUILD_TYPE=$BUILD_TYPE

# Build
echo -e "${YELLOW}Building...${NC}"
emmake make -j$(nproc)

# Check results
echo -e "${GREEN}Build complete! Checking artifacts...${NC}"
if [ -f "cpp/hello_wasm.wasm" ] && [ -f "cpp/hello_wasm.js" ]; then
    echo -e "${GREEN}✓ WebAssembly files generated successfully${NC}"
    ls -lh cpp/*.wasm cpp/*.js
else
    echo -e "${RED}✗ Build failed - WebAssembly files not found${NC}"
    exit 1
fi

echo -e "${GREEN}Build successful!${NC}"
echo ""
echo "To test the build:"
echo "  1. cd test/"
echo "  2. python3 server.py"
echo "  3. Open http://localhost:8000/index.html in Chrome"