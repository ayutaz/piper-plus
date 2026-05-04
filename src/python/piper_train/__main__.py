import argparse
import json
import logging
import pathlib
import platform
from pathlib import Path

import torch
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from pytorch_lightning.strategies import DDPStrategy

from .vits.ema import EMACallback
from .vits.lightning import VitsModel


# Allow Path objects in checkpoints (PyTorch 2.6+ weights_only=True)
torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])

# Fix PosixPath instantiation error when loading Linux checkpoints on Windows
if platform.system() == "Windows":
    pathlib.PosixPath = pathlib.WindowsPath

# Optional wandb integration
try:
    from pytorch_lightning.loggers import WandbLogger  # noqa: PLC0415

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False


_LOGGER = logging.getLogger(__package__)


def _is_legacy_hifigan_checkpoint(state_dict: dict) -> bool:
    """v1.11.0 以前の HiFi-GAN ベース ckpt を検出する。

    v1.12.0 で Decoder は MB-iSTFT-VITS2 に統一された。MB-iSTFT decoder は
    ``model_g.dec.subband_conv_post.*`` または ``model_g.dec.pqmf.*`` を持つが、
    HiFi-GAN decoder にはこれらが存在しない。decoder 系キーがあるのに
    MB-iSTFT のマーカーが無い場合、HiFi-GAN ckpt とみなす。
    """
    has_decoder_keys = any(k.startswith("model_g.dec.") for k in state_dict)
    has_mbistft_marker = any(
        k.startswith("model_g.dec.subband_conv_post")
        or k.startswith("model_g.dec.pqmf")
        for k in state_dict
    )
    return has_decoder_keys and not has_mbistft_marker


_LEGACY_HIFIGAN_MESSAGE = (
    "Checkpoint {path!r} appears to be from v1.11.0 or earlier (HiFi-GAN Generator). "
    "v1.12.0 unified the decoder to MB-iSTFT-VITS2, so HiFi-GAN ckpt files cannot be "
    "resumed for training. Fine-tune from the new MB-iSTFT base model instead:\n"
    "    https://huggingface.co/ayousanz/piper-plus-base/resolve/main/model.ckpt\n"
    "See docs/migration/v1.11-to-v1.12.md for the full migration guide."
)


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
        ddp_kwargs = {
            "find_unused_parameters": True,
            "gradient_as_bucket_view": True,
        }
        _LOGGER.info(
            "Using DDPStrategy with find_unused_parameters=True, gradient_as_bucket_view=True"
        )
        return DDPStrategy(**ddp_kwargs)
    return None


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
        "--precision",
        default="16-mixed",
        choices=("32-true", "16-mixed", "bf16-mixed"),
        help="Floating point precision (default: 16-mixed for faster training with minimal quality impact)",
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
        "--max_epochs", type=int, default=1000, help="Maximum number of epochs"
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
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Enable torch.compile() for potential training speedup (requires PyTorch 2.0+)",
    )
    parser.add_argument("--seed", type=int, default=1234)
    return parser


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
    if _is_legacy_hifigan_checkpoint(checkpoint["state_dict"]):
        raise RuntimeError(_LEGACY_HIFIGAN_MESSAGE.format(path=str(checkpoint_path)))
    missing, unexpected = model.load_state_dict(checkpoint["state_dict"], strict=False)
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

    args.dataset_dir = Path(args.dataset_dir)

    # Set default values for Trainer arguments
    if not args.default_root_dir:
        args.default_root_dir = args.dataset_dir

    torch.backends.cudnn.benchmark = True
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

    if args.no_wavlm:
        dict_args["use_wavlm_discriminator"] = False

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

    if args.compile:
        _LOGGER.info(
            "Compiling model sub-modules with torch.compile(mode='reduce-overhead', dynamic=True)"
        )
        if hasattr(model, "model_g"):
            model.model_g = torch.compile(
                model.model_g, mode="reduce-overhead", dynamic=True
            )
        if hasattr(model, "model_d"):
            model.model_d = torch.compile(
                model.model_d, mode="reduce-overhead", dynamic=True
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
        load_multispeaker_checkpoint(args.resume_from_multispeaker_checkpoint, model)

    # チェックポイントからの再開処理を修正
    if args.resume_from_checkpoint:
        _LOGGER.debug(
            "Loading weights from checkpoint: %s", args.resume_from_checkpoint
        )
        try:
            # まずは通常のResumeを試みる
            trainer.fit(model, ckpt_path=args.resume_from_checkpoint)
        except (RuntimeError, KeyError, NotImplementedError) as e:
            # RuntimeError (size mismatchなど) や KeyError (optimizer stateなし) が発生した場合
            _LOGGER.warning("Graceful resume failed with error: %s", e)
            _LOGGER.info("Attempting to load weights only (strict=False)...")

            # モデルの重みだけをロードする (不一致は許容)
            # NOTE: weights_only=False is required to handle PosixPath objects in checkpoints
            # This poses a security risk - only load trusted checkpoints
            checkpoint = torch.load(
                args.resume_from_checkpoint, map_location="cpu", weights_only=False
            )
            if _is_legacy_hifigan_checkpoint(checkpoint["state_dict"]):
                raise RuntimeError(
                    _LEGACY_HIFIGAN_MESSAGE.format(
                        path=str(args.resume_from_checkpoint)
                    )
                ) from None
            model.load_state_dict(checkpoint["state_dict"], strict=False)

            _LOGGER.info(
                "Weights loaded successfully with strict=False. Starting training without resuming optimizer state."  # noqa: E501
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
