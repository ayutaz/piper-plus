# piper-g2p

Multilingual G2P (Grapheme-to-Phoneme) for TTS — eSpeak-ng free, MIT licensed.

## Installation

```bash
pip install piper-g2p[ja,en]
```

## Usage

```python
from piper_g2p import get_phonemizer

ja = get_phonemizer("ja")
tokens = ja.phonemize("こんにちは")
# -> ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]

en = get_phonemizer("en")
tokens = en.phonemize("Hello world")
# -> ["h", "ʌ", "ˈ", "l", "oʊ", " ", "ˈ", "w", "ɜː", "l", "d"]
```

## License

MIT
