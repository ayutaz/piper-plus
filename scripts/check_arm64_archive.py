"""Check the exported ARM64 archive without extracting its filesystem."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


BINARY_PATH = "piper-plus/bin/piper-plus"
ABI_LIMITS = {"GLIBC": (2, 31), "GLIBCXX": (3, 4, 28), "CXXABI": (1, 3, 12)}


def inspect_elf(data: bytes, name: str, readelf: str) -> dict:
    """Inspect required (not exported) symbol versions with GNU readelf."""
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError(f"{name} is not a 64-bit little-endian ELF binary")
    if int.from_bytes(data[18:20], "little") != 183:
        raise ValueError(f"{name} is not AArch64 (ELF e_machine=183)")
    if int.from_bytes(data[16:18], "little") not in (2, 3):
        raise ValueError(f"{name} is not an executable or PIE/shared binary")
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "binary.elf"
        target.write_bytes(data)
        try:
            result = subprocess.run(
                [
                    readelf,
                    "--wide",
                    "--program-headers",
                    "--version-info",
                    "--dynamic",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "LC_ALL": "C"},
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"{name}: readelf inspection failed: {exc}") from exc
    if result.returncode or result.stderr.strip():
        raise ValueError(f"{name}: readelf inspection failed: {result.stderr.strip()}")
    if not re.search(r"^\s*LOAD\s", result.stdout, re.MULTILINE):
        raise ValueError(f"{name}: missing ELF load segments")
    needed = re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", result.stdout)
    required = []
    in_needs = False
    for line in result.stdout.splitlines():
        if line.startswith("Version "):
            in_needs = line.startswith("Version needs section ")
        if in_needs:
            required.extend(
                re.findall(r"Name:\s+((?:GLIBCXX|GLIBC|CXXABI)_[\w.]+)", line)
            )
    if needed and not required:
        raise ValueError(f"{name}: missing required ABI version information")
    maxima = {}
    for family, limit in ABI_LIMITS.items():
        versions = []
        for symbol in required:
            if not symbol.startswith(family + "_"):
                continue
            version = symbol[len(family) + 1 :]
            if not re.fullmatch(r"\d+(?:\.\d+)+", version):
                raise ValueError(f"{name}: unsupported ABI requirement {symbol}")
            number = tuple(map(int, version.split(".")))
            if number > limit:
                ceiling = ".".join(map(str, limit))
                raise ValueError(
                    f"{name}: requires {symbol}, exceeds {family}_{ceiling}"
                )
            versions.append(number)
        maxima[family] = ".".join(map(str, max(versions))) if versions else None
    return {"path": name, "maxima": maxima, "needed": needed}


def check_archive(path: Path, readelf: str = "readelf") -> list[dict]:
    """Reject incompatible ARM64 executables and bundled shared libraries."""
    reports = []
    with tarfile.open(path, "r:gz") as archive:
        try:
            member = archive.getmember(BINARY_PATH)
        except KeyError as exc:
            raise ValueError(f"Archive is missing {BINARY_PATH}") from exc
        if not member.isfile() or not member.mode & 0o111:
            raise ValueError(f"{BINARY_PATH} must be a regular executable file")
        libraries = [
            m
            for m in archive.getmembers()
            if m.isfile()
            and m.name.startswith("piper-plus/lib/")
            and ".so" in Path(m.name).name
        ]
        for entry in [member, *libraries]:
            binary = archive.extractfile(entry)
            assert binary is not None
            with binary:
                reports.append(inspect_elf(binary.read(), entry.name, readelf))
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--readelf", default="readelf", help="GNU readelf executable (binutils)"
    )
    parser.add_argument(
        "--report", type=Path, help="Write per-file ABI maxima and dependencies as JSON"
    )
    args = parser.parse_args()
    try:
        reports = check_archive(args.archive, args.readelf)
        if args.report:
            args.report.write_text(
                json.dumps(reports, indent=2) + "\n", encoding="utf-8"
            )
    except (OSError, tarfile.TarError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for report in reports:
        print(
            f"{report['path']}: {json.dumps(report['maxima'])}; NEEDED={','.join(report['needed'])}"
        )
    print(
        f"Verified ARM64 archive: GLIBC <= 2.31, GLIBCXX <= 3.4.28, CXXABI <= 1.3.12: {args.archive}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
