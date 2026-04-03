# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-01

### Added

- Initial release of `@piper-plus/g2p`
- IPA-first G2P API: `phonemize()` returns IPA token arrays (no PUA encoding)
- Japanese G2P via OpenJTalk WASM with prosody features (A1/A2/A3)
- English G2P with CMU-style rule-based conversion
- Chinese G2P with pinyin-based phonemization
- Spanish, French, Portuguese G2P (rule-based, zero external dependencies)
- `UnicodeLanguageDetector` for automatic language detection
- `PiperEncoder` for Piper TTS-compatible phoneme ID encoding
- `CustomDictionary` for user-defined pronunciation overrides (JSON v1.0/v2.0)
- `DictLoader` for OpenJTalk dictionary management (download + IndexedDB cache)
- Per-language subpath exports (`@piper-plus/g2p/ja`, `@piper-plus/g2p/en`, etc.)

[0.1.0]: https://github.com/ayutaz/piper-plus/releases/tag/g2p-v0.1.0
