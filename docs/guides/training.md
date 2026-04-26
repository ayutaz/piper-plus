# Training Guide

Training your own piper-plus model from scratch or fine-tuning an existing checkpoint. Covers basic single-speaker training through multi-GPU multi-speaker workflows.

> For production-grade pretraining and fine-tune command templates (e.g., 6-language multilingual base, Tsukuyomi-chan fine-tune), see [CLAUDE.md](../../CLAUDE.md) for the full set of advanced templates and parameter rationales.

See the [Training Guide](training/training-guide.md) for detailed instructions.

## Basic

```bash
uv pip install ".[train]"

uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --accelerator gpu --devices 1 --precision 16-mixed \
  --max_epochs 200 --batch-size 16 \
  --quality medium \
  --prosody-dim 16 \
  --ema-decay 0.9995
```

## Multi-speaker / Multi-GPU

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995
```

Multi-GPU automatically configures DDP (Distributed Data Parallel). NCCL environment variables are required. See the Multi-GPU Training Guide for details.

## ONNX Export

FP16 conversion is applied by default, reducing model size by ~50%. Use `--no-fp16` to disable.

```bash
# Standard model (FP16 by default)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Full precision (FP32)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM model (--stochastic enabled by default)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

## Checkpoint Management

- `--resume_from_checkpoint` — Resume training from checkpoint
- `--resume_from_single_speaker_checkpoint` — Convert single-speaker to multi-speaker model
- `--resume-from-multispeaker-checkpoint` — Convert multi-speaker to single-speaker for fine-tuning (auto-enables `--freeze-dp`)

## Voice Evaluation

`scripts/evaluation/` contains evaluation test texts.

---

→ Back to [README](../../README_EN.md)
