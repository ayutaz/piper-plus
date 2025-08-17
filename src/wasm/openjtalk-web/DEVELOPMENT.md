# OpenJTalk WebAssembly Development Guide

## Current Status

### ✅ Completed
- Project structure setup
- wasm_open_jtalk source analysis
- Docker build environment
- Browser-compatible Emscripten flags
- JavaScript API (OpenJTalkWeb class)
- Demo HTML page
- Development server

### 🚧 In Progress
- Building the actual WASM module
- Dictionary file handling
- Testing in browser

### 📋 TODO
- Dictionary compression and extraction
- Voice file optimization
- Memory usage profiling
- Performance optimization
- Web Worker integration
- Piper ONNX Runtime integration

## Architecture

### Build Process
1. **HTS Engine API** - Built with Emscripten
2. **OpenJTalk** - Built with Emscripten, linked with HTS Engine
3. **C++ Wrapper** - Exposes C functions for JavaScript
4. **WebAssembly Module** - Final output with browser-compatible settings

### Key Differences from wasm_open_jtalk
- **Environment**: `web,worker` instead of `node`
- **File System**: Browser virtual FS instead of Node.js FS
- **Module Format**: ES6 module with Promise-based initialization
- **API Design**: Class-based API for better browser integration

## Known Issues

### Dictionary Loading
The original wasm_open_jtalk uses Node.js file system. We need to:
1. Extract dictionary files from the archive
2. Load them into Emscripten's virtual file system
3. Handle this asynchronously in the browser

### Memory Usage
- Initial memory: 256MB
- Maximum memory: 512MB
- Need to profile actual usage and optimize

### Browser Compatibility
- Primary target: Chrome/Edge (Chromium-based)
- Future: Firefox, Safari
- Required features: WebAssembly, Fetch API, ES6 Modules

## Testing

### Local Testing
```bash
# 1. Prepare assets
./prepare-assets.sh

# 2. Build (requires Emscripten)
./build-local.sh

# 3. Start server
cd demo
python3 server.py

# 4. Open http://localhost:8080/
```

### Docker Testing
```bash
# Build with Docker
docker build -t piper-openjtalk-web build/
docker run -v $(pwd):/src piper-openjtalk-web

# Then start server as above
```

## Debugging

### Check WASM Loading
```javascript
// In browser console
OpenJTalkModule().then(module => {
  console.log('Module loaded:', module);
  console.log('Exported functions:', module.asm);
});
```

### Memory Usage
```javascript
// Check memory usage
if (performance.memory) {
  console.log('JS Heap:', performance.memory.usedJSHeapSize / 1024 / 1024, 'MB');
}
```

### File System
```javascript
// Check virtual file system
module.FS.readdir('/').forEach(file => console.log(file));
```

## Performance Considerations

### Optimization Strategies
1. **Lazy Loading**: Load dictionary on demand
2. **Compression**: Use Brotli for dictionary files
3. **Caching**: IndexedDB for persistent storage
4. **Web Workers**: Offload processing from main thread

### Benchmarks
- Target: < 3s initialization
- Target: < 100ms per sentence conversion
- Memory: < 256MB steady state

## Next Steps

1. **Get basic build working**
   - Fix any compilation errors
   - Ensure WASM module loads in browser

2. **Implement dictionary loading**
   - Extract dictionary files properly
   - Load into virtual FS

3. **Test basic functionality**
   - Text to phoneme conversion
   - Verify output matches native OpenJTalk

4. **Optimize and integrate**
   - Reduce file sizes
   - Improve loading time
   - Integrate with Piper