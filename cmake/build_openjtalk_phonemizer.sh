#!/bin/bash
# Build open_jtalk_phonemizer after OpenJTalk is built
# Usage: ./build_openjtalk_phonemizer.sh <compiler> <install_dir> <hts_engine_dir>

set -e

CC="$1"
INSTALL_DIR="$2"
HTS_ENGINE_DIR="$3"

echo "Building open_jtalk_phonemizer..."
echo "Compiler: $CC"
echo "Install dir: $INSTALL_DIR"
echo "HTS Engine dir: $HTS_ENGINE_DIR"

# Check if HTS Engine library exists
echo "Checking for HTS Engine library..."
if [ -f "$HTS_ENGINE_DIR/lib/libHTSEngine.a" ]; then
    echo "Found: $HTS_ENGINE_DIR/lib/libHTSEngine.a"
elif [ -f "$HTS_ENGINE_DIR/lib/HTSEngine.lib" ]; then
    echo "Found: $HTS_ENGINE_DIR/lib/HTSEngine.lib"
else
    echo "Warning: HTS Engine library not found in $HTS_ENGINE_DIR/lib/"
    echo "Contents of $HTS_ENGINE_DIR/lib/:"
    ls -la "$HTS_ENGINE_DIR/lib/" 2>/dev/null || echo "Directory does not exist"
fi

# Create bin directory if it doesn't exist
mkdir -p "$INSTALL_DIR/bin"

# Navigate to bin directory
cd bin

# Build the phonemizer binary
echo "Compiling open_jtalk_phonemizer..."
# Try to detect C++ compiler
if command -v g++ >/dev/null 2>&1; then
    CXX=g++
elif command -v c++ >/dev/null 2>&1; then
    CXX=c++
else
    # Fall back to C compiler with C++ stdlib
    CXX="$CC"
    EXTRA_LIBS="-lstdc++"
fi

# Platform-specific libraries
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS needs iconv for MeCab
    EXTRA_LIBS="$EXTRA_LIBS -liconv"
fi

# Check if HTS Engine library exists
echo "Checking for HTS Engine library..."
echo "HTS_ENGINE_DIR: $HTS_ENGINE_DIR"

# List contents of HTS Engine directory for debugging
echo "Contents of HTS Engine directory:"
ls -la "$HTS_ENGINE_DIR/" 2>/dev/null || echo "HTS_ENGINE_DIR does not exist"
echo "Contents of HTS Engine lib directory:"
ls -la "$HTS_ENGINE_DIR/lib/" 2>/dev/null || echo "lib directory does not exist"

# Check for HTS Engine library
HTS_LIB=""
if [ -f "$HTS_ENGINE_DIR/lib/libHTSEngine.a" ]; then
    HTS_LIB="$HTS_ENGINE_DIR/lib/libHTSEngine.a"
    echo "Found HTS Engine library: $HTS_LIB"
elif [ -f "$HTS_ENGINE_DIR/lib/HTSEngine.lib" ]; then
    HTS_LIB="$HTS_ENGINE_DIR/lib/HTSEngine.lib"
    echo "Found Windows HTS Engine library: $HTS_LIB"
elif [ -f "$HTS_ENGINE_DIR/lib/libhts_engine_stub.a" ]; then
    HTS_LIB="$HTS_ENGINE_DIR/lib/libhts_engine_stub.a"
    echo "Found HTS Engine stub library: $HTS_LIB"
else
    echo "ERROR: HTS Engine library not found!"
    echo "Searched for:"
    echo "  - $HTS_ENGINE_DIR/lib/libHTSEngine.a"
    echo "  - $HTS_ENGINE_DIR/lib/HTSEngine.lib"
    echo "  - $HTS_ENGINE_DIR/lib/libhts_engine_stub.a"
    echo ""
    echo "Directory contents:"
    ls -la "$HTS_ENGINE_DIR/" 2>/dev/null || echo "HTS_ENGINE_DIR does not exist"
    echo ""
    echo "Build directory contents:"
    find ../../.. -name "*HTSEngine*" -o -name "*hts_engine*" 2>/dev/null | head -20 || echo "No HTS files found"
    exit 1
fi

$CXX -o open_jtalk_phonemizer open_jtalk_phonemizer.c \
    -I../mecab/src -I../njd -I../jpcommon -I../njd_set_accent_phrase \
    -I../njd_set_accent_type -I../njd_set_digit -I../njd_set_long_vowel \
    -I../njd_set_pronunciation -I../njd_set_unvoiced_vowel -I../njd2jpcommon \
    -I../text2mecab -I../mecab2njd \
    ../text2mecab/libtext2mecab.a \
    ../mecab2njd/libmecab2njd.a \
    ../njd_set_pronunciation/libnjd_set_pronunciation.a \
    ../njd_set_digit/libnjd_set_digit.a \
    ../njd_set_accent_phrase/libnjd_set_accent_phrase.a \
    ../njd_set_accent_type/libnjd_set_accent_type.a \
    ../njd_set_unvoiced_vowel/libnjd_set_unvoiced_vowel.a \
    ../njd_set_long_vowel/libnjd_set_long_vowel.a \
    ../njd2jpcommon/libnjd2jpcommon.a \
    ../jpcommon/libjpcommon.a \
    ../mecab/src/libmecab.a \
    ../njd/libnjd.a \
    "$HTS_LIB" \
    -lm ${EXTRA_LIBS:-}

# Copy to install directory
echo "Installing open_jtalk_phonemizer to $INSTALL_DIR/bin/"
cp open_jtalk_phonemizer "$INSTALL_DIR/bin/"
chmod +x "$INSTALL_DIR/bin/open_jtalk_phonemizer"

echo "open_jtalk_phonemizer build complete!"