#!/usr/bin/env python3
from pathlib import Path

import setuptools
from setuptools import setup


this_dir = Path(__file__).parent
module_dir = this_dir / "piper_train"

# -----------------------------------------------------------------------------

# Load README in as long description
long_description: str = ""
readme_path = this_dir / "README.md"
if readme_path.is_file():
    long_description = readme_path.read_text(encoding="utf-8")


# ルートのVERSIONファイルから動的にバージョンを読み込む
version_path = this_dir.parent.parent / "VERSION"
if version_path.is_file():
    with open(version_path, encoding="utf-8") as version_file:
        version = version_file.read().strip()
else:
    version = "0.0.0"  # デフォルト値

# -----------------------------------------------------------------------------

setup(
    name="piper_train",
    version=version,
    description="A fast and local neural text to speech system",
    long_description=long_description,
    url="http://github.com/rhasspy/piper",
    author="Michael Hansen",
    author_email="mike@rhasspy.org",
    license="MIT",
    packages=setuptools.find_packages(),
    package_data={
        "piper_train": ["py.typed"],
    },
    install_requires=[
        "numpy<2.3",
    ],
    python_requires=">=3.11",
    extras_require={
        "inference": [
            "onnxruntime>=1.17",
            "soundfile>=0.12",
            "pyopenjtalk-plus",
            "g2p-en>=2.1.0",
            "fastapi>=0.110",
            "uvicorn>=0.27",
        ],
        "train": [
            "scipy>=1.12",
            "librosa>=0.10",
            "soundfile>=0.12",
            "pytorch-lightning>=2.0",
            "torchmetrics>=1.0",
            "transformers>=4.38",
            "onnx>=1.15",
            "onnxruntime-gpu>=1.17",
            "pyopenjtalk-plus",
            "mecab-python3>=1.0",
            "unidic-lite>=1.0",
            "g2p-en>=2.1.0",
            "tensorboard>=2.16",
            "wandb>=0.16",
            "tqdm>=4.66",
            "einops>=0.7",
            "numba>=0.59",
            "matplotlib>=3.8",
            "seaborn>=0.13",
            "pyyaml>=6.0",
            "onnxsim-prebuilt",
        ],
    },
    entry_points={
        "console_scripts": [
            "piper-train = piper_train.__main__:main",
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Text Processing :: Linguistic",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    keywords="rhasspy tts speech voice",
)
