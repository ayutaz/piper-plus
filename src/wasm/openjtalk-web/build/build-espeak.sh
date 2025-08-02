#!/bin/bash
set -eu

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TOOLS_DIR="$PROJECT_DIR/tools"
SRC_DIR="$PROJECT_DIR/src"
DIST_DIR="$PROJECT_DIR/dist"

echo "=== eSpeak-ng WebAssembly Build Script ==="
echo "Project directory: $PROJECT_DIR"

# Create directories
mkdir -p "$TOOLS_DIR/espeak-ng"
mkdir -p "$DIST_DIR"

# Clone eSpeak-ng if not exists
ESPEAK_DIR="$TOOLS_DIR/espeak-ng"
if [ ! -d "$ESPEAK_DIR/.git" ]; then
    echo "=== Cloning eSpeak-ng ==="
    git clone https://github.com/espeak-ng/espeak-ng.git "$ESPEAK_DIR"
    cd "$ESPEAK_DIR"
    # Use a stable commit
    git checkout 1.51.1
fi

cd "$ESPEAK_DIR"

# Apply patches if needed
if [ ! -f ".emscripten_patched" ]; then
    echo "=== Preparing eSpeak-ng for Emscripten ==="
    
    # Fix autogen.sh if needed
    if grep -q "ChangeLog.md" autogen.sh 2>/dev/null; then
        sed -i.bak 's/ChangeLog.md/CHANGELOG.md/g' autogen.sh
    fi
    
    touch ".emscripten_patched"
fi

# Configure for native build first (to generate language data)
if [ ! -f "Makefile" ]; then
    echo "=== Running autogen.sh ==="
    ./autogen.sh
    
    echo "=== Configuring for native build ==="
    ./configure
fi

# Build language data (only English for now)
echo "=== Building language data ==="
make -j4 en || true

# Clean before Emscripten build
echo "=== Cleaning for Emscripten build ==="
make clean || true

# Configure with Emscripten
echo "=== Configuring with Emscripten ==="
emconfigure ./configure \
    --prefix=/usr \
    --without-async \
    --without-mbrola \
    --without-sonic \
    --without-pcaudiolib \
    --without-klatt \
    --without-speechplayer

# Build library
echo "=== Building eSpeak-ng library ==="
emmake make -j4 src/libespeak-ng.la

# Compile to WASM
echo "=== Compiling to WebAssembly ==="
emcc -O2 \
    -s WASM=1 \
    -s MODULARIZE=1 \
    -s EXPORT_ES6=1 \
    -s EXPORT_NAME='ESpeakNG' \
    -s EXPORTED_FUNCTIONS='["_espeak_Initialize", "_espeak_Terminate", "_espeak_TextToPhonemes", "_espeak_SetVoiceByName", "_malloc", "_free"]' \
    -s EXPORTED_RUNTIME_METHODS='["ccall", "cwrap", "allocateUTF8", "UTF8ToString"]' \
    -s ALLOW_MEMORY_GROWTH=1 \
    -s INITIAL_MEMORY=33554432 \
    --embed-file espeak-ng-data@/usr/share/espeak-ng-data \
    src/.libs/libespeak-ng.a \
    -o "$DIST_DIR/espeak-ng.js"

echo "=== eSpeak-ng WebAssembly build complete ==="
echo "Output files:"
echo "  - $DIST_DIR/espeak-ng.js"
echo "  - $DIST_DIR/espeak-ng.wasm"
echo "  - $DIST_DIR/espeak-ng.data"