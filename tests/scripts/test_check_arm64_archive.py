"""Reject missing, corrupt, or incorrectly targeted ARM64 build artifacts."""

from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_arm64_archive.py"


@pytest.fixture
def validator():
    spec = importlib.util.spec_from_file_location("check_arm64_archive", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def readelf_output(*versions, needed=("libc.so.6",)):
    dynamic = "  LOAD 0x000000 0x000000 0x000000 0x100 0x100 R E 0x1000\n"
    dynamic += "\n".join(f" (NEEDED) Shared library: [{lib}]" for lib in needed)
    return (
        dynamic
        + "\nVersion needs section '.gnu.version_r' contains 1 entry:\n"
        + "\n".join(
            f"  Name: {version} Flags: none Version: {i + 2}"
            for i, version in enumerate(versions)
        )
    )


@pytest.fixture
def check_archive(validator, monkeypatch):
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, readelf_output("GLIBC_2.31"), ""
        ),
    )
    return validator.check_archive


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


@pytest.mark.parametrize("version", ["GLIBC_2.32", "GLIBC_2.38", "GLIBCXX_3.4.29"])
def test_newer_abi_is_rejected(
    validator, check_archive, tmp_path, monkeypatch, version
):
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a[0], 0, readelf_output(version), ""
        ),
    )
    with pytest.raises(ValueError, match=version):
        check_archive(make_archive(tmp_path, elf_header()))


def test_numeric_maxima_and_needed_are_reported(
    validator, check_archive, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a[0],
            0,
            readelf_output(
                "GLIBC_2.9", "GLIBC_2.31", "GLIBCXX_3.4.28", "CXXABI_1.3.12"
            ),
            "",
        ),
    )
    reports = check_archive(make_archive(tmp_path, elf_header()))
    assert reports[0]["maxima"] == {
        "GLIBC": "2.31",
        "GLIBCXX": "3.4.28",
        "CXXABI": "1.3.12",
    }
    assert reports[0]["needed"] == ["libc.so.6"]


def test_exported_versions_are_not_requirements(
    validator, check_archive, tmp_path, monkeypatch
):
    output = "Version definition section '.gnu.version_d' contains 1 entry:\n Name: GLIBC_2.99\n"
    output += readelf_output("GLIBC_2.31")
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, output, ""),
    )
    assert (
        check_archive(make_archive(tmp_path, elf_header()))[0]["maxima"]["GLIBC"]
        == "2.31"
    )


@pytest.mark.parametrize(
    "output,stderr,code",
    [
        ("", "corrupt ELF", 1),
        (readelf_output("GLIBC_2.31"), "truncated section", 0),
        (" (NEEDED) Shared library: [libc.so.6]\n", "", 0),
        (readelf_output("GLIBC_PRIVATE"), "", 0),
    ],
)
def test_incomplete_abi_inspection_fails(
    validator, check_archive, tmp_path, monkeypatch, output, stderr, code
):
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], code, output, stderr),
    )
    with pytest.raises(ValueError):
        check_archive(make_archive(tmp_path, elf_header()))


def test_missing_readelf_fails(validator, check_archive, tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("readelf")

    monkeypatch.setattr(validator.subprocess, "run", missing)
    with pytest.raises(ValueError, match="readelf"):
        check_archive(make_archive(tmp_path, elf_header()))


def test_header_without_load_segments_is_rejected(
    validator, check_archive, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a[0], 0, "No version information found in this file.", ""
        ),
    )
    with pytest.raises(ValueError, match="load segments"):
        check_archive(make_archive(tmp_path, elf_header()))


@pytest.mark.skipif(
    shutil.which("readelf") is None, reason="GNU binutils not installed"
)
def test_real_readelf_rejects_header_only_elf(validator, tmp_path):
    with pytest.raises(ValueError):
        validator.check_archive(make_archive(tmp_path, elf_header()))


def test_bundled_library_cannot_raise_glibc_floor(
    validator, check_archive, tmp_path, monkeypatch
):
    outputs = iter([readelf_output("GLIBC_2.31"), readelf_output("GLIBC_2.34")])
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, next(outputs), ""),
    )
    path = tmp_path / "bundle.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in (
            "piper-plus/bin/piper-plus",
            "piper-plus/lib/libonnxruntime.so.1.20.0",
        ):
            member = tarfile.TarInfo(name)
            member.mode = 0o755
            member.size = 64
            archive.addfile(member, io.BytesIO(elf_header()))
    with pytest.raises(ValueError, match=r"libonnxruntime.*GLIBC_2\.34"):
        check_archive(path)
