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

# Create bin directory if it doesn't exist
mkdir -p "$INSTALL_DIR/bin"

# Navigate to bin directory
cd bin

# Build the phonemizer binary
echo "Compiling open_jtalk_phonemizer..."
$CC -o open_jtalk_phonemizer open_jtalk_phonemizer.c \
    -I../mecab/src -I../njd -I../jpcommon -I../njd_set_accent_phrase \
    -I../njd_set_accent_type -I../njd_set_digit -I../njd_set_long_vowel \
    -I../njd_set_pronunciation -I../njd_set_unvoiced_vowel -I../njd2jpcommon \
    -I../text2mecab -I../mecab2njd \
    ../text2mecab/.libs/libtext2mecab.a \
    ../mecab2njd/.libs/libmecab2njd.a \
    ../njd_set_pronunciation/.libs/libnjd_set_pronunciation.a \
    ../njd_set_digit/.libs/libnjd_set_digit.a \
    ../njd_set_accent_phrase/.libs/libnjd_set_accent_phrase.a \
    ../njd_set_accent_type/.libs/libnjd_set_accent_type.a \
    ../njd_set_unvoiced_vowel/.libs/libnjd_set_unvoiced_vowel.a \
    ../njd_set_long_vowel/.libs/libnjd_set_long_vowel.a \
    ../njd2jpcommon/.libs/libnjd2jpcommon.a \
    ../jpcommon/.libs/libjpcommon.a \
    ../mecab/src/.libs/libmecab.a \
    ../njd/.libs/libnjd.a \
    "$HTS_ENGINE_DIR/lib/libHTSEngine.a" \
    -lm

# Copy to install directory
echo "Installing open_jtalk_phonemizer to $INSTALL_DIR/bin/"
cp open_jtalk_phonemizer "$INSTALL_DIR/bin/"
chmod +x "$INSTALL_DIR/bin/open_jtalk_phonemizer"

echo "open_jtalk_phonemizer build complete!"