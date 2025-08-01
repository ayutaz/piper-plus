# OpenJTalk WebAssembly Browser Implementation

## Overview

This directory contains the browser-compatible WebAssembly implementation of OpenJTalk for piper-plus.
Based on the successful approach of `wasm_open_jtalk`, this implementation ports the entire OpenJTalk
system to run in web browsers.

## Project Structure

```
openjtalk-web/
├── build/          # Build configuration and scripts
├── src/            # Source code (C++ wrappers and JS API)
├── dist/           # Built artifacts (JS, WASM, type definitions)
├── demo/           # Demo pages and examples
└── test/           # Unit and integration tests
```

## Build Requirements

- Emscripten 3.1.x or later
- CMake 3.10 or later
- Docker (recommended for reproducible builds)
- Node.js 16+ (for development tools)

## Quick Start

### 1. Prepare Assets

```bash
# Download dictionary and voice files
./prepare-assets.sh
```

### 2. Build

#### Using Docker (Recommended)

```bash
# Build the Docker image
docker build -t piper-openjtalk-web build/

# Run the build
docker run -v $(pwd):/src piper-openjtalk-web

# Output files will be in dist/
```

#### Local Build

```bash
# Install Emscripten first
# See: https://emscripten.org/docs/getting_started/downloads.html

# Run local build
./build-local.sh

# Output files will be in dist/
```

### 3. Test the Demo

```bash
# Start the development server
cd demo
python3 server.py

# Open in browser
# http://localhost:8080/
```

## Development Status

- [ ] Phase 1: Basic Implementation (In Progress)
  - [x] Project setup
  - [ ] wasm_open_jtalk source analysis
  - [ ] Build environment configuration
  - [ ] Browser-compatible build
  
- [ ] Phase 2: Optimization
  - [ ] Dictionary compression
  - [ ] Memory optimization
  - [ ] Performance tuning

- [ ] Phase 3: Integration
  - [ ] Piper ONNX Runtime integration
  - [ ] Streaming support
  - [ ] Production deployment

## Usage Example

```javascript
// Initialize OpenJTalk Web
const openjtalk = new OpenJTalkWeb();
await openjtalk.initialize({
  dictUrl: '/assets/dict.br',
  wasmUrl: '/assets/openjtalk.wasm'
});

// Convert text to phonemes
const phonemes = await openjtalk.textToPhonemes('こんにちは世界');
console.log(phonemes); // Output: phoneme sequence
```

## License

This project follows the licensing terms of OpenJTalk and piper-plus.