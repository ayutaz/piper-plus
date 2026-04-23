"""Phase 5 P5-T01: unit tests for prepare_emotion_finetune_dataset.

The real CREMA-D corpus is 27 GB and the fine-tune dataset output lives under
/data/piper/. This test uses a tmp_path-based mini corpus with three synthetic
WAV filenames + .npy stubs, so we exercise the manifest-builder logic without
requiring the full dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from piper_train.tools.prepare_emotion_finetune_dataset import (
    CREMA_D_SENTENCES,
    EMOTION_MAP,
    build_crema_d_manifest,
)


def _write_dummy_wav(path: Path) -> None:
    """Write a 44-byte RIFF header so the file exists on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 28)


def _write_dummy_style_vector(path: Path, dim: int = 256) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.random.randn(dim).astype(np.float32))


def _write_base_config(path: Path) -> None:
    """Write a minimal 6lang-style base config."""
    path.write_text(json.dumps({
        "audio": {"sample_rate": 22050},
        "phoneme_id_map": {"_": [0], "^": [1], "$": [2]},
        "num_languages": 6,
        "prosody_dim": 16,
    }, ensure_ascii=False, indent=2))


def _build_mini_corpus(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    crema_d_dir = tmp_path / "CREMA-D"
    audio_wav_dir = crema_d_dir / "AudioWAV"
    style_vectors_dir = tmp_path / "style_vectors_crema_d"
    output_dir = tmp_path / "dataset-crema-d-emotion"
    base_config = tmp_path / "base_config.json"
    _write_base_config(base_config)

    # 3 samples: different speakers / different emotions / valid sentences.
    samples = [
        "1001_IEO_ANG_XX",
        "1002_TIE_HAP_LO",
        "1003_DFA_SAD_MD",
    ]
    for stem in samples:
        _write_dummy_wav(audio_wav_dir / f"{stem}.wav")
        _write_dummy_style_vector(style_vectors_dir / f"{stem}.npy")

    return crema_d_dir, style_vectors_dir, output_dir, base_config


def test_emotion_map_has_all_six_labels() -> None:
    """Contract: CREMA-D is a 6-emotion corpus."""
    assert set(EMOTION_MAP.keys()) == {"ANG", "DIS", "FEA", "HAP", "NEU", "SAD"}
    assert set(EMOTION_MAP.values()) == {
        "angry", "disgusted", "fearful", "happy", "neutral", "sad",
    }


def test_crema_d_sentences_has_all_twelve() -> None:
    """Contract: CREMA-D ships exactly 12 fixed English sentences."""
    assert len(CREMA_D_SENTENCES) == 12
    for code, text in CREMA_D_SENTENCES.items():
        assert len(code) == 3
        assert text.endswith(".") or text.endswith("?") or text.endswith("!")


def test_build_manifest_produces_jsonl_and_config(tmp_path: Path) -> None:
    """build_crema_d_manifest writes dataset.jsonl + config.json."""
    crema_d_dir, style_vectors_dir, output_dir, base_config = _build_mini_corpus(tmp_path)

    n_written, n_skipped = build_crema_d_manifest(
        crema_d_dir=crema_d_dir,
        style_vectors_dir=style_vectors_dir,
        output_dir=output_dir,
        base_config_path=base_config,
        style_vector_dim=256,
    )

    assert n_written == 3
    assert n_skipped == 0
    assert (output_dir / "dataset.jsonl").is_file()
    assert (output_dir / "config.json").is_file()


def test_manifest_records_carry_required_fields(tmp_path: Path) -> None:
    """Each dataset.jsonl row must carry the Phase 1 fields."""
    crema_d_dir, style_vectors_dir, output_dir, base_config = _build_mini_corpus(tmp_path)
    build_crema_d_manifest(
        crema_d_dir=crema_d_dir,
        style_vectors_dir=style_vectors_dir,
        output_dir=output_dir,
        base_config_path=base_config,
    )

    lines = (output_dir / "dataset.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    required_keys = {
        "audio_path", "text", "speaker", "speaker_id",
        "language", "style_vector_path", "emotion",
    }
    for line in lines:
        record = json.loads(line)
        assert required_keys.issubset(record.keys())
        assert record["language"] == "en"
        assert record["emotion"] in {"angry", "happy", "sad"}


def test_config_inherits_and_overrides_base(tmp_path: Path) -> None:
    """config.json must inherit 6lang base keys and add style_* keys."""
    crema_d_dir, style_vectors_dir, output_dir, base_config = _build_mini_corpus(tmp_path)
    build_crema_d_manifest(
        crema_d_dir=crema_d_dir,
        style_vectors_dir=style_vectors_dir,
        output_dir=output_dir,
        base_config_path=base_config,
        style_vector_dim=256,
    )
    cfg = json.loads((output_dir / "config.json").read_text(encoding="utf-8"))
    # Inherited keys must be preserved bit-for-bit.
    assert cfg["phoneme_id_map"] == {"_": [0], "^": [1], "$": [2]}
    assert cfg["num_languages"] == 6
    assert cfg["prosody_dim"] == 16
    # New keys from Phase 1.
    assert cfg["num_speakers"] == 3
    assert cfg["style_vector_dim"] == 256
    assert cfg["style_condition_mode"] == "global"
    assert cfg["style_condition_dropout"] == 0.1


def test_missing_style_vector_is_skipped(tmp_path: Path) -> None:
    """Utterances lacking a .npy pair must be skipped, not raise."""
    crema_d_dir, style_vectors_dir, output_dir, base_config = _build_mini_corpus(tmp_path)
    # Delete one .npy — its WAV row should be skipped.
    missing_npy = style_vectors_dir / "1002_TIE_HAP_LO.npy"
    missing_npy.unlink()

    n_written, n_skipped = build_crema_d_manifest(
        crema_d_dir=crema_d_dir,
        style_vectors_dir=style_vectors_dir,
        output_dir=output_dir,
        base_config_path=base_config,
    )
    assert n_written == 2
    assert n_skipped == 1


def test_malformed_filename_is_skipped(tmp_path: Path) -> None:
    """Filenames not matching ``speaker_sentence_emotion_intensity`` must be skipped."""
    crema_d_dir, style_vectors_dir, output_dir, base_config = _build_mini_corpus(tmp_path)
    # Add a malformed entry.
    _write_dummy_wav(crema_d_dir / "AudioWAV" / "malformed.wav")
    _write_dummy_style_vector(style_vectors_dir / "malformed.npy")

    n_written, n_skipped = build_crema_d_manifest(
        crema_d_dir=crema_d_dir,
        style_vectors_dir=style_vectors_dir,
        output_dir=output_dir,
        base_config_path=base_config,
    )
    assert n_written == 3  # only the 3 well-formed samples
    assert n_skipped == 1  # malformed one skipped


def test_unknown_emotion_is_skipped(tmp_path: Path) -> None:
    """Unknown emotion tokens must be skipped silently."""
    crema_d_dir, style_vectors_dir, output_dir, base_config = _build_mini_corpus(tmp_path)
    # Add a file with an unknown emotion.
    stem = "1099_IEO_XYZ_HI"
    _write_dummy_wav(crema_d_dir / "AudioWAV" / f"{stem}.wav")
    _write_dummy_style_vector(style_vectors_dir / f"{stem}.npy")

    n_written, n_skipped = build_crema_d_manifest(
        crema_d_dir=crema_d_dir,
        style_vectors_dir=style_vectors_dir,
        output_dir=output_dir,
        base_config_path=base_config,
    )
    assert n_written == 3
    assert n_skipped == 1


def test_missing_audio_dir_raises(tmp_path: Path) -> None:
    """Absence of AudioWAV/ must fail fast with FileNotFoundError."""
    crema_d_dir = tmp_path / "CREMA-D"
    crema_d_dir.mkdir()
    style_vectors_dir = tmp_path / "style_vectors"
    style_vectors_dir.mkdir()
    output_dir = tmp_path / "output"
    base_config = tmp_path / "base_config.json"
    _write_base_config(base_config)

    with pytest.raises(FileNotFoundError, match="Audio subdirectory not found"):
        build_crema_d_manifest(
            crema_d_dir=crema_d_dir,
            style_vectors_dir=style_vectors_dir,
            output_dir=output_dir,
            base_config_path=base_config,
        )


def test_empty_audio_dir_raises(tmp_path: Path) -> None:
    """An empty AudioWAV/ must fail fast with RuntimeError."""
    crema_d_dir = tmp_path / "CREMA-D"
    (crema_d_dir / "AudioWAV").mkdir(parents=True)
    style_vectors_dir = tmp_path / "style_vectors"
    style_vectors_dir.mkdir()
    output_dir = tmp_path / "output"
    base_config = tmp_path / "base_config.json"
    _write_base_config(base_config)

    with pytest.raises(RuntimeError, match="No WAV files"):
        build_crema_d_manifest(
            crema_d_dir=crema_d_dir,
            style_vectors_dir=style_vectors_dir,
            output_dir=output_dir,
            base_config_path=base_config,
        )
