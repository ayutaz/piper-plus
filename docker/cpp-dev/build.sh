#!/bin/bash
set -e

# Build script for Piper C++ in Docker environment

echo "=== Piper C++ Build Script ==="
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
cmake /workspace \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=$BUILD_TYPE \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DBUILD_TESTS=ON

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
    gcovr -r /workspace --html --html-details -o /workspace/build/coverage.html
fi

echo "Build complete!"