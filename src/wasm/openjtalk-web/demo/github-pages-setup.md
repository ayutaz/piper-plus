# GitHub Pages Deployment Guide

## Overview

This document describes how to deploy the PiperPlus WebAssembly TTS demo to GitHub Pages. The demo uses the PiperPlus high-level API with Rust WASM phonemization and ONNX Runtime Web for fully in-browser speech synthesis.

## Architecture

| Component | Technology |
|-----------|-----------|
| Japanese phonemization | Rust WASM (jpreprocess, dictionary embedded in binary) |
| English phonemization | SimpleEnglishPhonemizer (rule-based) |
| Multilingual phonemization (ZH/KO/ES/FR/PT/SV) | SimpleUnifiedPhonemizer (character/rule-based) |
| Model loading | ModelManager (HuggingFace auto-download + IndexedDB cache) |
| ONNX inference | onnxruntime-web (WebGPU with WASM fallback) |

## Directory Structure

### Source layout (repository)

```
src/wasm/openjtalk-web/
├── demo/
│   ├── index.html                   # Main demo page
│   ├── simple-multilingual.html     # Simplified demo
│   ├── multilingual.html            # Multilingual demo with examples
│   ├── piper-espeak-english.html    # English-only demo
│   ├── piper-espeak-complete.html   # Full-featured demo
│   └── config.js                    # Deployment configuration
├── src/
│   ├── index.js                     # PiperPlus entry point
│   ├── model-manager.js             # HuggingFace model download + IndexedDB cache
│   ├── audio-result.js              # WAV encoding + playback
│   └── ...                          # Other PiperPlus modules
├── dist/
│   └── rust-wasm/
│       ├── piper_plus_wasm_bg.wasm  # Rust WASM binary (~15MB, dictionary embedded)
│       ├── piper_plus_wasm.js       # WASM JS bindings
│       └── piper_plus_wasm.d.ts     # TypeScript definitions
└── test/
    └── multilingual-demo/
        └── index.html               # 6-language multilingual demo (deployed as main page)
```

### Deployed layout (GitHub Pages root)

```
/ (GitHub Pages root)
├── index.html              (from test/multilingual-demo/index.html, paths rewritten)
├── 404.html                (copy of index.html)
├── src/
│   ├── index.js
│   ├── model-manager.js
│   ├── audio-result.js
│   └── ...
├── dist/
│   └── rust-wasm/
│       ├── piper_plus_wasm_bg.wasm
│       ├── piper_plus_wasm.js
│       └── piper_plus_wasm.d.ts
└── multilingual-demo/
    └── *.html
```

Note: ONNX models are NOT bundled in the deployment. The `ModelManager` downloads models from HuggingFace on first use and caches them in IndexedDB.

## Initialization Code

The PiperPlus API handles model download, WASM phonemizer initialization, and ONNX session creation in a single call:

```javascript
import { PiperPlus } from './src/index.js';

// Load ONNX Runtime from CDN
const script = document.createElement('script');
script.src = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js';
document.head.appendChild(script);

// Initialize PiperPlus (downloads model from HuggingFace on first use)
const piper = await PiperPlus.initialize({
    model: 'tsukuyomi',
    ort: globalThis.ort,
    onProgress: ({ stage, progress, message }) => {
        console.log(`[${stage}] ${(progress * 100).toFixed(0)}% - ${message}`);
    }
});

// Synthesize and play
const audio = await piper.synthesize('Hello, world!', { language: 'en' });
await audio.play();
```

## Deployment Method: GitHub Actions

Deployment is handled by `.github/workflows/deploy-webassembly-demo.yml`. This workflow:

1. **Builds Rust WASM** via `wasm-pack build --target web --release`
2. **Prepares deployment directory** by copying `dist/`, `src/`, and HTML files
3. **Rewrites paths** using `sed` to adjust relative paths (`../../` to `./` or `../`) for the flat deployment structure
4. **Deploys to GitHub Pages** via `actions/deploy-pages@v4`

### Triggering a deployment

- **Automatic**: Push to `dev` branch with changes under `src/wasm/`
- **Manual**: Use `workflow_dispatch` from the Actions tab

### WASM build prerequisite

The workflow installs `wasm-pack` and builds the Rust WASM binary automatically. To build locally:

```bash
# Install wasm-pack
cargo install wasm-pack --locked

# Build WASM (from repository root)
cd src/rust/piper-wasm
wasm-pack build --target web --release --out-dir ../../wasm/openjtalk-web/dist/rust-wasm
```

## config.js

`demo/config.js` provides centralized deployment settings:

```javascript
const deploymentConfig = {
    isGitHubPages: false,       // Set to true for GitHub Pages
    basePath: '',               // e.g., '/piper-plus/'
    defaultModel: 'tsukuyomi',  // Model name for PiperPlus.initialize()
    ortCdnUrl: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js',
};
```

Note: The current demo HTML files use inline configuration (model name and CDN URL are hardcoded in each HTML file). `config.js` is provided for external tools (e.g., deployment scripts) that need to modify settings programmatically.

## Important Notes

### File size limits
- GitHub Pages has a 100MB per-file limit. The WASM binary (~15MB) is well within this limit
- ONNX models are downloaded from HuggingFace at runtime, not bundled in the deployment

### HTTPS requirement
- `PiperPlus.initialize()` fetches models from HuggingFace via HTTPS
- GitHub Pages serves content over HTTPS automatically

### Cross-Origin Isolation
- `onnxruntime-web` WASM threads require `Cross-Origin-Isolation` headers (`Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp`)
- GitHub Pages does not set these headers by default, so onnxruntime-web falls back to the single-threaded `wasm` execution provider (not `wasm-threads`)

### CORS
- HuggingFace Hub API supports CORS, so model downloads work from any origin
- All static assets are served from the same origin (no CORS issues)

## Troubleshooting

1. **404 errors**: Verify that the deploy workflow's `sed` path rewriting matches the actual import paths in the HTML files
2. **Model download failures**: Check the browser console for HuggingFace API errors. The model name must match a known alias in `ModelManager` (e.g., `'tsukuyomi'`)
3. **WASM load failures**: Ensure `dist/rust-wasm/piper_plus_wasm_bg.wasm` is present in the deployment. Check the workflow's "Verify WASM output" step
4. **Slow first load**: The first visit downloads the ONNX model (~35MB). Subsequent visits use the IndexedDB cache
