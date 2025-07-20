#!/usr/bin/env python3
"""
Multi-GPU Training Test Script for Piper VITS
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def test_single_gpu():
    """Test single GPU training as baseline."""
    print("Testing single GPU training...")
    cmd = [
        sys.executable,
        "-m",
        "piper_train",
        "--dataset-dir",
        "/tmp/test_dataset",
        "--batch-size",
        "4",
        "--num-workers",
        "2",
        "--max_epochs",
        "1",
        "--devices",
        "1",
        "--fast_dev_run",
        "--checkpoint-epochs",
        "1",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Single GPU test passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Single GPU test failed: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False


def test_multi_gpu_ddp(num_gpus=2):
    """Test multi-GPU DDP training."""
    print(f"Testing {num_gpus} GPU DDP training...")
    cmd = [
        sys.executable,
        "-m",
        "piper_train",
        "--dataset-dir",
        "/tmp/test_dataset",
        "--batch-size",
        "2",  # Smaller batch per GPU
        "--num-workers",
        str(4 * num_gpus),
        "--max_epochs",
        "1",
        "--devices",
        str(num_gpus),
        "--strategy",
        "ddp",
        "--auto_lr_scaling",  # Enable automatic learning rate scaling
        "--fast_dev_run",
        "--checkpoint-epochs",
        "1",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ {num_gpus} GPU DDP test passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {num_gpus} GPU DDP test failed: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False


def create_dummy_dataset():
    """Create a minimal dummy dataset for testing."""
    dataset_dir = Path("/tmp/test_dataset")
    dataset_dir.mkdir(exist_ok=True)
    # Create config.json
    config = {"num_symbols": 100, "num_speakers": 1, "audio": {"sample_rate": 22050}}

    with open(dataset_dir / "config.json", "w") as f:
        json.dump(config, f)

    # Create dummy dataset.jsonl
    dataset_lines = []
    for i in range(10):
        data = {
            "audio_path": f"dummy_audio_{i}.wav",
            "phoneme_ids": list(range(10, 20)),  # Dummy phoneme sequence
            "speaker_id": 0,
        }
        dataset_lines.append(json.dumps(data))

    with open(dataset_dir / "dataset.jsonl", "w") as f:
        f.write("\n".join(dataset_lines))

    # Create dummy audio files (just create empty files for path validation)
    for i in range(10):
        audio_path = dataset_dir / f"dummy_audio_{i}.wav"
        # Create minimal WAV header
        with open(audio_path, "wb") as f:
            # Simple WAV header for 1 second of silence at 22050Hz
            sample_rate = 22050
            samples = np.zeros(sample_rate, dtype=np.int16)

            # WAV header
            f.write(b"RIFF")
            f.write((36 + len(samples) * 2).to_bytes(4, "little"))
            f.write(b"WAVE")
            f.write(b"fmt ")
            f.write((16).to_bytes(4, "little"))
            f.write((1).to_bytes(2, "little"))  # PCM
            f.write((1).to_bytes(2, "little"))  # mono
            f.write(sample_rate.to_bytes(4, "little"))
            f.write((sample_rate * 2).to_bytes(4, "little"))
            f.write((2).to_bytes(2, "little"))
            f.write((16).to_bytes(2, "little"))
            f.write(b"data")
            f.write((len(samples) * 2).to_bytes(4, "little"))
            samples.tofile(f)

    print(f"Created dummy dataset in {dataset_dir}")
    return dataset_dir


def main():
    parser = argparse.ArgumentParser(description="Test multi-GPU training")
    parser.add_argument(
        "--num-gpus", type=int, default=2, help="Number of GPUs to test"
    )
    parser.add_argument(
        "--skip-single", action="store_true", help="Skip single GPU test"
    )
    parser.add_argument(
        "--create-dataset", action="store_true", help="Create dummy dataset"
    )
    args = parser.parse_args()

    if args.create_dataset:
        create_dummy_dataset()
        return

    # Check if dummy dataset exists
    if not Path("/tmp/test_dataset").exists():
        print("Creating dummy dataset...")
        create_dummy_dataset()

    success = True

    if not args.skip_single:
        success &= test_single_gpu()

    if args.num_gpus > 1:
        success &= test_multi_gpu_ddp(args.num_gpus)

    if success:
        print("🎉 All multi-GPU tests passed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
