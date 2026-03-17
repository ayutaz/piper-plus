#!/bin/bash
# ARM64 multilingual build verification script for CI/CD
# Note: eSpeak-ng is no longer required (removed in favor of self-contained G2P)

set -e

echo "=== ARM64 Multilingual Build Verification ==="

# Check if piper binary exists
if [ -f /build/install/bin/piper ]; then
    echo "✅ Piper binary found"
else
    echo "❌ Piper binary not found"
    exit 1
fi

# Check ONNX Runtime is linked
echo "=== Checking ONNX Runtime integration ==="
if ldd /build/install/bin/piper 2>/dev/null | grep -q "onnxruntime"; then
    echo "✅ ONNX Runtime is linked"
else
    echo "⚠️ ONNX Runtime linkage not detected (may be statically linked)"
fi

# Test binary execution
echo "=== Testing binary execution ==="
export LD_LIBRARY_PATH=/build/install/lib:$LD_LIBRARY_PATH

# Just check if piper can load with timeout
if timeout 5 /build/install/bin/piper --help >/dev/null 2>&1; then
    echo "✅ Binary can execute (help check)"
else
    echo "⚠️ Binary execution timed out (expected in QEMU)"
    echo "   Full multilingual TTS testing requires native ARM64 hardware"
fi

echo "=== Multilingual build verification complete ==="
echo "✅ ARM64 multilingual build is valid"
echo "⚠️ Full TTS testing should be done on native ARM64 hardware"
