#!/bin/bash
# Cross-compile piper-plus for Android armeabi-v7a
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

ABI=armeabi-v7a
ANDROID_PLATFORM=android-24

# NDK path: use environment variable or default
ANDROID_NDK="${ANDROID_NDK:-${ANDROID_HOME:-$HOME/Android/Sdk}/ndk/27.0.12077973}"

if [ ! -d "$ANDROID_NDK" ]; then
    echo "Error: Android NDK not found at $ANDROID_NDK"
    echo "Set ANDROID_NDK environment variable to the NDK path"
    exit 1
fi

BUILD_DIR="$PROJECT_ROOT/build-android-$ABI"
INSTALL_DIR="$PROJECT_ROOT/install-android-$ABI"

echo "=== Building piper-plus for Android $ABI ==="
echo "NDK: $ANDROID_NDK"
echo "Build dir: $BUILD_DIR"
echo "Install dir: $INSTALL_DIR"

cmake -S "$PROJECT_ROOT" -B "$BUILD_DIR" \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$ABI" \
    -DANDROID_PLATFORM="$ANDROID_PLATFORM" \
    -DANDROID_STL=c++_shared \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
    -DBUILD_ANDROID_JNI=ON

cmake --build "$BUILD_DIR" --parallel "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
cmake --install "$BUILD_DIR" --strip

echo "=== Build complete: $INSTALL_DIR ==="
ls -la "$INSTALL_DIR/lib/"*.so 2>/dev/null || echo "No .so files found in install dir"
