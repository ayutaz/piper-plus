# Piper Documentation

Welcome to the Piper documentation. This directory contains detailed guides and references for using Piper.

## Available Documentation

### Getting Started
- [OpenJTalk Windows Guide](openjtalk-windows.md) - How to use Japanese TTS on Windows
- [Environment Variables Reference](environment-variables.md) - Complete list of configuration options
- [Troubleshooting Guide](troubleshooting.md) - Solutions to common problems

### Japanese Language Support
- [Japanese Usage Guide](../JAPANESE_USAGE.md) - Comprehensive Japanese TTS guide
- [Phoneme Mapping](../PHONEME_MAPPING.md) - Technical details on Japanese phoneme handling

### Quick Links

#### For Windows Users
Start with the [OpenJTalk Windows Guide](openjtalk-windows.md) to set up Japanese text-to-speech on Windows.

#### Environment Configuration
See [Environment Variables Reference](environment-variables.md) for all available configuration options.

#### Having Issues?
Check the [Troubleshooting Guide](troubleshooting.md) for solutions to common problems.

## Key Features

### Auto-Download Support
Piper can automatically download required files:
- OpenJTalk dictionary (~10MB)
- HTS voice files (~2MB)

No manual setup required for most users!

### Cross-Platform
- Windows (x64) - Full OpenJTalk support
- macOS (x64, arm64) - Full OpenJTalk support  
- Linux (amd64) - Full OpenJTalk support
- Linux (arm64) - Coming soon

### Offline Mode
After initial setup, Piper works completely offline. Set `PIPER_OFFLINE_MODE=1` to prevent any network access.

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