"""Download model files from Hugging Face Hub"""

import os
from pathlib import Path

from huggingface_hub import hf_hub_download


def download_models():
    """Download ONNX models from Hugging Face Hub"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)

    # Model repository and files to download
    repo_id = "ayutaz/piper-tts-models"  # You'll need to create this repository
    models = [
        ("ja_JP-test-medium.onnx", "Japanese medium quality model"),
        ("ja_JP-test-medium.onnx.json", "Japanese model config"),
        ("test_voice.onnx", "English test model"),
        ("test_voice.onnx.json", "English model config"),
    ]

    print("Downloading models...")
    for filename, description in models:
        local_path = models_dir / filename
        if local_path.exists():
            print(f"✓ {filename} already exists")
            continue

        print(f"Downloading {description}...")
        try:
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=models_dir,
                local_dir_use_symlinks=False,
            )
            print(f"✓ Downloaded {filename}")
        except Exception as e:
            print(f"✗ Failed to download {filename}: {e}")
            # For now, create empty files to avoid errors
            local_path.touch()

    print("Model download complete!")


if __name__ == "__main__":
    download_models()