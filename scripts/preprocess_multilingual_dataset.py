#!/usr/bin/env python3
"""
Preprocess multilingual datasets for VITS training.
Handles multiple language datasets and creates a unified multilingual dataset.
"""

import argparse
import json
import logging
import shutil
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class MultilingualDatasetPreprocessor:
    """Preprocessor for creating multilingual datasets."""

    def __init__(self, output_dir: Path, cache_dir: Path | None = None):
        self.output_dir = output_dir
        self.cache_dir = cache_dir or output_dir / "cache"
        self.dataset_info = {
            "languages": [],
            "speakers": {},
            "utterance_counts": {},
            "total_duration": 0.0,
        }

    def preprocess_datasets(
        self,
        dataset_configs: list[dict],
        sample_rate: int = 22050,
        max_workers: int = 4,
        phoneme_type: str = "multilingual",
        dataset_format: str = "ljspeech",
    ) -> Path:
        """
        Preprocess multiple language datasets into a unified multilingual dataset.

        Args:
            dataset_configs: List of dataset configurations
            sample_rate: Target sample rate
            max_workers: Number of parallel workers
            phoneme_type: Type of phonemization (should be "multilingual")
            dataset_format: Format of input datasets

        Returns:
            Path to the output directory
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        temp_outputs = []

        # Process each language dataset
        for config in dataset_configs:
            language = config["language"]
            input_dir = Path(config["input_dir"])
            speaker_id_offset = config.get("speaker_id_offset", 0)

            _LOGGER.info(f"Processing {language} dataset from {input_dir}")

            # Create temporary output directory for this language
            temp_output = self.output_dir / f"temp_{language}"
            temp_output.mkdir(exist_ok=True)

            # Run preprocessing for this language
            cmd = [
                "python", "-m", "piper_train.preprocess",
                "--input-dir", str(input_dir),
                "--output-dir", str(temp_output),
                "--language", language,
                "--sample-rate", str(sample_rate),
                "--dataset-format", dataset_format,
                "--max-workers", str(max_workers),
                "--cache-dir", str(self.cache_dir),
                "--multilingual",  # Enable multilingual mode
            ]

            # Add speaker ID offset if multi-speaker
            if speaker_id_offset > 0:
                cmd.extend(["--speaker-id", str(speaker_id_offset)])

            # Execute preprocessing
            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: PLW1510

            if result.returncode != 0:
                _LOGGER.error(f"Failed to preprocess {language}: {result.stderr}")
                continue

            _LOGGER.info(f"Successfully preprocessed {language}")
            temp_outputs.append((language, temp_output))

            # Update dataset info
            self.dataset_info["languages"].append(language)

        # Merge all preprocessed datasets
        _LOGGER.info("Merging preprocessed datasets...")
        merged_dataset_path = self._merge_datasets(temp_outputs)

        # Clean up temporary directories
        for _, temp_output in temp_outputs:
            shutil.rmtree(temp_output, ignore_errors=True)

        # Create final configuration
        self._create_final_config(sample_rate)

        return merged_dataset_path

    def _merge_datasets(self, temp_outputs: list[tuple[str, Path]]) -> Path:
        """Merge multiple preprocessed datasets into one."""
        merged_dataset_path = self.output_dir / "dataset.jsonl"
        merged_validation_path = self.output_dir / "validation.jsonl"

        all_utterances = []
        all_validation = []
        speaker_mapping = {}
        current_speaker_id = 0

        for language, temp_output in temp_outputs:
            dataset_path = temp_output / "dataset.jsonl"
            validation_path = temp_output / "validation.jsonl"

            # Process training data
            if dataset_path.exists():
                with open(dataset_path, encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue

                        utt = json.loads(line)

                        # Update speaker ID mapping
                        original_speaker_id = utt.get("speaker_id", 0)
                        speaker_key = f"{language}_{original_speaker_id}"

                        if speaker_key not in speaker_mapping:
                            speaker_mapping[speaker_key] = current_speaker_id
                            current_speaker_id += 1

                        utt["speaker_id"] = speaker_mapping[speaker_key]

                        # Add language metadata
                        utt["primary_language"] = language
                        if "text_language" not in utt:
                            utt["text_language"] = language

                        all_utterances.append(utt)

            # Process validation data
            if validation_path.exists():
                with open(validation_path, encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue

                        utt = json.loads(line)

                        # Apply same speaker mapping
                        original_speaker_id = utt.get("speaker_id", 0)
                        speaker_key = f"{language}_{original_speaker_id}"
                        utt["speaker_id"] = speaker_mapping.get(speaker_key, 0)

                        # Add language metadata
                        utt["primary_language"] = language
                        if "text_language" not in utt:
                            utt["text_language"] = language

                        all_validation.append(utt)

        # Write merged datasets
        with open(merged_dataset_path, "w", encoding="utf-8") as f:
            for utt in all_utterances:
                json.dump(utt, f, ensure_ascii=False)
                f.write("\n")

        if all_validation:
            with open(merged_validation_path, "w", encoding="utf-8") as f:
                for utt in all_validation:
                    json.dump(utt, f, ensure_ascii=False)
                    f.write("\n")

        # Update dataset info
        self.dataset_info["speakers"] = speaker_mapping
        self.dataset_info["utterance_counts"]["train"] = len(all_utterances)
        self.dataset_info["utterance_counts"]["validation"] = len(all_validation)

        _LOGGER.info(f"Merged {len(all_utterances)} training utterances")
        _LOGGER.info(f"Merged {len(all_validation)} validation utterances")
        _LOGGER.info(f"Total speakers: {len(speaker_mapping)}")

        return merged_dataset_path

    def _create_final_config(self, sample_rate: int):
        """Create the final configuration file."""
        # Load phoneme mapping
        phoneme_map_path = self.output_dir / "temp_ja" / "phoneme_map.json"
        if not phoneme_map_path.exists():
            # Use the first available phoneme map
            for lang in self.dataset_info["languages"]:
                temp_path = self.output_dir / f"temp_{lang}" / "phoneme_map.json"
                if temp_path.exists():
                    phoneme_map_path = temp_path
                    break

        # Copy phoneme map
        if phoneme_map_path.exists():
            shutil.copy(phoneme_map_path, self.output_dir / "phoneme_map.json")

        # Create config
        config = {
            "dataset": "multilingual",
            "audio": {
                "quality": "medium",
                "sample_rate": sample_rate,
                "channels": 1,
            },
            "num_speakers": len(self.dataset_info["speakers"]),
            "languages": self.dataset_info["languages"],
            "multilingual": True,
            "phoneme_config": {
                "phoneme_type": "multilingual",
                "phoneme_map": "multilingual",
                "vocab_size": 132,  # From our implementation
                "language_tags": True,
            },
            "phoneme_id_map": {},  # Will be loaded from phoneme_map.json
            "num_symbols": 512,  # Safe upper bound
            "speaker_id_map": self.dataset_info["speakers"],
            "utterance_counts": self.dataset_info["utterance_counts"],
        }

        config_path = self.output_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        _LOGGER.info(f"Created config at {config_path}")


def create_dataset_config(
    language: str,
    input_dir: str,
    speaker_id_offset: int = 0,
    max_utterances: int | None = None,
) -> dict:
    """Create a dataset configuration."""
    return {
        "language": language,
        "input_dir": input_dir,
        "speaker_id_offset": speaker_id_offset,
        "max_utterances": max_utterances,
    }


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Preprocess multilingual datasets for VITS training"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for the merged dataset",
    )
    parser.add_argument(
        "--config-file",
        type=Path,
        help="JSON configuration file with dataset paths",
    )
    parser.add_argument(
        "--japanese-dir",
        type=Path,
        help="Directory containing Japanese dataset (LJSpeech format)",
    )
    parser.add_argument(
        "--english-dir",
        type=Path,
        help="Directory containing English dataset (LJSpeech format)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=22050,
        help="Target sample rate (default: 22050)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--dataset-format",
        choices=["ljspeech", "mycroft"],
        default="ljspeech",
        help="Format of input datasets (default: ljspeech)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Directory to cache audio files",
    )

    args = parser.parse_args()

    # Prepare dataset configurations
    dataset_configs = []

    if args.config_file:
        # Load from configuration file
        with open(args.config_file, encoding="utf-8") as f:
            config_data = json.load(f)
            dataset_configs = config_data["datasets"]
    else:
        # Use command line arguments
        if args.japanese_dir:
            dataset_configs.append(
                create_dataset_config("ja", str(args.japanese_dir), 0)
            )

        if args.english_dir:
            dataset_configs.append(
                create_dataset_config("en", str(args.english_dir), 100)
            )

    if not dataset_configs:
        parser.error("No datasets specified. Use --config-file or --japanese-dir/--english-dir")

    # Create preprocessor
    preprocessor = MultilingualDatasetPreprocessor(
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
    )

    # Process datasets
    _LOGGER.info(f"Processing {len(dataset_configs)} datasets...")
    preprocessor.preprocess_datasets(
        dataset_configs=dataset_configs,
        sample_rate=args.sample_rate,
        max_workers=args.max_workers,
        dataset_format=args.dataset_format,
    )

    print(f"\nMultilingual dataset created at: {args.output_dir}")
    print(f"Languages: {', '.join(preprocessor.dataset_info['languages'])}")
    print(f"Total utterances: {preprocessor.dataset_info['utterance_counts']['train']}")
    print(f"Total speakers: {len(preprocessor.dataset_info['speakers'])}")

    print("\nTo train the model, run:")
    print("python -m piper_train.train_multilingual \\")
    print(f"  --dataset-dir {args.output_dir} \\")
    print("  --max_epochs 1000 \\")
    print("  --batch-size 16")


if __name__ == "__main__":
    main()
