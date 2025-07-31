# Japanese Piper TTS Model Training Guide

This guide explains how to train a Japanese TTS model for Piper using CSS10 dataset with support for unvoiced vowels.

## Features

- Support for unvoiced vowels (無声化母音) represented as uppercase letters (A, I, U, E, O)
- 58-phoneme system (expanded from 53) for more accurate Japanese representation
- OpenJTalk-based phonemization with full-context labels
- CSS10 Japanese dataset preparation
- High-quality Japanese TTS model training

## Prerequisites

1. Python 3.11 or higher
2. PyTorch with CUDA support (for GPU training)
3. OpenJTalk with dictionary installed
4. Piper TTS training environment

## Step 1: Install Dependencies

```bash
# Install Python dependencies
pip install torch torchaudio numpy scipy tqdm tensorboard matplotlib

# Install OpenJTalk (if not already installed)
# Ubuntu/Debian:
sudo apt-get install open-jtalk open-jtalk-mecab-naist-jdic

# macOS:
brew install open-jtalk

# Build Piper with OpenJTalk support
cd /path/to/piper
mkdir build && cd build
cmake .. -DUSE_OPENJTALK=ON
make -j$(nproc)
```

## Step 2: Prepare CSS10 Dataset

```bash
cd src/python

# Download and prepare CSS10 Japanese dataset
python prepare_css10_japanese.py --download --output-dir css10_prepared

# Or if you already have CSS10 Japanese data:
python prepare_css10_japanese.py --css10-dir /path/to/css10/japanese --output-dir css10_prepared
```

This will create:
- `css10_prepared/dataset.json` - Full dataset with phonemes
- `css10_prepared/train.txt` - Training filelist
- `css10_prepared/val.txt` - Validation filelist
- `css10_prepared/config.json` - Model configuration
- `css10_prepared/phoneme_stats.json` - Phoneme statistics including unvoiced vowels

## Step 3: Review Phoneme Statistics

Check the unvoiced vowel statistics:

```bash
python -c "
import json
with open('css10_prepared/phoneme_stats.json', 'r') as f:
    stats = json.load(f)
    unvoiced = {k: v for k, v in stats.items() if k in 'AIUEO'}
    print('Unvoiced vowel occurrences:')
    for k, v in sorted(unvoiced.items()):
        print(f'  {k}: {v:,}')
"
```

## Step 4: Train the Model

### Dataset Preprocessing (Required First)

```bash
# Preprocess CSS10 dataset with Japanese phonemization
python3 -m piper_train.preprocess \
    --language ja \
    --input-dir /path/to/css10-ja-ljspeech \
    --output-dir /path/to/dataset-css10-ja \
    --dataset-format ljspeech \
    --single-speaker \
    --sample-rate 22050 \
    --max-workers 45
```

### FP16 Training Configuration

To enable FP16 (half-precision) training for better performance:

```bash
# Add fp16_run to the generated config.json
# Method 1: Edit config.json directly and add:
#   "fp16_run": true

# Method 2: Use sed command
sed -i 's/"piper_version": "1.3.0"/"piper_version": "1.3.0",\n    "fp16_run": true/g' /path/to/dataset-css10-ja/config.json
```

### Multi-GPU Training (L4 × 4 GPUs)

```bash
# Set memory optimization
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# Train with multi-GPU DDP strategy
python -m piper_train \
    --dataset-dir /path/to/dataset-css10-ja \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 14 \
    --num-workers 16 \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --max_epochs 1500 \
    --checkpoint-epochs 50 \
    --ema-decay 0.9995 \
    --default_root_dir /path/to/output-css10-ja
```

**Note**: `ddp_find_unused_parameters_true` strategy is required for VITS models as some parameters may not be used in certain training steps.

### Single GPU Training

```bash
# Single GPU training command
python -m piper_train \
    --dataset-dir /path/to/dataset-css10-ja \
    --accelerator gpu \
    --devices 1 \
    --batch-size 32 \
    --num-workers 8 \
    --learning_rate 2e-4 \
    --max_epochs 2000 \
    --checkpoint-epochs 100 \
    --ema-decay 0.9995 \
    --default_root_dir /path/to/output-css10-ja
```

### Option B: Using custom training script

```python
# train_japanese_model.py
import torch
import json
from pathlib import Path

# Load configuration
with open('train_config_japanese.json', 'r') as f:
    config = json.load(f)

# Load phoneme mapping
from jp_phoneme_map import get_phoneme_id_map
phoneme_map = get_phoneme_id_map()

# Initialize model with proper phoneme count
config['model']['n_symbols'] = len(phoneme_map)

# Training code here...
```

## Step 5: Monitor Training

```bash
# Start TensorBoard
tensorboard --logdir ./logs/ja_JP_css10_openjtalk

# Open http://localhost:6006 in browser
```

## Step 6: Export Model

After training, export the model to ONNX format:

```bash
python export_onnx.py \
    --checkpoint ./checkpoints/ja_JP_css10_openjtalk/checkpoint_best.pth \
    --config ./css10_prepared/config.json \
    --output ./ja_JP_css10_openjtalk.onnx
```

## Step 7: Test the Model

```bash
# Test with Piper
echo "今日は良い天気です" | piper \
    --model ./ja_JP_css10_openjtalk.onnx \
    --output_file test.wav

# The model will correctly handle unvoiced vowels:
# です → d e s U (unvoiced う)
# でした → d e sh I t a (unvoiced い)
```

## Phoneme Mapping

The model uses the following phoneme mapping:

### Basic Vowels
- Voiced: a, i, u, e, o (lowercase)
- Unvoiced: A, I, U, E, O (uppercase)

### Special Phonemes
- N: Moraic nasal (ん)
- q: Glottal stop (っ)
- cl: Geminate consonant closure

### Multi-character Phonemes (mapped to PUA)
- Long vowels: a:, i:, u:, e:, o:
- Palatalized consonants: ky, gy, ty, dy, ny, hy, my, ry, py, by
- Special consonants: ch, ts, sh, zy

## Customization

### Adjust Unvoiced Vowel Handling

To train without preserving unvoiced vowels:

```bash
python prepare_css10_japanese.py \
    --css10-dir /path/to/css10/japanese \
    --output-dir css10_prepared_lowercase \
    --no-preserve-unvoiced
```

### Modify Training Parameters

Edit `train_config_japanese.json`:
- `batch_size`: Adjust based on GPU memory
- `learning_rate`: Fine-tune for better convergence
- `max_epochs`: Increase for better quality

## Troubleshooting

### OpenJTalk not found
Ensure OpenJTalk is in PATH or build `open_jtalk_phonemizer` from Piper source.

### CUDA out of memory
Reduce `batch_size` in training configuration.

### Poor audio quality
- Increase training epochs
- Adjust `noise_scale` and `length_scale` during inference
- Ensure dataset has good audio quality

## References

- [CSS10: A Collection of Single Speaker Speech Datasets](https://github.com/Kyubyong/css10)
- [OpenJTalk](http://open-jtalk.sourceforge.net/)
- [Piper TTS](https://github.com/rhasspy/piper)