# Browser Compatibility Tests for Piper WebAssembly

This directory contains automated browser compatibility tests using Playwright.

## Setup

```bash
npm install
npm run install  # Install Playwright browsers
```

## Running Tests

### All browsers
```bash
npm test
```

### Specific browser
```bash
npm run test:chrome
npm run test:firefox
npm run test:safari
```

### With UI (headed mode)
```bash
npm run test:headed
```

### Debug mode
```bash
npm run test:debug
```

## Test Categories

1. **Basic Functionality** (`basic-functionality.spec.ts`)
   - WebAssembly support
   - SIMD detection
   - SharedArrayBuffer availability
   - Web Audio API
   - WebGL support
   - Module loading

2. **Browser-Specific** (`browser-specific.spec.ts`)
   - Chrome: WebGPU, memory API, OffscreenCanvas
   - Firefox: SAB handling, WASM streaming
   - Safari: Audio autoplay policy, memory limits, CORS
   - Edge: Chromium compatibility

3. **TTS Integration** (`tts-integration.spec.ts`)
   - Full TTS pipeline
   - Streaming synthesis
   - Error handling
   - Performance comparison

## Test Results

Results are saved in:
- `playwright-report/` - HTML report
- `test-results/` - JSON results
- Console output - Detailed logs

## Viewing Results

```bash
npm run report
```

## CI Integration

Tests run automatically on CI with:
- Chrome (stable)
- Firefox (stable)
- Safari (WebKit)
- Edge

## Browser Requirements

- Chrome 91+ (SIMD support)
- Firefox 89+ (SIMD support)
- Safari 15+ (Basic support)
- Edge 91+ (Chromium-based)

## Known Issues

1. **Safari**:
   - Requires user interaction for audio playback
   - No SharedArrayBuffer without COOP/COEP headers
   - Limited WebGL extensions

2. **Firefox**:
   - Requires proper COOP/COEP headers for SAB
   - WASM streaming requires correct MIME type

3. **All browsers**:
   - Large WASM modules may take time to load
   - Memory usage varies by browser
   - WebGPU is experimental (Chrome only)