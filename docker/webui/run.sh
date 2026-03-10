#!/bin/bash
# Helper script to run Piper WebUI in Docker

set -e

# Default values
MODELS_DIR="${MODELS_DIR:-$(pwd)/models}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/output}"
PORT="${PORT:-7860}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting piper-plus WebUI...${NC}"

# Create directories if they don't exist
mkdir -p "$MODELS_DIR" "$OUTPUT_DIR"

# Check if models directory has any models
if [ -z "$(ls -A $MODELS_DIR/*.onnx 2>/dev/null)" ]; then
    echo -e "${YELLOW}Warning: No ONNX models found in $MODELS_DIR${NC}"
    echo "Please add some models to use the WebUI effectively."
fi

# Build and run
echo "Building Docker image..."
docker build -t piper-webui -f docker/webui/Dockerfile .

echo -e "\nStarting container..."
docker run --rm -it \
    -p ${PORT}:7860 \
    -v "$MODELS_DIR":/models \
    -v "$OUTPUT_DIR":/output \
    -e GRADIO_SERVER_NAME=0.0.0.0 \
    --name piper-webui \
    piper-webui

echo -e "\n${GREEN}WebUI is running at http://localhost:${PORT}${NC}"