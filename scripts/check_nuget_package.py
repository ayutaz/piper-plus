"""Verify a NuGet.org repository-signed copy has the exact build payload."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


SIGNATURE = ".signature.p7s"


def payload(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"NuGet package has duplicate members: {path}")
        result = {}
        for item in archive.infolist():
            if item.filename != SIGNATURE:
                with archive.open(item) as stream:
                    result[item.filename] = hashlib.file_digest(
                        stream, "sha256"
                    ).hexdigest()
        return result


def compare_packages(original: Path, published: Path) -> None:
    if payload(original) != payload(published):
        raise ValueError("Public NuGet payload differs from the build")
    with zipfile.ZipFile(published) as archive:
        if (
            SIGNATURE not in archive.namelist()
            or not archive.getinfo(SIGNATURE).file_size
        ):
            raise ValueError("Public NuGet package is missing its repository signature")


def download_public_copy(original: Path, destination: Path) -> None:
    with zipfile.ZipFile(original) as archive:
        nuspecs = [item for item in archive.namelist() if item.endswith(".nuspec")]
        if len(nuspecs) != 1:
            raise ValueError("Expected exactly one NuGet nuspec")
        root = ET.fromstring(archive.read(nuspecs[0]))
    fields = {node.tag.rsplit("}", 1)[-1]: node.text for node in root.iter()}
    name, version = fields["id"], fields["version"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version
    ):
        raise ValueError("Invalid NuGet name/version")
    name, version = name.lower(), version.lower()
    url = f"https://api.nuget.org/v3-flatcontainer/{name}/{version}/{name}.{version}.nupkg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--retry",
            "5",
            "--retry-all-errors",
            "--retry-delay",
            "10",
            "--output",
            str(destination),
            url,
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("published", type=Path)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        download_public_copy(args.original, args.published)
    compare_packages(args.original, args.published)
    print(f"Verified NuGet repository copy: {args.published}")


if __name__ == "__main__":
    main()
