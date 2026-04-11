# Changelog

All notable changes to the `piper-plus` npm package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-04-11

### Breaking Changes

- **@piper-plus/g2p dependency**: Updated from `^0.2.0` to `^0.3.0`. The `@piper-plus/g2p` package removed `voiceData` from its API (see `@piper-plus/g2p` CHANGELOG for details).

### Changed

- Bumped `@piper-plus/g2p` dependency to `^0.3.0`

## [0.3.0] - 2026-04-11

### Breaking Changes

- **WASM ABI**: `_openjtalk_initialize()` now takes 1 parameter (dictionary path only). The voice path parameter has been removed.
- **HTS voice dependency removed**: `.htsvoice` files are no longer downloaded, cached, or referenced. The phonemization pipeline operates in dictionary-only mode.

### Removed

- HTS voice file support: all voice-related download, caching, and initialization logic
- `voice` parameter from `_openjtalk_initialize()` WASM export
- Voice file checks in `verify-build.sh`

### Added

- Build verification checks: voice file absence check, WASM binary size regression check
- Contract tests verifying voice-free initialization

## [0.2.0] - 2026-04-02

### Changed

- Phonemization backend: Emscripten OpenJTalk C WASM replaced with Rust jpreprocess WASM (wasm-bindgen)
- Dictionary delivery: separate download (~20MB tar.gz) replaced with WASM-bundled NAIST-JDIC (~19MB gzip total)
- IndexedDB usage: ~103MB (dictionary cache) reduced to 0 (models only via ModelManager)
- Initialization time: 3-5s (fetch + decompress + IndexedDB + Emscripten FS) reduced to 0.3-1s (single WASM load)
- `SimpleUnifiedPhonemizer.initialize()` now accepts `PhonemizerInitConfig` with `configJson` (model config.json string)
- WASM loading uses `WebAssembly.compileStreaming()` with automatic `arrayBuffer` fallback for older browsers
- Phoneme IDs returned as `Int32Array` (was `BigInt64Array` internally in Rust; downcast to i32 for JS ergonomics)

### Added

- `WasmPhonemizer` class: low-level Rust WASM phonemizer with bundled dictionary, exposed via wasm-bindgen
- `WasmPhonemizeResult` type: structured result with `phoneme_ids` (Int32Array), `prosody_features` (Int32Array), `phoneme_count`
- Structured error code: `WASM_RUNTIME_ERROR` (.code property on Error) for WebAssembly runtime errors
- WASM error boundary: `_callWasm()` wrapper converts `WebAssembly.RuntimeError` into tagged JS errors
- Input validation: 100K character limit enforced before WASM invocation
- Initialization race condition protection: concurrent `initialize()` calls share a single promise
- 30-second WASM initialization timeout with clear error message
- `console_error_panic_hook` integration: Rust panics display full stack traces in browser console
- Language hint parameter on `WasmPhonemizer.phonemize()`: logs `console.warn` when auto-detection disagrees
- `WasmPhonemizer.detect_language()`: language auto-detection via Rust
- `WasmPhonemizer.get_supported_languages()`: returns languages from model's `language_id_map`
- `get_api_version()`: returns WASM module version (from Cargo.toml at build time)
- Per-language Cargo feature gates: build JA-only or any subset (`--no-default-features --features ja`)
- wasm-bindgen-test suite (16 tests) for Rust WASM module
- Feature flag CI: 4 feature combinations tested in `.github/workflows/wasm-build.yml`
- `[profile.wasm-release]` in workspace Cargo.toml: `opt-level = 'z'`, LTO, single codegen unit, panic = abort, strip

### Removed

- `DictManager` class and all dictionary download/cache logic (dict-manager.js)
- `japanese_phoneme_extract.js` — JS-side fullcontext label parsing (now handled by Rust)
- eSpeak-ng integration: `ESpeakPhonemeExtractor`, `espeak_phonemizer`, `unified_api.js`
- OpenJTalk C WASM files: `dist/openjtalk.js`, `dist/openjtalk.wasm`, `dist/load-dictionary.js`
- Legacy wrapper: `openjtalk_wrapper.js`, `api.js` (ccall-based)
- DictManager test files and helpers (`test-dict-manager*.js`, `dict-mock.js`)
- SHA-256 dictionary verification logic
- Emscripten virtual filesystem (FS) dictionary/voice file management
- HTS voice file download and caching (voice no longer needed for phonemization)

### Fixed

- Question marker phonemization: `?` (general), `?!` (emphatic), `?.` (declarative), `?~` (confirmation) now correctly mapped via Rust `get_question_type()` (v0.1.x always mapped to declarative `$`)
- PUA character mapping: complete 96-entry coverage including U+E016-E018 (question markers) that were missing in v0.1.x
- Prosody feature extraction: A1/A2/A3 values from fullcontext labels now returned alongside phoneme IDs via Rust `labels_to_tokens_with_prosody()`
- Non-JA language phoneme ID double-mapping bug

## [0.1.1] - 2026-03-01

### Added

- Initial public release with Emscripten OpenJTalk WASM
- Japanese phonemization via OpenJTalk C compiled to Emscripten WASM
- English phonemization via SimpleEnglishPhonemizer (rule-based)
- Character-based fallback for zh, ko, es, fr, pt, sv
- DictManager: dictionary download with SHA-256 verification, gzip decompression, IndexedDB caching
- PiperPlus high-level API: initialize, synthesize, dispose
- AudioResult: play, toBlob, toWav, download
- ModelManager: HuggingFace model download with IndexedDB caching
- WebGPU session manager with WASM fallback
- Streaming synthesis pipeline
- TypeScript type definitions

[0.3.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.3.0
[0.4.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.4.0
