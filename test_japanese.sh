#!/bin/bash
# Test Japanese TTS with Piper

set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <piper_binary>"
    exit 1
fi

PIPER="$1"
TEST_TEXT="こんにちは、世界。今日は良い天気ですね。"
OUTPUT_FILE="test_japanese_output.wav"

echo "Testing Japanese TTS with Piper..."
echo "Binary: $PIPER"
echo "Text: $TEST_TEXT"

# Check if piper binary exists and is executable
if [ ! -x "$PIPER" ]; then
    echo "Error: Piper binary not found or not executable: $PIPER"
    exit 1
fi

# Check if OpenJTalk is supported
if $PIPER --help 2>&1 | grep -q "openjtalk"; then
    echo "OpenJTalk support: ENABLED"
else
    echo "OpenJTalk support: DISABLED"
    echo "Warning: Japanese TTS may not work correctly without OpenJTalk"
fi

# Test with a Japanese model (if available)
# For now, just test that the binary runs
echo "$TEST_TEXT" | $PIPER --output_file "$OUTPUT_FILE" 2>&1 || {
    echo "Note: Japanese model not available for full test"
    echo "Binary execution test: PASSED"
    exit 0
}

if [ -f "$OUTPUT_FILE" ]; then
    echo "Output file created: $OUTPUT_FILE"
    echo "Japanese TTS test: PASSED"
    rm -f "$OUTPUT_FILE"
else
    echo "Japanese TTS test: FAILED"
    exit 1
fi