# Piper WebAssembly Module

This directory contains the WebAssembly implementation of Piper TTS for browser-based Japanese text-to-speech.

## 🌐 Live Demo

**[Piper WebAssembly TTS Demo](https://ayutaz.github.io/piper-plus/)**

The demo includes:
- Full TTS Demo - Complete Japanese text-to-speech pipeline
- Streaming TTS Demo - Real-time streaming synthesis
- Performance Benchmark - SIMD and WebGL optimization testing
- Simple Demo - Basic functionality test

## Directory Structure

```
src/wasm/
├── cpp/          # C++ source code for WebAssembly
├── js/           # JavaScript/TypeScript wrapper
├── test/         # Test files
├── build/        # Build output (generated)
├── CMakeLists.txt # CMake configuration
├── setup_env.sh  # Emscripten environment setup
├── build.sh      # Build automation script
└── .gitignore    # Git ignore rules
```

## Prerequisites

- Emscripten SDK (3.1.61+)
- CMake (3.15+)
- Node.js (18+)
- Chrome (113+) - PC版のみ対応

## Quick Start

### 1. Install Emscripten (one-time setup)

```bash
# From piper root directory
cd tools
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
```

### 2. Build WebAssembly module

```bash
cd src/wasm
./build.sh  # or ./build.sh --debug for debug build
```

### 3. Test in browser

```bash
cd build/test
python3 server.py
# Open http://localhost:8000/index.html in Chrome
```

### 4. Deploy to GitHub Pages

The project includes automated deployment to GitHub Pages:

```bash
# Trigger deployment workflow
git push origin main

# Or manually trigger from GitHub Actions
# Go to Actions → Deploy WASM Demo → Run workflow
```

The demo will be available at: https://[username].github.io/[repo-name]/

## Build Options

- `./build.sh` - Release build (optimized)
- `./build.sh --debug` - Debug build with assertions
- `./build.sh --clean` - Clean rebuild

## Current Status

✅ Development environment setup complete
✅ Basic WebAssembly build working
✅ CMake configuration for Chrome-optimized build
✅ Test harness ready

## Next Steps

See [Task 0.2](../../docs/webassembly-investigation/detailed-implementation-plan.md) for the next implementation phase.

## Development

For detailed implementation plans and technical documentation:
- [Master Plan](../../docs/webassembly-investigation/webassembly-implementation-master-plan.md)
- [Technical Investigation](../../docs/webassembly-investigation/webassembly-technical-investigation.md)
- [Task Breakdown](../../docs/webassembly-investigation/detailed-implementation-plan.md)