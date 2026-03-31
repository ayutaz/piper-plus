# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-31

### Added
- 7 languages: JA, EN, ZH, KO, ES, FR, PT
- `Phonemizer` ABC with `phonemize()` and `phonemize_with_prosody()`
- `PiperEncoder` for Piper TTS phoneme_ids generation
- `MultilingualPhonemizer` with `UnicodeLanguageDetector`
- `CustomDictionary` (JSON v1.0/v2.0)
- PUA mapping table (87 entries) loaded from shared `pua.json`
- `PhonemizerRegistry` with entry_points plugin discovery
- 122 tests
- GitHub Actions CI (3 OS x 2 Python)
