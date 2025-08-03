#!/bin/bash
set -eu

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TOOLS_DIR="$PROJECT_DIR/tools"
SRC_DIR="$PROJECT_DIR/src"
DIST_DIR="$PROJECT_DIR/dist"

echo "=== Unified Phonemizer WebAssembly Build Script ==="
echo "Project directory: $PROJECT_DIR"

# Create directories
mkdir -p "$DIST_DIR"

# Build OpenJTalk first (if build script exists)
if [ -f "$SCRIPT_DIR/build-openjtalk.sh" ]; then
    echo "=== Building OpenJTalk ==="
    "$SCRIPT_DIR/build-openjtalk.sh"
else
    echo "=== Using existing build.sh for OpenJTalk ==="
    "$SCRIPT_DIR/build.sh"
fi

# Build eSpeak-ng
echo "=== Building eSpeak-ng ==="
"$SCRIPT_DIR/build-espeak.sh"

# Now build the unified wrapper
echo "=== Building Unified Phonemizer ==="

# Set include paths
OPENJTALK_INCLUDE="-I$TOOLS_DIR/open_jtalk/src/mecab -I$TOOLS_DIR/open_jtalk/src/mecab2njd -I$TOOLS_DIR/open_jtalk/src/text2mecab -I$TOOLS_DIR/open_jtalk/src/njd -I$TOOLS_DIR/open_jtalk/src/njd_set_pronunciation -I$TOOLS_DIR/open_jtalk/src/njd_set_digit -I$TOOLS_DIR/open_jtalk/src/njd_set_accent_phrase -I$TOOLS_DIR/open_jtalk/src/njd_set_accent_type -I$TOOLS_DIR/open_jtalk/src/njd_set_unvoiced_vowel -I$TOOLS_DIR/open_jtalk/src/njd_set_long_vowel -I$TOOLS_DIR/open_jtalk/src/njd2jpcommon -I$TOOLS_DIR/open_jtalk/src/jpcommon"
HTS_INCLUDE="-I$TOOLS_DIR/hts_engine_API/include"
ESPEAK_INCLUDE="-I$TOOLS_DIR/espeak-ng/src/include/espeak-ng"

# Set library paths
OPENJTALK_LIBS="$TOOLS_DIR/open_jtalk/src/build/*.o"
HTS_LIBS="$TOOLS_DIR/hts_engine_API/src/build/*.o"
ESPEAK_LIBS="$TOOLS_DIR/espeak-ng/src/.libs/libespeak-ng.a"

# Compile the unified wrapper
emcc -O2 \
    $OPENJTALK_INCLUDE \
    $HTS_INCLUDE \
    $ESPEAK_INCLUDE \
    -c "$SRC_DIR/phonemizer_wrapper.cpp" \
    -o "$DIST_DIR/phonemizer_wrapper.o"

# Also compile existing wrappers if they exist
if [ -f "$SRC_DIR/openjtalk_wrapper.cpp" ]; then
    emcc -O2 \
        $OPENJTALK_INCLUDE \
        $HTS_INCLUDE \
        -c "$SRC_DIR/openjtalk_wrapper.cpp" \
        -o "$DIST_DIR/openjtalk_wrapper.o"
fi

# Link everything together
echo "=== Linking unified phonemizer ==="
emcc -O2 \
    -s WASM=1 \
    -s MODULARIZE=1 \
    -s EXPORT_ES6=1 \
    -s EXPORT_NAME='UnifiedPhonemizer' \
    -s EXPORTED_FUNCTIONS='["_phonemizer_initialize_openjtalk", "_phonemizer_initialize_espeak", "_phonemizer_text_to_phonemes", "_phonemizer_set_language", "_phonemizer_free_string", "_phonemizer_terminate", "_malloc", "_free"]' \
    -s EXPORTED_RUNTIME_METHODS='["ccall", "cwrap", "allocateUTF8", "UTF8ToString", "FS"]' \
    -s ALLOW_MEMORY_GROWTH=1 \
    -s INITIAL_MEMORY=67108864 \
    -s FORCE_FILESYSTEM=1 \
    --embed-file "$TOOLS_DIR/espeak-ng/espeak-ng-data@/usr/share/espeak-ng-data" \
    "$DIST_DIR/phonemizer_wrapper.o" \
    "$DIST_DIR/openjtalk_wrapper.o" \
    $OPENJTALK_LIBS \
    $HTS_LIBS \
    $ESPEAK_LIBS \
    -lm \
    -o "$DIST_DIR/unified_phonemizer.js"

echo "=== Unified phonemizer build complete ==="
echo "Output files:"
echo "  - $DIST_DIR/unified_phonemizer.js"
echo "  - $DIST_DIR/unified_phonemizer.wasm"
echo "  - $DIST_DIR/unified_phonemizer.data"