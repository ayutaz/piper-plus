# piper-phonemize (Piper-Plus Edition)

Cross-platform Python package for text phonemization with bundled espeak-ng, designed for piper-plus.

## Features

- **Cross-platform**: Pre-built wheels for Windows, macOS (Intel/Apple Silicon), and Linux (x64/ARM64)
- **Python 3.11+ support**: Works with Python 3.11, 3.12, and 3.13
- **Bundled dependencies**: Includes espeak-ng and ONNX Runtime - no system dependencies required
- **Easy installation**: Simple pip install with no compilation needed
- **API compatible**: Drop-in replacement for piper-phonemize

## Installation

```bash
pip install piper-phonemize
```

## Usage

```python
import piper_phonemize

# Simple phonemization
phonemes = piper_phonemize.phonemize_espeak("Hello world", "en-us")
print(phonemes)
# Output: ['h', 'ə', 'l', 'oʊ', ' ', 'w', 'ɜː', 'l', 'd']

# Get phoneme IDs for neural TTS
ids = piper_phonemize.phoneme_ids_espeak(phonemes)
print(ids)
# Output: [104, 601, 108, 111, 32, 119, 604, 108, 100]

# High-level API
phonemes, ids = piper_phonemize.phonemize(
    "Hello world",
    language="en-us",
    return_phonemes=True,
    return_ids=True
)
```

## Supported Languages

Supports all espeak-ng languages including:
- English (en-us, en-gb)
- German (de)
- French (fr)
- Spanish (es)
- Italian (it)
- Dutch (nl)
- Russian (ru)
- Chinese (cmn)
- Japanese (ja) - requires external OpenJTalk
- And many more...

## Platform Support

| Platform | Architecture | Python Versions |
|----------|-------------|----------------|
| Windows | x64 | 3.11, 3.12, 3.13 |
| macOS | x86_64, arm64, universal2 | 3.11, 3.12, 3.13 |
| Linux | x86_64, aarch64 | 3.11, 3.12, 3.13 |

## Building from Source

If you need to build from source:

```bash
# Clone the repository
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus/src/piper_phonemize_bundled

# Install build dependencies
pip install pybind11 cmake build

# Build dependencies
python build_dependencies.py

# Build the package
python -m build
```

## Development

For development, install in editable mode:

```bash
pip install -e .[dev]
```

Run tests:

```bash
pytest tests/
```

## License

MIT License - see the main piper-plus repository for details.

## Credits

Based on [piper-phonemize](https://github.com/rhasspy/piper-phonemize) by Michael Hansen.
Bundled version created for [piper-plus](https://github.com/ayutaz/piper-plus) project.
