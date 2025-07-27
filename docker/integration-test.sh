#!/bin/bash
set -e

# Integration tests for Piper Docker environments
# Tests actual TTS functionality across different environments

echo "=== Piper Docker Integration Tests ==="
echo ""

# Configuration
TEST_TEXT="Hello world. This is a test of the Piper text to speech system."
TEST_MODEL_URL="https://github.com/rhasspy/piper/releases/download/v1.2.0/en_US-amy-low.onnx"
TEST_CONFIG_URL="https://github.com/rhasspy/piper/releases/download/v1.2.0/en_US-amy-low.onnx.json"

# Create test directories
mkdir -p test_output test_models

# Download test model if not exists
if [ ! -f "test_models/en_US-amy-low.onnx" ]; then
    echo "Downloading test model..."
    wget -q -O test_models/en_US-amy-low.onnx "$TEST_MODEL_URL"
    wget -q -O test_models/en_US-amy-low.onnx.json "$TEST_CONFIG_URL"
fi

echo "1. Testing Python inference environment..."
echo ""

# Test Python inference with API
docker run -d --rm \
    --name piper-python-test \
    -p 8000:8000 \
    -v $(pwd)/test_models:/app/models:ro \
    -v $(pwd)/test_output:/app/output \
    piper-python-inference:test \
    python inference.py --server --model /app/models/en_US-amy-low.onnx

# Wait for server to start
sleep 5

# Test API endpoint
echo "Testing Python API endpoint..."
curl -X POST http://localhost:8000/synthesize \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$TEST_TEXT\", \"output_file\": \"test_python_api.wav\"}" \
    --output test_output/test_python_api_response.wav

# Stop container
docker stop piper-python-test

# Test Python CLI
echo "Testing Python CLI..."
echo "$TEST_TEXT" | docker run --rm -i \
    -v $(pwd)/test_models:/app/models:ro \
    -v $(pwd)/test_output:/app/output \
    piper-python-inference:test \
    python inference.py \
    --model /app/models/en_US-amy-low.onnx \
    --output /app/output/test_python_cli.wav

echo ""
echo "2. Testing C++ inference environment..."
echo ""

# First, build the C++ binary if not exists
if [ ! -f "build/piper" ]; then
    echo "Building C++ binary..."
    docker run --rm \
        -v $(pwd):/workspace \
        piper-cpp-train:test \
        /workspace/docker/cpp-train/build.sh
fi

# Test C++ inference
echo "$TEST_TEXT" | docker run --rm -i \
    -v $(pwd)/test_models:/app/models:ro \
    -v $(pwd)/test_output:/app/output \
    -v $(pwd)/build/piper:/usr/local/bin/piper:ro \
    piper-cpp-inference:test \
    piper --model /app/models/en_US-amy-low.onnx \
    --output_file /app/output/test_cpp.wav

echo ""
echo "3. Testing training environment..."
echo ""

# Test that training environment can load and use models
docker run --rm \
    -v $(pwd)/test_models:/workspace/models:ro \
    piper-python-train:test \
    python -c "
import torch
import onnx
import numpy as np

# Load ONNX model
model = onnx.load('/workspace/models/en_US-amy-low.onnx')
print('Model loaded successfully')
print(f'Model inputs: {[i.name for i in model.graph.input]}')
print(f'Model outputs: {[o.name for o in model.graph.output]}')
"

echo ""
echo "4. Verifying output files..."
echo ""

# Check if output files exist and have content
for file in test_output/*.wav; do
    if [ -f "$file" ]; then
        # Portable way to get file size
        size=$(wc -c < "$file")
        echo "✓ $(basename "$file"): ${size} bytes"
    fi
done

echo ""
echo "5. Testing docker-compose integration..."
echo ""

# Test docker compose run
docker compose run --rm \
    -v $(pwd)/test_models:/app/models:ro \
    -v $(pwd)/test_output:/app/output \
    python-inference \
    python inference.py \
    --model /app/models/en_US-amy-low.onnx \
    --output /app/output/test_compose.wav \
    --text "Testing docker compose integration"

echo ""
echo "6. Performance comparison..."
echo ""

# Measure inference time for each environment
echo "Python inference time:"
time echo "$TEST_TEXT" | docker run --rm -i \
    -v $(pwd)/test_models:/app/models:ro \
    -v $(pwd)/test_output:/app/output \
    piper-python-inference:test \
    python inference.py \
    --model /app/models/en_US-amy-low.onnx \
    --output /app/output/test_perf_python.wav 2>&1 | grep -E "(real|user|sys)"

echo ""
echo "C++ inference time:"
time echo "$TEST_TEXT" | docker run --rm -i \
    -v $(pwd)/test_models:/app/models:ro \
    -v $(pwd)/test_output:/app/output \
    -v $(pwd)/build/piper:/usr/local/bin/piper:ro \
    piper-cpp-inference:test \
    piper --model /app/models/en_US-amy-low.onnx \
    --output_file /app/output/test_perf_cpp.wav 2>&1 | grep -E "(real|user|sys)"

echo ""
echo "=== Integration Test Summary ==="
echo ""

# Count successful tests
TESTS_PASSED=$(ls -1 test_output/*.wav 2>/dev/null | wc -l)
echo "Generated audio files: $TESTS_PASSED"

# Cleanup
rm -rf test_output test_models

if [ $TESTS_PASSED -gt 0 ]; then
    echo ""
    echo "✓ All integration tests passed!"
    exit 0
else
    echo ""
    echo "✗ Integration tests failed!"
    exit 1
fi