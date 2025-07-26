#!/bin/bash
set -e

# Build script for Piper C++ in Docker environment

echo "=== Piper C++ Build Script ==="
echo "CUDA Version: $(nvcc --version | grep release | awk '{print $5}' | sed 's/,//')"
echo ""

# Set build type
BUILD_TYPE=${BUILD_TYPE:-Release}
echo "Build type: $BUILD_TYPE"

# Enable ccache
export CCACHE_DIR=/workspace/.ccache
export CC="ccache clang"
export CXX="ccache clang++"

# Create build directory
mkdir -p /workspace/build
cd /workspace/build

# Configure with CMake
echo "Configuring with CMake..."
cmake /workspace/piper \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=$BUILD_TYPE \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DBUILD_TESTS=ON \
    -DUSE_CUDA=ON \
    -DCUDA_ARCH_LIST="70;75;80;86;89;90" \
    -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc

# Build
echo "Building..."
ninja -j$(nproc)

# Run tests if requested
if [ "$RUN_TESTS" = "1" ]; then
    echo "Running tests..."
    ctest --output-on-failure
fi

# Generate coverage report if requested
if [ "$COVERAGE" = "1" ]; then
    echo "Generating coverage report..."
    gcovr -r /workspace/piper --html --html-details -o /workspace/build/coverage.html
fi

echo "Build complete!"