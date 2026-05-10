#!/bin/bash
set -e

MODEL_DIR="${PIPER_MODEL_DIR:-/models}"

# Download model if PIPER_MODEL is specified
if [ -n "$PIPER_MODEL" ]; then
    echo "Checking model: $PIPER_MODEL"
    python -c "
from piper_train.model_manager import resolve_model_path, download_model
import sys, os

model_name = os.environ['PIPER_MODEL']
model_dir = os.environ.get('PIPER_MODEL_DIR', '/models')

# Already downloaded?
path = resolve_model_path(model_name, model_dir)
if path:
    print(f'Model ready: {path}', file=sys.stderr)
    sys.exit(0)

# Download
if not download_model(model_name, model_dir):
    print(f'Failed to download model: {model_name}', file=sys.stderr)
    sys.exit(1)
"
fi

exec python /app/app.py --model-dir "$MODEL_DIR" --output-dir "${PIPER_OUTPUT_DIR:-/output}" "$@"
