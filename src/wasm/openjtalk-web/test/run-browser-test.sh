#!/bin/bash
set -eu

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== OpenJTalk WebAssembly ブラウザテスト ==="
echo ""
echo "プロジェクトディレクトリ: $PROJECT_DIR"
echo ""

# Check if dist files exist
if [ ! -f "$PROJECT_DIR/dist/openjtalk.js" ] || [ ! -f "$PROJECT_DIR/dist/openjtalk.wasm" ]; then
    echo "⚠️  ビルド成果物が見つかりません"
    echo "   先に build/docker-build-simple.sh を実行してください"
    exit 1
fi

echo "✓ ビルド成果物を確認:"
ls -la "$PROJECT_DIR/dist/"
echo ""

# Start Python HTTP server
echo "HTTPサーバーを起動中..."
echo "ブラウザで以下のURLを開いてください:"
echo ""
echo "  http://localhost:8080/demo/index.html"
echo ""
echo "サーバーを停止するには Ctrl+C を押してください"
echo ""

cd "$PROJECT_DIR"
python3 -m http.server 8080