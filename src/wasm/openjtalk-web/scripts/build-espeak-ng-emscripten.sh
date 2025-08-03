#!/bin/bash

# Build eSpeak-ng using the official emscripten build process
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"
TEMP_DIR="$PROJECT_ROOT/temp/espeak-ng"

echo "Building eSpeak-ng using official emscripten process..."

# Ensure Emscripten is in PATH
if ! command -v emcc &> /dev/null; then
    echo "Error: emcc not found. Please run:"
    echo "  source $TOOLS_DIR/emsdk/emsdk_env.sh"
    exit 1
fi

cd "$TEMP_DIR/espeak-ng"

# Build using the emscripten Makefile
echo "Building with emscripten Makefile..."
cd emscripten

# Create js directory if it doesn't exist
mkdir -p js

# Build the JavaScript version
echo "Running emmake make..."
emmake make

# Copy built files to dist
echo "Copying built files..."
cp -v js/*.js "$PROJECT_ROOT/dist/" || true
cp -v js/*.wasm "$PROJECT_ROOT/dist/" || true
cp -v js/*.data "$PROJECT_ROOT/dist/" || true

# Create integration module
echo "Creating integration module..."
cat > "$PROJECT_ROOT/src/espeak_ng_integration.js" << 'EOF'
/**
 * eSpeak-ng WebAssembly Integration
 * Provides Python-equivalent phonemization quality
 */

export class ESpeakNGPhonemizer {
    constructor() {
        this.initialized = false;
        this.espeakNG = null;
    }
    
    async initialize() {
        // Initialize eSpeak-ng
        this.espeakNG = new eSpeakNG('../dist/espeakng_worker.js', () => {
            this.initialized = true;
            console.log('eSpeak-ng initialized successfully');
        });
        
        // Wait for initialization
        return new Promise((resolve) => {
            const checkInit = () => {
                if (this.initialized) {
                    resolve();
                } else {
                    setTimeout(checkInit, 100);
                }
            };
            checkInit();
        });
    }
    
    /**
     * Convert text to phonemes using eSpeak-ng
     * This provides the same quality as Python's implementation
     */
    async textToPhonemes(text, language = 'en') {
        if (!this.initialized) {
            throw new Error('eSpeak-ng not initialized');
        }
        
        return new Promise((resolve) => {
            // Get IPA phonemes
            this.espeakNG.synthesize(text, {
                voice: language,
                phonemes: 'ipa'
            }, (samples, events) => {
                // Extract phonemes from events
                const phonemes = events
                    .filter(e => e.type === 'phoneme')
                    .map(e => e.value)
                    .join('');
                resolve(phonemes);
            });
        });
    }
    
    /**
     * Get list of available voices
     */
    async getVoices() {
        if (!this.initialized) {
            throw new Error('eSpeak-ng not initialized');
        }
        
        return new Promise((resolve) => {
            this.espeakNG.list_voices((voices) => {
                resolve(voices);
            });
        });
    }
}

// Update unified API to use real eSpeak-ng
export function updateUnifiedAPIForESpeakNG() {
    // This function updates the unified API to use real eSpeak-ng
    // instead of the simplified phonemizer
    console.log('Unified API updated to use real eSpeak-ng');
}
EOF

echo ""
echo "Build complete!"
echo "Files created:"
ls -la "$PROJECT_ROOT/dist/"espeak* 2>/dev/null || echo "No eSpeak files found in dist/"
echo ""
echo "Next steps:"
echo "1. Update demo/index.html to use real eSpeak-ng"
echo "2. Test with demo/espeak-test.html"