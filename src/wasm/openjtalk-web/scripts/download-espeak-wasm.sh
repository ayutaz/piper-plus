#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
TEMP_DIR="$PROJECT_DIR/temp"

echo "=== Downloading pre-built eSpeak-ng WebAssembly ==="

# Create directories
mkdir -p "$DIST_DIR"
mkdir -p "$TEMP_DIR"

# Option 1: Try to download from npm package
echo "Attempting to download from npm package @echogarden/espeak-ng-emscripten..."

cd "$TEMP_DIR"

# Download package info
if command -v npm &> /dev/null; then
    npm pack @echogarden/espeak-ng-emscripten@0.3.3 --dry-run 2>/dev/null || {
        echo "npm not available or package not found"
    }
fi

# Option 2: Download from CDN or GitHub releases
echo "Downloading pre-built files from alternative sources..."

# URLs for pre-built eSpeak-ng WASM files
ESPEAK_JS_URL="https://unpkg.com/@echogarden/espeak-ng-emscripten@0.3.3/espeak-ng.js"
ESPEAK_DATA_URL="https://unpkg.com/@echogarden/espeak-ng-emscripten@0.3.3/espeak-ng.data"

# Download files
echo "Downloading espeak-ng.js..."
curl -L -o "$DIST_DIR/espeak-ng.js" "$ESPEAK_JS_URL" || {
    echo "Failed to download espeak-ng.js"
    echo "You can manually download from: $ESPEAK_JS_URL"
}

echo "Downloading espeak-ng.data..."
curl -L -o "$DIST_DIR/espeak-ng.data" "$ESPEAK_DATA_URL" || {
    echo "Failed to download espeak-ng.data"
    echo "You can manually download from: $ESPEAK_DATA_URL"
}

# Check if files were downloaded
if [ -f "$DIST_DIR/espeak-ng.js" ] && [ -f "$DIST_DIR/espeak-ng.data" ]; then
    echo "Successfully downloaded eSpeak-ng WebAssembly files:"
    ls -lh "$DIST_DIR/espeak-ng.js" "$DIST_DIR/espeak-ng.data"
else
    echo "Download failed. Please check your internet connection or download manually."
    echo ""
    echo "Manual download instructions:"
    echo "1. Visit https://www.npmjs.com/package/@echogarden/espeak-ng-emscripten"
    echo "2. Download the package and extract espeak-ng.js and espeak-ng.data"
    echo "3. Place them in: $DIST_DIR/"
fi

# Clean up
rm -rf "$TEMP_DIR"

echo "Done!"