#!/bin/bash

# Build script for GitHub Pages deployment

set -e

echo "Building Piper WebAssembly demo for GitHub Pages..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[BUILD]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "build-demo.sh" ]; then
    print_error "Please run this script from the src/wasm directory"
    exit 1
fi

# Build MeCab
print_status "Building MeCab WebAssembly module..."
cd mecab
if [ ! -d "node_modules" ]; then
    npm ci
fi
npm run build:wasm
npm run build
cd ..
print_success "MeCab built successfully"

# Build OpenJTalk
print_status "Building OpenJTalk WebAssembly module..."
cd openjtalk
if [ ! -d "node_modules" ]; then
    npm ci
fi
if [ ! -f "build/openjtalk.js" ]; then
    ./build.sh
fi
npm run build
cd ..
print_success "OpenJTalk built successfully"

# Build ONNX Runtime integration
print_status "Building ONNX Runtime integration..."
cd onnx
if [ ! -d "node_modules" ]; then
    npm ci
fi
npm run build
cd ..
print_success "ONNX Runtime integration built successfully"

# Create demo directory structure
print_status "Preparing demo site..."
DEMO_DIR="../../demo-site"
rm -rf $DEMO_DIR
mkdir -p $DEMO_DIR

# Copy demo pages with path adjustments
print_status "Copying and adjusting demo pages..."
for html_file in test/*.html; do
    if [ -f "$html_file" ]; then
        filename=$(basename "$html_file")
        print_status "Processing $filename..."
        
        # Adjust paths in HTML files
        sed -e 's|src="/mecab/|src="./mecab/|g' \
            -e 's|src="/openjtalk/|src="./openjtalk/|g' \
            -e 's|src="/onnx/|src="./onnx/|g' \
            -e 's|src="/test/|src="./test/|g' \
            -e 's|from "/mecab/|from "./mecab/|g' \
            -e 's|from "/openjtalk/|from "./openjtalk/|g' \
            -e 's|from "/onnx/|from "./onnx/|g' \
            -e 's|href="/|href="./|g' \
            -e 's|"/dictionary"|"./dictionary"|g' \
            -e 's|"/data/|"./data/|g' \
            "$html_file" > "$DEMO_DIR/$filename"
    fi
done

# Copy built assets
print_status "Copying built assets..."
mkdir -p $DEMO_DIR/mecab/build
cp -r mecab/build/* $DEMO_DIR/mecab/build/

mkdir -p $DEMO_DIR/openjtalk/build
cp -r openjtalk/build/* $DEMO_DIR/openjtalk/build/

mkdir -p $DEMO_DIR/onnx/dist
cp -r onnx/dist/* $DEMO_DIR/onnx/dist/

# Copy data files if they exist
if [ -d "mecab/data" ]; then
    print_status "Copying MeCab dictionary data..."
    mkdir -p $DEMO_DIR/mecab/data
    cp -r mecab/data/* $DEMO_DIR/mecab/data/
fi

if [ -d "openjtalk/data" ]; then
    print_status "Copying OpenJTalk data..."
    mkdir -p $DEMO_DIR/openjtalk/data
    cp -r openjtalk/data/* $DEMO_DIR/openjtalk/data/
fi

# Copy test models if available
if [ -d "../../test/models" ]; then
    print_status "Copying test models..."
    mkdir -p $DEMO_DIR/test/models
    cp -r ../../test/models/*.onnx* $DEMO_DIR/test/models/ 2>/dev/null || true
fi

# Create a simple HTTP server script for local testing
cat > $DEMO_DIR/serve.py << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import os

PORT = 8000

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    print(f"Server running at http://localhost:{PORT}/")
    print("Press Ctrl-C to stop")
    httpd.serve_forever()
EOF

chmod +x $DEMO_DIR/serve.py

# Create README for the demo site
cat > $DEMO_DIR/README.md << 'EOF'
# Piper WebAssembly TTS Demo

This is the demo site for Piper TTS WebAssembly implementation.

## Local Testing

To test locally, run:

```bash
python3 serve.py
```

Then open http://localhost:8000/ in Chrome.

## Requirements

- Chrome 113+ (recommended)
- At least 1GB RAM
- WebAssembly support

## Available Demos

- **MeCab Test**: Japanese morphological analysis
- **OpenJTalk Test**: Phoneme conversion
- **Full TTS Demo**: Complete text-to-speech pipeline
- **Streaming Demo**: Real-time streaming synthesis
- **Real Model Demo**: Using actual Piper models

## Note

The demos require downloading large dictionary and model files on first load.
EOF

print_success "Demo site prepared at $DEMO_DIR"
print_status "To test locally, run:"
echo "  cd $DEMO_DIR"
echo "  python3 serve.py"