"""Check real WAV validation and fail-closed Docker smoke behavior."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import wave
from pathlib import Path

import pytest


@pytest.fixture
def runtime():
    path = Path(__file__).resolve().parents[2] / "scripts/check_arm64_runtime.py"
    spec = importlib.util.spec_from_file_location("arm64_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_wav(path, samples=b"\x01\x00" * 2205):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(samples)


def test_valid_waveform_has_positive_duration(runtime, tmp_path):
    path = tmp_path / "output.wav"
    write_wav(path)
    assert runtime.check_wav(path)["duration_seconds"] == 0.1


@pytest.mark.parametrize("samples", [b"", b"\x00\x00" * 2205])
def test_empty_or_silent_wav_fails(runtime, tmp_path, samples):
    path = tmp_path / "output.wav"
    write_wav(path, samples)
    with pytest.raises(ValueError):
        runtime.check_wav(path)


def test_loader_error_is_preserved_and_fails(runtime, tmp_path, monkeypatch):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "GLIBC_2.38 not found")

    monkeypatch.setattr(runtime.subprocess, "run", run)
    with pytest.raises(ValueError, match="exit 1"):
        runtime.run_logged(["docker", "run"], tmp_path, "container")
    assert (tmp_path / "container.stderr.log").read_text() == "GLIBC_2.38 not found"
    assert json.loads((tmp_path / "container.command.json").read_text()) == [
        "docker",
        "run",
    ]


def test_runtime_timeout_is_preserved_and_fails(runtime, tmp_path, monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command, 1, output=b"partial", stderr=b"timeout detail"
        )

    monkeypatch.setattr(runtime.subprocess, "run", run)
    with pytest.raises(ValueError, match="timed out"):
        runtime.run_logged(["docker", "run"], tmp_path, "container")
    assert (tmp_path / "container.stdout.log").read_text() == "partial"
    assert (tmp_path / "container.stderr.log").read_text() == "timeout detail"


def test_existing_waveform_cannot_make_a_rerun_pass(runtime, tmp_path):
    inputs = []
    for name in ("archive", "model", "config"):
        path = tmp_path / name
        path.write_bytes(b"input")
        inputs.append(path)
    output = tmp_path / "out"
    output.mkdir()
    write_wav(output / "output.wav")
    with pytest.raises(ValueError, match="fresh output directory"):
        runtime.check_runtime(*inputs, "bullseye", output)


@pytest.mark.parametrize("modern_cli", [False, True])
def test_image_metadata_supports_modern_and_legacy_docker(
    runtime, tmp_path, monkeypatch, modern_cli
):
    inputs = []
    for name in ("archive", "model", "config"):
        path = tmp_path / name
        path.write_bytes(b"input")
        inputs.append(path)

    def run(command, output, label):
        if label == "image-inspect-help":
            return (
                "Options: --platform string"
                if modern_cli
                else "Options: --format string"
            )
        if label == "image":
            if modern_cli:
                assert command[3:5] == ["--platform", "linux/arm64"]
            elif "--platform" in command:
                raise ValueError("unknown flag: --platform")
            return json.dumps([{"Architecture": "arm64", "Id": "sha256:arm64-image"}])
        if label == "container":
            assert "debian:trixie" in command
            assert command[command.index("--platform") + 1] == "linux/arm64"
            write_wav(output / "output.wav")
            return "PIPER_HELP_OK\nPIPER_SYNTH_OK\n"
        return ""

    monkeypatch.setattr(runtime, "run_logged", run)
    report = runtime.check_runtime(*inputs, "trixie", tmp_path / "out")
    assert report["help"] == report["synthesis"] == "success"


def test_image_inspection_errors_are_not_ignored(runtime, tmp_path, monkeypatch):
    def run(command, output, label):
        if label == "image-inspect-help":
            return "Options: --format string"
        raise ValueError("daemon unavailable")

    monkeypatch.setattr(runtime, "run_logged", run)
    with pytest.raises(ValueError, match="daemon unavailable"):
        runtime.inspect_image("debian:bullseye", tmp_path)
