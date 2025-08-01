#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WASM_OPENJTALK_DIR="$PROJECT_DIR/tools/wasm_open_jtalk"

# Source emsdk environment
source "$WASM_OPENJTALK_DIR/tools/emsdk/emsdk_env.sh"

OPEN_JTALK_DIR="$WASM_OPENJTALK_DIR/tools/open_jtalk"

# Build test
echo "Building text2mecab test..."

# Include paths  
INCLUDE_FLAGS="-I$OPEN_JTALK_DIR/src/text2mecab"

# Compile
gcc "$SCRIPT_DIR/test-text2mecab.c" \
    "$OPEN_JTALK_DIR/src/text2mecab/text2mecab.c" \
    -o "$SCRIPT_DIR/test-text2mecab" \
    $INCLUDE_FLAGS

echo "Build complete. Running test..."
echo ""

# Run test
"$SCRIPT_DIR/test-text2mecab"