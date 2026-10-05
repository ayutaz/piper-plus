"""Check the exported ARM64 archive without extracting its filesystem."""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path


BINARY_PATH = "piper-plus/bin/piper-plus"


def check_archive(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        try:
            member = archive.getmember(BINARY_PATH)
        except KeyError as exc:
            raise ValueError(f"Archive is missing {BINARY_PATH}") from exc
        if not member.isfile() or not member.mode & 0o111:
            raise ValueError(f"{BINARY_PATH} must be a regular executable file")
        binary = archive.extractfile(member)
        assert binary is not None
        with binary:
            header = binary.read(64)
        if len(header) < 64 or header[:7] != b"\x7fELF\x02\x01\x01":
            raise ValueError(f"{BINARY_PATH} is not a 64-bit little-endian ELF binary")
        if int.from_bytes(header[18:20], "little") != 183:
            raise ValueError(f"{BINARY_PATH} is not AArch64 (ELF e_machine=183)")
        if int.from_bytes(header[16:18], "little") not in (2, 3):
            raise ValueError(f"{BINARY_PATH} is not an executable or PIE binary")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        check_archive(args.archive)
    except (OSError, tarfile.TarError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Verified ARM64 executable in {args.archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
