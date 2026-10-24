# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **English is read with the CMU dictionary and g2p_en's normalization (Issue #828)**: the English G2P used a small built-in dictionary and spelling rules, so 45 English golden cases differed from Python (`brown`, `reading`, digits dropped). It now follows the Rust `EnglishPhonemizer` step by step: g2p_en's normalization (numbers, years, ordinals, `$` / `£`, decimals, accents, `i.e.` / `e.g.`, Unicode spaces, TweetTokenizer-style splitting; `src/en/normalize.js`), the CMU dictionary, the suffix fallback, splitting at `-` / `.` and CamelCase, and letter names for words nothing else reads. The dictionary (`data/cmudict_data.json`, 3.7 MB, byte-equal to `src/rust/piper-plus-g2p/data/`) is loaded lazily: `G2P.create()` awaits it only when `en` is enabled, Node reads it synchronously on first use, and in a browser the synchronous API throws until `await EnglishG2P#initialize()` (or `EnglishG2P.create()`). A dictionary can be passed as the `cmuDict` option. New exports: `loadCmuDict`, `isCmuDictLoaded`, `normalizeNumbers`, `normalizeAndTokenize`. `phonemizeWithProsody` now returns Python's English values (a2 = stress, a3 = phoneme count of the word) instead of zeros. `THIRD_PARTY_LICENSES.md` carries the CMU dictionary license. The package grows by about 0.9 MB packed (3.8 MB unpacked).
- **Chinese is read with the pinyin dictionary (Issue #829)**: the Chinese G2P passed text through character by character, so every Chinese golden case differed from Python. It now follows the Rust `ChinesePhonemizer` step by step: longest phrase match (2 to 8 characters) in `pinyin_phrases.json`, then `pinyin_single.json`, tone sandhi (third-tone runs, 一, 不), pinyin to IPA, erhua, and ZH-EN loanword reading of English next to Chinese (#384). `G2P` with language `zh` splits the text by script as Rust's `phonemize_with_language` does. The two dictionaries (2.7 MB, numeric tones, byte-equal to `src/rust/piper-plus-g2p/data/`) ship in `data/` and are loaded lazily: `G2P.create()` awaits them only when `zh` is enabled, and `new ChineseG2P()` without `initialize()` keeps the old character-by-character output. New exports: `loadPinyinDictionary`, `createPinyinDictionary`, `PinyinDictionary`, `isPinyinDictionaryLoaded`, the `pinyinDict` option, and `ChineseG2P#initialize` / `setPinyinDictionary`. `phonemizeWithProsody` now returns real tone and position values for Chinese. `data/zh_en_loanword.json` is now in `files` (it was imported but not published), and `THIRD_PARTY_LICENSES.md` carries the pypinyin MIT notice. The package grows from 78 kB to 834 kB packed (0.3 MB to 3.0 MB unpacked).
- **CJK punctuation is no longer Japanese (Issue #823)**: `UnicodeLanguageDetector` classified CJK punctuation (、。，！？「」 ...) and the fullwidth forms of ASCII symbols and digits as `ja` whenever Japanese was enabled, which split a Chinese sentence at every ， and 。 and put a Japanese segment between Chinese and an English word after a Chinese comma. These characters are now neutral and join the segment around them, as `docs/spec/cjk-punctuation-contract.toml` specifies for every runtime. Halfwidth katakana stays `ja` and fullwidth Latin letters stay Latin. `G2P` now rewrites them as ASCII (`，` → `,`, `、` → `,`, `。` → `.`, `３` → `3`, others → space) before an en / es / fr / pt / pt-PT / sv G2P sees the text, so `Hola，amigo！` reads like `Hola,amigo!` instead of losing its punctuation. The rewrite is exported as `normalizeCjkPunctuationForLatin`.

## [0.4.2] - 2026-08-28

### Fixed

- **Default Japanese dictionary download returned HTTP 404 (Issue #634)**: `DICT_TAR_GZ_URL` in `src/dict-loader.js` pointed at `ayutaz/piper-plus` release tag `dict-v1.0.0`, which does not exist. Any consumer that did not pass an explicit `dictUrl` therefore hit a 404 and Japanese G2P failed every time. The URL now matches the canonical source the Rust / C# / C++ runtimes already use (`r9y9/open_jtalk` v1.11.1); `DICT_SHA256` was already the checksum for that archive, so only the one line was wrong.
- **Package declared MIT but shipped no license text (Issue #640)**: `package.json` set `"license": "MIT"` while the published tarball contained no `LICENSE` file of any kind, which the MIT terms do not permit — the copyright and permission notice must accompany every copy. `LICENSE.md` is now included in `files`. The same change drops `dist/openjtalk.js` and `dist/openjtalk.wasm` from `files`: the Emscripten OpenJTalk build was retired in #301 and nothing has produced those artifacts since, so npm was silently discarding both entries and the tarball never contained a `dist/` directory at all.

## [0.4.1] - 2026-06-07

### Added

- **SSML public API root exports (`isSsml` / `parseSsml` / `SsmlParser`)**: these root re-exports already exist in `src/index.js`, but the registry's 0.4.0 predates them, so consumers importing from the main entry (e.g. `openjtalk-web`'s `synthesizeSsml`) hit `does not provide an export named 'isSsml'`. This 0.4.1 release ships those existing root exports to the registry (version bump only — no source / API change).

### Fixed

- **Swedish (sv) per-word language detection (Issue #539)**: Swedish words containing `å`/`ä`/`ö` (e.g. `så`, `och`, `för`, `är`) were misdetected as English. The Swedish LID is reworked from the previous char-level approach to a word-level post-pass with a **conservative policy** (strong indicators: `å`/`Å` or an exact match in a 46-word function-word list; `ä`/`ö` alone are NOT sufficient — shared with German/Finnish/loanwords). `UnicodeLanguageDetector` now loads the bundled `data/sv_function_words.json`, byte-identical to every other runtime mirror and enforced by a new cross-runtime sync gate.

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
