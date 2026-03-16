#!/bin/bash
set -e

# Set up environment
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Set default model path if MODEL_PATH is provided
if [ -n "$MODEL_PATH" ]; then
    export PIPER_MODEL_PATH="$MODEL_PATH"
fi

# If first arg starts with '-', treat as piper arguments
if [ "${1#-}" != "$1" ]; then
    set -- piper "$@"
fi

exec "$@"