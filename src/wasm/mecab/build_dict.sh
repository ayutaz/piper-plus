#!/bin/bash
# MeCab dictionary build script for WebAssembly

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Building MeCab dictionary for WebAssembly..."

# Create dictionary build directory
mkdir -p dict/ipadic-wasm

# Copy dictionary source files
cp -r src/mecab-ipadic/* dict/ipadic-wasm/

# We need mecab-dict-index tool, but for WASM we'll use a pre-built dictionary
# For now, we'll use the minimal dictionary for testing
echo "Using minimal dictionary for initial build..."

# Create mecabrc configuration file
cat > dict/mecabrc << EOF
; Configuration file for MeCab WebAssembly
dicdir = /dict
userdic = 
; output-format-type = wakati
; input-buffer-size = 8192
; node-format = %m\t%H\n
; bos-format = 
; eos-format = EOS\n
; eos-format = 
; unk-format = %m\t%H\n
; unk-feature = UNKNOWN
EOF

echo "Dictionary preparation complete!"