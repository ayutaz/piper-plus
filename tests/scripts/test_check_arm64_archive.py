"""Reject missing, corrupt, or incorrectly targeted ARM64 build artifacts."""

from __future__ import annotations

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_arm64_archive.py"


@pytest.fixture
def check_archive():
    spec = importlib.util.spec_from_file_location("check_arm64_archive", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_archive


def make_archive(tmp_path, data, name="piper-plus/bin/piper-plus", mode=0o755):
    path = tmp_path / "piper-plus-cpp-linux-arm64.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = len(data)
        entry.mode = mode
        archive.addfile(entry, io.BytesIO(data))
    return path


def elf_header(machine=183, elf_class=2, byte_order=1):
    data = bytearray(64)
    data[:7] = b"\x7fELF" + bytes([elf_class, byte_order, 1])
    data[16:18] = (3).to_bytes(2, "little")
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data)


def test_native_arm64_binary_is_accepted(check_archive, tmp_path):
    check_archive(make_archive(tmp_path, elf_header()))


@pytest.mark.parametrize(
    "data",
    [
        elf_header(machine=62),
        elf_header(elf_class=1),
        elf_header(byte_order=2),
        b"not ELF",
        b"\x7fELF",
    ],
)
def test_wrong_architecture_or_corrupt_binary_fails(check_archive, tmp_path, data):
    with pytest.raises(ValueError):
        check_archive(make_archive(tmp_path, data))


def test_missing_binary_fails(check_archive, tmp_path):
    with pytest.raises(ValueError, match="piper-plus/bin/piper-plus"):
        check_archive(make_archive(tmp_path, elf_header(), name="build/bin/piper-plus"))


def test_non_executable_binary_fails(check_archive, tmp_path):
    with pytest.raises(ValueError, match="executable"):
        check_archive(make_archive(tmp_path, elf_header(), mode=0o644))


def test_missing_archive_fails(check_archive, tmp_path):
    with pytest.raises(FileNotFoundError):
        check_archive(tmp_path / "missing.tar.gz")
