import argparse
import json
import logging
from pathlib import Path

import torch
import pathlib
torch.serialization.add_safe_globals([pathlib.PosixPath])
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from pytorch_lightning.strategies import DDPStrategy


# Optional wandb integration
try:
    from pytorch_lightning.loggers import WandbLogger

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

from .vits.ema import EMACallback
from .vits.lightning import VitsModel


_LOGGER = logging.getLogger(__package__)


def calculate_effective_batch_size(batch_size, num_gpus=1):
    """Calculate effective batch size for multi-GPU training."""
    return batch_size * num_gpus


def calculate_learning_rate(base_lr, effective_batch_size, base_batch_size=16):
    """Calculate learning rate with linear scaling for multi-GPU training."""
    return base_lr * (effective_batch_size / base_batch_size)


def configure_ddp_strategy(num_gpus, user_strategy=None):
    """Configure DDP strategy for multi-GPU training.

    Args:
        num_gpus: Number of GPUs to use
        user_strategy: User-specified strategy (optional)

    Returns:
        Strategy configuration or None
    """
    if user_strategy:
        _LOGGER.info(f"Using user-specified strategy: {user_strategy}")
        return user_strategy
    elif num_gpus >= 2:
        _LOGGER.info(
            "Using optimized DDPStrategy with gradient_as_bucket_view=True for memory efficiency"
        )
        return DDPStrategy(
            find_unused_parameters=True,
            gradient_as_bucket_view=True,
        )
    return None


def main():
    logging.basicConfig(level=logging.DEBUG)

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
        "--precision",
        default="16-mixed",
        choices=("32-true", "16-mixed", "bf16-mixed"),
        help="Floating point precision (default: 16-mixed for faster training with minimal quality impact)",
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
    parser.add_argument("--seed", type=int, default=1234)
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

    # Setup callbacks
    callbacks = []
    if args.checkpoint_epochs is not None:
        callbacks.append(
            ModelCheckpoint(
                every_n_epochs=args.checkpoint_epochs,
                save_top_k=args.save_top_k,
                save_last=True,
            )
        )
        _LOGGER.debug(
            "Checkpoints will be saved every %s epoch(s)", args.checkpoint_epochs
        )

    # EMA is enabled by default
    if not args.no_ema:
        callbacks.append(EMACallback(decay=args.ema_decay))
        _LOGGER.info("Using EMA with decay rate %s", args.ema_decay)
    else:
        _LOGGER.info("EMA disabled by user request")

    # Setup loggers
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

    trainer_kwargs = {
        "accelerator": args.accelerator,
        "devices": args.devices,
        "precision": args.precision,
        "max_epochs": args.max_epochs,
        "callbacks": callbacks,
        "default_root_dir": args.default_root_dir,
        "logger": loggers,
    }

    # Multi-GPU DDP optimization
    # Use DDPStrategy with gradient_as_bucket_view=True for memory efficiency
    # find_unused_parameters=True is required for GAN training (Generator/Discriminator alternate)
    strategy = configure_ddp_strategy(num_gpus, args.strategy)
    if strategy:
        trainer_kwargs["strategy"] = strategy

    # When using SpeakerBalancedBatchSampler, disable Lightning's automatic distributed sampler
    # The batch sampler handles DDP-awareness internally
    if args.samples_per_speaker > 0 and num_speakers > 1:
        trainer_kwargs["use_distributed_sampler"] = False
        _LOGGER.info("Disabled distributed sampler for SpeakerBalancedBatchSampler")

    trainer = Trainer(**trainer_kwargs)

    dict_args = vars(args)

    if args.no_wavlm:
        dict_args["use_wavlm_discriminator"] = False

    # Set learning rate (either scaled or base)
    if hasattr(args, "auto_lr_scaling") and args.auto_lr_scaling and num_gpus > 1:
        dict_args["learning_rate"] = scaled_lr
    else:
        dict_args["learning_rate"] = getattr(args, "base_lr", 2e-4)

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
        dict_args["upsample_rates"] = (8, 8, 2, 2)
        dict_args["upsample_initial_channel"] = 512
        dict_args["upsample_kernel_sizes"] = (16, 16, 4, 4)

    # マルチスピーカーモデルの場合、gin_channelsを768に設定（品質向上のため）
    if num_speakers > 1 and "gin_channels" not in dict_args:
        dict_args["gin_channels"] = 768

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
        for key in list(g_dict.keys()):
            # Remove keys that can't be copied over due to missing speaker embedding
            if (
                key.startswith("dec.cond")
                or key.startswith("dp.cond")
                or ("enc.cond_layer" in key)
            ):
                g_dict.pop(key, None)

        # Copy over the multi-speaker model, excluding keys related to the
        # speaker embedding (which is missing from the single-speaker model).
        load_state_dict(model.model_g, g_dict)
        load_state_dict(model.model_d, model_single.model_d.state_dict())
        _LOGGER.info(
            "Successfully converted single-speaker checkpoint to multi-speaker"
        )

    # チェックポイントからの再開処理を修正
    if args.resume_from_checkpoint:
        _LOGGER.debug(
            "Loading weights from checkpoint: %s", args.resume_from_checkpoint
        )
        try:
            # まずは通常のResumeを試みる
            trainer.fit(model, ckpt_path=args.resume_from_checkpoint)
        except (RuntimeError, KeyError) as e:
            # RuntimeError (size mismatchなど) や KeyError (optimizer stateなし) が発生した場合
            _LOGGER.warning("Graceful resume failed with error: %s", e)
            _LOGGER.info("Attempting to load weights only (strict=False)...")

            # モデルの重みだけをロードする (不一致は許容)
            # NOTE: weights_only=False is required to handle PosixPath objects in checkpoints
            # This poses a security risk - only load trusted checkpoints
            checkpoint = torch.load(
                args.resume_from_checkpoint, map_location="cpu", weights_only=False
            )
            model.load_state_dict(checkpoint["state_dict"], strict=False)

            _LOGGER.info(
                "Weights loaded successfully with strict=False. Starting training without resuming optimizer state."  # noqa: E501
            )

            # argsからresume_from_checkpointを削除
            args_dict = vars(args)
            if "resume_from_checkpoint" in args_dict:
                del args_dict["resume_from_checkpoint"]

            # 新しいTrainerインスタンスを作成（ckpt_pathをクリアするため）
            # Setup callbacks
            callbacks = []
            if args.checkpoint_epochs is not None:
                callbacks.append(
                    ModelCheckpoint(
                        every_n_epochs=args.checkpoint_epochs,
                        save_top_k=args.save_top_k,
                        save_last=True,
                    )
                )
                _LOGGER.debug(
                    "Checkpoints will be saved every %s epoch(s)",
                    args.checkpoint_epochs,
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
            }

            # Multi-GPU DDP optimization
            strategy = configure_ddp_strategy(num_gpus, args.strategy)
            if strategy:
                trainer_kwargs["strategy"] = strategy

            # When using SpeakerBalancedBatchSampler, disable Lightning's automatic distributed sampler
            if args.samples_per_speaker > 0 and num_speakers > 1:
                trainer_kwargs["use_distributed_sampler"] = False

            trainer = Trainer(**trainer_kwargs)

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
