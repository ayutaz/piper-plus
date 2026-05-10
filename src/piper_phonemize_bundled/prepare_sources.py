#!/usr/bin/env python3
"""
Prepare C++ source files for piper-phonemize-bundled
Copies source files from piper-phonemize external dependency
"""

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def copy_sources():
    """Copy C++ source files from piper-phonemize external"""
    src_dir = Path(__file__).parent

    # Destination directory for C++ sources
    cpp_dir = src_dir / "piper_phonemize" / "cpp" / "src"
    cpp_dir.mkdir(parents=True, exist_ok=True)

    # List of required source files
    required_files = [
        "phonemize.cpp",
        "phonemize.hpp",
        "phoneme_ids.cpp",
        "phoneme_ids.hpp",
        "tashkeel.cpp",
        "tashkeel.hpp",
        "python.cpp",
    ]

    # Try to find sources in the main build directory
    project_root = src_dir.parent.parent

    # Possible source locations
    source_locations = [
        # From CMake build
        project_root / "build" / "_deps" / "piper_phonemize-src" / "src",
        project_root / "build" / "p" / "src" / "piper_phonemize_external" / "src",
        # From lib directory
        project_root / "lib" / "piper-phonemize" / "src",
    ]

    # Find the first existing source location
    source_dir = None
    for location in source_locations:
        if location.exists():
            source_dir = location
            print(f"Found source files at: {source_dir}")
            break

    if not source_dir:
        print("Local source files not found, downloading from GitHub...")

        # Download from piper-phonemize GitHub repository
        url = "https://github.com/rhasspy/piper-phonemize/archive/refs/heads/master.zip"

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "piper-phonemize.zip"
            print(f"Downloading {url}...")
            urllib.request.urlretrieve(url, zip_path)

            print("Extracting source files...")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(tmpdir)

            source_dir = Path(tmpdir) / "piper-phonemize-master" / "src"
            if not source_dir.exists():
                print("Error: Source directory not found in downloaded archive")
                return False

            # Copy files from the downloaded source
            print("Found source files in downloaded archive")

            # Copy required files (skip python.cpp if it already exists)
            copied_files = []
            for filename in required_files:
                dst_file = cpp_dir / filename
                if filename == "python.cpp" and dst_file.exists():
                    print(f"  Skipped: {filename} (already exists)")
                    continue

                src_file = source_dir / filename
                if src_file.exists():
                    shutil.copy2(src_file, dst_file)
                    copied_files.append(filename)
                    print(f"  Copied: {filename}")
                # Some files might be optional
                elif filename not in ["python.cpp"]:
                    print(f"  Warning: {filename} not found (might be optional)")

            # Also copy any additional headers
            for header_file in source_dir.glob("*.h"):
                dst_file = cpp_dir / header_file.name
                shutil.copy2(header_file, dst_file)
                copied_files.append(header_file.name)
                print(f"  Copied: {header_file.name}")

            print(f"\nSuccessfully copied {len(copied_files)} files from GitHub")
            return True

    # If we get here, we have a local source directory
    # Copy each required file (skip python.cpp if it already exists)
    copied_files = []
    for filename in required_files:
        dst_file = cpp_dir / filename
        if filename == "python.cpp" and dst_file.exists():
            print(f"  Skipped: {filename} (already exists)")
            copied_files.append(filename)
            continue

        src_file = source_dir / filename
        if src_file.exists():
            shutil.copy2(src_file, dst_file)
            copied_files.append(filename)
            print(f"  Copied: {filename}")
        # Some files might be optional
        elif filename not in ["python.cpp"]:
            print(f"  Warning: {filename} not found (might be optional)")

    # Also copy any additional headers
    for header_file in source_dir.glob("*.h"):
        dst_file = cpp_dir / header_file.name
        shutil.copy2(header_file, dst_file)
        copied_files.append(header_file.name)
        print(f"  Copied: {header_file.name}")

    print(f"\nSuccessfully copied {len(copied_files)} files")
    return True


def copy_data_files():
    """Copy espeak-ng-data files"""
    src_dir = Path(__file__).parent
    data_dir = src_dir / "piper_phonemize" / "data" / "espeak-ng-data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Try to find espeak-ng-data in the build directory
    project_root = src_dir.parent.parent

    # Possible data locations
    data_locations = [
        project_root
        / "build"
        / "_deps"
        / "piper_phonemize-src"
        / "espeak-ng"
        / "espeak-ng-data",
        project_root
        / "build"
        / "p"
        / "src"
        / "piper_phonemize_external"
        / "espeak-ng"
        / "espeak-ng-data",
        project_root / "lib" / "piper-phonemize" / "espeak-ng" / "espeak-ng-data",
    ]

    # Find the first existing data location
    source_data = None
    for location in data_locations:
        if location.exists():
            source_data = location
            print(f"Found espeak-ng-data at: {source_data}")
            break

    if source_data:
        # Copy the entire data directory
        shutil.copytree(source_data, data_dir, dirs_exist_ok=True)
        print(f"Copied espeak-ng-data to {data_dir}")
        return True
    else:
        print("Warning: espeak-ng-data not found, will be downloaded during build")
        return False


def main():
    print("Preparing source files for piper-phonemize-bundled...")

    # Copy C++ sources
    if not copy_sources():
        print("\nNote: Source files will need to be downloaded during CI build")

    # Copy data files
    copy_data_files()

    print("\nPreparation complete!")


if __name__ == "__main__":
    main()
