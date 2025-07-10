#!/bin/bash

# Find open_jtalk binary
OPENJTALK=""
if [ -f "./test_windows_build/bin/open_jtalk.exe" ]; then
    OPENJTALK="./test_windows_build/bin/open_jtalk.exe"
elif [ -f "./build/oj/bin/open_jtalk" ]; then
    OPENJTALK="./build/oj/bin/open_jtalk"
else
    echo "OpenJTalk binary not found"
    exit 1
fi

echo "Using OpenJTalk: $OPENJTALK"

# Create test input
echo "こんにちは" > test_input.txt

# Get dictionary path
DICT_PATH="$HOME/.local/share/piper/open_jtalk_dic_utf_8-1.11"
if [ ! -d "$DICT_PATH" ]; then
    echo "Dictionary not found at $DICT_PATH"
    exit 1
fi

# Run OpenJTalk with trace output
echo "Running OpenJTalk..."
"$OPENJTALK" -x "$DICT_PATH" -ot test_trace.txt test_input.txt

echo "Trace output:"
cat test_trace.txt

# Clean up
rm -f test_input.txt test_trace.txt