"""Write a byte-stable xcframework ZIP for SwiftPM checksums."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import zipfile
from pathlib import Path


def create_archive(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if not source.is_dir() or destination.is_relative_to(source):
        raise ValueError("Use an xcframework directory and an archive outside it")
    metadata = plistlib.loads((source / "Info.plist").read_bytes())
    metadata["AvailableLibraries"].sort(key=lambda item: item["LibraryIdentifier"])
    for library in metadata["AvailableLibraries"]:
        library["SupportedArchitectures"].sort()
    canonical_plist = plistlib.dumps(metadata, sort_keys=True)
    entries = sorted(
        [source, *source.rglob("*")],
        key=lambda path: path.relative_to(source.parent).as_posix(),
    )
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in entries:
            name = path.relative_to(source.parent).as_posix()
            is_link = path.is_symlink()
            is_directory = path.is_dir() and not is_link
            info = zipfile.ZipInfo(
                name + ("/" if is_directory else ""), (1980, 1, 1, 0, 0, 0)
            )
            info.create_system = 3
            mode = (
                stat.S_IFLNK | 0o777
                if is_link
                else (stat.S_IFDIR | 0o755 if is_directory else stat.S_IFREG | 0o644)
            )
            info.external_attr = mode << 16
            if is_directory:
                info.external_attr |= 0x10
            info.compress_type = zipfile.ZIP_DEFLATED
            if is_directory:
                archive.writestr(info, b"")
            elif is_link:
                archive.writestr(info, os.readlink(path).encode("utf-8"))
            elif path == source / "Info.plist":
                archive.writestr(info, canonical_plist)
            else:
                with path.open("rb") as original, archive.open(info, "w") as packed:
                    shutil.copyfileobj(original, packed, 1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    create_archive(args.source, args.destination)


if __name__ == "__main__":
    main()
