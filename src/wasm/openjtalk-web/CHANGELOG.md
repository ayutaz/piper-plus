# Changelog

All notable changes to the `piper-plus` npm package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add `SpeakerEncoder.initialize({ frontEnd: "kaldi-fbank" })`, which computes the zs-v1 CAM++ embedding the same way as the Python recipe (torchaudio Kaiser resampling to 16 kHz, 80-bin `kaldi.fbank`, mean subtraction, L2 normalization). Checked against torchaudio with a golden fixture. `initialize` also accepts `modelData` in place of `modelUrl`. The default `"mel"` front end is unchanged.
- Add `PiperPlus.findDroppedSymbols(text, { language })`, which lists the symbols the phonemizer produced but the model's phoneme table lacks. Encoding still drops them silently; this lets an app warn before synthesis. It also works with `@piper-plus/g2p` 0.4.2, whose `encode()` does not report them.
- The GitHub Pages multilingual demo gains a zero-shot section: upload or record a reference clip, compute the embedding in the browser, and read text in six languages with the public zs-v1 base.

### Fixed

- `piper-plus` bin (`bin/piper-cli.js`, the Node CLI for `--json-input`): apply the same short-text handling and Issue #499 EOS-region trim as `PiperPlus.synthesize()`. The bin wrote the raw decoder output, 1,536 samples (6 frames) longer than the other runtimes for the parity fixture. The helpers moved to `src/short-text.js`; `src/index.js` re-exports them, so the public API is unchanged.
- Chinese text with digits or Latin words, for models with zh and en: read them with the English G2P instead of character by character (#847). `123` became `1 2 3` because the Rust WASM G2P had no English dictionary; it now gets the CMU dictionary of `@piper-plus/g2p` on the first Chinese request. With an `@piper-plus/g2p` that has no `loadCmuDict` (up to the 0.4.2 release on npm), a warning is logged and the old reading is kept.
- Streaming (`synthesizeStreaming`): do not end a chunk at a full stop between two digits (`3.14`) or inside `e.g.` / `i.e.` (#831). The pieces were phonemized separately and read differently from the whole sentence.
- Text with a language is phonemized by the bundled Rust WASM G2P as in Python: the text is split by script and its Latin-script parts are read as that language, so English words inside Chinese text are read in Mandarin through the ZH-EN loanword table instead of being passed to the Chinese phonemizer as raw letters. Japanese text still goes whole to OpenJTalk.
- French in the bundled Rust WASM G2P: an elision clitic (`l'` `d'` `j'` `qu'` ..., straight or typographic apostrophe) is read together with the rest of the word, so `c'est` is `s ɛ s`, and a liaison trigger (`les`, `nous`, `est`, ...) ends with its linking consonant before a word starting with a vowel or h + vowel, as in Python (#822).
- CJK punctuation (、。，！？「」 ...) and fullwidth ASCII symbols belong to no language in the bundled Rust WASM G2P (#823). A Chinese sentence in a model with `ja` lost its `，` and `。`, which were put in a Japanese segment; in a Latin-script segment they are now rewritten as ASCII before G2P.

### Security

- `model: "base"` / `"zero-shot-base-zs-v1"` now checks the downloaded `base.onnx` against its pinned SHA-256. The published `base.onnx.json` has no `sha256`, so the file was previously not verified.

## [0.8.2] - 2026-10-23

### Added

- Add `base` and `zero-shot-base-zs-v1` registry aliases for the public experimental Zero-Shot bundle at revision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1`. Resolve its nested `releases/zs-v1/base.onnx` and matching `base.onnx.json` pair with revision-isolated cache keys; this records browser download resolution and does not claim browser synthesis or quality validation.
- Check CDN delivery in CI. `npm run check:cdn` fails when the README or the demo loads a package from a CDN that refuses one of its files (jsDelivr: over 50 MB). `npm run test:real-cdn` runs the README importmap against the real CDNs and checks that Japanese audio is not cut short; it runs in required PR CI and again after `npm publish`. The browser tests now also check Japanese and Chinese audio length, cover a failed G2P WASM fetch, and fail on the WASM load-failure warning.

### Changed

- Fail loudly when the Rust WASM phonemizer cannot be loaded. `initialize()` now rejects if the model has no language other than Japanese and Chinese; otherwise `synthesize()` rejects for Japanese or Chinese text (explicit or auto-detected) instead of routing it to the JS fallback, which produced almost no audio. Other languages keep working with a warning, as before.

### Fixed

- Load `piper-plus` from unpkg in the README importmap example. jsDelivr refuses files over 50 MB, so the bundled G2P WASM (about 60 MB) returned 403 and Japanese text produced almost no audio. The browser test now also routes unpkg and fails if `piper-plus` is loaded from jsDelivr.
- Route English to the JS G2P even when the Rust WASM bundle loads for Japanese or Chinese. The WASM bundle has no English dictionary and spelled words out letter by letter.
- Regenerate the bundled `pinyin_single.json` / `pinyin_phrases.json` with numeric tones (`ni3`). The previous files carried tone marks (`nǐ`), which the WASM parser read as tone 5 with a broken final.

## [0.8.1] - 2026-10-08

### Changed

- Update the README installation and importmap examples and the demo to ONNX Runtime Web 1.30.0, the version the package is tested with; the peer dependency stays `onnxruntime-web >=1.22.0`. `npm run check:browser-runtime` fails in PR CI and pre-commit when an example or the demo drifts from that pin.

## [0.8.0] - 2026-10-06

### Changed

- Require ONNX Runtime Web >=1.22.0 for public input metadata; update the demo and README importmap accordingly.

### Fixed

- Include both Chinese pinyin dictionaries in the npm tarball; previous versions requested missing assets and silently fell back to character passthrough.
- Align phoneme timing with real audio length using ceil quantization, skip PAD/BOS/EOS, use deterministic reverse mappings, and unify subtitle millisecond rounding.
- Read speaker embedding dimensions and mask ranks from the ONNX graph instead of sending fixed 192-dimensional embeddings and rank-1 masks (#760). Reject invalid embeddings with explicit errors.

### Added

- Verify the exact packed npm distribution in a clean installation with real multilingual synthesis, README examples, and browser playback before publication and in required PR CI.
- Mandatory PR tests with tiny real ORT Web graphs on 1.22.0 and 1.30.0, plus Chromium synthesis/playback tests using pinned CSS10 and Tsukuyomi models.

## [0.7.0] - 2026-08-28

### Added

#### SSML 合成統合 (synthesize 側)

`@piper-plus/g2p` の SSML パーサーを高位 API に統合。Python/Rust/Go/C# と同等の synthesize-side iteration を WASM/JS でも提供。

**新規 API:**

- `PiperPlus.synthesizeSsml(ssmlText, options)` — SSML 入力をセグメント単位で iterate、`<prosody rate>` を `length_scale` に適用、`<break>` で silence 挿入、全 chunk を連結して `AudioResult` を返す
- `PiperPlus.synthesize(text)` が `<speak` で始まる入力を自動検知して `synthesizeSsml` に dispatch (opt-out: `{ ssml: false }`)
- 高位エクスポート: `isSsml`, `parseSsml`, `SsmlParser` (`@piper-plus/g2p` からの re-export)

**仕様:** `docs/spec/ssml-contract.toml` (`applies_to` に `"wasm"` を追加、status table を ✓ に更新)。`tests/fixtures/ssml/contract.json` と byte-for-byte 互換。

**テスト:** `test/js/test-piper-plus-ssml.js` (23 件): re-export 確認 / `synthesize()` 自動 dispatch / segment iteration / `length_scale` 適用 / silence 挿入 / fixture parity。

#### Speaker Encoder synthesize 統合 (#478)

参照音声から話者埋め込みを作り、そのまま合成に流せる高位 API をブラウザ側に追加。CLI の `--reference-audio` + `--speaker-encoder-model` に相当する経路が JS だけで完結する。

**新規 API:**

- `PiperPlus.synthesizeFromReferenceAudio({ text, referenceWav, encoder })` — 参照 WAV をエンコードし、得られた埋め込みを `synthesize()` に `speakerEmbedding` として渡す
- `synthesize(text, { speakerEmbedding })` — `SynthesizeOptions` に `speakerEmbedding` を追加
- 型: `SynthesizeFromReferenceAudioParams`

#### CLI エントリポイント

- `package.json` に `bin` を追加 (`piper-plus` → `bin/piper-cli.js`)。インストールすると `node_modules/.bin/piper-plus` が生え、グローバルインストールでは `piper-plus` コマンドが作られる
- **注意:** PyPI 版 `piper-plus` の console script と同名。両方をグローバルに入れている場合は PATH 上で衝突しうる

#### その他の公開 API 追加

- `trimEosRegion` — EOS 領域トリムを Rust / Go / C# / C++ とそろえた (#507)
- ORT ウォームアップ定数 8 種 (`WARMUP_BOS_TOKEN` / `WARMUP_EOS_TOKEN` / `WARMUP_DEFAULT_RUNS` / `WARMUP_DUMMY_PHONEME` / `WARMUP_LENGTH_SCALE` / `WARMUP_NOISE_SCALE` / `WARMUP_NOISE_W` / `WARMUP_PHONEME_LENGTH`) — `docs/spec/ort-session-contract.toml` の値をコードから参照可能に
- `RustWasmAdapter.create()` の `options.jaDict` — `ja-external` / `multilingual-external` variant 向けに外部 JA 辞書を opt-in で投入する (#640)。取得 → SHA-256 検証 → 投入の順で適用し、既定 URL は持たない
- `RustWasmAdapter#japaneseDictionaryStatus` — 上記の結果を `"not-requested"` / `"unsupported"` / `"loaded"` / `"failed"` で公開 (#640)

### Deprecated

- `PiperPlus.synthesizeWithVoiceCloning(text, speakerEmbedding, options)` — `synthesize(text, { speakerEmbedding })` に置き換え。後方互換のため残しており、削除は将来のメジャーリリースで行う (#478)

### Removed

- `exports` から `./wasm/ja` と `./wasm/ja-lite` を削除 (#640)。この 2 つは #301 で宣言されて以来どの公開版でも実体 0 ファイルで、0.6.0 の tarball でも `require.resolve` が `MODULE_NOT_FOUND` になる状態だった。依存できた利用者は存在しないため実質的な破壊的変更ではない

### Fixed

- `files` に `bin/**/*.js` を追加。これがないと `bin` で宣言した CLI が tarball に入らない (#640)

## [0.6.0] - 2026-05-04

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

[Unreleased]: https://github.com/ayutaz/piper-plus/compare/npm-v0.8.2...HEAD
[0.8.2]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.8.2
[0.8.1]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.8.1
[0.8.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.8.0
[0.7.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.7.0
[0.6.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.6.0
[0.3.1]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.3.1
[0.3.0]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.3.0
[0.1.1]: https://github.com/ayutaz/piper-plus/releases/tag/npm-v0.1.1
