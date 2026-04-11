#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSETS_DIR="$SCRIPT_DIR/demo/assets"
REFERENCE_DIR="$SCRIPT_DIR/wasm_open_jtalk_reference"

echo "=== Preparing assets for OpenJTalk WebAssembly ==="

# Create assets directory
mkdir -p "$ASSETS_DIR"

# Check if reference repository exists
if [ ! -d "$REFERENCE_DIR" ]; then
    echo "Reference repository not found. Cloning..."
    git clone https://github.com/hrhr49/wasm_open_jtalk.git "$REFERENCE_DIR"
fi

# Copy dictionary files
echo "Copying dictionary files..."
if [ -d "$REFERENCE_DIR/etc/open_jtalk_dic_utf_8-1.11" ]; then
    cp -r "$REFERENCE_DIR/etc/open_jtalk_dic_utf_8-1.11" "$ASSETS_DIR/dict"
    echo "Dictionary files copied to $ASSETS_DIR/dict"
else
    echo "Warning: Dictionary files not found in reference repository"
fi

# Create compressed dictionary for web delivery
if command -v tar &> /dev/null && [ -d "$ASSETS_DIR/dict" ]; then
    echo "Creating compressed dictionary..."
    cd "$ASSETS_DIR"
    tar -czf dict.tar.gz dict/
    echo "Created dict.tar.gz"
    cd "$SCRIPT_DIR"
fi

echo ""
echo "Assets preparation complete!"
echo "Files in assets directory:"
ls -la "$ASSETS_DIR/"