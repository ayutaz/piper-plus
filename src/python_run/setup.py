#!/usr/bin/env python3
from pathlib import Path

import setuptools
from setuptools import setup


this_dir = Path(__file__).parent
module_dir = this_dir / "piper"

# VERSIONファイルから動的にバージョンを読み込む
version_file = this_dir.parent.parent / "VERSION"
if version_file.is_file():
    version = version_file.read_text(encoding="utf-8").strip()
else:
    # フォールバック: src/python/piper_train/VERSIONから読み込み
    version_file_alt = this_dir.parent / "python" / "piper_train" / "VERSION"
    if version_file_alt.is_file():
        version = version_file_alt.read_text(encoding="utf-8").strip()
    else:
        version = "0.0.0"  # デフォルト値

requirements = []
requirements_path = this_dir / "requirements.txt"
if requirements_path.is_file():
    with open(requirements_path, encoding="utf-8") as requirements_file:
        requirements = [
            line.strip()
            for line in requirements_file
            if line.strip() and not line.strip().startswith("#")
        ]

# README.md を PyPI 用の長い説明として読み込む
long_description = ""
readme_path = this_dir / "README.md"
if readme_path.is_file():
    long_description = readme_path.read_text(encoding="utf-8")

data_files = [module_dir / "voices.json"]

# -----------------------------------------------------------------------------

setup(
    name="piper-plus",
    version=version,
    description=(
        "A fast, high-quality neural text-to-speech system supporting "
        "8 languages (ja/en/zh/ko/es/fr/pt/sv) with VITS architecture."
    ),
    url="https://github.com/ayutaz/piper-plus",
    author="yousan",
    author_email="rabbitcats77@gmail.com",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(exclude=["tests", "tests.*", "build", "build.*"]),
    package_data={"piper": [str(p.relative_to(module_dir)) for p in data_files]},
    entry_points={
        "console_scripts": [
            "piper = piper.__main__:main",
        ]
    },
    install_requires=requirements,
    python_requires=">=3.11",
    extras_require={
        "gpu": ["onnxruntime-gpu>=1.11.0,<2"],
        "http": [
            "fastapi>=0.110,<1",
            "uvicorn[standard]>=0.27,<1",
        ],
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
    keywords="piper japanese and other languages tts",
)
