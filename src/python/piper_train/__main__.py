import argparse
import json
import logging
import os
from pathlib import Path
from pickle import UnpicklingError

import torch
import torch.backends.cuda as bcuda
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from pytorch_lightning.strategies import DDPStrategy

from .vits.commons import (
    normalize_checkpoint_state_dict,
    remap_weight_norm_keys,
)
from .vits.ema import EMACallback
from .vits.lightning import VitsModel


# NOTE: the pathlib safe-globals registration and the Windows PosixPath
# alias live in `piper_train._compat`, which `piper_train/__init__.py`
# imports eagerly — so they are already applied by the time this module
# runs. Do not re-add a copy here: the duplicate that used to sit at this
# spot drifted out of sync and registered the wrong keys under CPython
# 3.13 (see `_compat.py` for why the module spelling matters).

# Optional wandb integration
try:
    from pytorch_lightning.loggers import WandbLogger  # noqa: PLC0415

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False


_LOGGER = logging.getLogger(__package__)


# NOTE: HiFi-GAN checkpoint detection and its migration message now live in
# `vits.commons`, applied via `normalize_checkpoint_state_dict`, so the
# training entry point, the ONNX exporter and the Lightning hook all share
# one implementation. Import them from there, not from this module.


def calculate_effective_batch_size(batch_size, num_gpus=1):
    """Calculate effective batch size for multi-GPU training."""
    return batch_size * num_gpus


def calculate_learning_rate(base_lr, effective_batch_size, base_batch_size=16):
    """Calculate learning rate with linear scaling for multi-GPU training."""
    return base_lr * (effective_batch_size / base_batch_size)


def configure_ddp_strategy(num_gpus, user_strategy=None, no_wavlm=False):
    """Configure DDP strategy for multi-GPU training.

    Args:
        num_gpus: Number of GPUs to use
        user_strategy: User-specified strategy (optional)
        no_wavlm: Whether WavLM is disabled (unused, kept for API compatibility).

    Returns:
        Strategy configuration or None
    """
    if user_strategy:
        _LOGGER.info(f"Using user-specified strategy: {user_strategy}")
        return user_strategy
    elif num_gpus >= 2:
        # static_graph=True (Plan A, 37ea0158 相当) は 4x A100 DDP の実走で
        # 「unused parameters ... enable find_unused_parameters」の
        # RuntimeError を起こし棄却 (2026-08-02 v8 smoke)。GAN 交互最適化の
        # unused set (G step / D step) は static graph の「毎 iteration 同一」
        # 前提を満たさない。v7 完走実績のある find_unused_parameters=True
        # のみに戻す (gradient_as_bucket_view は無害なので維持)。
        ddp_kwargs = {
            "find_unused_parameters": True,
            "gradient_as_bucket_view": True,
        }
        # NVLink の無いホスト (NUMA 跨ぎ all-reduce) では勾配通信が律速に
        # なる (v8 smoke 実測: 11.1 s/step のうち ~5.7s が通信)。opt-in で
        # 勾配を bf16 圧縮して通信量を半減する。bf16-mixed 学習では勾配の
        # 数値表現が元々 bf16 精度相当のため品質影響は小さい
        if os.environ.get("PIPER_PLUS_DDP_BF16_COMPRESS") == "1":
            from torch.distributed.algorithms.ddp_comm_hooks import (  # noqa: PLC0415
                default_hooks,
            )

            ddp_kwargs["ddp_comm_hook"] = default_hooks.bf16_compress_hook
            _LOGGER.info("DDP comm hook: bf16_compress (gradient all-reduce halved)")
        _LOGGER.info(
            "Using DDPStrategy with find_unused_parameters=True, "
            "gradient_as_bucket_view=True"
        )
        return DDPStrategy(**ddp_kwargs)
    return None


def _resolve_grad_clip(gradient_clip_val: float | None) -> float | None:
    """CLI --gradient-clip-val を VitsModel.grad_clip にマップする。

    VITS は ``automatic_optimization=False`` で動作するため、Lightning Trainer
    の自動 ``gradient_clip_val`` は使えない (MisconfigurationException)。代わりに
    ``training_step`` 内で ``torch.nn.utils.clip_grad_norm_`` を直接呼び出す
    実装になっており、その値は ``VitsModel.__init__(grad_clip=...)`` 経由で渡る。

    None / 0 以下は clipping 無効化として ``None`` を返す。
    """
    if gradient_clip_val is None or gradient_clip_val <= 0:
        return None
    return float(gradient_clip_val)


def _build_trainer(args, loggers, num_gpus, num_speakers):
    """Build a Trainer instance with callbacks and strategy from args.

    This is called both on the normal path and when falling back from a
    failed checkpoint resume (where a fresh Trainer is needed to clear
    the stale ckpt_path).
    """
    callbacks = []
    if args.checkpoint_epochs is not None:
        checkpoint_dir = Path(args.default_root_dir) / "checkpoints"
        callbacks.append(
            ModelCheckpoint(
                dirpath=str(checkpoint_dir),
                every_n_epochs=args.checkpoint_epochs,
                save_top_k=args.save_top_k,
                save_last=True,
                save_on_train_epoch_end=True,
            )
        )
        _LOGGER.debug(
            "Checkpoints will be saved every %s epoch(s) to %s",
            args.checkpoint_epochs,
            checkpoint_dir,
        )

    # EMA is enabled by default
    if not args.no_ema:
        callbacks.append(EMACallback(decay=args.ema_decay))
        _LOGGER.info("Using EMA with decay rate %s", args.ema_decay)
    else:
        _LOGGER.info("EMA disabled by user request")

    trainer_kwargs = {
        "accelerator": args.accelerator,
        "devices": args.devices,
        "precision": args.precision,
        "max_epochs": args.max_epochs,
        "callbacks": callbacks,
        "default_root_dir": args.default_root_dir,
        "logger": loggers,
        "check_val_every_n_epoch": args.val_every_n_epochs,
        "limit_val_batches": args.limit_val_batches,
    }

    # NOTE: VITS は automatic_optimization=False (manual optimization) のため
    # Trainer(gradient_clip_val=...) は使えない (Lightning が MisconfigurationException を投げる)。
    # 代わりに VitsModel.training_step 内で torch.nn.utils.clip_grad_norm_ を呼び出す
    # (lightning.py:589-604)。値は VitsModel(grad_clip=...) で渡される。

    # --limit-train-batches: テスト用に学習バッチ数を制限
    if getattr(args, "limit_train_batches", None) is not None:
        trainer_kwargs["limit_train_batches"] = args.limit_train_batches

    # Multi-GPU DDP optimization
    strategy = configure_ddp_strategy(num_gpus, args.strategy, no_wavlm=args.no_wavlm)
    if strategy:
        trainer_kwargs["strategy"] = strategy

    # When using SpeakerBalancedBatchSampler, disable Lightning's automatic distributed sampler
    if args.samples_per_speaker > 0 and num_speakers > 1:
        trainer_kwargs["use_distributed_sampler"] = False
        _LOGGER.info("Disabled distributed sampler for SpeakerBalancedBatchSampler")

    return Trainer(**trainer_kwargs)


def create_parser():
    """Create the argument parser for piper_train.

    Extracted so that tests can import and reuse the canonical parser
    instead of duplicating argparse definitions.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir", required=True, help="Path to pre-processed dataset directory"
    )
    parser.add_argument(
        "--checkpoint-epochs",
        type=int,
        help="Save checkpoint every N epochs (default: 1)",
    )
    parser.add_argument(
        "--quality",
        default="medium",
        choices=("x-low", "medium", "high"),
        help="Quality/size of model (default: medium)",
    )
    parser.add_argument(
        "--resume_from_single_speaker_checkpoint",
        help="For multi-speaker models only. Converts a single-speaker checkpoint to multi-speaker and resumes training",  # noqa: E501
    )
    parser.add_argument(
        "--resume-from-multispeaker-checkpoint",
        help="For single-speaker fine-tuning. Loads a multi-speaker checkpoint with strict=False "
        "(emb_g is skipped), adds emb_g mean to all emb_lang rows for conditioning correction, "
        "and preserves original language embeddings. "
        "Optimizer state is reset (training starts from epoch 0). "
        "Automatically enables --freeze-dp.",
    )
    parser.add_argument(
        "--resume-weights-only",
        help="Warm-restart: load model weights from a checkpoint with strict=False "
        "and start a FRESH training run (epoch 0, new optimizer / LR schedule). "
        "Use when the continuation config is incompatible with strict Trainer "
        "resume — e.g. enabling the WavLM discriminator (adds parameters that "
        "are fresh-initialized) or replacing an exhausted LR schedule. "
        "Mutually exclusive with --resume_from_checkpoint and "
        "--resume-from-multispeaker-checkpoint.",
    )
    parser.add_argument(
        "--save-top-k",
        type=int,
        default=-1,
        help="Save top k checkpoints (-1 to save all).",
    )
    parser.add_argument(
        "--no-ema",
        action="store_true",
        help="Disable EMA (Exponential Moving Average). EMA is enabled by default for training stability",
    )
    parser.add_argument(
        "--ema-decay",
        type=float,
        default=0.9995,
        help="EMA decay rate (default: 0.9995)",
    )
    parser.add_argument(
        "--auto_lr_scaling",
        action="store_true",
        default=True,
        help="Automatically scale learning rate for multi-GPU training (default: enabled)",
    )
    parser.add_argument(
        "--disable_auto_lr_scaling",
        action="store_true",
        help="Disable automatic learning rate scaling for multi-GPU training",
    )
    parser.add_argument(
        "--base_lr",
        type=float,
        default=2e-4,
        help="Base learning rate for single GPU training",
    )
    # WavLM Discriminator arguments (always enabled by default for improved audio quality)
    parser.add_argument(
        "--wavlm-model-name",
        default="microsoft/wavlm-base-plus",
        help="WavLM model name from HuggingFace (default: microsoft/wavlm-base-plus)",
    )
    parser.add_argument(
        "--c-wavlm",
        type=float,
        default=0.5,
        help="WavLM discriminator loss weight (default: 0.5)",
    )
    parser.add_argument(
        "--wavlm-every-n-steps",
        type=int,
        default=1,
        help="Compute WavLM loss every N steps (default: 1, higher = faster training)",
    )
    parser.add_argument(
        "--no-wavlm",
        action="store_true",
        help="Disable WavLM discriminator (faster training, slightly lower quality)",
    )
    parser.add_argument(
        "--use-mrd",
        action="store_true",
        default=False,
        help="Enable MRD (UnivNet-style multi-resolution spectrogram "
        "discriminator) at native sample rate. Adds adversarial supervision "
        "of 5-11 kHz spectral fine structure that mel loss (coarse "
        "high-frequency bins) and the 16 kHz WavLM discriminator cannot "
        "see — the band where multi-speaker zero-shot noise lives "
        "(docs/design/zero-shot-noise-root-cause-pqmf.md).",
    )
    parser.add_argument(
        "--c-mrd",
        type=float,
        default=1.0,
        help="MRD loss weight (default: 1.0, used with --use-mrd)",
    )
    parser.add_argument(
        "--c-full-stft",
        type=float,
        default=0.0,
        help="Full-band linear-frequency multi-resolution STFT loss weight "
        "(default: 0 = disabled). Supervises high-frequency spectral "
        "structure that mel L1 cannot resolve (coarse high-frequency mel "
        "bins). Complements --use-mrd (regression vs adversarial).",
    )
    parser.add_argument(
        "--reinit-pqmf",
        action="store_true",
        default=False,
        help="After loading checkpoint weights, re-initialize the PQMF filter "
        "bank with freshly-constructed (canonical) coefficients instead of "
        "the ones stored in the checkpoint. Required when re-adapting a "
        "checkpoint trained against the pre-v9 buggy bank to the fixed bank "
        "(docs/design/zero-shot-noise-root-cause-pqmf.md). Only supported "
        "with --resume-weights-only (strict Trainer resume restores buffers "
        "after fit starts and would silently undo the re-init).",
    )
    parser.add_argument(
        "--train-decoder-only",
        action="store_true",
        default=False,
        help="Freeze all generator parameters except the decoder (dec.*). "
        "Used with --reinit-pqmf for v9 decoder re-adaptation fine-tuning: "
        "the PQMF-target contamination only ever back-propagated through "
        "the decoder, so re-adapting it alone against the fixed bank may "
        "avoid a full retrain.",
    )
    parser.add_argument(
        "--freeze-dp",
        action="store_true",
        default=False,
        help="Freeze Duration Predictor parameters during training. "
        "Use for fine-tuning to prevent duration prediction degradation.",
    )
    # MB-iSTFT Generator options
    parser.add_argument(
        "--c-sub-stft",
        type=float,
        default=1.0,
        help="Sub-band STFT loss weight for MB-iSTFT training (default: 1.0)",
    )
    # Trainer arguments
    parser.add_argument("--accelerator", default="gpu", help="Accelerator to use")
    parser.add_argument("--devices", type=int, default=1, help="Number of devices")
    parser.add_argument(
        "--strategy", default=None, help="Training strategy (e.g., ddp)"
    )
    parser.add_argument(
        "--no-pin-memory",
        action="store_true",
        help="Disable pin_memory in DataLoader (reduces CPU RAM for 4+ GPUs)",
    )
    parser.add_argument(
        "--prefetch-factor",
        type=int,
        default=4,
        help="DataLoader prefetch_factor (samples pre-loaded per worker, default: 4). "
        "Raised from PyTorch's default of 2 so the H2D pipeline stays warm now that "
        "Batch implements pin_memory(). Set lower (e.g. 2) if RAM is tight; only "
        "meaningful when --num-workers > 0.",
    )
    parser.add_argument(
        "--samples-per-speaker",
        type=int,
        default=0,
        help="Number of samples per speaker in each batch for multi-speaker models. "
        "When set > 0, enables speaker-balanced batch sampling to stabilize Duration Predictor training. "
        "Recommended: 4 (e.g., batch_size=32 with samples_per_speaker=4 → 8 speakers × 4 samples). "
        "Set to 0 to disable (default: 0).",
    )
    parser.add_argument(
        "--language-balanced-sampling",
        action="store_true",
        default=False,
        help="Force language-balanced sampling across multiple language groups "
        "(distributes batch slots equally per language, e.g. 6-language model gets ~16.7%% each). "
        "If not specified, auto-enabled when speaker count ratio between languages >= 3:1. "
        "Requires --samples-per-speaker > 0, num_speakers > 1, and num_languages > 1; "
        "single-speaker multilingual models bypass SpeakerBalancedBatchSampler entirely "
        "(this flag has no effect there).",
    )
    parser.add_argument(
        "--enable-length-bucketing",
        action="store_true",
        default=False,
        help="Enable phoneme-length bucketing inside each speaker slot of SpeakerBalancedBatchSampler "
        "(opt-in, default: disabled). Utterances of the same speaker are pre-sorted by phoneme length "
        "and grouped into buckets of samples_per_speaker. This reduces padding overhead in "
        "UtteranceCollate and shortens per-step time on long-tailed length distributions. "
        "The samples_per_speaker contract is preserved. Bucket order is shuffled every epoch to "
        "maintain sampling diversity. Has no effect when SpeakerBalancedBatchSampler is not used "
        "(single-speaker or --samples-per-speaker=0).",
    )
    parser.add_argument(
        "--precomputed-mel",
        action="store_true",
        default=False,
        help="Load precomputed linear spectrograms from ``{dataset_dir}/mel/*.mel.npy`` "
        "instead of the legacy ``.spec.pt`` cache. Requires running "
        "``python -m piper_train.tools.precompute_mel`` first. "
        "Backward-compat: per-utterance fallback to ``audio_spec_path`` when a "
        "``.mel.npy`` sibling is missing, so this flag is safe to pass even on "
        "partially-precomputed datasets. Default: off.",
    )
    parser.add_argument(
        "--precision",
        default="bf16-mixed",
        choices=("32-true", "16-mixed", "bf16-mixed"),
        help="Floating point precision (default: bf16-mixed for faster training with minimal quality impact)",
    )
    parser.add_argument(
        "--val-every-n-epochs",
        type=int,
        default=5,
        help="Run validation every N epochs (default: 5). Training loss is monitored via WandB every step, "
        "so validation is only needed for quality trend checks.",
    )
    parser.add_argument(
        "--limit-val-batches",
        type=int,
        default=50,
        help="Limit validation to N batches per validation run (default: 50). "
        "50 batches (~1000 samples) is statistically sufficient for trend monitoring.",
    )
    parser.add_argument(
        "--limit-train-batches",
        type=int,
        default=None,
        help="Limit training to N batches per epoch (for testing). Default: None (no limit).",
    )
    parser.add_argument(
        "--max_epochs",
        type=int,
        default=100,
        help="Maximum number of epochs (default: 100)",
    )
    parser.add_argument(
        "--default_root_dir", default=None, help="Default path for logs and weights"
    )
    parser.add_argument(
        "--resume_from_checkpoint",
        default=None,
        help="Path to checkpoint to resume from",
    )
    VitsModel.add_model_specific_args(parser)
    # Zero-shot speaker conditioning arguments
    parser.add_argument(
        "--spk-emb-noise-sigma",
        type=float,
        default=0.05,
        help="Gaussian noise sigma for speaker embedding perturbation during training "
        "(default: 0.05). Set to 0 to disable.",
    )
    parser.add_argument(
        "--d-update-interval",
        type=int,
        default=1,
        help="Discriminator update interval relative to generator (D:G ratio). "
        "Default: 1 (update D every G step, i.e. 1:1 ratio).",
    )
    parser.add_argument(
        "--grad-probe-every",
        type=int,
        default=0,
        help="Diagnostic (zero-shot v10 roadmap A-1c): every N steps, measure "
        "per-loss gradient L2 norms (mel/kl/spk/dino/sub_stft/full_stft/mrd/"
        "mpd_msd/wavlm) on shared probe parameters (spk_proj / dec.conv_pre / "
        "enc_p.proj / flow.flows[0].pre) and log them as grad_probe/* plus a "
        "spk-vs-spectral ratio (SCL gradient-dilution measurement). "
        "0 disables entirely with zero overhead (default: 0).",
    )
    # LR scheduler arguments
    parser.add_argument(
        "--lr-scheduler",
        choices=("cosine", "exponential"),
        default="cosine",
        help="Learning rate scheduler type (default: cosine). "
        "'cosine' uses CosineAnnealingLR with warmup; "
        "'exponential' uses the legacy ExponentialLR (gamma=lr_decay).",
    )
    parser.add_argument(
        "--lr-warmup-epochs",
        type=int,
        default=5,
        help="Number of linear warmup epochs for cosine scheduler (default: 5). "
        "Ignored when --lr-scheduler=exponential.",
    )
    parser.add_argument(
        "--lr-min",
        type=float,
        default=1e-5,
        help="Minimum learning rate for cosine annealing (default: 1e-5). "
        "Ignored when --lr-scheduler=exponential.",
    )
    # Speaker embedding dropout (deprecated)
    parser.add_argument(
        "--spk-emb-dropout",
        type=float,
        default=0.0,
        help="(deprecated, ignored) Speaker embedding dropout rate. "
        "This argument is kept for backward compatibility but has no effect.",
    )
    parser.add_argument(
        "--speaker-encoder-torch-path",
        type=str,
        default=None,
        help="Path to torch CAM++ weights (campplus_cn_common.bin, HF mirror: "
        "funasr/campplus). Enables DIFFERENTIABLE SCL: the frozen torch "
        "encoder backpropagates through the generated waveform, so loss_spk "
        "actually trains speaker similarity. Without this, the ONNX encoder "
        "path computes loss_spk under no_grad (monitoring only, zero "
        "gradient).",
    )
    parser.add_argument(
        "--spk-loss-type",
        type=str,
        choices=["cosine", "infonce"],
        default="cosine",
        help="SCL loss form (used with --speaker-encoder-torch-path): "
        "'cosine' pulls the generated embedding toward its own reference; "
        "'infonce' additionally requires discriminating the reference from "
        "other speakers in the batch (same-speaker false negatives are "
        "masked via speaker ids).",
    )
    parser.add_argument(
        "--spk-loss-positives",
        type=str,
        choices=["same_utt", "cross_utt"],
        default="same_utt",
        help="Positive definition for --spk-loss-type infonce (v10 roadmap "
        "B-1): 'same_utt' (legacy) uses the conditioning utterance's own "
        "embedding as the positive — known Goodhart path (Phase 0 Arm B): "
        "the loss can be satisfied by matching the utterance embedding "
        "without transferring speaker identity. 'cross_utt' uses same-"
        "speaker OTHER-utterance embeddings as positives (SupCon form; the "
        "same-utt diagonal is excluded from the denominator, not treated "
        "as a negative). Requires samples-per-speaker > 1.",
    )
    parser.add_argument(
        "--scl-detach-z",
        action="store_true",
        help="v10 roadmap B-3: compute SCL on an extra decoder forward with "
        "the posterior z detached, so SCL gradients flow only into the "
        "speaker conditioning (spk_proj) and decoder — never into the "
        "posterior encoder. Blocks the 'decoder reads timbre from the "
        "ground-truth-derived z' leak. Costs one extra decoder forward "
        "per generator step.",
    )
    parser.add_argument(
        "--segment-size",
        type=int,
        default=8192,
        help="Decoder training slice length in samples (default 8192 = ~0.37s "
        "@22.05kHz). Longer slices give the SCL speaker encoder a usable "
        "window (0.37s is too short for stable speaker embeddings) at the "
        "cost of decoder/discriminator VRAM and step time.",
    )
    # Speaker encoder path
    parser.add_argument(
        "--speaker-encoder-path",
        type=str,
        default=None,
        help="Path to speaker encoder ONNX for embedding extraction "
        "(SCL now uses mel-domain loss).",
    )
    parser.add_argument(
        "--c-dino",
        type=float,
        default=0.5,
        help="DINO self-distillation loss weight (default: 0.5)",
    )
    parser.add_argument(
        "--kl-annealing-epochs",
        type=int,
        default=10,
        help="KL annealing epochs: linearly increase KL weight from 0.1 to 1.0 "
        "over this many epochs (default: 10, 0 to disable)",
    )
    parser.add_argument(
        "--max-spec-length",
        type=int,
        default=700,
        help="Maximum spectrogram length; utterances longer than this are excluded "
        "(default: 700). Use to prevent OOM on long utterances.",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Enable torch.compile() for potential training speedup (requires PyTorch 2.0+)",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        default=False,
        help="Disable torch.compile() (recommended for T4 GPUs where compile overhead is large)",
    )
    parser.add_argument(
        "--compile-mode",
        type=str,
        default="reduce-overhead",
        choices=[
            "default",
            "reduce-overhead",
            "max-autotune",
            "max-autotune-no-cudagraphs",
        ],
        help="torch.compile() mode (default: reduce-overhead). "
        "When --enable-length-bucketing fixes shapes per batch, prefer "
        "'max-autotune' (CUDA Graph capture) or 'max-autotune-no-cudagraphs' "
        "for kernel autotuning without CUDA Graph capture.",
    )
    parser.add_argument(
        "--compile-dynamic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable dynamic shape tracing for torch.compile() (default: True). "
        "Set --no-compile-dynamic together with length bucketing "
        "(fixed per-batch shapes) to allow CUDA Graph capture with "
        "--compile-mode=max-autotune.",
    )
    parser.add_argument(
        "--gradient-clip-val",
        type=float,
        default=1.0,
        help="Gradient norm clipping value to prevent NaN explosion (default: 1.0). Set 0 to disable.",
    )
    # T1: channels_last memory format (opt-in) — Conv2d Discriminator (active)
    # + MBiSTFTGenerator (silent no-op, plumbing for future Conv2d).
    # Targets ~-16% sec/step on A100 SXM4 by dispatching DiscriminatorP Conv2d
    # layers to NHWC Tensor Core kernels (nsys measured 12.8% nchw↔nhwc
    # conversion + 8% conv overhead on v8 real-config traces). T1 拡張: 同一 flag
    # を SynthesizerTrn.dec (MBiSTFTGenerator) にも propagate。 現状は Conv1d のみ
    # で構成されるため PyTorch の Module.to() が 3D weight を skip し実質 no-op、
    # ただし将来 Generator 側に Conv2d を追加した際に自動 NHWC 化される
    # (future-proofing)。 Safe rollout: default OFF、 silent fallback on sm_75
    # (T4) and older via PyTorch's kernel dispatcher.
    parser.add_argument(
        "--channels-last",
        action="store_true",
        default=False,
        help="Enable torch.channels_last memory format for MultiPeriodDiscriminator "
        "(DiscriminatorP Conv2d — active) and SynthesizerTrn.dec (MBiSTFTGenerator "
        "— silent no-op today, plumbing for future Conv2d). Opt-in perf switch, "
        "targets NHWC Tensor Core kernels on A100 SXM4 / Ada 6000 (~-16%% sec/step "
        "expected from the D side). Silent fallback to nchw on sm_75 (T4) and "
        "older hardware.",
    )
    # T6: Hybrid precision — override Discriminator forward precision independently
    # of Lightning's global --precision setting. Default "inherit" keeps the
    # status quo: D forward follows --precision. "bf16-mixed" wraps D forward in
    # torch.autocast(bf16) so MPD/MSD run at bf16 even under --precision 32-true
    # (SCL / DINO / loss compute stay fp32 via the outer autocast(enabled=False)
    # block plus an explicit inner wrap around SCL). "32-true" forces D forward
    # to fp32 even under --precision bf16-mixed (debug / parity check).
    parser.add_argument(
        "--disc-precision",
        default="inherit",
        choices=("inherit", "bf16-mixed", "32-true"),
        help="Discriminator forward autocast precision override (hybrid precision). "
        "'inherit' (default) uses --precision as-is. 'bf16-mixed' forces D forward "
        "to bf16 autocast (SCL stays fp32 via the outer autocast(enabled=False) "
        "block and the explicit inner wrap). '32-true' forces D forward to fp32 "
        "even under --precision bf16-mixed for numerical parity checks. Motivation: "
        "on v8 A100 SXM4 real-config traces --precision bf16-mixed regressed to "
        "14.0 sec/step (vs 32-true simplified 5.15 sec/step) due to SCL / DINO "
        "bf16 instability; hybrid precision preserves the D-forward bf16 speed win "
        "(~20-30%% expected) without exposing SCL to bf16 numerics.",
    )
    # T3: SDPA fast path for TextEncoder self-attention (opt-in).
    # Swaps the manual matmul path (`(Q/sqrt(d)) @ K^T + scores_local +
    # softmax + relative-V correction`) for
    # ``F.scaled_dot_product_attention``, folding the relative-K bias into
    # ``attn_mask``. The relative-V correction is dropped because SDPA does
    # not surface ``p_attn`` (this is why the flag is named
    # ``--attn-drop-rel-v``). Default OFF preserves the manual path with
    # bit-parity vs prior checkpoints. Expected win: +2-5% throughput and
    # ~60MB/batch activation-memory saving on the v8 real config (only the
    # TextEncoder attention path is affected; PosteriorEncoder / Flow / Dec
    # are untouched).
    parser.add_argument(
        "--attn-drop-rel-v",
        action="store_true",
        default=False,
        help="Swap TextEncoder MultiHeadAttention for "
        "F.scaled_dot_product_attention (SDPA) with additive relative-K bias. "
        "Drops the relative-V correction. Opt-in perf switch (+2-5%% throughput, "
        "-60MB activation memory / batch). Default OFF preserves the manual "
        "matmul path with bit-parity vs prior checkpoints. Only affects "
        "TextEncoder self-attention (Encoder / TextEncoder in vits.models); "
        "PosteriorEncoder / Flow / MBiSTFTGenerator unaffected.",
    )
    parser.add_argument("--seed", type=int, default=1234)
    return parser


def check_resume_flags_exclusive(args) -> None:
    """--resume-weights-only と他の resume 系フラグの併用を拒否する。

    weights-only warm restart は optimizer / LR / epoch を意図的に捨てる。
    strict resume 系と併用されると「どちらの意味か」が曖昧になり、
    どちらに転んでも事故 (LR schedule の再開 or 二重ロード) になるため
    起動時に fail-fast する。
    """
    if not getattr(args, "resume_weights_only", None):
        return
    conflicts = [
        name
        for name, flag in [
            ("--resume_from_checkpoint", getattr(args, "resume_from_checkpoint", None)),
            (
                "--resume-from-multispeaker-checkpoint",
                getattr(args, "resume_from_multispeaker_checkpoint", None),
            ),
            (
                "--resume_from_single_speaker_checkpoint",
                getattr(args, "resume_from_single_speaker_checkpoint", None),
            ),
        ]
        if flag
    ]
    if conflicts:
        raise SystemExit(
            f"--resume-weights-only は {', '.join(conflicts)} と併用できません。"
            "warm restart (weights のみ、epoch 0 から) か strict resume かの"
            "どちらか一方を指定してください。"
        )


def reinit_pqmf_bank(model) -> None:
    """PQMF buffer を新規構築 (canonical) の係数で上書きする (v9 再適応 FT 用)。

    checkpoint の state_dict は PQMF buffer (persistent) を含むため、旧 ckpt を
    ロードすると壊れた旧バンク係数が復元される — これは通常は望ましい後方互換
    (旧モデルは旧バンクで学習済み) だが、v9 の decoder 再適応 FT では
    「旧 decoder 重み + 修正済みバンク」から学習を始めたい。VitsModel.pqmf と
    model_g.dec.pqmf は同一インスタンス (PR #320 A1) なので片方の上書きで両方に
    効くが、将来の分離に備えて両方に適用する。
    """
    from .vits.mb_istft import PQMF

    fresh = PQMF(subbands=model.pqmf.subbands).state_dict()
    model.pqmf.load_state_dict(fresh)
    if model.model_g.dec.pqmf is not model.pqmf:
        model.model_g.dec.pqmf.load_state_dict(fresh)
    _LOGGER.info(
        "PQMF bank re-initialized with canonical coefficients (--reinit-pqmf); "
        "checkpoint-stored bank discarded."
    )


def load_weights_only_checkpoint(checkpoint_path: str, model) -> tuple[list, list]:
    """checkpoint から model weights のみを strict=False でロードする (warm restart)。

    optimizer / LR scheduler / epoch カウンタは一切復元しない。呼び出し後は
    通常の ``trainer.fit(model)`` で epoch 0 から新しい schedule で学習を開始する。

    典型的な用途: 学習済み ckpt に対して WavLM discriminator を後から有効化する
    継続学習 (v8.1)。ckpt に存在しないキー (model_d_wavlm.* 等) は fresh-init の
    まま残り、ckpt にしか無いキーは捨てられる。

    Returns:
        (missing_keys, unexpected_keys) — ログ済みだが呼び出し側の検証用に返す。
    """
    _LOGGER.info("Warm-restart (weights only) from: %s", checkpoint_path)
    # NOTE: weights_only=False is required to handle PosixPath objects in checkpoints
    # This poses a security risk - only load trusted checkpoints
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state_dict = checkpoint["state_dict"]
    if _is_legacy_hifigan_checkpoint(state_dict):
        raise RuntimeError(_LEGACY_HIFIGAN_MESSAGE.format(path=str(checkpoint_path)))
    remapped_sd = remap_weight_norm_keys(state_dict, model.state_dict())
    missing, unexpected = model.load_state_dict(remapped_sd, strict=False)
    _LOGGER.info(
        "Warm-restart weights loaded (strict=False): missing=%d (fresh-init kept), "
        "unexpected=%d (dropped)",
        len(missing),
        len(unexpected),
    )
    if missing:
        _LOGGER.info("Fresh-initialized keys (not in checkpoint): %s", missing)
    if unexpected:
        _LOGGER.info("Dropped checkpoint keys (not in model): %s", unexpected)
    return missing, unexpected


def load_multispeaker_checkpoint(checkpoint_path: str, model: VitsModel) -> None:
    """Load a multispeaker checkpoint for single-speaker fine-tuning.

    Removes emb_g, adds emb_g mean to emb_lang rows, and loads with strict=False.

    Steps:
        1. Load checkpoint with ``strict=False`` (emb_g is automatically skipped).
        2. Add emb_g mean to all emb_lang rows for conditioning distribution correction.
        3. Preserve all emb_lang rows so the frozen Duration Predictor retains
           correct conditioning for every language.

    Optimizer state is discarded; training restarts from epoch 0.

    Args:
        checkpoint_path: Path to the multispeaker ``.ckpt`` file.
        model: A :class:`VitsModel` instance (single-speaker) to load weights into.
    """
    _LOGGER.info("Resuming from multispeaker checkpoint: %s", checkpoint_path)

    # 1. strict=False でロード（emb_g は自動スキップ）
    # NOTE: weights_only=False is required to handle PosixPath objects in checkpoints
    # This poses a security risk - only load trusted checkpoints
    checkpoint = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )
    # Rejects HiFi-GAN checkpoints and migrates pre-FiLM decoders (issue #616).
    normalized_sd, _ = normalize_checkpoint_state_dict(
        checkpoint["state_dict"], model.state_dict(), checkpoint_path=checkpoint_path
    )
    missing, unexpected = model.load_state_dict(normalized_sd, strict=False)
    _LOGGER.info(
        "Weights loaded (strict=False). Missing keys: %s. Unexpected keys: %s.",
        missing,
        unexpected,
    )

    # 2. emb_g 平均を emb_lang に加算（conditioning 分布補正）
    #    emb_g は平均ノルム ~0.68 でほぼゼロ中心のため影響は軽微だが、
    #    conceptual correctness のため実施する。
    saved_sd = checkpoint["state_dict"]
    emb_g_weight = saved_sd.get("model_g.emb_g.weight")
    if emb_g_weight is not None and hasattr(model.model_g, "emb_lang"):
        emb_g_mean = emb_g_weight.mean(dim=0)  # [gin_channels]
        _LOGGER.info(
            "emb_g mean norm: %.4f → adding to all emb_lang rows for conditioning correction",
            emb_g_mean.norm().item(),
        )
        with torch.no_grad():
            model.model_g.emb_lang.weight.add_(emb_g_mean.unsqueeze(0))
        _LOGGER.info("emb_g_mean added to emb_lang.")
    else:
        _LOGGER.info(
            "emb_g not found in checkpoint or model has no emb_lang; skipping conditioning correction."
        )

    # 3. All emb_lang rows are preserved with emb_g_mean correction.
    #    Previously emb_lang[0] (JA) was copied to emb_lang[1] (EN), but this
    #    caused the frozen Duration Predictor to lose EN conditioning, breaking
    #    English duration prediction. Keeping original embeddings + correction
    #    lets the DP predict correct duration patterns for all languages.
    if hasattr(model.model_g, "emb_lang") and model.model_g.n_languages > 1:
        _LOGGER.info(
            "All emb_lang rows preserved with emb_g_mean correction "
            "for correct duration prediction across languages."
        )

    _LOGGER.info(
        "Multispeaker → single-speaker transfer complete. "
        "Starting training from epoch 0 (optimizer state reset)."
    )


def apply_transfer_defaults(
    args: argparse.Namespace,
    num_speakers: int,
    num_languages: int,
) -> None:
    """Auto-set defaults before model creation for transfer learning.

    1. gin_channels: set to 512 for multi-speaker or multi-language models
       when not explicitly specified (value == 0).
    2. freeze_dp: auto-enable when --resume-from-multispeaker-checkpoint is used.

    Mutates *args* in place.  Callers should use ``vars(args)`` afterward
    to obtain a dict view that reflects the updated values.
    """
    # gin_channels 自動設定
    # 768 は ONNX エクスポート時の数値精度低下を引き起こす
    # VitsModel.__init__ のフォールバック (512) と一致させる
    if (num_speakers > 1 or num_languages > 1) and getattr(
        args, "gin_channels", 0
    ) == 0:
        args.gin_channels = 512

    # freeze_dp 自動有効化
    # モデル作成前に設定しないと save_hyperparameters() に反映されない
    if (
        getattr(args, "resume_from_multispeaker_checkpoint", None)
        and not args.freeze_dp
    ):
        args.freeze_dp = True
        _LOGGER.info(
            "Auto-enabled --freeze-dp for multispeaker→single-speaker transfer"
        )


def main():
    logging.basicConfig(level=logging.DEBUG)

    parser = create_parser()
    args = parser.parse_args()
    _LOGGER.debug(args)

    check_resume_flags_exclusive(args)

    args.dataset_dir = Path(args.dataset_dir)

    # Set default values for Trainer arguments
    if not args.default_root_dir:
        args.default_root_dir = args.dataset_dir

    torch.backends.cudnn.benchmark = True
    # TF32 enable for Ampere+ (sm_80+: A100 / RTX 6000 Ada / RTX 5090). On
    # sm_75 (T4) and older, these settings are no-ops. Speeds up matmul and
    # conv by ~1.3-1.5x with negligible quality impact for TTS workloads.
    # Issue #527 / DR-007 (PR #569).
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    # torch 2.x canonical TF32 dispatcher. Complements `matmul.allow_tf32`
    # for matmul kernels that are chosen via the newer API (e.g. loss code
    # under `autocast(enabled=False)`). No-op on sm_75 / CPU. "high" keeps
    # TF32 for matmul while leaving reductions at FP32.
    torch.set_float32_matmul_precision("high")

    # SDPA backend priority explicit control (T5, Issue #527).
    # PyTorch's scaled_dot_product_attention auto-dispatches to one of
    # flash / mem_efficient / math / cudnn backends. Explicitly prioritize
    # the fast fused kernels and down-priority the math (naive) fallback so
    # that on Ampere+ (sm_80+: A100 / RTX 6000 Ada / RTX 5090) attention
    # layers take the flash / mem_efficient path (~2x faster, lower VRAM).
    # On sm_75 (T4) / CPU these calls are no-ops or safely ignored.
    # torch 2.11 adds cudnn SDPA backend (fastest on Blackwell / Hopper);
    # enable via hasattr guard so torch < 2.11 still imports cleanly.
    bcuda.enable_flash_sdp(True)
    bcuda.enable_mem_efficient_sdp(True)
    # Math backend must stay enabled — SDPA raises "Invalid backend" when
    # flash/mem-efficient decline (e.g. additive attn_mask float32 or
    # non-power-of-2 head_dim) and no fallback is available. Priority still
    # favours flash/mem-efficient; math is only used when both decline.
    # Observed 2026-07-09 on A100 SXM4 with T3 --attn-drop-rel-v: additive
    # rel-K bias attn_mask forced math fallback, and disabling it crashed
    # the whole attention path.
    bcuda.enable_math_sdp(True)
    if hasattr(bcuda, "enable_cudnn_sdp"):
        bcuda.enable_cudnn_sdp(True)  # torch 2.11+ new backend
    _LOGGER.info(
        "SDPA backends: flash=%s mem_efficient=%s math=%s",
        bcuda.flash_sdp_enabled(),
        bcuda.mem_efficient_sdp_enabled(),
        bcuda.math_sdp_enabled(),
    )

    torch.manual_seed(args.seed)

    # Multi-GPU configuration
    num_gpus = (
        args.devices
        if isinstance(args.devices, int)
        else len(args.devices)
        if args.devices
        else 1
    )
    _LOGGER.info(f"Training with {num_gpus} GPU(s)")
    _LOGGER.info(f"Using precision: {args.precision}")

    # Log WavLM Discriminator status
    if args.no_wavlm:
        _LOGGER.info("WavLM Discriminator disabled by --no-wavlm flag")
    else:
        _LOGGER.info(
            f"WavLM Discriminator enabled: model={args.wavlm_model_name}, weight={args.c_wavlm}"
        )

    # Initialize scaled_lr
    scaled_lr = args.base_lr

    # Automatic learning rate scaling for multi-GPU training
    # Disable if --disable_auto_lr_scaling is set
    if args.disable_auto_lr_scaling:
        args.auto_lr_scaling = False

    if args.auto_lr_scaling and num_gpus > 1:
        original_lr = getattr(args, "learning_rate", args.base_lr)
        effective_batch_size = calculate_effective_batch_size(
            getattr(args, "batch_size", 16), num_gpus
        )
        scaled_lr = calculate_learning_rate(original_lr, effective_batch_size)
        args.learning_rate = scaled_lr
        _LOGGER.info(
            f"Auto-scaled learning rate from {original_lr} to {scaled_lr} for {num_gpus} GPUs"
        )
        _LOGGER.info(f"Effective batch size: {effective_batch_size}")

    config_path = args.dataset_dir / "config.json"
    dataset_path = args.dataset_dir / "dataset.jsonl"

    with open(config_path, encoding="utf-8") as config_file:
        # See preprocess.py for format
        config = json.load(config_file)
        num_symbols = int(config["num_symbols"])
        num_speakers = int(config["num_speakers"])
        num_languages = int(config.get("num_languages", 1))
        sample_rate = int(config["audio"]["sample_rate"])

    # Setup loggers (created once and reused across Trainer instances)
    loggers = []

    # TensorBoard logger (always enabled)
    tb_logger = TensorBoardLogger(
        save_dir=args.default_root_dir,
        name="lightning_logs",
    )
    loggers.append(tb_logger)

    # Wandb logger (if available)
    if WANDB_AVAILABLE:
        dataset_name = args.dataset_dir.name
        wandb_logger = WandbLogger(
            project="piper-tts",
            name=dataset_name,
            save_dir=args.default_root_dir,
            log_model=False,
        )
        loggers.append(wandb_logger)
        _LOGGER.info("Wandb logging enabled: project=piper-tts, name=%s", dataset_name)
    else:
        _LOGGER.info("Wandb not available, using TensorBoard only")

    trainer = _build_trainer(args, loggers, num_gpus, num_speakers)

    dict_args = vars(args)

    # CLI --gradient-clip-val (Trainer 用の名前) → VitsModel(grad_clip=...) にマップ
    dict_args["grad_clip"] = _resolve_grad_clip(getattr(args, "gradient_clip_val", 1.0))
    if dict_args["grad_clip"] is not None:
        _LOGGER.info(
            "Gradient clipping enabled in training_step: max_norm=%.2f (manual optimization)",
            dict_args["grad_clip"],
        )

    if args.no_wavlm:
        dict_args["use_wavlm_discriminator"] = False

    # T1: propagate CLI --channels-last (argparse hyphen→underscore) to the
    # VitsModel constructor keyword ``use_channels_last``. argparse names the
    # attribute ``channels_last``; the hparam is ``use_channels_last`` to match
    # the MultiPeriodDiscriminator / DiscriminatorP + MBiSTFTGenerator kwargs.
    # T1 拡張: この 1 個の flag が VitsModel から D 側 (active) と G 側 (silent
    # no-op) の両方に propagate される (対称性 + future-proofing)。
    dict_args["use_channels_last"] = getattr(args, "channels_last", False)
    if dict_args["use_channels_last"]:
        _LOGGER.info(
            "channels_last memory format enabled (--channels-last): "
            "DiscriminatorP Conv2d weights → NHWC (active), MBiSTFTGenerator "
            "Conv1d weights → default layout (silent no-op, future-proofing)."
        )

    # T6: propagate CLI --disc-precision (default "inherit" → no override).
    dict_args["disc_precision"] = getattr(args, "disc_precision", "inherit")
    if dict_args["disc_precision"] != "inherit":
        _LOGGER.info(
            "Hybrid precision enabled (--disc-precision=%s): D forward wraps in "
            "explicit autocast; SCL / DINO / loss compute stay fp32.",
            dict_args["disc_precision"],
        )

    # T3: propagate CLI --attn-drop-rel-v (argparse hyphen→underscore) to
    # the VitsModel constructor keyword ``attn_drop_rel_v``. When True, the
    # TextEncoder self-attention swaps its manual matmul path for
    # F.scaled_dot_product_attention (relative-K bias folded into attn_mask;
    # relative-V correction dropped). Default False = manual path (bit-parity
    # vs prior checkpoints).
    dict_args["attn_drop_rel_v"] = getattr(args, "attn_drop_rel_v", False)
    if dict_args["attn_drop_rel_v"]:
        _LOGGER.info(
            "SDPA fast path enabled for TextEncoder self-attention "
            "(--attn-drop-rel-v): relative-K bias fused into attn_mask, "
            "relative-V correction dropped."
        )

    # Warn about deprecated --spk-emb-dropout
    if getattr(args, "spk_emb_dropout", 0.0) != 0.0:
        _LOGGER.warning(
            "--spk-emb-dropout is deprecated and ignored. Value %.2f will have no effect.",
            args.spk_emb_dropout,
        )

    # Log new training parameters
    _LOGGER.info("Speaker embedding noise sigma: %s", args.spk_emb_noise_sigma)
    _LOGGER.info("D:G update interval: %s", args.d_update_interval)
    _LOGGER.info(
        "LR scheduler: %s (warmup=%d epochs, min_lr=%.1e)",
        args.lr_scheduler,
        args.lr_warmup_epochs,
        args.lr_min,
    )

    # Set learning rate (either scaled or base)
    if hasattr(args, "auto_lr_scaling") and args.auto_lr_scaling and num_gpus > 1:
        dict_args["learning_rate"] = scaled_lr
    else:
        dict_args["learning_rate"] = getattr(args, "base_lr", 2e-4)

    # MB-iSTFT decoder is the only generator path. Total upsample factor is
    # 256x = upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x); the
    # quality preset adjusts resblock complexity and channel count, but not
    # the upsample structure.
    dict_args["upsample_rates"] = (4, 4)
    dict_args["upsample_kernel_sizes"] = (16, 16)

    if args.quality == "x-low":
        dict_args["hidden_channels"] = 96
        dict_args["inter_channels"] = 96
        dict_args["filter_channels"] = 384
    elif args.quality == "high":
        dict_args["resblock"] = "1"
        dict_args["resblock_kernel_sizes"] = (3, 7, 11)
        dict_args["resblock_dilation_sizes"] = (
            (1, 3, 5),
            (1, 3, 5),
            (1, 3, 5),
        )
        dict_args["upsample_initial_channel"] = 512

    apply_transfer_defaults(args, num_speakers, num_languages)

    # num_workers自動調整機能を削除
    # ユーザー指定のnum_workersをそのまま使用する
    # 大規模マルチスピーカーモデルでは共有メモリ制約のため、
    # ユーザーが適切な値を設定する必要がある

    model = VitsModel(
        num_symbols=num_symbols,
        num_speakers=num_speakers,
        num_languages=num_languages,
        sample_rate=sample_rate,
        dataset=[dataset_path],
        **dict_args,
    )

    if getattr(args, "no_compile", False):
        args.compile = False
    if args.compile:
        compile_mode = getattr(args, "compile_mode", "reduce-overhead")
        compile_dynamic = getattr(args, "compile_dynamic", True)
        _LOGGER.info(
            "Compiling model sub-modules with torch.compile(mode=%r, dynamic=%r)",
            compile_mode,
            compile_dynamic,
        )
        # NOTE: dynamic=True disables CUDA Graph capture. When length bucketing
        # (--enable-length-bucketing) fixes shapes within each batch, pass
        # --no-compile-dynamic together with --compile-mode=max-autotune to enable
        # CUDA Graph capture (biggest win for A100/H100). Use
        # max-autotune-no-cudagraphs when kernel autotune is desired without
        # graph capture (dynamic shapes still allowed).
        if hasattr(model, "model_g"):
            model.model_g = torch.compile(
                model.model_g, mode=compile_mode, dynamic=compile_dynamic
            )
        if hasattr(model, "model_d"):
            model.model_d = torch.compile(
                model.model_d, mode=compile_mode, dynamic=compile_dynamic
            )

    if args.resume_from_single_speaker_checkpoint:
        assert num_speakers > 1, (
            "--resume_from_single_speaker_checkpoint is only for multi-speaker models. Use --resume_from_checkpoint for single-speaker models."
        )  # noqa: E501

        # Load single-speaker checkpoint
        _LOGGER.debug(
            "Resuming from single-speaker checkpoint: %s",
            args.resume_from_single_speaker_checkpoint,
        )
        model_single = VitsModel.load_from_checkpoint(
            args.resume_from_single_speaker_checkpoint,
            dataset=None,
        )
        g_dict = model_single.model_g.state_dict()
        # NOTE: cond 層 (dec.cond, dp.cond, enc.cond_layer 等) は
        # single/multi-speaker どちらも gin_channels=512 で形状が同一のため
        # 除外不要。全重みを転移してよい。

        # Copy over the single-speaker weights; keys missing in g_dict
        # (e.g. emb_g of the multi-speaker target) will keep their
        # randomly-initialized values.
        load_state_dict(model.model_g, g_dict)
        load_state_dict(model.model_d, model_single.model_d.state_dict())
        _LOGGER.info(
            "Successfully converted single-speaker checkpoint to multi-speaker"
        )

    if args.resume_from_multispeaker_checkpoint:
        assert num_speakers == 1, (
            "--resume-from-multispeaker-checkpoint はシングルスピーカーモデル専用です。"
            "マルチスピーカーへの転移には --resume_from_single_speaker_checkpoint を使用してください。"
        )
        _LOGGER.info(
            "Resuming from multispeaker checkpoint: %s",
            args.resume_from_multispeaker_checkpoint,
        )

        # This used to be an inline copy of `load_multispeaker_checkpoint`,
        # which left the function itself unreachable — and the two had already
        # drifted apart (only the function rejected HiFi-GAN checkpoints, only
        # the inline copy remapped weight_norm keys). One implementation now.
        load_multispeaker_checkpoint(args.resume_from_multispeaker_checkpoint, model)

    if getattr(args, "resume_weights_only", None):
        load_weights_only_checkpoint(args.resume_weights_only, model)
        _LOGGER.info(
            "Warm restart: starting fresh training run (epoch 0, new optimizer / "
            "LR schedule) from loaded weights."
        )

    if getattr(args, "reinit_pqmf", False):
        if not getattr(args, "resume_weights_only", None):
            raise SystemExit(
                "--reinit-pqmf は --resume-weights-only と併用してください。"
                "strict resume (--resume_from_checkpoint) は fit 開始後に "
                "checkpoint の buffer を復元するため、再初期化が黙って旧バンクに"
                "巻き戻されます。"
            )
        reinit_pqmf_bank(model)

    # チェックポイントからの再開処理を修正
    if args.resume_from_checkpoint:
        _LOGGER.debug(
            "Loading weights from checkpoint: %s", args.resume_from_checkpoint
        )
        try:
            # まずは通常のResumeを試みる
            trainer.fit(model, ckpt_path=args.resume_from_checkpoint)
        except (RuntimeError, KeyError, NotImplementedError, UnpicklingError) as e:
            # RuntimeError (size mismatchなど) や KeyError (optimizer stateなし) が発生した場合
            _LOGGER.warning("Graceful resume failed with error: %s", e)
            _LOGGER.info("Attempting to load weights only (strict=False)...")

            # モデルの重みだけをロードする (不一致は許容)
            # NOTE: weights_only=False is required to handle PosixPath objects in checkpoints
            # This poses a security risk - only load trusted checkpoints
            checkpoint = torch.load(
                args.resume_from_checkpoint, map_location="cpu", weights_only=False
            )
            normalized_sd, _ = normalize_checkpoint_state_dict(
                checkpoint["state_dict"],
                model.state_dict(),
                checkpoint_path=args.resume_from_checkpoint,
            )
            model.load_state_dict(normalized_sd, strict=False)

            _LOGGER.warning(
                "Weights were loaded with strict=False, but optimizer state and "
                "epoch counter are NOT restored: training restarts from epoch 0. "
                "If this checkpoint was meant to continue a run, stop here and "
                "investigate the error above instead of letting it retrain."
            )

            # argsからresume_from_checkpointを削除
            args_dict = vars(args)
            if "resume_from_checkpoint" in args_dict:
                del args_dict["resume_from_checkpoint"]

            # 新しいTrainerインスタンスを作成（ckpt_pathをクリアするため）
            trainer = _build_trainer(args, loggers, num_gpus, num_speakers)

            # 新しいTrainerで学習を開始
            trainer.fit(model)
    else:
        # チェックポイントが指定されていない場合は、通常通り学習を開始
        trainer.fit(model)


def load_state_dict(model, saved_state_dict):
    state_dict = model.state_dict()
    saved_state_dict = remap_weight_norm_keys(saved_state_dict, state_dict)
    new_state_dict = {}

    for k, v in state_dict.items():
        if k in saved_state_dict:
            # Use saved value
            new_state_dict[k] = saved_state_dict[k]
        else:
            # Use initialized value
            _LOGGER.debug("%s is not in the checkpoint", k)
            new_state_dict[k] = v

    model.load_state_dict(new_state_dict)


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    main()
