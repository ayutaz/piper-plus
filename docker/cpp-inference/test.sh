#!/bin/bash
set -e

echo "=== C++ Inference Container Test ==="
echo ""

# Test 1: Check piper binary
echo "--- Piper Binary Test ---"
if command -v piper &> /dev/null; then
    echo "✓ piper binary found: $(which piper)"
    piper --version || echo "Warning: Could not get version"
else
    echo "✗ piper binary not found"
    exit 1
fi

echo ""

# Test 2: Check libraries
echo "--- Library Test ---"
libs=(
    "libonnxruntime.so"
    "libespeak-ng.so"
    "libpiper_phonemize.so"
    "libHTSEngine.so"
    "libsndfile.so"
)

all_libs_found=true
for lib in "${libs[@]}"; do
    if ldconfig -p | grep -q "$lib"; then
        echo "✓ $lib"
    else
        echo "✗ $lib not found"
        all_libs_found=false
    fi
done

if [ "$all_libs_found" = false ]; then
    echo "Warning: Some libraries missing from ldconfig cache"
    echo "Checking /usr/local/lib..."
    ls -la /usr/local/lib/ | grep -E "(onnx|espeak|piper|HTS|sndfile)" || true
fi

echo ""

# Test 3: Check espeak-ng data
echo "--- eSpeak-ng Data Test ---"
if [ -d "/usr/local/share/espeak-ng-data" ]; then
    echo "✓ eSpeak-ng data directory found"
    echo "  Languages: $(ls /usr/local/share/espeak-ng-data/lang | wc -l)"
else
    echo "✗ eSpeak-ng data directory not found"
fi

echo ""

# Test 4: Check CUDA (optional)
echo "--- CUDA Test ---"
if command -v nvidia-smi &> /dev/null; then
    if nvidia-smi &> /dev/null; then
        echo "✓ CUDA GPU available"
        nvidia-smi --query-gpu=name --format=csv,noheader | head -1
    else
        echo "ℹ nvidia-smi command failed (no GPU or driver issue)"
    fi
else
    echo "ℹ CUDA not available (CPU inference only)"
fi

echo ""

# Test 5: Help command test
echo "--- Help Command Test ---"
if piper --help &> /dev/null; then
    echo "✓ piper --help works"
else
    echo "✗ piper --help failed"
    exit 1
fi

echo ""

# Test 6: Model directory check
echo "--- Model Directory Test ---"
if [ -d "/app/models" ]; then
    echo "✓ /app/models directory exists"
    if [ "$(ls -A /app/models 2>/dev/null)" ]; then
        echo "  Models found:"
        ls -la /app/models/*.onnx 2>/dev/null | head -5 || echo "  No .onnx files found"
    else
        echo "  Directory is empty (models should be mounted)"
    fi
else
    echo "✗ /app/models directory not found"
fi

echo ""
echo "=== Summary ==="
echo "Container is ready for inference!"
echo "Mount your models to /app/models and run:"
echo "  piper --model /app/models/your_model.onnx --output_file output.wav"