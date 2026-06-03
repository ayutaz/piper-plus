# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **ZH-EN code-switching (Issue #384)**: English acronyms and loanwords
  inside a Chinese context are now phonemised as Mandarin pinyin instead
  of US English. `ChinesePhonemizer.phonemize_embedded_english()` and
  the bundled `data/zh_en_loanword.json` (65 acronyms, 40 loanwords,
  full A-Z letter fallback) drive the conversion. `MultilingualPhonemizer`
  detects ``[zh, en, zh]`` / ``[zh, en]`` / ``[en, zh]`` patterns and
  dispatches automatically. Custom overrides via the new
  `zh_en_loanword_dict_paths` constructor argument.

### Fixed

- **Swedish (sv) per-word language detection (Issue #539)**: Swedish words
  containing `å`/`ä`/`ö` (e.g. `så`, `och`, `för`, `är`) were misdetected
  as English. Per-word Swedish LID is restored and unified across all
  runtimes with a **conservative policy**: strong indicators are `å`/`Å`
  or an exact match in a 46-word function-word list; `ä`/`ö` alone are NOT
  sufficient (shared with German/Finnish/loanwords). The detector loads the
  bundled `data/sv_function_words.json`, byte-identical to every runtime
  mirror and enforced by a new sync gate
  (`scripts/check_swedish_lid_consistency.py`). Regression history: #297
  added per-word sv LID to all runtimes; #300's package extraction silently
  dropped it from Python/Rust.

## [0.1.0] - 2026-04-01

### Added

#### Languages
- 7 languages: JA (pyopenjtalk), EN (g2p-en), ZH (pypinyin), KO (g2pk2), ES, FR, PT (rule-based)
- All dependencies are GPL-free (MIT / Apache-2.0 / BSD-3-Clause)

#### Core API
- `Phonemizer` ABC with IPA-first design: `phonemize()` returns clean IPA tokens, encoding is a separate step
- `phonemize_with_prosody()` for languages that support prosody features (e.g., Japanese A1/A2/A3)
- `PhonemizerRegistry` with auto-discovery and `entry_points` plugin support for third-party phonemizer extensions
- `MultilingualPhonemizer` with Unicode-based language detection (`UnicodeLanguageDetector`)
- Composite language code support (e.g., `"ja-en-zh"`) for multilingual models

#### Encoding
- `PiperEncoder` for phoneme ID encoding compatible with Piper TTS models
- PUA mapping (87 entries) as canonical `pua.json` shared with C#/Rust implementations
- `phoneme_id_map` loading with BOS/EOS/padding token handling

#### Dictionaries
- `CustomDictionary` with JSON v1.0/v2.0 format support (compatible with C++/Rust implementations)

#### Safety
- Input sanitization: `MAX_INPUT_LENGTH=10000` limit and control character stripping

#### Testing & CI
- 170+ test cases
- GitHub Actions CI (3 OS x 2 Python)

### Architecture
- IPA-first: `phonemize()` returns clean IPA tokens; encoding to integer IDs is handled separately by `PiperEncoder`
- GPL-free: no eSpeak-ng dependency; all runtime dependencies are MIT/Apache-2.0/BSD-3-Clause
- Plugin system via setuptools `entry_points` (`piper_plus_g2p.phonemizers` group)
