#!/bin/bash

# Build eSpeak-ng for WebAssembly
# Based on official espeak-ng/emscripten implementation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/espeak-ng"
TOOLS_DIR="$PROJECT_ROOT/tools"

echo "Building eSpeak-ng for WebAssembly..."

# Check if Emscripten is available
if ! command -v emcc &> /dev/null; then
    echo "Error: Emscripten (emcc) not found. Please install and configure Emscripten first."
    echo "Visit: https://emscripten.org/docs/getting_started/downloads.html"
    exit 1
fi

# Create directories
mkdir -p "$BUILD_DIR"
mkdir -p "$TOOLS_DIR"

# Clone eSpeak-ng if not exists
if [ ! -d "$TOOLS_DIR/espeak-ng" ]; then
    echo "Cloning eSpeak-ng..."
    cd "$TOOLS_DIR"
    git clone https://github.com/espeak-ng/espeak-ng.git
    cd espeak-ng
    git checkout 1.51.1  # Use stable version
else
    echo "eSpeak-ng already cloned."
    cd "$TOOLS_DIR/espeak-ng"
fi

# Run autogen if needed
if [ ! -f "configure" ]; then
    echo "Running autogen.sh..."
    # Fix missing ChangeLog.md issue
    if [ ! -f "ChangeLog.md" ] && [ -f "CHANGELOG.md" ]; then
        ln -sf CHANGELOG.md ChangeLog.md
    fi
    ./autogen.sh
fi

# Configure for Emscripten
echo "Configuring for Emscripten..."
cd "$BUILD_DIR"

# Configure with minimal features for web
emconfigure "$TOOLS_DIR/espeak-ng/configure" \
    --prefix="$BUILD_DIR/install" \
    --without-async \
    --without-mbrola \
    --without-sonic \
    --without-pcaudiolib \
    --disable-shared \
    --enable-static

# Build
echo "Building eSpeak-ng..."
emmake make -j$(nproc)

# Copy emscripten files if they exist
if [ -d "$TOOLS_DIR/espeak-ng/emscripten" ]; then
    echo "Copying emscripten files..."
    cp -r "$TOOLS_DIR/espeak-ng/emscripten"/* "$BUILD_DIR/"
fi

# Build the JavaScript version
echo "Building JavaScript version..."
cd "$BUILD_DIR"

# Create minimal wrapper if needed
if [ ! -f "espeak-ng-wrapper.c" ]; then
    cat > espeak-ng-wrapper.c << 'EOF'
#include <emscripten.h>
#include <espeak-ng/speak_lib.h>

EMSCRIPTEN_KEEPALIVE
int espeak_initialize() {
    return espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, NULL, 0);
}

EMSCRIPTEN_KEEPALIVE
const char* espeak_text_to_phonemes(const char* text, const char* voice) {
    static char phonemes[1024];
    espeak_SetVoiceByName(voice);
    
    const void *user_data = NULL;
    unsigned int position = 0;
    espeak_POSITION_TYPE position_type = POS_CHARACTER;
    
    espeak_TextToPhonemes(&text, phonemes, sizeof(phonemes), 
                          espeakCHARS_UTF8 | espeakPHONEMES_IPA, &position, 
                          position_type, &user_data);
    
    return phonemes;
}

EMSCRIPTEN_KEEPALIVE
void espeak_terminate() {
    espeak_Terminate();
}
EOF
fi

# Compile to WebAssembly
echo "Compiling to WebAssembly..."
emcc \
    -I"$TOOLS_DIR/espeak-ng/src/include" \
    -I"$BUILD_DIR/install/include" \
    -L"$BUILD_DIR/src/.libs" \
    espeak-ng-wrapper.c \
    -lespeak-ng \
    -s WASM=1 \
    -s MODULARIZE=1 \
    -s EXPORT_ES6=1 \
    -s EXPORT_NAME="createEspeakNGModule" \
    -s EXPORTED_FUNCTIONS='["_espeak_initialize", "_espeak_text_to_phonemes", "_espeak_terminate"]' \
    -s EXTRA_EXPORTED_RUNTIME_METHODS='["ccall", "cwrap", "UTF8ToString"]' \
    -s ALLOW_MEMORY_GROWTH=1 \
    -s TOTAL_MEMORY=33554432 \
    --preload-file "$TOOLS_DIR/espeak-ng/espeak-ng-data@/espeak-ng-data" \
    -o "$PROJECT_ROOT/dist/espeak-ng.js"

echo "Build complete!"
echo "Output files:"
echo "  - $PROJECT_ROOT/dist/espeak-ng.js"
echo "  - $PROJECT_ROOT/dist/espeak-ng.wasm"
echo "  - $PROJECT_ROOT/dist/espeak-ng.data"

# Create usage example
cat > "$PROJECT_ROOT/demo/espeak-ng-test.html" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>eSpeak-ng WebAssembly Test</title>
</head>
<body>
    <h1>eSpeak-ng WebAssembly Test</h1>
    <input type="text" id="text" value="Hello world" />
    <select id="voice">
        <option value="en">English</option>
        <option value="es">Spanish</option>
        <option value="fr">French</option>
        <option value="de">German</option>
    </select>
    <button onclick="convert()">Convert to Phonemes</button>
    <div id="result"></div>

    <script type="module">
        import createEspeakNGModule from '../dist/espeak-ng.js';
        
        let Module;
        let espeakInitialized = false;
        
        window.initEspeak = async function() {
            Module = await createEspeakNGModule();
            const result = Module.ccall('espeak_initialize', 'number', [], []);
            espeakInitialized = result >= 0;
            console.log('eSpeak-ng initialized:', espeakInitialized);
        };
        
        window.convert = function() {
            if (!espeakInitialized) {
                alert('Please wait for initialization');
                return;
            }
            
            const text = document.getElementById('text').value;
            const voice = document.getElementById('voice').value;
            
            const phonemes = Module.ccall(
                'espeak_text_to_phonemes',
                'string',
                ['string', 'string'],
                [text, voice]
            );
            
            document.getElementById('result').innerText = 'Phonemes: ' + phonemes;
        };
        
        // Initialize on load
        initEspeak();
    </script>
</body>
</html>
EOF

echo "Test page created: $PROJECT_ROOT/demo/espeak-ng-test.html"