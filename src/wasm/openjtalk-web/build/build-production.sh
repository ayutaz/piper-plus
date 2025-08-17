#!/bin/bash
set -eu

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
SRC_DIR="$PROJECT_DIR/src"

# Use wasm_open_jtalk's built libraries
WASM_OPENJTALK_DIR="$PROJECT_DIR/tools/wasm_open_jtalk"

echo "=== Building Production OpenJTalk WebAssembly ==="

# Check if libraries exist
if [ ! -f "$WASM_OPENJTALK_DIR/tools/open_jtalk/src/build/libopenjtalk.a" ]; then
    echo "Error: OpenJTalk library not found. Run build-with-wasm-openjtalk.sh first"
    exit 1
fi

# Source emsdk environment
source "$WASM_OPENJTALK_DIR/tools/emsdk/emsdk_env.sh"

# Build the production version (without debug output)
echo "Building production version..."

OPEN_JTALK_DIR="$WASM_OPENJTALK_DIR/tools/open_jtalk"
HTS_ENGINE_API_DIR="$WASM_OPENJTALK_DIR/tools/hts_engine_API"

# Include paths
INCLUDE_FLAGS="-I$OPEN_JTALK_DIR/src/jpcommon \
    -I$OPEN_JTALK_DIR/src/mecab/src \
    -I$OPEN_JTALK_DIR/src/mecab2njd \
    -I$OPEN_JTALK_DIR/src/njd \
    -I$OPEN_JTALK_DIR/src/njd2jpcommon \
    -I$OPEN_JTALK_DIR/src/njd_set_accent_phrase \
    -I$OPEN_JTALK_DIR/src/njd_set_accent_type \
    -I$OPEN_JTALK_DIR/src/njd_set_digit \
    -I$OPEN_JTALK_DIR/src/njd_set_long_vowel \
    -I$OPEN_JTALK_DIR/src/njd_set_pronunciation \
    -I$OPEN_JTALK_DIR/src/njd_set_unvoiced_vowel \
    -I$OPEN_JTALK_DIR/src/text2mecab \
    -I$HTS_ENGINE_API_DIR/include"

# Libraries
LIBS="$OPEN_JTALK_DIR/src/build/libopenjtalk.a \
    $HTS_ENGINE_API_DIR/src/build/lib/libhts_engine_API.a"

# Create production source without debug logs
echo "Creating production source..."
sed -E 's/EM_ASM\({[^}]*}\);?//g' "$SRC_DIR/openjtalk_safe.c" > "$SRC_DIR/openjtalk_production.c"

# Build command
emcc "$SRC_DIR/openjtalk_production.c" \
    -o "$DIST_DIR/openjtalk.js" \
    $INCLUDE_FLAGS \
    $LIBS \
    -DCHARSET_UTF_8 \
    -s ENVIRONMENT=web,worker \
    -s MODULARIZE=1 \
    -s EXPORT_ES6=1 \
    -s EXPORT_NAME=OpenJTalkModule \
    -s INITIAL_MEMORY=67108864 \
    -s ALLOW_MEMORY_GROWTH=1 \
    -s FILESYSTEM=1 \
    -s FORCE_FILESYSTEM=1 \
    -s EXPORTED_RUNTIME_METHODS='["FS","cwrap","ccall","setValue","getValue","UTF8ToString","stringToUTF8","lengthBytesUTF8","allocateUTF8"]' \
    -s EXPORTED_FUNCTIONS='["_malloc","_free","_openjtalk_initialize","_openjtalk_clear","_openjtalk_synthesis_labels","_openjtalk_free_string","_get_version","_test_function"]' \
    -O3 \
    -s ASSERTIONS=0 \
    --closure 1

# Clean up
rm -f "$SRC_DIR/openjtalk_production.c"

echo "=== Production build complete ==="
echo "Output files:"
ls -la "$DIST_DIR/openjtalk.js" "$DIST_DIR/openjtalk.wasm"
echo ""
echo "Sizes:"
echo "  JavaScript: $(stat -f%z "$DIST_DIR/openjtalk.js" 2>/dev/null || stat -c%s "$DIST_DIR/openjtalk.js" 2>/dev/null) bytes"
echo "  WebAssembly: $(stat -f%z "$DIST_DIR/openjtalk.wasm" 2>/dev/null || stat -c%s "$DIST_DIR/openjtalk.wasm" 2>/dev/null) bytes"