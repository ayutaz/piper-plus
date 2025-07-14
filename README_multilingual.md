# Multilingual VITS for Piper-Plus

This document describes the multilingual Text-to-Speech (TTS) implementation for piper-plus, supporting Japanese (OpenJTalk) and other languages (espeak-ng) in a unified model.

## Features

- **Unified Model**: Single model supporting multiple languages
- **Language Support**: Japanese, English, Chinese, Spanish, French, German, Korean
- **Code-Switching**: Natural language switching within sentences
- **Transfer Learning**: Convert existing single-language models to multilingual

## Quick Start

### 1. Verify Setup

```bash
python scripts/verify_multilingual_setup.py
```

### 2. Prepare Datasets

Create a configuration file `multilingual_config.json`:

```json
{
  "datasets": [
    {
      "language": "ja",
      "input_dir": "/path/to/japanese_dataset",
      "speaker_id_offset": 0
    },
    {
      "language": "en", 
      "input_dir": "/path/to/english_dataset",
      "speaker_id_offset": 100
    }
  ]
}
```

Dataset format should be LJSpeech-style:
- `metadata.csv`: Contains `filename|text` or `filename|speaker|text`
- `wav/` or `wavs/`: Directory containing audio files

### 3. Preprocess Data

```bash
# Using the shell script
./scripts/run_multilingual_preprocessing.sh \
  -c multilingual_config.json \
  -o multilingual_dataset

# Or directly with Python
python scripts/preprocess_multilingual_dataset.py \
  --config-file multilingual_config.json \
  --output-dir multilingual_dataset
```

### 4. Train Model

```bash
python -m piper_train.train_multilingual \
  --dataset-dir multilingual_dataset \
  --max_epochs 1000 \
  --batch-size 16 \
  --quality medium \
  --gpus 1
```

## Architecture

### Phoneme Mapping
- **Total Vocabulary**: 132 phonemes
- **ID Ranges**:
  - 0-99: Special tokens and language tags
  - 100-199: Japanese phonemes (OpenJTalk)
  - 200-299: English phonemes (espeak-ng)
  - 400-499: Common phonemes (future optimization)

### Model Extensions
- **Language Embedding**: 64-dimensional embeddings for each language
- **Multilingual Text Encoder**: Extended VITS encoder with language support
- **Unified Training**: Single model learns all languages simultaneously

## Implementation Details

### Key Files

**Phonemization**:
- `src/python/piper_train/phonemize/multilingual.py` - Main phonemizer
- `src/python/piper_train/phonemize/multilingual_phoneme_map.py` - Phoneme ID mapping
- `src/python/piper_train/phonemize/multilingual_dataset.py` - Dataset formatter

**Model**:
- `src/python/piper_train/vits/models_multilingual.py` - Multilingual VITS model
- `src/python/piper_train/vits/lightning_multilingual.py` - Training logic
- `src/python/piper_train/vits/dataset_multilingual.py` - Dataset loader

**Training**:
- `src/python/piper_train/train_multilingual.py` - Training script
- `scripts/preprocess_multilingual_dataset.py` - Preprocessing script

### Language Tags

The system uses language tags to identify language boundaries:
```
<lang:ja>こんにちは</lang:ja><lang:en>Hello</lang:en>
```

## Examples

### Mixed Language Text
```python
# Japanese + English
text = "今日のmeetingは3時からです。"
# Automatically detected and processed

# Code-switching
text = "Let's go to 東京 tomorrow!"
# Both languages handled in single utterance
```

### Transfer Learning
```bash
# Convert single-language model to multilingual
python -m piper_train.train_multilingual \
  --dataset-dir multilingual_dataset \
  --convert-from-single-lang path/to/japanese_model.ckpt \
  --max_epochs 500
```

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   ```bash
   pip install pyopenjtalk  # For Japanese
   pip install piper-phonemize  # For other languages
   ```

2. **Memory Issues**
   - Reduce batch size: `--batch-size 8`
   - Use fewer workers: `--max-workers 2`

3. **Language Detection Errors**
   - Specify primary language in dataset
   - Check text encoding (must be UTF-8)

## Documentation

- [Dataset Preparation Guide](docs/multilingual-dataset-preparation-guide.md)
- [Model Specification](docs/multilingual-model-specification.md)
- [Implementation Summary](docs/multilingual-implementation-summary.md)
- [Phase 2 Summary](docs/multilingual-phase2-summary.md)

## Future Improvements

- [ ] Dynamic language loading
- [ ] Zero-shot language adaptation
- [ ] Prosody transfer between languages
- [ ] More language support

## License

Same as piper-plus project.