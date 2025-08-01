# OpenJTalk WebAssembly

Browser-based Japanese text-to-speech synthesis using OpenJTalk and Piper ONNX models.

## 🚀 Live Demo

Visit the live demo: [https://ayutaz.github.io/piper-plus/](https://ayutaz.github.io/piper-plus/)

## 📋 Features

- **Pure Browser-Based**: Runs entirely in the browser without server dependencies
- **Japanese TTS**: High-quality Japanese speech synthesis using OpenJTalk phonemization
- **ONNX Runtime**: Neural synthesis using Piper ONNX models
- **Compact Size**: WASM < 400KB, JS < 40KB
- **Cross-Platform**: Works on desktop and mobile browsers

## 🛠️ Development

### Prerequisites

- Node.js 18+
- Emscripten 3.1.47
- CMake 3.10+
- Python 3.8+ (for build scripts)

### Building

```bash
# Clone the repository
git clone https://github.com/rhasspy/piper.git
cd piper/src/wasm/openjtalk-web

# Build for production
npm run build

# Build for development (with debug symbols)
npm run build:debug
```

### Testing

```bash
# Run unit tests
npm test

# Run tests in watch mode
npm run test:watch
```

### Local Development

```bash
# Start local HTTP server
npm run serve

# Open browser at http://localhost:8081/test/production-audio-test.html
```

## 📦 Project Structure

```
openjtalk-web/
├── assets/           # Dictionary and voice files
│   ├── dict/        # NAIST Japanese Dictionary
│   └── voice/       # HTS voice (for initialization)
├── build/           # Build scripts
│   ├── build-production.sh
│   └── build-safe.sh (debug)
├── dist/            # Build output
│   ├── openjtalk.js
│   └── openjtalk.wasm
├── models/          # ONNX models
├── src/             # C source files
│   └── openjtalk_safe.c
└── test/            # Test files
    ├── production-audio-test.html
    └── js/
        ├── openjtalk-piper-integration.js
        └── test-openjtalk-integration.js
```

## 🔧 API Usage

```javascript
import OpenJTalkPiperTTS from './openjtalk-piper-integration.js';

// Initialize TTS
const tts = new OpenJTalkPiperTTS();
await tts.initialize({
    openjtalk: {
        jsPath: 'dist/openjtalk.js',
        wasmPath: 'dist/openjtalk.wasm',
        dictPath: 'assets/dict',
        voicePath: 'assets/voice/mei_normal.htsvoice'
    },
    onnx: {
        modelPath: 'models/ja_JP-test-medium.onnx',
        modelConfigPath: 'models/ja_JP-test-medium.onnx.json'
    }
});

// Generate speech
const audioData = await tts.textToSpeech('こんにちは、世界！');

// Create WAV file
const wavBlob = tts.createWAV(audioData, 22050);
const audioUrl = URL.createObjectURL(wavBlob);

// Play audio
const audio = new Audio(audioUrl);
audio.play();
```

## 🚀 Deployment

### GitHub Pages

The project includes automated deployment to GitHub Pages:

1. **Automatic deployment**: Push to `dev` branch triggers deployment
2. **Manual deployment**: Use GitHub Actions workflow dispatch

```bash
# Push to dev branch for automatic deployment
git push origin dev

# Or trigger manual deployment from GitHub Actions UI
```

### Self-Hosting

To host on your own server:

1. Build the project: `npm run build`
2. Copy these directories to your web server:
   - `dist/`
   - `assets/`
   - `models/`
   - `test/` (for demo pages)
3. Ensure your server has proper CORS headers for WASM files

## 📄 License

This project is part of Piper TTS and follows the same license terms.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Run tests: `npm test`
4. Submit a pull request

## 🐛 Known Issues

- Some browsers may require user interaction before playing audio
- iOS Safari requires specific handling for Web Audio API
- Large models may take time to load on slower connections

## 📚 References

- [OpenJTalk](http://open-jtalk.sourceforge.net/)
- [Piper TTS](https://github.com/rhasspy/piper)
- [ONNX Runtime Web](https://onnxruntime.ai/docs/get-started/with-javascript.html)
- [Emscripten](https://emscripten.org/)