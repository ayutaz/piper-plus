"""Validate release wheel metadata and runtime files before publication."""

from __future__ import annotations

import argparse
import email
import zipfile
from pathlib import Path


def verify_wheel(path: Path, name: str, version: str) -> None:
    modules = {
        "piper-plus": (
            "piper_plus/__init__.py",
            "piper_plus/voice.py",
            "piper_plus/__main__.py",
            "piper_plus/phonemize/data/zh_en_loanword.json",
            "piper_plus/phonemize/data/sv_function_words.json",
        ),
        "piper-plus-g2p": (
            "piper_plus_g2p/__init__.py",
            "piper_plus_g2p/registry.py",
            "piper_plus_g2p/ssml.py",
            "piper_plus_g2p/data/pua.json",
            "piper_plus_g2p/data/zh_en_loanword.json",
            "piper_plus_g2p/data/sv_function_words.json",
            "piper_plus_g2p/THIRD_PARTY_LICENSES.md",
        ),
    }
    with zipfile.ZipFile(path) as archive:
        files = set(archive.namelist())
        metadata = [f for f in files if f.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("Wheel must have exactly one METADATA file")
        message = email.message_from_bytes(archive.read(metadata[0]))
        if message["Name"] != name or message["Version"] != version:
            raise ValueError(
                f"Wheel name/version mismatch: {message['Name']}@{message['Version']}, expected {name}@{version}"
            )
        if name == "piper-plus" and any(f.startswith("piper/") for f in files):
            raise ValueError("Wheel contains the legacy piper module")
        missing = set(modules[name]) - files
        if not any(".dist-info/licenses/" in f and "LICENSE" in f for f in files):
            missing.add("license notice")
        if missing:
            raise ValueError(f"Wheel missing required files: {sorted(missing)}")
    print(f"Verified {path.name}: {name}@{version}, {len(files)} files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name", required=True, choices=["piper-plus", "piper-plus-g2p"]
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("wheels", type=Path, nargs="+")
    args = parser.parse_args()
    for wheel in args.wheels:
        verify_wheel(wheel, args.name, args.version)


if __name__ == "__main__":
    main()
