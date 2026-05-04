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

## MB-iSTFT-VITS2 Decoder

The VITS decoder is **MB-iSTFT (Multi-Band inverse STFT) + PQMF**, the only generator path. Total upsample factor is `upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x`, delivering approximately **2.21x faster CPU ONNX inference** (100 phoneme p50) versus the legacy HiFi-GAN baseline. The output shape `[B, 1, T]` is preserved, so existing C++/Rust/C#/Go/WASM runtimes work unchanged. Both `--quality medium` and `--quality high` are supported (the latter applies bigger ResBlocks and 512 initial channels).

### Sub-band STFT loss tuning

| Option | Default | Description |
|--------|---------|-------------|
| `--c-sub-stft` | `1.0` | Weight for sub-band STFT loss |
| `--sub-stft-fft-sizes` | `171,384,683` | FFT sizes for sub-band Multi-resolution STFT loss (3 resolutions) |
| `--sub-stft-hop-sizes` | `10,30,60` | Hop sizes |
| `--sub-stft-win-sizes` | `60,150,300` | Window sizes |

## ONNX Export

FP16 conversion is applied by default, reducing model size by ~50%. Use `--no-fp16` to disable.

```bash
# Standard model (FP16 by default)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Full precision (FP32)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx
```

## Checkpoint Management

- `--resume_from_checkpoint` — Resume training from checkpoint
- `--resume_from_single_speaker_checkpoint` — Convert single-speaker to multi-speaker model
- `--resume-from-multispeaker-checkpoint` — Convert multi-speaker to single-speaker for fine-tuning (auto-enables `--freeze-dp`)

> Existing HiFi-GAN-based `.ckpt` files (pre-MB-iSTFT) are no longer compatible with `--resume_from_checkpoint`. Use the new MB-iSTFT base models published with this release.

## Voice Evaluation

`scripts/evaluation/` contains evaluation test texts.

---

→ Back to [README](../../README_EN.md)
