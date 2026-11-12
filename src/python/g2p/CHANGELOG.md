# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `normalize_cjk_punctuation_for_latin`, which `MultilingualPhonemizer`
  applies to en/es/fr/pt/sv segments so the English G2P no longer deletes
  `，` and joins the words around it (`Hello，world`). The rules are in
  `docs/spec/cjk-punctuation-contract.toml`.

### Changed

- `UnicodeLanguageDetector.detect_char` returns `None` for CJK punctuation
  and fullwidth ASCII symbols (U+3000-303F, U+FF00-FF20, U+FF3B-FF40,
  U+FF5B-FF64, U+FFE0-FFEF) instead of `"ja"`, so `MultilingualPhonemizer`
  keeps them in the segment around them: a Chinese sentence keeps its
  `，` and `。`, and `你好，GPS` reads GPS in Mandarin (#823).

### Fixed

- Control characters are stripped by one rule, shared with the other
  runtimes: `\n`, `\t` and `\r` stay; VT, FF and NEL (U+000B, U+000C,
  U+0085) become a space, because they separate words; DEL, the other C0
  and the C1 characters (U+0080-009F) are removed. One of them inside a
  word used to break the reading in ja / en / sv: an accent phrase split, a
  lost stress, a word read as two (#934). #934 removed VT / FF / NEL too,
  which joined the words around them.
- Every language strips control characters before phonemizing, through
  both `phonemize` and `phonemize_with_prosody`. Until now only ja and en
  (and the `phonemize` of sv) did: zh, ko, es, fr, pt, pt-PT, the
  `phonemize_with_prosody` of sv, `ChinesePhonemizer.phonemize_embedded_english`
  and `MultilingualPhonemizer` passed them through, and a NUL inside
  `hola` made es / fr / pt read two words. The new
  `Phonemizer._strip_control_chars` sets no length limit; the
  10000-character limit of `_sanitize_input` stays where it was (ja, en,
  the `phonemize` of sv), so callers that pass whole texts, such as
  `piper_plus.PiperPlus.synthesize`, are not rejected. A non-`str`
  argument raises `TypeError` in every language.
- `JapanesePhonemizer` applies the custom dictionary after stripping, so an
  entry matches a word that had a control character inside it.
- The rule is now a cross-runtime contract,
  `docs/spec/input-sanitize-contract.toml`, and
  `tests/test_input_contract.py` runs the shared cases of
  `tests/fixtures/g2p/input_sanitize_cases.json` for every registered
  language.

### Security

- The `en` and `all` extras require `nltk>=3.10.4` instead of
  `nltk>=3.10.0`, which leaves GHSA-8mgp-746c-j5xp / CVE-2026-81726
  (model-artifact APIs bypass pathsec, affected `<= 3.10.3`). English
  output is unchanged.

## [0.3.1] - 2026-10-16

### Fixed

- Replace the external g2p-en/Distance dependency with the reviewed private
  English backend, retaining the Apache-2.0/MIT notices and pronunciation.
- Require installed-wheel license, frozen pronunciation and public-model
  synthesis gates before publication; recheck the exact upload wheel's
  version, dependencies, bundled weights and notices.

## [0.3.0] - 2026-10-06

### Added

- Include third-party license notices in the wheel and verify wheel metadata, dictionaries, and notices before publication.

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

[Unreleased]: https://github.com/ayutaz/piper-plus/compare/python-g2p-v0.3.1...HEAD
[0.3.1]: https://github.com/ayutaz/piper-plus/releases/tag/python-g2p-v0.3.1
[0.3.0]: https://github.com/ayutaz/piper-plus/releases/tag/python-g2p-v0.3.0
