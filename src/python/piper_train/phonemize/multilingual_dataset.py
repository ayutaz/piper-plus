#!/usr/bin/env python3
"""Dataset formatter for multilingual TTS training."""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


try:
    from .multilingual import Language, MultilingualPhonemizer
    from .multilingual_phoneme_map import get_multilingual_phoneme_mapper
except ImportError:
    from piper_train.phonemize.multilingual import (
        Language,
        MultilingualPhonemizer,
    )
    from piper_train.phonemize.multilingual_phoneme_map import (
        get_multilingual_phoneme_mapper,
    )

_LOGGER = logging.getLogger(__name__)


@dataclass
class MultilingualUtterance:
    """Represents a single utterance in the multilingual dataset."""

    audio_path: str
    text: str
    text_language: str  # "mixed", "ja", "en", etc.
    segments: list[dict[str, Any]]  # Language segments
    phonemes: list[str]
    phoneme_ids: list[int]
    duration: float
    speaker_id: int = 0
    metadata: dict[str, Any] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Ensure metadata is a dict
        if data["metadata"] is None:
            data["metadata"] = {}
        return data


class MultilingualDatasetFormatter:
    """Formats utterances for multilingual TTS training."""

    def __init__(self):
        self.phonemizer = MultilingualPhonemizer()
        self.phoneme_mapper = get_multilingual_phoneme_mapper()

    def format_utterance(
        self,
        text: str,
        audio_path: str,
        duration: float,
        speaker_id: int = 0,
        primary_language: str | None = None,
    ) -> MultilingualUtterance:
        """
        Format a single utterance for the dataset.

        Args:
            text: Input text
            audio_path: Path to audio file
            duration: Audio duration in seconds
            speaker_id: Speaker ID (for multi-speaker models)
            primary_language: Primary language hint (optional)

        Returns:
            MultilingualUtterance object
        """
        # Convert language code to enum
        lang_enum = None
        if primary_language:
            try:
                lang_enum = Language(primary_language)
            except ValueError:
                _LOGGER.warning(f"Unknown language: {primary_language}")

        # Detect language segments
        segments = self.phonemizer.language_detector.split_mixed_text(text)

        # Override detected language if primary language is specified
        if lang_enum and len(segments) == 1:
            segments[0].language = lang_enum

        # Convert segments to dict format
        segment_dicts = []
        for seg in segments:
            segment_dicts.append(
                {
                    "text": seg.text,
                    "language": seg.language.value,
                    "start_idx": seg.start_idx,
                    "end_idx": seg.end_idx,
                }
            )

        # Phonemize text
        phonemes = self.phonemizer.phonemize(text, lang_enum)
        phoneme_ids = self.phonemizer.phonemize_to_ids(text, lang_enum)

        # Determine text language
        if len(segments) == 1:
            text_language = segments[0].language.value
        else:
            text_language = "mixed"

        # Calculate language ratios
        language_counts = {}
        total_chars = 0
        for seg in segments:
            lang = seg.language.value
            char_count = len(seg.text.strip())
            language_counts[lang] = language_counts.get(lang, 0) + char_count
            total_chars += char_count

        language_ratios = {}
        if total_chars > 0:
            for lang, count in language_counts.items():
                language_ratios[lang] = round(count / total_chars, 2)

        # Determine primary language from ratios
        if language_ratios and not primary_language:
            primary_language = max(language_ratios, key=language_ratios.get)

        # Create metadata
        metadata = {
            "primary_language": primary_language or "unknown",
            "language_ratio": language_ratios,
            "num_segments": len(segments),
            "num_phonemes": len(phonemes),
        }

        return MultilingualUtterance(
            audio_path=audio_path,
            text=text,
            text_language=text_language,
            segments=segment_dicts,
            phonemes=phonemes,
            phoneme_ids=phoneme_ids,
            duration=duration,
            speaker_id=speaker_id,
            metadata=metadata,
        )

    def create_dataset_config(
        self,
        dataset_name: str,
        audio_quality: str,
        sample_rate: int,
        num_speakers: int = 1,
        languages: list[str] = None,
    ) -> dict[str, Any]:
        """
        Create configuration for the multilingual dataset.

        Args:
            dataset_name: Name of the dataset
            audio_quality: Audio quality level (low, medium, high)
            sample_rate: Audio sample rate
            num_speakers: Number of speakers in the dataset
            languages: List of languages in the dataset

        Returns:
            Configuration dictionary
        """
        if languages is None:
            languages = ["ja", "en"]

        config = {
            "dataset": dataset_name,
            "audio": {
                "quality": audio_quality,
                "sample_rate": sample_rate,
                "channels": 1,
            },
            "num_speakers": num_speakers,
            "languages": languages,
            "multilingual": True,
            "phoneme_config": {
                "phoneme_type": "multilingual",
                "phoneme_map": "multilingual",
                "vocab_size": self.phoneme_mapper.get_vocab_size(),
                "language_tags": True,
            },
            "phoneme_id_map": {
                "ja": dict(list(self.phoneme_mapper.phoneme_to_id.items())[:100]),
                "en": dict(list(self.phoneme_mapper.phoneme_to_id.items())[100:200]),
                "_": dict(
                    list(self.phoneme_mapper.phoneme_to_id.items())[:50]
                ),  # Special tokens
            },
        }

        return config

    def save_dataset(
        self,
        utterances: list[MultilingualUtterance],
        output_dir: Path,
        dataset_name: str,
        audio_quality: str,
        sample_rate: int,
        validation_split: float = 0.05,
    ):
        """
        Save dataset to files.

        Args:
            utterances: List of utterances
            output_dir: Output directory
            dataset_name: Dataset name
            audio_quality: Audio quality
            sample_rate: Sample rate
            validation_split: Fraction of data for validation
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Split into train and validation
        num_val = int(len(utterances) * validation_split)
        val_utterances = utterances[:num_val]
        train_utterances = utterances[num_val:]

        # Save train dataset
        train_file = output_dir / "dataset.jsonl"
        with open(train_file, "w", encoding="utf-8") as f:
            for utt in train_utterances:
                json.dump(utt.to_dict(), f, ensure_ascii=False)
                f.write("\n")

        # Save validation dataset
        if val_utterances:
            val_file = output_dir / "validation.jsonl"
            with open(val_file, "w", encoding="utf-8") as f:
                for utt in val_utterances:
                    json.dump(utt.to_dict(), f, ensure_ascii=False)
                    f.write("\n")

        # Collect language statistics
        languages = set()
        for utt in utterances:
            for seg in utt.segments:
                languages.add(seg["language"])

        # Get number of speakers
        speaker_ids = {utt.speaker_id for utt in utterances}
        num_speakers = len(speaker_ids)

        # Save configuration
        config = self.create_dataset_config(
            dataset_name=dataset_name,
            audio_quality=audio_quality,
            sample_rate=sample_rate,
            num_speakers=num_speakers,
            languages=sorted(languages),
        )

        config_file = output_dir / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Save phoneme mapping
        phoneme_map_file = output_dir / "phoneme_map.json"
        self.phoneme_mapper.save_mapping(phoneme_map_file)

        # Print statistics
        _LOGGER.info(f"Dataset saved to {output_dir}")
        _LOGGER.info(f"Total utterances: {len(utterances)}")
        _LOGGER.info(f"Training utterances: {len(train_utterances)}")
        _LOGGER.info(f"Validation utterances: {len(val_utterances)}")
        _LOGGER.info(f"Languages: {sorted(languages)}")
        _LOGGER.info(f"Speakers: {num_speakers}")


if __name__ == "__main__":
    # Test the dataset formatter
    formatter = MultilingualDatasetFormatter()

    # Test utterances
    test_data = [
        ("こんにちは", "audio1.wav", 1.5, 0, "ja"),
        ("Hello world", "audio2.wav", 1.2, 0, "en"),
        ("こんにちは、Hello!", "audio3.wav", 2.0, 0, None),
        ("今日はいい天気ですね。Let's go outside!", "audio4.wav", 3.5, 0, None),
    ]

    utterances = []
    for text, audio_path, duration, speaker_id, lang in test_data:
        utt = formatter.format_utterance(text, audio_path, duration, speaker_id, lang)
        utterances.append(utt)

        print(f"\n{'=' * 50}")
        print(f"Text: {text}")
        print(f"Language: {utt.text_language}")
        print(f"Segments: {utt.segments}")
        print(
            f"Phonemes: {utt.phonemes[:20]}..."
            if len(utt.phonemes) > 20
            else f"Phonemes: {utt.phonemes}"
        )
        print(
            f"Phoneme IDs: {utt.phoneme_ids[:20]}..."
            if len(utt.phoneme_ids) > 20
            else f"Phoneme IDs: {utt.phoneme_ids}"
        )
        print(f"Metadata: {utt.metadata}")

    # Test saving dataset
    output_dir = Path("/tmp/multilingual_test_dataset")
    formatter.save_dataset(
        utterances=utterances,
        output_dir=output_dir,
        dataset_name="test_multilingual",
        audio_quality="medium",
        sample_rate=22050,
        validation_split=0.25,
    )

    print(f"\nDataset saved to {output_dir}")
