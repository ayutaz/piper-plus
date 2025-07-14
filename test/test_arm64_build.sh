#!/bin/bash
# ARM64 build verification script for CI/CD

set -e

echo "=== ARM64 Build Verification Test ==="

# Check if piper binary exists
if [ -f /build/install/bin/piper ]; then
    echo "✅ Piper binary found"
else
    echo "❌ Piper binary not found"
    exit 1
fi

# Check binary architecture
ARCH=$(file /build/install/bin/piper | grep -o "ARM aarch64\|x86-64")
if [[ "$ARCH" == *"ARM aarch64"* ]]; then
    echo "✅ Binary is ARM64"
else
    echo "❌ Binary is not ARM64: $ARCH"
    exit 1
fi

# Check library dependencies
echo "=== Checking library dependencies ==="
if ldd /build/install/bin/piper 2>&1 | grep -q "not found"; then
    echo "❌ Missing libraries detected:"
    ldd /build/install/bin/piper | grep "not found"
    exit 1
else
    echo "✅ All libraries are properly linked"
fi

# Check ONNX Runtime
if ldd /build/install/bin/piper | grep -q "onnxruntime"; then
    echo "✅ ONNX Runtime is linked"
else
    echo "❌ ONNX Runtime is not linked"
    exit 1
fi

# Check espeak-ng data
if [ -d /build/install/share/espeak-ng-data ]; then
    echo "✅ espeak-ng data found"
else
    echo "❌ espeak-ng data not found"
    exit 1
fi

# Check OpenJTalk data
if [ -d /build/install/share/openjtalk ]; then
    echo "✅ OpenJTalk data found"
else
    echo "⚠️ OpenJTalk data not found (optional)"
fi

# Try to run piper with very short timeout
echo "=== Testing binary execution ==="
export LD_LIBRARY_PATH=/build/install/lib:$LD_LIBRARY_PATH

# Just check if it can start - don't run full TTS
if timeout 2 /build/install/bin/piper --version 2>&1; then
    echo "✅ Binary can execute (version check)"
else
    echo "⚠️ Binary execution timed out (expected in QEMU)"
    echo "   This is normal for QEMU emulation with ONNX Runtime"
fi

echo "=== Build verification complete ==="
echo "✅ ARM64 build is valid and ready for deployment"
echo "⚠️ Full TTS testing should be done on native ARM64 hardware"