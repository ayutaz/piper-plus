#!/bin/bash

# Download English model from Piper releases
# This downloads a small, fast English model suitable for demos

set -e

cd "$(dirname "$0")/.."

echo "Downloading English TTS model..."

# Create models directory if it doesn't exist
mkdir -p models

# Download en_US-lessac-medium model (good quality, reasonable size)
MODEL_URL="https://github.com/rhasspy/piper/releases/download/v0.0.2/en_US-lessac-medium.onnx"
CONFIG_URL="https://github.com/rhasspy/piper/releases/download/v0.0.2/en_US-lessac-medium.onnx.json"

echo "Downloading model file..."
curl -L -o models/en_US-lessac-medium.onnx "$MODEL_URL"

echo "Downloading config file..."
curl -L -o models/en_US-lessac-medium.onnx.json "$CONFIG_URL"

echo "English model downloaded successfully!"
echo "Model: models/en_US-lessac-medium.onnx"
echo "Config: models/en_US-lessac-medium.onnx.json"