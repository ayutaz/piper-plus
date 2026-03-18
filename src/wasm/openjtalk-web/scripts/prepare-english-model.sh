#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_DIR/models"

echo "=== Checking Multilingual Model for WebAssembly Demo ==="

# Both Japanese and English now use the same multilingual model.
# There is no separate en_US-test-medium model.

MODEL_FILE="$MODELS_DIR/multilingual-test-medium.onnx"

if [ -f "$MODEL_FILE" ]; then
    echo "Multilingual model found: $MODEL_FILE"
    echo "Size: $(du -h "$MODEL_FILE" | cut -f1)"
    echo ""
    echo "This single model handles both Japanese and English synthesis."
else
    echo "Multilingual model not found at: $MODEL_FILE"
    echo ""
    echo "To add the multilingual model:"
    echo "1. Train or download the multilingual-test-medium model"
    echo "2. Copy it to: $MODEL_FILE"
    echo ""
    echo "Note: Both Japanese and English share this single model file."
fi
