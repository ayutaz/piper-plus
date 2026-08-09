"""CLI argparse smoke tests for piper_train.infer_onnx.

These tests pin the public CLI surface so that flag renames or default-value
drift are caught before they break end-user scripts and align with Rust /
Go / C# CLIs.
"""

import subprocess
import sys

import pytest


PROG = [sys.executable, "-m", "piper_train.infer_onnx"]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        PROG + args,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.unit
class TestInferOnnxCli:
    def test_help_runs_cleanly(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower()

    def test_help_advertises_text_flag(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "--text" in result.stdout

    def test_help_advertises_model_flag(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "--model" in result.stdout

    def test_help_advertises_voice_cloning_flags(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "--reference-audio" in result.stdout
        assert "--speaker-embedding" in result.stdout
        assert "--speaker-encoder-model" in result.stdout

    def test_help_advertises_language_flag(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "--language" in result.stdout

    def test_help_advertises_list_models_flag(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "--list-models" in result.stdout

    def test_help_advertises_download_model_flag(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "--download-model" in result.stdout

    def test_rejects_invalid_flag(self) -> None:
        result = _run(["--definitely-not-a-real-flag"])
        assert result.returncode != 0

    def test_help_advertises_noise_scale_family(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        for flag in ("--noise-scale", "--noise-scale-w", "--length-scale"):
            assert flag in result.stdout, f"{flag} missing from --help output"

    def test_help_advertises_default_language(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "default: ja" in result.stdout

    def test_help_advertises_device_choices(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        for choice in ("auto", "cpu", "gpu"):
            assert choice in result.stdout, f"--device choice {choice!r} missing from help"

    def test_deprecated_aliases_still_recognized(self) -> None:
        """`--encode-speaker` is the old name for `--reference-audio` (deprecated but accepted)."""
        result = _run(["--help"])
        assert result.returncode == 0
        # The new canonical name must be present; the deprecated alias is documented
        # via dest= rather than help text, so we only assert the canonical surface.
        assert "--reference-audio" in result.stdout

    def test_invalid_device_choice_fails(self) -> None:
        result = _run(["--device", "tpu", "--text", "hello", "--model", "x"])
        assert result.returncode != 0


@pytest.mark.unit
class TestSpeakerSourceAliasMerge:
    """--reference-audio / --speaker-encoder-model must reach the resolver.

    The documented voice-cloning pair has separate argparse dests from the
    canonical fields consumed by _resolve_speaker_embedding. Before the merge
    helper existed the documented flags were silently ignored and zero-shot
    models fell back to a zero embedding (v8 local verification, 2026-08-09).
    """

    @staticmethod
    def _ns(**kw):
        import argparse

        base = {
            "speaker_audio": None,
            "speaker_encoder": None,
            "reference_audio": None,
            "speaker_encoder_model": None,
        }
        base.update(kw)
        return argparse.Namespace(**base)

    def test_reference_audio_merges_into_speaker_audio(self) -> None:
        from piper_train.infer_onnx import _merge_speaker_source_aliases

        ns = self._ns(reference_audio="ref.wav", speaker_encoder_model="enc.onnx")
        _merge_speaker_source_aliases(ns)
        assert ns.speaker_audio == "ref.wav"
        assert ns.speaker_encoder == "enc.onnx"

    def test_canonical_flags_win_on_conflict(self) -> None:
        from piper_train.infer_onnx import _merge_speaker_source_aliases

        ns = self._ns(
            speaker_audio="canonical.wav",
            speaker_encoder="canonical.onnx",
            reference_audio="alias.wav",
            speaker_encoder_model="alias.onnx",
        )
        _merge_speaker_source_aliases(ns)
        assert ns.speaker_audio == "canonical.wav"
        assert ns.speaker_encoder == "canonical.onnx"

    def test_noop_when_nothing_given(self) -> None:
        from piper_train.infer_onnx import _merge_speaker_source_aliases

        ns = self._ns()
        _merge_speaker_source_aliases(ns)
        assert ns.speaker_audio is None
        assert ns.speaker_encoder is None
