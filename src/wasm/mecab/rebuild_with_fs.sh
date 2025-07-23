#!/bin/bash
# Rebuild MeCab with FS support

echo "Rebuilding MeCab with FS export..."

# Clean build
rm -rf build
mkdir build
cd build

# Configure with FS export
emcmake cmake .. \
  -DCMAKE_CXX_FLAGS="-s EXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString','stringToUTF8','allocate','HEAP8','HEAP32','FS'] -s FORCE_FILESYSTEM=1"

# Build
emmake make

# Check if FS is exported
echo "Checking FS export..."
if grep -q "FS:" mecab_wasm.js; then
    echo "✅ FS successfully exported"
else
    echo "❌ FS not exported"
fi

echo "Build complete"