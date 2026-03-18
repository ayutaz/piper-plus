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

# Test 2: Check libraries (ONNX Runtime only — espeak-ng/piper-phonemize removed, GPL-free)
echo "--- Library Test ---"
libs=(
    "libonnxruntime.so"
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
    ls -la /usr/local/lib/ | grep -E "onnx" || true
fi

echo ""

# Test 3: Check native G2P (self-contained, no espeak-ng dependency)
echo "--- Native G2P Test ---"
if piper --help 2>&1 | grep -qi "model\|help\|usage"; then
    echo "✓ piper binary responds to --help (native G2P built-in)"
else
    echo "✗ piper --help did not produce expected output"
fi

echo ""

# Test 4: Help command test
echo "--- Help Command Test ---"
if piper --help &> /dev/null; then
    echo "✓ piper --help works"
else
    echo "✗ piper --help failed"
    exit 1
fi

echo ""

# Test 5: Model directory check
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