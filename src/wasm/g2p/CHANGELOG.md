# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-11

### Breaking Changes

- **JapaneseG2P**: `voiceData` is no longer required or accepted in `jaDict`. Pass `{ dictFiles }` only (matching `DictLoader.loadJaDict()` return value). Legacy `{ dictData }` is still accepted for backward compatibility.
- **DictLoader**: `includeVoice` and `voiceUrl` options removed from `loadJaDict()`. Return value no longer includes `voiceData`.
- **TypeScript types**: `voiceData` removed from `JaDictData`, `includeVoice`/`voiceUrl` removed from `DictLoadOptions`.
- **WASM ABI**: `_openjtalk_initialize()` now takes 1 parameter (dict path only), not 2.

### Removed

- HTS voice file dependency: `.htsvoice` files are no longer downloaded, cached, or referenced.
- `DEFAULT_VOICE_URL`, `VOICE_CACHE_KEY` constants from `dict-loader.js`.
- Voice-related validation in `JapaneseG2P._loadDict()`.

### Added

- Contract tests verifying voice-free initialization (`test-g2p-contract.js`).

## [0.2.0] - 2026-04-07

### Changed

- Published to npm as `@piper-plus/g2p` under `@piper-plus` Organization
- Korean G2P and Swedish G2P added

## [0.1.0] - 2026-04-01

### Added

- Initial release of `@piper-plus/g2p`
- IPA-first G2P API: `phonemize()` returns IPA token arrays (no PUA encoding)
- Japanese G2P via OpenJTalk WASM with prosody features (A1/A2/A3)
- English G2P with CMU-style rule-based conversion
- Chinese G2P with pinyin-based phonemization
- Spanish, French, Portuguese G2P (rule-based, zero external dependencies)
- `UnicodeLanguageDetector` for automatic language detection
- `Encoder` for Piper TTS-compatible phoneme ID encoding
- `CustomDictionary` for user-defined pronunciation overrides (JSON v1.0/v2.0)
- `DictLoader` for OpenJTalk dictionary management (download + IndexedDB cache)
- Per-language subpath exports (`@piper-plus/g2p/ja`, `@piper-plus/g2p/en`, etc.)

[0.1.0]: https://github.com/ayutaz/piper-plus/releases/tag/g2p-v0.1.0
[0.2.0]: https://github.com/ayutaz/piper-plus/releases/tag/g2p-v0.2.0
[0.3.0]: https://github.com/ayutaz/piper-plus/releases/tag/g2p-v0.3.0
