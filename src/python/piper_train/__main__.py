import argparse
import json
import logging
from pathlib import Path

import torch
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint

from .vits.lightning import VitsModel

_LOGGER = logging.getLogger(__package__)


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
    # Trainer arguments (previously added by Trainer.add_argparse_args)
    parser.add_argument("--accelerator", default="auto", help="Accelerator to use")
    parser.add_argument("--devices", type=int, default=1, help="Number of devices")
    parser.add_argument("--max_epochs", type=int, default=1000, help="Maximum number of epochs")
    parser.add_argument("--precision", default="32-true", help="Training precision")
    parser.add_argument("--accumulate_grad_batches", type=int, default=1, help="Accumulate gradients over k batches")
    parser.add_argument("--gradient_clip_val", type=float, default=None, help="Gradient clipping value")
    parser.add_argument("--val_check_interval", type=float, default=1.0, help="How often to check the validation set")
    parser.add_argument("--log_every_n_steps", type=int, default=50, help="How often to log within steps")
    parser.add_argument("--default_root_dir", type=str, default=None, help="Default path for logs and weights")
    parser.add_argument("--fast_dev_run", action="store_true", help="Run a fast development run")
    parser.add_argument("--strategy", type=str, default=None, help="Training strategy (e.g., ddp, ddp_spawn)")
    parser.add_argument("--enable_progress_bar", action="store_true", default=True, help="Enable progress bar")
    parser.add_argument("--detect_anomaly", action="store_true", help="Enable anomaly detection")
    
    VitsModel.add_model_specific_args(parser)
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()
    _LOGGER.debug(args)

    args.dataset_dir = Path(args.dataset_dir)
    if not args.default_root_dir:
        args.default_root_dir = args.dataset_dir

    torch.backends.cudnn.benchmark = True
    torch.manual_seed(args.seed)

    config_path = args.dataset_dir / "config.json"
    dataset_path = args.dataset_dir / "dataset.jsonl"

    with open(config_path, encoding="utf-8") as config_file:
        # See preprocess.py for format
        config = json.load(config_file)
        num_symbols = int(config["num_symbols"])
        num_speakers = int(config["num_speakers"])
        sample_rate = int(config["audio"]["sample_rate"])

    # Create trainer manually (replacing Trainer.from_argparse_args)
    trainer_kwargs = {
        "accelerator": args.accelerator,
        "devices": args.devices,
        "max_epochs": args.max_epochs,
        "precision": args.precision,
        "accumulate_grad_batches": args.accumulate_grad_batches,
        "gradient_clip_val": args.gradient_clip_val,
        "val_check_interval": args.val_check_interval,
        "log_every_n_steps": args.log_every_n_steps,
        "default_root_dir": args.default_root_dir or args.dataset_dir,
        "fast_dev_run": args.fast_dev_run,
        "enable_progress_bar": args.enable_progress_bar,
        "detect_anomaly": args.detect_anomaly,
    }
    
    # Add strategy if specified
    if args.strategy:
        trainer_kwargs["strategy"] = args.strategy
    
    # Configure callbacks
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
    
    if callbacks:
        trainer_kwargs["callbacks"] = callbacks
    
    trainer = Trainer(**trainer_kwargs)

    dict_args = vars(args)
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

    model = VitsModel(
        num_symbols=num_symbols,
        num_speakers=num_speakers,
        sample_rate=sample_rate,
        dataset=[dataset_path],
        **dict_args,
    )

    if args.resume_from_single_speaker_checkpoint:
        assert (
            num_speakers > 1
        ), "--resume_from_single_speaker_checkpoint is only for multi-speaker models. Use --resume_from_checkpoint for single-speaker models."  # noqa: E501

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
            checkpoint = torch.load(args.resume_from_checkpoint, map_location="cpu")
            model.load_state_dict(checkpoint["state_dict"], strict=False)

            _LOGGER.info(
                "Weights loaded successfully with strict=False. Starting training without resuming optimizer state."  # noqa: E501
            )

            # argsからresume_from_checkpointを削除
            args_dict = vars(args)
            if "resume_from_checkpoint" in args_dict:
                del args_dict["resume_from_checkpoint"]

            # 新しいTrainerインスタンスを作成（ckpt_pathをクリアするため）
            # Create new trainer without checkpoint path
            new_trainer_kwargs = trainer_kwargs.copy()
            new_callbacks = []
            if args.checkpoint_epochs is not None:
                new_callbacks.append(
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
            if new_callbacks:
                new_trainer_kwargs["callbacks"] = new_callbacks
            
            trainer = Trainer(**new_trainer_kwargs)

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
