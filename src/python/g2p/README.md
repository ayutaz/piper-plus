# piper-plus-g2p

Multilingual G2P (Grapheme-to-Phoneme) for TTS. eSpeak-ng free. MIT licensed. 8 languages.

**Standalone package** — piper-plus TTS エンジンなしで G2P 単体として利用可能です。任意の TTS エンジンと組み合わせて使えます。

## Why piper-plus-g2p?

- **MIT licensed** -- no eSpeak-ng (GPL) dependency in your TTS pipeline
- **8 languages** -- JA, EN, ZH, KO, ES, FR, PT, SV with consistent IPA output
- **IPA-first design** -- returns pure IPA token sequences, ready for any TTS model

## Comparison

| | piper-plus-g2p | phonemizer | gruut | Misaki |
|---|---|---|---|---|
| License | MIT | GPL (eSpeak-ng) | MIT | Apache-2.0 |
| Languages | 8 | 100+ | 20+ | EN only |
| eSpeak-ng required | No | Yes | No | No |
| IPA output | Yes | Yes | Yes | Yes |

## Installation

```bash
pip install piper-plus-g2p               # Rule-based languages (ES, FR, PT, SV)
pip install piper-plus-g2p[ja,en]        # Japanese + English
pip install piper-plus-g2p[all]          # All 8 languages
```

> **Note:** The `ja` extra requires `pyopenjtalk-plus`, which provides pre-built wheels for Linux, macOS, and Windows. See [pyopenjtalk-plus](https://pypi.org/project/pyopenjtalk-plus/) for platform details.

## Quick Start

```python
from piper_plus_g2p import get_phonemizer

ja = get_phonemizer("ja")
ja.phonemize("こんにちは")
# -> ["k", "o", "[", "N_n", "n", "i", "ch", "i", "w", "a"]

en = get_phonemizer("en")
en.phonemize("Hello world")
# -> ["h", "ə", "l", "ˈ", "o", "ʊ", " ", "w", "ˈ", "ɜ", "ː", "l", "d"]
```

## Supported Languages

| Language | Code | Extra | Backend | Notes |
|---|---|---|---|---|
| Japanese | `ja` | `piper-plus-g2p[ja]` | pyopenjtalk-plus | Context-dependent N variants, prosody info |
| English | `en` | `piper-plus-g2p[en]` | g2p-en | CMU-dict + neural fallback |
| Chinese | `zh` | `piper-plus-g2p[zh]` | pypinyin | Pinyin-to-IPA conversion |
| Korean | `ko` | `piper-plus-g2p[ko]` | g2pk2 | Optional dependency |
| Spanish | `es` | -- | Rule-based | No external dependency |
| French | `fr` | -- | Rule-based | No external dependency |
| Portuguese | `pt` | -- | Rule-based | No external dependency |
| Swedish | `sv` | -- | Rule-based | No external dependency |

## Advanced Usage

### Multilingual (Composite Language Code)

Pass a hyphen-joined code like `"ja-en-zh"` to `get_phonemizer` to
automatically create a `MultilingualPhonemizer`. Language detection is
Unicode-based, so mixed-script text is handled without explicit tagging.

```python
from piper_plus_g2p import get_phonemizer

multi = get_phonemizer("ja-en-zh")
tokens = multi.phonemize("こんにちは Hello 你好")
```

### PiperEncoder

Converts IPA token lists into integer `phoneme_ids` for Piper ONNX models.

```python
from piper_plus_g2p.encode import PiperEncoder, get_phoneme_id_map

id_map = get_phoneme_id_map("ja")
encoder = PiperEncoder(id_map)
phoneme_ids = encoder.encode(["k", "o", "[", "N_n", "n", "i", "ch", "i", "w", "a"])
```

## Piper Model Compatibility

piper-plus-g2p produces phoneme tokens directly compatible with
[Piper TTS](https://github.com/rhasspy/piper) ONNX models. Use
`PiperEncoder` with the model's `phoneme_id_map` from `config.json`:

```python
import json
from piper_plus_g2p import get_phonemizer
from piper_plus_g2p.encode import PiperEncoder

with open("model/config.json") as f:
    config = json.load(f)

encoder = PiperEncoder(config["phoneme_id_map"])
phonemizer = get_phonemizer("ja")
tokens = phonemizer.phonemize("こんにちは")
phoneme_ids = encoder.encode(tokens)
# -> ready for ONNX inference
```

Use `strict=True` to raise errors on unknown tokens instead of silently
skipping them:

```python
encoder = PiperEncoder(config["phoneme_id_map"], strict=True)
```

## Cross-Platform Consistency

piper-plus-g2p is also available as:
- **Rust crate**: `piper-plus-g2p` on crates.io
- **Go module**: `github.com/ayutaz/piper-plus/src/go/phonemize`
- **npm package**: `@piper-plus/g2p` for browser/WASM

All three implementations share the same PUA mapping table and are
validated against a common test fixture.

## Requirements

- Python >= 3.11
- Language backends are installed via extras (see [Supported Languages](#supported-languages))

## License

MIT
