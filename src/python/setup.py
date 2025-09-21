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

requirements = []
# Use requirements-train.txt from project root
requirements_path = this_dir.parent.parent / "requirements-train.txt"
if requirements_path.is_file():
    with open(requirements_path, encoding="utf-8") as requirements_file:
        requirements = requirements_file.read().splitlines()

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
    install_requires=requirements,
    python_requires=">=3.11",
    extras_require={},
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
