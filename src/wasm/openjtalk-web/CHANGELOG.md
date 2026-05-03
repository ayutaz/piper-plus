# Changelog

All notable changes to the `piper-plus` npm package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Phoneme Timing 機能 (新規モジュール)

ブラウザ上で完全動作する phoneme timing 出力機能を追加。VITS Duration Predictor から音素ごとの timing を抽出し、リップシンク・字幕生成・カラオケアプリケーションで使用可能。

**新規モジュール:**
- `src/timing.js` — `durationsToTiming`, `timingToJson`, `timingToJsonCompact`, `timingToTsv`, `timingToSrt`, `buildPhonemeIdToTokenMap`, `DEFAULT_HOP_LENGTH`
- メインエクスポート + `./timing` サブパスエクスポート両対応

**AudioResult 拡張:**
- `timing` プロパティ (TimingResult | null、deep frozen で immutable)
- `hasTimingInfo` プロパティ (boolean)
- 後方互換: 2 引数コンストラクタ `new AudioResult(samples, sampleRate)` も動作

**PiperPlus 拡張:**
- `_infer()` の戻り値型を `Float32Array` → `{ audio: Float32Array, durations: Float32Array | null }` に変更
- `synthesize()` / `synthesizeWithVoiceCloning()` で AudioResult に timing を伝搬
- `synthesizeStreaming()` は引き続き Float32Array チャンクを返す (timing は streaming パスでは捨てられる - intentional)
- `_createTiming()`, `_getPhonemeIdToTokenMap()` 内部 helper 追加 (phoneme_id_map 逆引き、PUA 対応、length alignment)

**バリデーション:**
- `sampleRate` / `hopLength` の `NaN` / `Infinity` チェック → `TypeError`
- `phonemeTokens` 長さ不一致 → `RangeError`
- 負の duration は警告ログ付きで 0 にクランプ

**TypeScript 型定義:**
- `PhonemeTimingInfo`, `TimingResult` インターフェース
- `AudioResult` の `timing` / `hasTimingInfo` プロパティ
- 全 timing 関数の JSDoc + `@example` + `@throws` 完備

**互換性:**
- Rust/Go/C++/C#/Python と byte-for-byte 互換 (`(hop_length / sample_rate) * 1000` 計算式統一)
- 既存 `AudioResult` / `synthesize()` API は完全な後方互換

**テスト追加 (+90 件以上):**
- `test/js/test-phoneme-timing.js` (66 テスト): 計算精度、エッジケース、SRT、buildPhonemeIdToTokenMap、validation、performance
- `test/js/test-audio-result-timing.js` (18 テスト): timing プロパティ、deep freeze immutability
- `test/js/test-piper-plus-timing.js` (22 テスト): E2E 統合、length alignment、cache、streaming/voice cloning パス

**README.npm.md:**
- "Phoneme Timing for Lip-Sync & Subtitles" セクション追加
- Viseme マッピング例
- Output format リファレンス

### Tests

- 全テスト: 376 passed, 1 skipped, 0 failed (リグレッション 0 件)

## [0.4.0] - 2026-04-12

### Breaking Changes

- **@piper-plus/g2p dependency**: Updated from `^0.2.0` to `^0.3.0`. The `@piper-plus/g2p` package removed `voiceData` from its API (see `@piper-plus/g2p` CHANGELOG for details).

### Changed

- Bumped `@piper-plus/g2p` dependency to `^0.3.0`

## [0.3.1] - 2026-04-08

### Changed

- Documentation: README.md でのバージョン表記を npm 公開状況に合わせて更新 (#330)
- 内部依存関係の minor 整理 (テストランナーは 376 passed を維持)

### Fixed

- パッケージ構成の軽微な修正 (npm publish 後の patch バージョン)

## [0.3.0] - 2026-04-07

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

[0.1.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.1.0
[0.1.1]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.1.1
[0.3.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.3.0
[0.3.1]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.3.1
[0.4.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.4.0
