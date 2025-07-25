#!/bin/bash
# Helper script to run piper with correct eSpeak-ng data path

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set eSpeak-ng data path
export ESPEAK_DATA_PATH="${SCRIPT_DIR}/build/pi/share/espeak-ng-data"

# Run piper with all arguments passed to this script
"${SCRIPT_DIR}/build/piper" "$@"