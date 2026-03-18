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

# Dependency directories (override via environment variables if needed)
ONNXRUNTIME_DIR="${ONNXRUNTIME_DIR:-$PROJECT_ROOT/third-party/onnxruntime-android}"
OPENJTALK_DIR="${OPENJTALK_DIR:-$PROJECT_ROOT/third-party/openjtalk-android}"
SPDLOG_DIR="${SPDLOG_DIR:-$PROJECT_ROOT/third-party/spdlog}"
FMT_DIR="${FMT_DIR:-$PROJECT_ROOT/third-party/fmt}"

echo "=== Building piper-plus for Android $ABI ==="
echo "NDK: $ANDROID_NDK"
echo "Build dir: $BUILD_DIR"
echo "Install dir: $INSTALL_DIR"

# Validate required dependency directories
MISSING=0
for DEP_NAME_DIR in "ONNXRUNTIME_DIR:$ONNXRUNTIME_DIR" "OPENJTALK_DIR:$OPENJTALK_DIR" "SPDLOG_DIR:$SPDLOG_DIR" "FMT_DIR:$FMT_DIR"; do
    DEP_NAME="${DEP_NAME_DIR%%:*}"
    DEP_DIR="${DEP_NAME_DIR#*:}"
    if [ ! -d "$DEP_DIR" ]; then
        echo "Error: $DEP_NAME not found at $DEP_DIR"
        echo "  Set $DEP_NAME environment variable to override"
        MISSING=1
    fi
done
if [ "$MISSING" -ne 0 ]; then
    exit 1
fi

# NOTE: ANDROID_STL=c++_shared requires libc++_shared.so to be packaged in the
# APK (typically in jniLibs/<ABI>/). Use c++_static instead if you prefer a
# self-contained binary with no shared C++ runtime dependency.
cmake -S "$PROJECT_ROOT/src/android/piper-android" -B "$BUILD_DIR" \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$ABI" \
    -DANDROID_PLATFORM="$ANDROID_PLATFORM" \
    -DANDROID_STL=c++_shared \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
    -DBUILD_ANDROID_JNI=ON \
    -DONNXRUNTIME_DIR="$ONNXRUNTIME_DIR" \
    -DOPENJTALK_DIR="$OPENJTALK_DIR" \
    -DSPDLOG_DIR="$SPDLOG_DIR" \
    -DFMT_DIR="$FMT_DIR"

cmake --build "$BUILD_DIR" --parallel "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
cmake --install "$BUILD_DIR" --strip

echo "=== Build complete: $INSTALL_DIR ==="
if ! ls "$INSTALL_DIR/lib/"*.so 1>/dev/null 2>&1; then
    echo "Error: No .so files found in $INSTALL_DIR/lib/"
    exit 1
fi
echo "Build successful:"
ls -la "$INSTALL_DIR/lib/"*.so
