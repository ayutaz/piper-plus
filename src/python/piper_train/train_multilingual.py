#!/usr/bin/env python3
"""
Training script for multilingual VITS model.
Supports training on mixed Japanese (OpenJTalk) and other language (espeak-ng) data.
"""

import argparse
import json
import logging
from pathlib import Path

import torch
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint

from .vits.lightning_multilingual import MultilingualVitsModel

_LOGGER = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Train multilingual VITS model")
    parser.add_argument(
        "--dataset-dir",
        required=True,
        help="Path to pre-processed multilingual dataset directory",
    )
    parser.add_argument(
        "--checkpoint-epochs",
        type=int,
        help="Save checkpoint every N epochs (default: 1)",
    )
    parser.add_argument(
        "--quality",
        default="medium",
        choices=("x-low", "low", "medium", "high"),
        help="Quality/size of model (default: medium)",
    )
    parser.add_argument(
        "--num-languages",
        type=int,
        default=8,
        help="Maximum number of languages to support (default: 8)",
    )
    parser.add_argument(
        "--lang-embedding-dim",
        type=int,
        default=64,
        help="Dimension of language embeddings (default: 64)",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        help="Resume training from checkpoint",
    )
    parser.add_argument(
        "--convert-from-single-lang",
        help="Convert a single-language checkpoint to multilingual and resume training",
    )
    parser.add_argument(
        "--save-top-k",
        type=int,
        default=-1,
        help="Save top k checkpoints (-1 to save all).",
    )

    # Add PyTorch Lightning Trainer arguments
    Trainer.add_argparse_args(parser)

    # Add model-specific arguments
    MultilingualVitsModel.add_model_specific_args(parser)

    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()
    _LOGGER.debug(args)

    args.dataset_dir = Path(args.dataset_dir)
    if not args.default_root_dir:
        args.default_root_dir = args.dataset_dir

    torch.backends.cudnn.benchmark = True
    torch.manual_seed(args.seed)

    # Load dataset configuration
    config_path = args.dataset_dir / "config.json"
    dataset_path = args.dataset_dir / "dataset.jsonl"

    # Also check for validation dataset
    validation_path = args.dataset_dir / "validation.jsonl"
    dataset_paths = [dataset_path]
    if validation_path.exists():
        dataset_paths.append(validation_path)

    with open(config_path, encoding="utf-8") as config_file:
        config = json.load(config_file)

        # Check if this is a multilingual dataset
        if not config.get("multilingual", False):
            _LOGGER.warning(
                "Dataset does not appear to be multilingual. Consider using standard training script."
            )

        num_symbols = int(config["num_symbols"])
        num_speakers = int(config["num_speakers"])
        sample_rate = int(config["audio"]["sample_rate"])

        # Get language information
        languages = config.get("languages", ["ja", "en"])
        language_map = {lang: idx for idx, lang in enumerate(languages)}

        # Add "mixed" language for code-switching
        if "mixed" not in language_map:
            language_map["mixed"] = len(language_map)

        _LOGGER.info(f"Languages in dataset: {languages}")
        _LOGGER.info(f"Language mapping: {language_map}")

    # Set up trainer
    trainer = Trainer.from_argparse_args(args)
    if args.checkpoint_epochs is not None:
        trainer.callbacks = [
            ModelCheckpoint(
                every_n_epochs=args.checkpoint_epochs, save_top_k=args.save_top_k
            )
        ]
        _LOGGER.debug(
            "Checkpoints will be saved every %s epoch(s)", args.checkpoint_epochs
        )

    # Adjust model parameters based on quality setting
    dict_args = vars(args)
    if args.quality == "x-low":
        dict_args["hidden_channels"] = 96
        dict_args["inter_channels"] = 96
        dict_args["filter_channels"] = 384
        dict_args["lang_embedding_dim"] = 32
    elif args.quality == "low":
        dict_args["hidden_channels"] = 128
        dict_args["inter_channels"] = 128
        dict_args["filter_channels"] = 512
        dict_args["lang_embedding_dim"] = 48
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
        dict_args["lang_embedding_dim"] = 128

    # Create model
    model = MultilingualVitsModel(
        num_symbols=num_symbols,
        num_speakers=num_speakers,
        num_languages=args.num_languages,
        sample_rate=sample_rate,
        dataset=dataset_paths,
        language_map=language_map,
        **dict_args,
    )

    # Handle checkpoint conversion if needed
    if args.convert_from_single_lang:
        _LOGGER.info(
            f"Converting single-language checkpoint: {args.convert_from_single_lang}"
        )

        # Load single-language checkpoint
        checkpoint = torch.load(args.convert_from_single_lang, map_location="cpu")
        state_dict = checkpoint["state_dict"]

        # Initialize multilingual model state dict
        ml_state_dict = model.state_dict()

        # Copy compatible weights
        for key, value in state_dict.items():
            if key in ml_state_dict and ml_state_dict[key].shape == value.shape:
                ml_state_dict[key] = value
                _LOGGER.debug(f"Copied weight: {key}")
            else:
                _LOGGER.debug(f"Skipped weight: {key}")

        # Load the modified state dict
        model.load_state_dict(ml_state_dict, strict=False)
        _LOGGER.info("Checkpoint conversion completed")

    # Train model
    if args.resume_from_checkpoint or args.convert_from_single_lang:
        trainer.fit(
            model,
            ckpt_path=args.resume_from_checkpoint
            if args.resume_from_checkpoint
            else None,
        )
    else:
        trainer.fit(model)


if __name__ == "__main__":
    main()
