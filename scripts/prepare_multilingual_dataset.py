#!/usr/bin/env python3
"""
Script to prepare a multilingual dataset for training.
Creates sample data for testing the multilingual VITS model.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from piper_train.phonemize.multilingual_dataset import MultilingualDatasetFormatter

_LOGGER = logging.getLogger(__name__)


def create_sample_utterances():
    """Create sample utterances for testing."""
    sample_data = [
        # Japanese only
        {
            "text": "こんにちは、今日はいい天気ですね。",
            "audio_path": "samples/ja_001.wav",
            "duration": 3.2,
            "speaker_id": 0,
            "primary_language": "ja"
        },
        {
            "text": "ありがとうございます。",
            "audio_path": "samples/ja_002.wav",
            "duration": 1.8,
            "speaker_id": 0,
            "primary_language": "ja"
        },

        # English only
        {
            "text": "Hello, how are you today?",
            "audio_path": "samples/en_001.wav",
            "duration": 2.5,
            "speaker_id": 0,
            "primary_language": "en"
        },
        {
            "text": "This is a test of the text to speech system.",
            "audio_path": "samples/en_002.wav",
            "duration": 3.8,
            "speaker_id": 0,
            "primary_language": "en"
        },

        # Mixed Japanese and English
        {
            "text": "今日のmeetingは3時からです。",
            "audio_path": "samples/mixed_001.wav",
            "duration": 2.8,
            "speaker_id": 0,
            "primary_language": None
        },
        {
            "text": "このsoftwareはopen sourceです。",
            "audio_path": "samples/mixed_002.wav",
            "duration": 3.0,
            "speaker_id": 0,
            "primary_language": None
        },
        {
            "text": "Let's go to 東京 tomorrow!",
            "audio_path": "samples/mixed_003.wav",
            "duration": 2.2,
            "speaker_id": 0,
            "primary_language": None
        },

        # Code-switching examples
        {
            "text": "私はPythonでprogrammingをしています。",
            "audio_path": "samples/mixed_004.wav",
            "duration": 3.5,
            "speaker_id": 0,
            "primary_language": None
        },
        {
            "text": "Please call me at 午後2時.",
            "audio_path": "samples/mixed_005.wav",
            "duration": 2.6,
            "speaker_id": 0,
            "primary_language": None
        },
    ]

    return sample_data


def create_dummy_audio_files(output_dir: Path, utterances: list):
    """Create dummy audio and spectrogram files for testing."""
    import numpy as np

    for utt in utterances:
        # Create dummy paths
        audio_path = output_dir / utt.audio_path
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        # Create dummy audio data (silence)
        sample_rate = 22050
        duration = utt.duration
        num_samples = int(sample_rate * duration)
        audio_data = np.zeros(num_samples, dtype=np.float32)

        # Save normalized audio
        audio_norm_path = audio_path.with_suffix('.norm.npy')
        np.save(audio_norm_path, audio_data)

        # Create dummy spectrogram
        n_fft = 1024
        hop_length = 256
        num_frames = (num_samples // hop_length) + 1
        spec_data = np.zeros((n_fft // 2 + 1, num_frames), dtype=np.float32)

        # Save spectrogram
        audio_spec_path = audio_path.with_suffix('.spec.npy')
        np.save(audio_spec_path, spec_data)

        # Update utterance with actual paths
        utt.audio_norm_path = str(audio_norm_path)
        utt.audio_spec_path = str(audio_spec_path)


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Prepare a multilingual dataset for VITS training"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("multilingual_dataset"),
        help="Output directory for the dataset",
    )
    parser.add_argument(
        "--dataset-name",
        default="multilingual_test",
        help="Name of the dataset",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=22050,
        help="Audio sample rate",
    )
    parser.add_argument(
        "--audio-quality",
        default="medium",
        choices=["low", "medium", "high"],
        help="Audio quality setting",
    )
    parser.add_argument(
        "--validation-split",
        type=float,
        default=0.2,
        help="Fraction of data to use for validation",
    )
    parser.add_argument(
        "--create-dummy-audio",
        action="store_true",
        help="Create dummy audio files for testing",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Create formatter
    formatter = MultilingualDatasetFormatter()

    # Get sample utterances
    sample_data = create_sample_utterances()

    # Create dummy audio files if requested
    if args.create_dummy_audio:
        _LOGGER.info("Creating dummy audio files...")
        create_dummy_audio_files(args.output_dir, sample_data)

    # Format utterances
    utterances = []
    for data in sample_data:
        # Skip if audio files don't exist and not creating dummy files
        if not args.create_dummy_audio:
            audio_path = args.output_dir / data["audio_path"]
            if not audio_path.with_suffix('.norm.npy').exists():
                _LOGGER.warning(f"Skipping {data['text']}: audio files not found")
                continue

        utt = formatter.format_utterance(
            text=data["text"],
            audio_path=data.get("audio_norm_path", data["audio_path"]),
            duration=data["duration"],
            speaker_id=data["speaker_id"],
            primary_language=data.get("primary_language"),
        )

        # Update audio paths if dummy files were created
        if args.create_dummy_audio:
            utt.audio_path = data.get("audio_norm_path", data["audio_path"])

        utterances.append(utt)

    _LOGGER.info(f"Formatted {len(utterances)} utterances")

    # Show some examples
    print("\nExample utterances:")
    for i, utt in enumerate(utterances[:3]):
        print(f"\n--- Utterance {i+1} ---")
        print(f"Text: {utt.text}")
        print(f"Language: {utt.text_language}")
        print(f"Segments: {len(utt.segments)}")
        for seg in utt.segments:
            print(f"  - {seg['language']}: {seg['text']}")
        print(f"Phonemes ({len(utt.phonemes)}): {' '.join(utt.phonemes[:20])}...")
        print(f"Language ratios: {utt.metadata['language_ratio']}")

    # Save dataset
    formatter.save_dataset(
        utterances=utterances,
        output_dir=args.output_dir,
        dataset_name=args.dataset_name,
        audio_quality=args.audio_quality,
        sample_rate=args.sample_rate,
        validation_split=args.validation_split,
    )

    print(f"\nDataset saved to: {args.output_dir}")
    print("Files created:")
    print(f"  - dataset.jsonl ({len(utterances) - int(len(utterances) * args.validation_split)} utterances)")
    print(f"  - validation.jsonl ({int(len(utterances) * args.validation_split)} utterances)")
    print("  - config.json")
    print("  - phoneme_map.json")

    # Show training command
    print("\nTo train the model, run:")
    print("python -m piper_train.train_multilingual \\")
    print(f"  --dataset-dir {args.output_dir} \\")
    print("  --max_epochs 100 \\")
    print("  --batch-size 16 \\")
    print(f"  --validation-split {args.validation_split} \\")
    print("  --checkpoint-epochs 10")


if __name__ == "__main__":
    main()
