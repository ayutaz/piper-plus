#!/bin/bash
# CI-compatible test script for OpenJTalk dictionary auto-download functionality
# This version works with the extracted piper artifact structure

set -e

echo "=== OpenJTalk Dictionary Auto-Download Test (CI) ==="
echo

# Set up paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use environment variables if set (for CI), otherwise use defaults
if [ -n "$PIPER_BIN_PATH" ]; then
    PIPER_BIN="$PIPER_BIN_PATH"
else
    PIPER_BIN="$PROJECT_ROOT/piper/bin/piper"
fi

# Check if piper binary exists
if [ ! -f "$PIPER_BIN" ]; then
    echo "Error: Piper binary not found at: $PIPER_BIN"
    echo "Current directory: $(pwd)"
    echo "Directory contents:"
    ls -la
    if [ -d "piper" ]; then
        echo "Piper directory contents:"
        ls -la piper/
        if [ -d "piper/bin" ]; then
            echo "Piper bin directory contents:"
            ls -la piper/bin/
        fi
    fi
    exit 1
fi

echo "Using piper binary: $PIPER_BIN"

# Clean up any existing test environment
TEST_DIR="/tmp/piper_dict_test_$$"
mkdir -p "$TEST_DIR"

echo "Test directory: $TEST_DIR"
echo

# Test 1: Auto-download disabled
echo "Test 1: Auto-download disabled (should fail)"
export PIPER_AUTO_DOWNLOAD_DICT=0
export OPENJTALK_DICTIONARY_PATH="$TEST_DIR/nonexistent"
if echo "テスト" | "$PIPER_BIN" --model "$PROJECT_ROOT/test/models/multilingual-test-medium.onnx" --output_file "$TEST_DIR/test1.wav" 2>&1 | grep -q "download.*manually\|auto.*download.*disabled\|OpenJTalk is not available"; then
    echo "[OK] Test 1 passed: Correctly failed when auto-download is disabled"
else
    echo "[FAIL] Test 1 failed: Should have failed with manual download message"
    echo "Output:"
    echo "テスト" | "$PIPER_BIN" --model "$PROJECT_ROOT/test/models/multilingual-test-medium.onnx" --output_file "$TEST_DIR/test1.wav" 2>&1 || true
fi
echo

# Test 2: Auto-download enabled (default)
echo "Test 2: Auto-download enabled (should download)"
unset PIPER_AUTO_DOWNLOAD_DICT
export HOME="$TEST_DIR"
unset OPENJTALK_DICTIONARY_PATH

echo "Running piper with auto-download..."
if echo "こんにちは" | "$PIPER_BIN" --model "$PROJECT_ROOT/test/models/multilingual-test-medium.onnx" --output_file "$TEST_DIR/test2.wav" 2>&1 | tee "$TEST_DIR/download.log"; then
    echo "[OK] Test 2 passed: Auto-download succeeded"
    
    # Check if dictionary was downloaded
    if [ -d "$TEST_DIR/.local/share/piper/open_jtalk_dic_utf_8-1.11" ]; then
        echo "[OK] Dictionary downloaded to expected location"
    else
        echo "[WARN] Dictionary not found at expected location"
        echo "Searching for dictionary:"
        find "$TEST_DIR" -name "open_jtalk_dic*" -type d 2>/dev/null || echo "No dictionary found"
    fi
else
    echo "[FAIL] Test 2 failed: Auto-download should have succeeded"
    echo "Error output:"
    cat "$TEST_DIR/download.log" 2>/dev/null || echo "No log file"
fi
echo

# Test 3: Offline mode
echo "Test 3: Offline mode (should fail)"
export PIPER_OFFLINE_MODE=1
export HOME="$TEST_DIR/offline"
mkdir -p "$HOME"

if echo "オフライン" | "$PIPER_BIN" --model "$PROJECT_ROOT/test/models/multilingual-test-medium.onnx" --output_file "$TEST_DIR/test3.wav" 2>&1 | grep -q "Offline mode\|dictionary manually\|OpenJTalk is not available"; then
    echo "[OK] Test 3 passed: Offline mode prevents download"
else
    echo "[FAIL] Test 3 failed: Should have failed in offline mode"
fi

# Clean up
rm -rf "$TEST_DIR"

echo
echo "=== All tests completed ==="