#!/bin/bash
# Emscripten環境設定スクリプト

# プロジェクトルートから実行する場合
export EMSDK_PATH="/Users/s19447/Desktop/total-piper/piper/tools/emsdk"

if [ -f "$EMSDK_PATH/emsdk_env.sh" ]; then
    source "$EMSDK_PATH/emsdk_env.sh"
    echo "Emscripten environment loaded successfully"
    emcc --version
else
    echo "Error: Emscripten SDK not found at $EMSDK_PATH"
    echo "Please run: cd tools && git clone https://github.com/emscripten-core/emsdk.git"
    echo "Then: cd emsdk && ./emsdk install latest && ./emsdk activate latest"
    exit 1
fi