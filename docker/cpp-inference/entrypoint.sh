#!/bin/bash
set -e

# Set up environment
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Check piper installation
if command -v piper &> /dev/null; then
    echo "Piper version: $(piper --version)"
else
    echo "Warning: Piper binary not found in PATH"
fi

# Set default model path if MODEL_PATH is provided
if [ -n "$MODEL_PATH" ]; then
    export PIPER_MODEL_PATH="$MODEL_PATH"
fi

# Execute command
exec "$@"