"""Unit tests for ``piper_train.tools.download_crema_d``.

These tests do NOT touch the network -- the ~27 GB CREMA-D repo is too large
to mirror in CI. Instead, we stage a miniature fixture directory that mimics
the expected layout (``AudioWAV/<speaker>_<sentence>_<emotion>_<intensity>.wav``)
and assert that parsing, metadata generation, and verification behave correctly.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import numpy as np
import pytest

try:
    import soundfile as sf  # noqa: F401

    _HAS_SOUNDFILE = True
except ImportError:
    _HAS_SOUNDFILE = False

from piper_train.tools import download_crema_d as mod


def _write_wav(path: Path, *, samplerate: int = 16000, subtype: str = "PCM_16") -> None:
    """Write a short silent WAV file with the given format."""
    assert _HAS_SOUNDFILE, "soundfile required for this test"
    # Short tone so the file is non-empty but tiny.
    duration_s = 0.05
    samples = np.zeros(int(duration_s * samplerate), dtype=np.float32)
    import soundfile as _sf
    _sf.write(str(path), samples, samplerate, subtype=subtype)


@pytest.fixture
def dummy_crema_dir(tmp_path: Path) -> Path:
    """Stage a miniature CREMA-D-like directory with a handful of WAVs."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")

    root = tmp_path / "CREMA-D"
    audio = root / "AudioWAV"
    audio.mkdir(parents=True)

    _write_wav(audio / "1001_IWW_ANG_HI.wav")
    _write_wav(audio / "1001_IWW_HAP_MD.wav")
    _write_wav(audio / "1001_IWW_NEU_XX.wav")
    _write_wav(audio / "1002_DFA_SAD_LO.wav")
    return root


@pytest.mark.unit
def test_emotion_code_parsing():
    """parse_filename splits 4-part stems correctly; unknown shapes return None."""
    assert mod.parse_filename("1001_IWW_ANG_HI") == ("1001", "IWW", "ANG", "HI")
    # 3-part filename is rejected
    assert mod.parse_filename("1001_IWW_ANG") is None


@pytest.mark.unit
def test_emotion_code_map_completeness():
    """All 6 CREMA-D emotions are mapped to canonical names."""
    assert set(mod.EMOTION_CODE_MAP) == {"ANG", "DIS", "FEA", "HAP", "NEU", "SAD"}
    assert mod.EMOTION_CODE_MAP["ANG"] == "angry"
    assert mod.EMOTION_CODE_MAP["NEU"] == "neutral"


@pytest.mark.unit
def test_metadata_generation_with_dummy_files(dummy_crema_dir: Path):
    """generate_metadata writes metadata.csv + emotions.csv with correct rows."""
    stats = mod.generate_metadata(dummy_crema_dir)
    assert stats["total"] == 4

    metadata_lines = (dummy_crema_dir / "metadata.csv").read_text(encoding="utf-8").splitlines()
    # Skip comment lines
    data_lines = [ln for ln in metadata_lines if not ln.startswith("#")]
    assert len(data_lines) == 4
    # Each line: utt_id|text|emotion
    for line in data_lines:
        parts = line.split("|")
        assert len(parts) == 3
        assert parts[2] in mod.EMOTION_CODE_MAP.values()

    emotions_lines = (dummy_crema_dir / "emotions.csv").read_text(encoding="utf-8").splitlines()
    data_lines = [ln for ln in emotions_lines if not ln.startswith("#")]
    assert len(data_lines) == 4
    # 1001_IWW_ANG_HI -> angry
    assert any(line.startswith("1001_IWW_ANG_HI,angry") for line in data_lines)
    # 1001_IWW_NEU_XX -> neutral
    assert any(line.startswith("1001_IWW_NEU_XX,neutral") for line in data_lines)

    assert stats["emotion_counts"]["angry"] == 1
    assert stats["emotion_counts"]["happy"] == 1
    assert stats["emotion_counts"]["neutral"] == 1
    assert stats["emotion_counts"]["sad"] == 1


@pytest.mark.unit
def test_metadata_skips_unknown_emotion_code(tmp_path: Path):
    """Files with unknown emotion codes are skipped with a warning."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    root = tmp_path / "crema"
    (root / "AudioWAV").mkdir(parents=True)
    _write_wav(root / "AudioWAV" / "1001_IWW_ZZZ_XX.wav")  # unknown emotion
    _write_wav(root / "AudioWAV" / "1001_IWW_ANG_XX.wav")
    stats = mod.generate_metadata(root)
    assert stats["total"] == 1
    assert "1001_IWW_ZZZ_XX.wav" in stats["skipped"]


@pytest.mark.unit
def test_metadata_skips_malformed_filename(tmp_path: Path):
    """Files whose stem has fewer than 4 parts are skipped."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    root = tmp_path / "crema"
    (root / "AudioWAV").mkdir(parents=True)
    _write_wav(root / "AudioWAV" / "short_name.wav")
    _write_wav(root / "AudioWAV" / "1001_IWW_ANG_XX.wav")
    stats = mod.generate_metadata(root)
    assert stats["total"] == 1
    assert "short_name.wav" in stats["skipped"]


@pytest.mark.unit
def test_verify_accepts_16khz_pcm16(dummy_crema_dir: Path):
    """verify() reports zero bad_files when all sample files are 16 kHz PCM_16."""
    stats = mod.verify(dummy_crema_dir, sample_n=4)
    assert stats["wav_count"] == 4
    assert stats["bad_files"] == []


@pytest.mark.unit
def test_verify_detects_wrong_samplerate(tmp_path: Path):
    """verify() flags WAVs whose samplerate != 16 kHz."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    root = tmp_path / "crema"
    (root / "AudioWAV").mkdir(parents=True)
    _write_wav(root / "AudioWAV" / "1001_IWW_ANG_XX.wav")  # 16 kHz OK
    _write_wav(root / "AudioWAV" / "1002_IWW_ANG_XX.wav", samplerate=22050)
    stats = mod.verify(root, sample_n=10)
    assert stats["wav_count"] == 2
    # The 22050 file must be flagged
    flagged = [name for name, _reason in stats["bad_files"]]
    assert "1002_IWW_ANG_XX.wav" in flagged


@pytest.mark.unit
def test_verify_missing_audio_dir_raises(tmp_path: Path):
    """verify() raises FileNotFoundError when AudioWAV/ is absent."""
    with pytest.raises(FileNotFoundError):
        mod.verify(tmp_path)


@pytest.mark.unit
def test_copy_license_writes_fallback_when_missing(tmp_path: Path):
    """copy_license writes ODbL fallback when no LICENSE file exists."""
    out = mod.copy_license(tmp_path)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "ODbL" in text or "Open Database License" in text


@pytest.mark.unit
def test_copy_license_uses_repo_license(tmp_path: Path):
    """copy_license prefers the repo's LICENSE.txt when present."""
    (tmp_path / "LICENSE.txt").write_text("Custom ODbL license body", encoding="utf-8")
    out = mod.copy_license(tmp_path)
    assert out.read_text(encoding="utf-8") == "Custom ODbL license body"


@pytest.mark.unit
def test_skip_if_exists_is_idempotent(tmp_path: Path):
    """When --skip-if-exists is set, download() must NOT invoke git clone."""
    target = tmp_path / "CREMA-D"
    target.mkdir()
    with mock.patch.object(mod.subprocess, "run") as run_mock:
        mod.download(target, skip_if_exists=True)
        run_mock.assert_not_called()


@pytest.mark.unit
def test_download_invokes_git_clone(tmp_path: Path):
    """download() invokes ``git clone --depth=1`` against the official URL."""
    target = tmp_path / "new-clone-target"
    with mock.patch.object(mod.subprocess, "run") as run_mock:
        mod.download(target, skip_if_exists=False)
    assert run_mock.called
    args = run_mock.call_args[0][0]
    assert args[0] == "git"
    assert args[1] == "clone"
    assert "--depth=1" in args
    assert mod.CREMA_D_REPO in args


@pytest.mark.unit
def test_main_verify_only_flow(dummy_crema_dir: Path):
    """`main --verify-only` works end-to-end on a staged fixture directory."""
    argv = ["--data-dir", str(dummy_crema_dir), "--verify-only"]
    rc = mod.main(argv)
    assert rc == 0
    assert (dummy_crema_dir / "metadata.csv").exists()
    assert (dummy_crema_dir / "emotions.csv").exists()
    assert (dummy_crema_dir / "LICENSE_CREMA_D.txt").exists()
