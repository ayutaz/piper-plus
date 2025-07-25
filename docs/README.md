# Piper Documentation

Welcome to the Piper documentation. This directory contains detailed guides and references for using and developing with Piper TTS.

## Documentation Index

### 🚀 Getting Started
- [Quick Start Japanese](quick_start_japanese.md) - Japanese TTS quick start guide
- [Windows Setup](windows-setup.md) - Complete Windows installation guide
- [Environment Variables](environment-variables.md) - Configuration options reference
- [Troubleshooting Guide](troubleshooting.md) - Solutions to common problems

### 🎯 Core Features
- [CLI Enhancements](CLI_ENHANCEMENTS.md) - Enhanced command-line features (volume, auto-play, file input)
- [Phoneme Input Guide](PHONEME_INPUT.md) - Direct phoneme specification with `[[ ]]` notation
- [GPU Configuration](GPU_CONFIGURATION.md) - Multi-GPU support and device selection

### 🇯🇵 Japanese Language Support
- [Japanese Usage Guide](../JAPANESE_USAGE.md) - Comprehensive Japanese TTS guide
- [Complete Japanese Training Guide](COMPLETE_JAPANESE_TRAINING_GUIDE.md) - Training Japanese models
- [OpenJTalk API](openjtalk-api.md) - OpenJTalk integration details
- [OpenJTalk Windows](openjtalk-windows.md) - Windows-specific Japanese TTS setup
- [OpenJTalk ARM64 Linux](openjtalk-arm64-linux.md) - ARM64 Linux support

### 🔧 Development & Training
- [Architecture Overview](Architecture.md) - System architecture and design
- [Package Structure](PackageStructure.md) - Project organization
- [Multi-GPU Training](MULTI_GPU_TRAINING.md) - Training with multiple GPUs
- [Model Size Impact Analysis](model-size-impact-analysis-ja.md) - Model size vs quality analysis

### 🌐 Multilingual Support
- [Multilingual Testing](MULTILINGUAL_TESTING.md) - Testing multiple languages
- [Multilingual Test Results](MULTILINGUAL_TEST_RESULTS.md) - Test results and benchmarks

### 🔬 Technical Deep Dives
- [ARM64 Optimization](arm64-optimization.md) - NEON optimizations for ARM processors
- [WebAssembly Investigation](webassembly-investigation/README.md) - WebGL/WebAssembly support
- [Competitive Analysis](competitive-analysis/README.md) - Market positioning
- [License Compliance](LICENSE_COMPLIANCE.md) - Open source license information

### 🔄 Migration & Integration
- [Workflow Migration](workflow-migration.md) - CI/CD workflow migration guide
- [Unity Plugin Investigation](unity-plugin-investigation-ja.md) - Unity integration research
- [Unity Development](unity-piper-tts-*.md) - Unity TTS development docs

### 📋 Project Management
- [Phase 1 Kickoff](phase1-kickoff.md) - Project phase 1 overview
- [Phase 1 Progress](phase1-progress.md) - Development progress tracking

## Quick Start

### 🎤 Basic Usage
```bash
# English TTS
echo "Hello world" | piper --model en_US-lessac-medium.onnx --output_file hello.wav

# Japanese TTS
echo "こんにちは世界" | piper --model ja_JP-test-medium.onnx --output_file japanese.wav
```

### 🆕 New Features (v1.5.0+)

#### Volume Control & Auto-Play
```bash
# Adjust volume and auto-play
piper "Hello world" --model en_US-lessac-medium.onnx --volume 1.5 --auto-play
```

#### Phoneme Input
```bash
# Direct phoneme specification
echo "Say [[ h ə l oʊ ]] clearly" | piper --model en_US-lessac.onnx -f hello.wav
```

#### GPU Selection
```bash
# Use specific GPU device
piper "Hello" --model model.onnx --use-cuda --gpu-device-id 1 -f output.wav
```

## Key Features

### ✨ Enhanced CLI Features
- **Volume Control**: Adjust output volume (0.1-2.0)
- **Auto-Play**: Automatically play generated audio
- **File Input**: Process text files directly
- **Direct Text**: Pass text as command argument

### 🎯 Phoneme Support
- **Direct Input**: Use `[[ phonemes ]]` notation
- **Multi-Language**: Supports IPA and Japanese phonemes
- **Precise Control**: Override pronunciation for any word

### 🚀 GPU Acceleration
- **Multi-GPU**: Select specific GPU devices
- **CUDA Support**: Hardware acceleration
- **Environment Config**: Set via `PIPER_GPU_DEVICE_ID`

### 🌍 Language Support
- **30+ Languages**: Including Japanese, English, German, French, Chinese
- **Auto-Download**: Dictionary and voice files downloaded automatically
- **Offline Mode**: Works without internet after initial setup

### 📱 Platform Support
- **Windows** (x64): Full OpenJTalk support
- **macOS** (x64, arm64): Full OpenJTalk support  
- **Linux** (x64, arm64): Full OpenJTalk support
- **WebAssembly**: Experimental support

## Contributing

To improve documentation:
1. Fork the repository
2. Make your changes
3. Submit a pull request

Please ensure all documentation:
- Uses clear, simple language
- Includes practical examples
- Covers common error cases
- Is tested and accurate