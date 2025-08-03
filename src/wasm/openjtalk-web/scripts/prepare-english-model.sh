#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_DIR/models"

echo "=== Preparing English Model for WebAssembly Demo ==="

# For demo purposes, we'll use a lightweight approach
# In production, you would download or convert an actual English model

# Check if we have a sample English model in the main Piper project
PIPER_ROOT="$(cd "$PROJECT_DIR/../../../.." && pwd)"
SAMPLE_MODEL=""

# Search for English models
echo "Searching for English models in Piper project..."
for model in "$PIPER_ROOT"/test*.onnx "$PIPER_ROOT"/models/en*.onnx; do
    if [ -f "$model" ]; then
        echo "Found model: $model"
        SAMPLE_MODEL="$model"
        break
    fi
done

if [ -n "$SAMPLE_MODEL" ]; then
    echo "Copying English model to WebAssembly demo..."
    cp "$SAMPLE_MODEL" "$MODELS_DIR/en_US-test-medium.onnx"
    echo "Model copied successfully"
else
    echo "No existing English model found."
    echo ""
    echo "To add an English model:"
    echo "1. Download a Piper English model (e.g., en_US-lessac-medium.onnx)"
    echo "2. Copy it to: $MODELS_DIR/en_US-test-medium.onnx"
    echo ""
    echo "Or for testing, you can create a dummy model:"
    echo "  touch $MODELS_DIR/en_US-test-medium.onnx"
    echo ""
    echo "Note: The model config (en_US-test-medium.onnx.json) is already created."
fi