"""Unit tests for ``piper_train.tools.inject_style_labels``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from piper_train.tools import inject_style_labels as injector


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


@pytest.mark.unit
def test_inject_with_default_emotion(tmp_path: Path):
    """Without emotion CSV, every row gets ``--default-emotion`` (neutral)."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [
            {"audio_path": "wavs/1001_IWW.wav", "phoneme_ids": [1, 2, 3]},
            {"audio_path": "wavs/1002_DFA.wav", "phoneme_ids": [4, 5]},
        ],
    )
    output = tmp_path / "out.jsonl"
    stats = injector.inject_style_labels(
        input_dataset=manifest,
        output_manifest=output,
        default_emotion="neutral",
    )
    assert stats["total"] == 2
    assert stats["emotion_counts"] == {"neutral": 2}
    rows = [json.loads(ln) for ln in output.read_text().splitlines()]
    assert all(r["emotion"] == "neutral" for r in rows)
    assert all(r["style_vector_path"] is None for r in rows)


@pytest.mark.unit
def test_inject_with_emotion_csv(tmp_path: Path):
    """``utt_id,emotion`` CSV overrides default per-utterance."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [
            {"audio_path": "wavs/1001_IWW_ANG_HI.wav"},
            {"audio_path": "wavs/1002_IWW_HAP_MD.wav"},
            {"audio_path": "wavs/1003_DFA_NEU_XX.wav"},
        ],
    )
    csv = tmp_path / "emotions.csv"
    csv.write_text(
        "# utt_id,emotion\n"
        "1001_IWW_ANG_HI,angry\n"
        "1002_IWW_HAP_MD,happy\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.jsonl"
    csv_map = injector.load_emotion_mapping_from_csv(csv)
    assert csv_map == {"1001_IWW_ANG_HI": "angry", "1002_IWW_HAP_MD": "happy"}

    injector.inject_style_labels(
        input_dataset=manifest,
        output_manifest=output,
        emotion_csv_mapping=csv_map,
        default_emotion="neutral",
    )
    rows = [json.loads(ln) for ln in output.read_text().splitlines()]
    assert [r["emotion"] for r in rows] == ["angry", "happy", "neutral"]


@pytest.mark.unit
def test_inject_with_style_vector_path(tmp_path: Path):
    """Existing ``.npy`` files are attached; missing ones -> None."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [
            {"audio_path": "wavs/utt_a.wav"},
            {"audio_path": "wavs/utt_b.wav"},
            {"audio_path": "wavs/utt_c.wav"},
        ],
    )
    vectors = tmp_path / "vectors"
    vectors.mkdir()
    np.save(str(vectors / "utt_a.npy"), np.ones(4, dtype=np.float32))
    np.save(str(vectors / "utt_b.npy"), np.ones(4, dtype=np.float32))

    output = tmp_path / "out.jsonl"
    stats = injector.inject_style_labels(
        input_dataset=manifest,
        output_manifest=output,
        style_vectors_dir=vectors,
        default_emotion="neutral",
    )
    rows = [json.loads(ln) for ln in output.read_text().splitlines()]
    assert rows[0]["style_vector_path"] is not None
    assert rows[1]["style_vector_path"] is not None
    assert rows[2]["style_vector_path"] is None
    assert stats["with_vector"] == 2
    assert stats["skipped"] == 1


@pytest.mark.unit
def test_inject_materialises_from_style_bank(tmp_path: Path):
    """With ``--style-bank`` + ``--output-dir``, per-utterance .npy files are written."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [
            {"audio_path": "wavs/u1.wav"},
            {"audio_path": "wavs/u2.wav"},
        ],
    )
    bank_path = tmp_path / "bank.npz"
    centroids = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32
    )
    global_c = np.array([0.5, 0.5, 0.0, 0.0], dtype=np.float32)
    np.savez(
        str(bank_path),
        emotion_names=np.array(["angry", "happy"], dtype=object),
        emotion_centroids=centroids,
        global_centroid=global_c,
    )
    csv = tmp_path / "emo.csv"
    csv.write_text("u1,angry\nu2,happy\n", encoding="utf-8")
    csv_map = injector.load_emotion_mapping_from_csv(csv)

    output = tmp_path / "out.jsonl"
    out_vectors = tmp_path / "out_vectors"
    injector.inject_style_labels(
        input_dataset=manifest,
        output_manifest=output,
        emotion_csv_mapping=csv_map,
        style_bank_path=bank_path,
        output_vectors_dir=out_vectors,
        default_emotion="neutral",
    )
    assert (out_vectors / "u1.npy").exists()
    assert (out_vectors / "u2.npy").exists()
    assert np.allclose(np.load(str(out_vectors / "u1.npy")), centroids[0])
    assert np.allclose(np.load(str(out_vectors / "u2.npy")), centroids[1])


@pytest.mark.unit
def test_inject_idempotent_overwrites(tmp_path: Path):
    """Running injection twice yields the same JSONL content."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [{"audio_path": "wavs/u1.wav", "phoneme_ids": [1, 2]}],
    )
    output = tmp_path / "out.jsonl"
    injector.inject_style_labels(
        input_dataset=manifest, output_manifest=output, default_emotion="neutral"
    )
    first = output.read_text()
    injector.inject_style_labels(
        input_dataset=output, output_manifest=output, default_emotion="neutral"
    )
    second = output.read_text()
    assert first == second


@pytest.mark.unit
def test_inject_preserves_existing_fields(tmp_path: Path):
    """Existing phoneme_ids / speaker_id / prosody_features survive injection."""
    manifest = tmp_path / "manifest.jsonl"
    row = {
        "audio_path": "wavs/u1.wav",
        "phoneme_ids": [1, 8, 5],
        "speaker_id": 42,
        "prosody_features": [{"a1": -2, "a2": 1, "a3": 5}],
    }
    _write_jsonl(manifest, [row])
    output = tmp_path / "out.jsonl"
    injector.inject_style_labels(
        input_dataset=manifest, output_manifest=output, default_emotion="neutral"
    )
    out_row = json.loads(output.read_text().splitlines()[0])
    assert out_row["phoneme_ids"] == [1, 8, 5]
    assert out_row["speaker_id"] == 42
    assert out_row["prosody_features"] == [{"a1": -2, "a2": 1, "a3": 5}]
    assert out_row["emotion"] == "neutral"


@pytest.mark.unit
def test_inject_row_count_preserved(tmp_path: Path):
    """Input JSONL row count equals output row count."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [{"audio_path": f"wavs/u{i}.wav"} for i in range(10)],
    )
    output = tmp_path / "out.jsonl"
    stats = injector.inject_style_labels(
        input_dataset=manifest, output_manifest=output, default_emotion="neutral"
    )
    assert stats["total"] == 10
    assert len(output.read_text().splitlines()) == 10


@pytest.mark.unit
def test_inject_skips_blank_lines(tmp_path: Path):
    """Blank lines in the manifest are silently skipped."""
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"audio_path": "wavs/a.wav"}) + "\n"
        + "\n"
        + json.dumps({"audio_path": "wavs/b.wav"}) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.jsonl"
    injector.inject_style_labels(
        input_dataset=manifest, output_manifest=output, default_emotion="neutral"
    )
    assert len(output.read_text().splitlines()) == 2


@pytest.mark.unit
def test_validate_emotions_against_bank_detects_missing(tmp_path: Path):
    """Emotions absent from the style bank are flagged."""
    bank_path = tmp_path / "bank.npz"
    np.savez(
        str(bank_path),
        emotion_names=np.array(["angry", "happy"], dtype=object),
        emotion_centroids=np.eye(2, dtype=np.float32),
        global_centroid=np.array([0.5, 0.5], dtype=np.float32),
    )
    missing = injector.validate_emotions_against_bank(
        {"utt1": "angry", "utt2": "unknown_emotion"}, bank_path
    )
    assert missing == {"unknown_emotion"}


@pytest.mark.unit
def test_load_emotion_map_inverts(tmp_path: Path):
    """JSON emotion map is inverted so CSV codes map to friendly labels."""
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps({"happy": "HAP", "sad": "SAD", "neutral": "NEU"}),
        encoding="utf-8",
    )
    mapping = injector.load_emotion_map(path)
    # Keys are lowercased to match CSV loader normalisation.
    assert mapping["hap"] == "happy"
    assert mapping["sad"] == "sad"
    assert mapping["neu"] == "neutral"


@pytest.mark.unit
def test_load_emotion_map_rejects_non_object(tmp_path: Path):
    """Non-object JSON maps raise ValueError."""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(["happy", "sad"]), encoding="utf-8")
    with pytest.raises(ValueError):
        injector.load_emotion_map(path)


@pytest.mark.unit
def test_emotion_csv_applies_translation(tmp_path: Path):
    """Emotion translation map converts CSV codes into friendly labels."""
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(
        manifest,
        [
            {"audio_path": "wavs/u1.wav"},
            {"audio_path": "wavs/u2.wav"},
        ],
    )
    csv = tmp_path / "emo.csv"
    csv.write_text("u1,HAP\nu2,SAD\n", encoding="utf-8")
    emotion_csv = injector.load_emotion_mapping_from_csv(csv)
    # Translation keys must also be lowercase (matches CSV loader behaviour).
    translation = {"hap": "happy", "sad": "sad"}
    output = tmp_path / "out.jsonl"
    injector.inject_style_labels(
        input_dataset=manifest,
        output_manifest=output,
        emotion_csv_mapping=emotion_csv,
        emotion_translation=translation,
        default_emotion="neutral",
    )
    rows = [json.loads(ln) for ln in output.read_text().splitlines()]
    assert [r["emotion"] for r in rows] == ["happy", "sad"]
