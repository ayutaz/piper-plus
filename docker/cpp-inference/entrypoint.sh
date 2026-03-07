#!/bin/bash
set -e

# Set up environment
export CUDA_HOME=/usr/local/cuda
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:/usr/local/lib:$LD_LIBRARY_PATH

# Check if running with NVIDIA GPU
if command -v nvidia-smi &> /dev/null; then
    echo "=== GPU Information ==="
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    echo ""
fi

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