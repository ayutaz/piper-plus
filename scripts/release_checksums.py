"""Generate flat GitHub asset checksums and verify downloaded release bytes."""

import argparse
import hashlib
import re
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def generate(directory):
    files = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or not path.name.endswith((".zip", ".tar.gz")):
            continue
        if path.name in files:
            raise ValueError(f"duplicate release asset name: {path.name}")
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", path.name):
            raise ValueError(f"invalid release asset name: {path.name}")
        files[path.name] = path
    if not files:
        raise ValueError("no release archives found")
    return "".join(f"{digest(files[name])}  {name}\n" for name in sorted(files))


def verify(directory, manifest):
    seen = set()
    for line in manifest.splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.+-]+)", line)
        if not match or match[2] in (".", ".."):
            raise ValueError(f"invalid checksum row: {line!r}")
        expected, name = match.groups()
        if name in seen:
            raise ValueError(f"duplicate checksum name: {name}")
        seen.add(name)
        path = directory / name
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise ValueError(f"checksum mismatch or missing asset: {name}")
    if not seen:
        raise ValueError("empty checksum manifest")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.directory, args.verify.read_text(encoding="utf-8"))
    elif args.output:
        args.output.write_text(generate(args.directory), encoding="utf-8", newline="\n")
    else:
        parser.error("--output or --verify is required")


if __name__ == "__main__":
    main()
