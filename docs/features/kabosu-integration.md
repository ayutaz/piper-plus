# kabosu-core Integration: Enhanced Japanese Preprocessing

## Overview

Piper TTS Plus now includes enhanced Japanese text preprocessing features from [kabosu-core](https://github.com/q9uri/kabosu-core), significantly improving phonemization accuracy for Japanese text.

## Features Integrated (Phase 1)

### 1. Variant Kanji Normalization (異体字正規化)

Automatically converts variant kanji characters to their standard forms using three authoritative dictionaries:

- **jinmei-variants.txt**: Personal name kanji variants (法務省人名漢字表)
- **joyo-variants.txt**: Standard kanji variants (文科省常用漢字表)
- **non-cjk.txt**: Non-CJK/pseudo-kanji mappings

**Examples:**
```python
"齋藤" → "斎藤"
"邊" → "辺"
```

### 2. English to Katakana Conversion

Uses VOICEVOX-derived `kanalizer` library for accurate English-to-Katakana conversion:

**Examples:**
```python
"docker" → "ドッカー"
"github" → "ギットハブ"
"python" → "パイソン"
```

### 3. Half-width to Full-width Conversion

Normalizes half-width characters (半角) to full-width (全角):

**Examples:**
```python
"ｱｲｳｴｵ" → "アイウエオ"
"123" → "１２３"
```

## Installation

Install additional dependencies for enhanced preprocessing:

```bash
cd /data/piper
pip install -r requirements-train.txt
```

New dependencies added:
- `kanalizer>=0.1.1` - English to Katakana conversion
- `sudachipy>=0.6.10` - Japanese morphological analyzer (for future features)
- `sudachidict-core>=20250825` - Sudachi dictionary
- `jaconv>=0.4.0` - Japanese character conversion
- `jpreprocess>=0.1.5` - Japanese preprocessing library

## Usage

### Basic Usage

The preprocessing is **enabled by default** in `phonemize_japanese()`:

```python
from piper_train.phonemize import phonemize_japanese

# Automatically applies:
# 1. Variant kanji normalization
# 2. English→Katakana conversion
# 3. Half-width→Full-width conversion
phonemes = phonemize_japanese("齋藤さんはdockerを使います")
```

### Disable Preprocessing

If you need to disable the enhanced preprocessing:

```python
phonemes = phonemize_japanese(
    "テキスト",
    use_kabosu_preprocessing=False  # Disable kabosu-core features
)
```

### Individual Preprocessing Functions

You can also use preprocessing functions directly:

```python
from piper_train.phonemize.japanese_utils import (
    preprocess_japanese_text,
    convert_english_to_katakana,
    convert_half_to_full,
)
from piper_train.phonemize.itaiji import normalize_itaiji

# Apply all preprocessing
text = preprocess_japanese_text("齋藤さんはdockerを使います")
# Result: "斎藤さんはドッカーを使います"

# Individual functions
text = normalize_itaiji("齋藤")  # "斎藤"
text = convert_english_to_katakana("github")  # "ギットハブ"
text = convert_half_to_full("ｱｲｳｴｵ")  # "アイウエオ"

# Selective preprocessing
text = preprocess_japanese_text(
    "input",
    normalize_variants=True,   # Apply variant kanji normalization
    convert_hankaku=True,      # Convert half-width to full-width
    convert_english=False,     # Skip English conversion
)
```

## Training with Enhanced Preprocessing

When preprocessing your dataset:

```bash
python -m piper_train.preprocess \
  --language ja \
  --input-dir /path/to/wavs \
  --output-dir /path/to/dataset
```

The phonemizer will automatically use enhanced preprocessing. No additional flags needed!

## Testing

Run the test suite to verify integration:

```bash
# Run all Japanese preprocessing tests
pytest src/python/tests/test_japanese_kabosu.py -v

# Run specific test class
pytest src/python/tests/test_japanese_kabosu.py::TestVariantKanjiNormalization -v
```

## File Structure

New files added:

```
src/python/piper_train/phonemize/
├── itaiji.py              # Variant kanji normalization
├── japanese_utils.py      # Preprocessing utilities
├── japanese.py            # Updated with kabosu integration
└── dict/                  # Variant kanji dictionaries
    ├── jinmei-variants.txt
    ├── joyo-variants.txt
    └── non-cjk.txt

src/python/tests/
└── test_japanese_kabosu.py  # Integration tests
```

## Performance Impact (Phase 1)

- **Memory**: Minimal (~5MB for dictionaries)
- **Speed**: Preprocessing adds ~10-20ms per utterance
- **Accuracy**: Significant improvement for:
  - Variant kanji (rare names, historical texts)
  - Technical terms (Docker, GitHub, Python, etc.)
  - Mixed half-width/full-width text

## Phase 2: BERT-based Reading Estimation (✅ Completed)

### Overview

Phase 2 integrates `yomikata`, a BERT-based heteronym disambiguation system that determines context-appropriate readings for ambiguous kanji.

### Features

**Context-aware Reading Disambiguation:**
- Analyzes entire sentence context using BERT transformer
- Supports 130+ ambiguous word forms
- Achieves 94% global accuracy

**Examples:**
```python
"畳の表" → "たたみのオモテ" (surface, not table)
"風が強い" → "カゼが強い" (wind, not style)
"今日は" → "キョウは" (today, not nowadays)
```

### Setup

Install yomikata and download BERT model:

```bash
# Install yomikata (included in requirements-train.txt)
pip install git+https://github.com/q9uri/yomikata.git

# Download BERT model (~400MB)
python -m yomikata download
```

### Usage

**Enabled by default in preprocessing:**

```python
from piper_train.phonemize import phonemize_japanese

# Yomikata automatically applies context-based disambiguation
phonemes = phonemize_japanese("畳の表は美しい")
```

**Direct usage:**

```python
from piper_train.phonemize.japanese_utils import apply_yomikata

text = "畳の表"
result = apply_yomikata(text)
# Result: "畳のオモテ"
```

**Disable if needed:**

```python
from piper_train.phonemize.japanese_utils import preprocess_japanese_text

text = preprocess_japanese_text(
    "畳の表",
    use_yomikata=False  # Disable BERT-based disambiguation
)
```

### Performance Impact (Phase 2)

- **Memory**: +400MB (BERT model)
- **Speed**: +100-200ms per sentence (BERT inference)
- **Initialization**: ~1 second (first call only)
- **Accuracy**: 94% for heteronym disambiguation

### Testing

```bash
# Run Phase 2 tests (requires yomikata + model download)
pytest src/python/tests/test_japanese_kabosu.py::TestYomikataIntegration -v

# Run all tests including Phase 2
pytest src/python/tests/test_japanese_kabosu.py -v
```

## Future Enhancements (Phase 3-4)

Planned features from kabosu-core:

### Phase 3: Advanced Accent Processing
- `retreat_acc_nuc()`: Adjust accent nucleus position
- `modify_acc_after_chaining()`: Verb + auxiliary accent fixes
- `process_odori_features()`: Iteration marks (々, ゝ, etc.)

### Phase 4: Optional Marine Integration
- Accent prediction using deep learning
- ~500MB model (optional, GPU-accelerated)

## License

kabosu-core components are licensed under MIT License:
- Original: https://github.com/q9uri/kabosu-core
- Dictionary data: © 2009 CJKV Ideograph Database (MIT)

## Troubleshooting

### Missing Dependencies

If you see import errors:

```bash
pip install kanalizer jaconv jpreprocess sudachipy sudachidict-core
```

### Dictionary Not Found

If variant kanji normalization fails:

```bash
# Verify dictionaries are present
ls src/python/piper_train/phonemize/dict/
# Should show: jinmei-variants.txt, joyo-variants.txt, non-cjk.txt
```

### Yomikata Model Not Downloaded (Phase 2)

If you see warnings about missing BERT model:

```bash
# Download yomikata BERT model
python -m yomikata download
```

**Common issues:**
- Model download requires internet connection
- Model size is ~400MB
- Download location: `~/.cache/yomikata/` (Linux/Mac) or `%USERPROFILE%\.cache\yomikata\` (Windows)

### M1 Mac Installation Issues

If `fugashi` (yomikata dependency) fails to install on M1 Mac:

```bash
# Install Xcode Command Line Tools first
xcode-select --install

# Then try installing
pip install git+https://github.com/q9uri/yomikata.git
python -m yomikata download
```

## References

- kabosu-core: https://github.com/q9uri/kabosu-core
- kanalizer: https://github.com/VOICEVOX/kanalizer
- yomikata: https://github.com/passaglia/yomikata
- jpreprocess: https://github.com/jpreprocess/jpreprocess
