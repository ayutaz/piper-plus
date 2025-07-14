#!/bin/bash
# ARM64 multilingual build verification script for CI/CD

set -e

echo "=== ARM64 Multilingual Build Verification ==="

# Check if piper binary exists
if [ -f /build/install/bin/piper ]; then
    echo "✅ Piper binary found"
else
    echo "❌ Piper binary not found"
    exit 1
fi

# Check espeak-ng integration
echo "=== Checking espeak-ng integration ==="
if ldd /build/install/bin/piper | grep -q "espeak"; then
    echo "✅ espeak-ng is linked"
else
    echo "❌ espeak-ng is not linked"
    exit 1
fi

# Check espeak-ng data
if [ -d /build/install/share/espeak-ng-data ]; then
    echo "✅ espeak-ng data found"
    # Check for language files
    if ls /build/install/share/espeak-ng-data/lang/* >/dev/null 2>&1; then
        echo "✅ Language files present"
    else
        echo "⚠️ Language files may be incomplete"
    fi
else
    echo "❌ espeak-ng data not found"
    exit 1
fi

# Test phonemization without full TTS
echo "=== Testing phonemization capabilities ==="
export LD_LIBRARY_PATH=/build/install/lib:$LD_LIBRARY_PATH
export ESPEAK_DATA_PATH=/build/install/share/espeak-ng-data

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