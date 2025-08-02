#!/bin/bash

# Complete build process for eSpeak-ng WebAssembly
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"
ESPEAK_DIR="$PROJECT_ROOT/temp/espeak-ng/espeak-ng"

echo "Complete eSpeak-ng WebAssembly build process..."

# Ensure Emscripten is in PATH
if ! command -v emcc &> /dev/null; then
    echo "Error: emcc not found. Please run:"
    echo "  source $TOOLS_DIR/emsdk/emsdk_env.sh"
    exit 1
fi

cd "$ESPEAK_DIR"

# First, build eSpeak-ng normally to ensure we have all the data files
echo "Step 1: Building eSpeak-ng with configure..."
if [ ! -f "Makefile" ]; then
    # Fix ChangeLog.md issue
    if [ ! -f "ChangeLog.md" ] && [ -f "CHANGELOG.md" ]; then
        ln -sf CHANGELOG.md ChangeLog.md
    fi
    
    # Run autogen
    ./autogen.sh
    
    # Configure for local build first
    emconfigure ./configure --prefix=/usr --without-async --without-mbrola --without-sonic --without-pcaudiolib
fi

# Build to generate data files
echo "Step 2: Building to generate data files..."
emmake make

# Now build the emscripten version
echo "Step 3: Building emscripten version..."
cd emscripten

# The Makefile expects certain environment variables
export EMSCRIPTEN="$TOOLS_DIR/emsdk/upstream/emscripten"

# Build using the emscripten-specific Makefile
emmake make

# Copy the built files
echo "Step 4: Copying built files..."
mkdir -p "$PROJECT_ROOT/dist/espeak-ng"
cp -v js/* "$PROJECT_ROOT/dist/espeak-ng/" 2>/dev/null || echo "No JS files found yet"

# If the above doesn't work, try the manual approach
if [ ! -f "$PROJECT_ROOT/dist/espeak-ng/espeakng_worker.js" ]; then
    echo "Step 5: Manual emscripten compilation..."
    
    # Compile the glue code
    emcc espeakng_glue.cpp \
        -I../src/include \
        -L../src/.libs \
        -lespeak-ng \
        -s WASM=1 \
        -s ALLOW_MEMORY_GROWTH=1 \
        -s INVOKE_RUN=0 \
        -s MODULARIZE=1 \
        -s EXPORT_NAME="'createESpeakNGModule'" \
        -s EXPORTED_FUNCTIONS='["_espeak_Initialize", "_espeak_Synth", "_espeak_TextToPhonemes", "_espeak_SetVoiceByName", "_espeak_Terminate"]' \
        -s EXTRA_EXPORTED_RUNTIME_METHODS='["ccall", "cwrap", "FS", "UTF8ToString", "stringToUTF8"]' \
        --preload-file ../espeak-ng-data@/espeak-ng-data \
        -o js/espeakng_module.js
        
    echo "Manual compilation complete"
fi

echo ""
echo "Build process complete!"
echo "Output files:"
ls -la "$PROJECT_ROOT/dist/espeak-ng/" 2>/dev/null || echo "No files in dist/espeak-ng/"

# Create a test HTML file
cat > "$PROJECT_ROOT/demo/espeak-ng-full-test.html" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>eSpeak-ng Full Test</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>eSpeak-ng WebAssembly Full Test</h1>
    <p>This tests the complete eSpeak-ng implementation</p>
    
    <div>
        <textarea id="text" rows="4" cols="50">Hello world! This is a test of the text to speech system.</textarea><br>
        <button onclick="testPhonemes()">Get Phonemes (IPA)</button>
        <button onclick="testSynth()">Synthesize Speech</button>
    </div>
    
    <div>
        <h3>Phonemes:</h3>
        <pre id="phonemes"></pre>
    </div>
    
    <div>
        <h3>Audio:</h3>
        <audio id="audio" controls></audio>
    </div>
    
    <script type="text/javascript">
        // Load eSpeak-ng
        let espeakReady = false;
        
        // This would load the actual compiled module
        console.log('eSpeak-ng test page loaded');
        console.log('To complete the integration:');
        console.log('1. Ensure eSpeak-ng is properly compiled');
        console.log('2. Load the worker and module');
        console.log('3. Initialize with voice data');
        
        function testPhonemes() {
            const text = document.getElementById('text').value;
            document.getElementById('phonemes').textContent = 
                'eSpeak-ng phonemization would show IPA phonemes here\n' +
                'This requires the compiled WASM module';
        }
        
        function testSynth() {
            alert('Speech synthesis requires the compiled eSpeak-ng module');
        }
    </script>
</body>
</html>
EOF

echo ""
echo "Test page created: demo/espeak-ng-full-test.html"
echo ""
echo "Note: The build process may need adjustments based on your system."
echo "Check the espeak-ng/emscripten directory for more details."