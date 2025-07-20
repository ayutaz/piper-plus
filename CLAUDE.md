# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Piper is a fast, local neural text-to-speech (TTS) system optimized for the Raspberry Pi 4. This enhanced version includes comprehensive Japanese language support with OpenJTalk integration and multi-GPU training capabilities using PyTorch Lightning 2.x.

## Architecture

**Core Components:**
- `src/cpp/` - C++17 TTS engine using ONNX Runtime for inference
- `src/python/piper_train/` - Python training framework with PyTorch Lightning
- `src/python_run/` - Runtime package (`piper-tts-plus` on PyPI)
- `cmake/` - Cross-platform build system with external dependencies

**Key Technologies:**
- VITS (Variational Inference TTS) neural architecture
- ONNX Runtime for optimized inference
- OpenJTalk for Japanese text processing
- PyTorch Lightning 2.x for distributed training

## Development Commands

### Python Training Environment
```bash
# Setup virtual environment and dependencies
cd src/python
./scripts/setup.sh

# Install training dependencies
pip install -r requirements.txt

# Build Cython extensions
./build_monotonic_align.sh
```

### Code Quality
```bash
# Run all linting and formatting (use ruff instead of legacy tools)
ruff check --fix .
ruff format .

# Type checking
mypy src/python/piper_train/

# Legacy script (uses black, flake8, pylint, mypy)
src/python/scripts/check.sh
```

### Testing
```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit          # Fast unit tests
pytest -m integration   # Integration tests
pytest -m japanese      # Japanese TTS tests
pytest -m training      # Training tests
pytest -m requires_gpu  # GPU tests

# Run tests in parallel
pytest -n auto

# Run with coverage
pytest --cov=src/python/piper_train --cov=src/python_run/piper
```

### Training
```bash
# Single GPU training
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --batch-size 16 \
  --base_lr 2e-4

# Multi-GPU training (DDP strategy)
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --batch-size 16 \
  --devices 2 \
  --strategy ddp \
  --base_lr 2e-4

# Resume from checkpoint
python -m piper_train \
  --resume_from_checkpoint /path/to/checkpoint.ckpt

# Fine-tuning from single speaker to multi-speaker
python -m piper_train \
  --resume_from_single_speaker_checkpoint /path/to/single_speaker.ckpt
```

### C++ Build System
```bash
# Build C++ components
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release

# Platform-specific builds automatically download dependencies:
# - piper-phonemize, ONNX Runtime, fmt, spdlog
```

### Model Export and Inference
```bash
# Export trained model to ONNX
python -m piper_train.export_onnx \
  --checkpoint /path/to/checkpoint.ckpt \
  --output /path/to/model.onnx

# Export with optimization (NEW)
python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt \
  /path/to/model.onnx \
  --simplify

# Optimize existing ONNX model (NEW)
python -m piper_train.export_onnx \
  --simplify-only /path/to/existing_model.onnx

# Run inference
echo "Hello world" | ./piper --model model.onnx --output_file output.wav

# GPU inference
echo "Hello world" | ./piper --model model.onnx --use-cuda --output_file output.wav
```

## Training Configuration

**Model Quality Levels:**
- `low` - 16kHz sample rate, smaller model
- `medium` - 22.05kHz sample rate, smaller model  
- `high` - 22.05kHz sample rate, larger model

**Key Training Parameters:**
- `--batch-size` - Batch size per GPU (automatically scaled for multi-GPU)
- `--devices` - Number of GPUs to use
- `--strategy ddp` - Distributed Data Parallel for multi-GPU
- `--base_lr` - Base learning rate (auto-scaled with `--auto_lr_scaling`)
- `--num-workers` - DataLoader worker processes
- `--save-top-k` - Number of checkpoints to keep
- `--gradient_clip_val` - Gradient clipping threshold
- `--accumulate_grad_batches` - Gradient accumulation steps
- `--precision 16-mixed` - Mixed precision training

## Japanese TTS Support

**Environment Variables:**
- `OPENJTALK_DICTIONARY_DIR` - Path to OpenJTalk dictionary (auto-downloaded if unset)
- `OPENJTALK_VOICE` - Path to HTS voice model (auto-downloaded if unset)
- `PIPER_AUTO_DOWNLOAD_DICT=0` - Disable auto-download
- `PIPER_OFFLINE_MODE=1` - Enable offline mode

**Usage:**
```bash
# Japanese TTS with auto-setup
echo "こんにちは" | ./piper --model ja-model.onnx --output_file japanese.wav

# Python package with Japanese support
pip install "piper-tts-plus[gpu]"
```

## Testing Infrastructure

**Test Categories (pytest markers):**
- `unit` - Fast, isolated tests
- `integration` - Tests requiring external resources
- `japanese` - Japanese TTS functionality
- `training` - Model training tests
- `inference` - Model inference tests
- `requires_gpu` - GPU-dependent tests
- `requires_openjtalk` - OpenJTalk-dependent tests
- `requires_model` - Tests needing model files

## Development Notes

**Key Architectural Patterns:**
- PyTorch Lightning modules in `vits/lightning.py` handle distributed training
- Phonemization uses pluggable backends (`phonemize/` directory)
- Japanese text processing integrates OpenJTalk via `pyopenjtalk-plus`
- Model export uses ONNX for cross-platform deployment
- Multi-speaker models use speaker embeddings with automatic ID mapping

**Performance Optimizations:**
- ARM64 NEON SIMD support for embedded devices
- CUDA acceleration for training and inference
- DataLoader optimization with `pin_memory=True`
- Automatic learning rate scaling for multi-GPU training
- Checkpoint management with configurable retention
- ONNX model optimization with built-in simplifier support

**Cross-Platform Support:**
- Windows: MSVC with CUDA support
- macOS: Apple Silicon native builds (Intel Mac deprecated)
- Linux: x64/ARM64 with full feature support