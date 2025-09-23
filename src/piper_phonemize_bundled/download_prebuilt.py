#!/usr/bin/env python3
"""
Download pre-built espeak-ng and ONNX Runtime libraries
Simpler approach for CI builds
"""

import argparse
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def download_file(url, dest_path):
    """Simple file download"""
    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, dest_path)
    print("Download complete!")


def extract_archive(archive_path, extract_to):
    """Extract zip or tar.gz archive"""
    print(f"Extracting {archive_path}...")
    if str(archive_path).endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_to)
    elif str(archive_path).endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as t:
            t.extractall(extract_to)
    else:
        raise ValueError(f"Unknown archive format: {archive_path}")


def download_espeak_data():
    """Download espeak-ng data files only"""
    src_dir = Path(__file__).parent
    data_dir = src_dir / "piper_phonemize" / "data" / "espeak-ng-data"

    if data_dir.exists():
        print(f"espeak-ng-data already exists at {data_dir}")
        return

    data_dir.mkdir(parents=True, exist_ok=True)

    # Download espeak-ng repository to get data files
    url = "https://github.com/rhasspy/espeak-ng/archive/0f65aa301e0d6bae5e172cc74197d32a6182200f.zip"

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "espeak-ng.zip"
        download_file(url, zip_path)

        extract_archive(zip_path, tmpdir)

        # Copy espeak-ng-data
        src_data = (
            Path(tmpdir)
            / "espeak-ng-0f65aa301e0d6bae5e172cc74197d32a6182200f"
            / "espeak-ng-data"
        )
        if src_data.exists():
            shutil.copytree(src_data, data_dir, dirs_exist_ok=True)
            print(f"Copied espeak-ng-data to {data_dir}")
        else:
            print("Warning: espeak-ng-data not found in archive")


def main():
    parser = argparse.ArgumentParser(description="Download pre-built dependencies")
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Only download data files, not libraries",
    )

    parser.parse_args()  # Parse arguments even though not used currently

    print("Downloading dependencies for piper-phonemize-bundled...")

    # For CI builds, we only need the data files
    # The actual libraries will be built by setuptools
    download_espeak_data()

    print("Download complete!")


if __name__ == "__main__":
    main()
