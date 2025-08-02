#!/bin/bash

# Install Emscripten SDK for building eSpeak-ng
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"

echo "Installing Emscripten SDK..."

mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Clone emsdk
if [ ! -d "emsdk" ]; then
    echo "Cloning Emscripten SDK..."
    git clone https://github.com/emscripten-core/emsdk.git
else
    echo "Emscripten SDK already cloned, updating..."
    cd emsdk
    git pull
    cd ..
fi

cd emsdk

# Install and activate latest SDK
echo "Installing latest Emscripten..."
./emsdk install latest
./emsdk activate latest

echo ""
echo "Emscripten installed successfully!"
echo ""
echo "To use Emscripten in your current shell, run:"
echo "  source $TOOLS_DIR/emsdk/emsdk_env.sh"
echo ""
echo "After sourcing, you can build eSpeak-ng by running:"
echo "  ./scripts/build-espeak-ng.sh"