"""Read-only readiness audit rejects missing inputs and data leakage."""

import json

import numpy as np
import pytest


pytest.importorskip(
    "torch",
    reason="Dataset audit loads PiperDataset from the train extra; lightweight Windows CI omits it.",
)

pytestmark = pytest.mark.unit


def test_missing_and_invalid_artifacts_never_become_verified(tmp_path):
    from piper_train.tools.audit_zero_shot_inputs import audit_artifacts

    bad = tmp_path / "bad.npy"
    np.save(bad, np.full(192, np.nan, dtype=np.float32))
    rows = audit_artifacts(
        [
            {
                "id": "missing",
                "role": "encoder",
                "path": str(tmp_path / "absent.onnx"),
                "kind": "onnx",
            },
            {
                "id": "bad",
                "role": "reference",
                "path": str(bad),
                "kind": "embedding",
                "dimension": 192,
            },
        ]
    )
    assert [row["status"] for row in rows] == ["missing", "invalid"]
    assert rows[1]["sha256"]


def test_dataset_relative_paths_hash_leakage_and_provenance(tmp_path):
    from piper_train.tools.audit_zero_shot_inputs import audit_datasets

    directories = [tmp_path / "train", tmp_path / "holdout"]
    specs = []
    for directory, role in zip(directories, ["train", "holdout"], strict=True):
        directory.mkdir()
        (directory / "audio.wav").write_bytes(b"same-real-audio")
        np.save(
            directory / "embedding.npy", np.ones(192, dtype=np.float32) / np.sqrt(192)
        )
        row = {
            "speaker": "same-speaker",
            "language_id": 0,
            "phoneme_ids": [1, 2],
            "audio_path": "audio.wav",
            "audio_norm_path": "missing.npy",
            "audio_spec_path": "missing.spec.pt",
            "speaker_embedding_path": "embedding.npy",
        }
        manifest = directory / "dataset.jsonl"
        manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
        specs.append({"id": role, "role": role, "path": str(manifest)})
    before = [p.read_bytes() for d in directories for p in d.iterdir()]
    result = audit_datasets(specs)
    assert result["speaker_overlap"] == ["same-speaker"]
    assert len(result["audio_hash_overlap"]) == 1
    assert result["datasets"][0]["missing_by_field"]["audio_norm_path"] == 1
    assert result["datasets"][0]["embedding_unverified"] == 1
    assert result["datasets"][0]["embedding_invalid"] == 0
    assert not result["training_ready"]
    assert before == [p.read_bytes() for d in directories for p in d.iterdir()]


def test_expected_count_and_malformed_records_prevent_readiness(tmp_path):
    from piper_train.tools.audit_zero_shot_inputs import audit_datasets

    manifest = tmp_path / "dataset.jsonl"
    manifest.write_text('{"speaker": "x"}\nnot-json\n', encoding="utf-8")
    result = audit_datasets(
        [{"id": "train", "role": "train", "path": str(manifest), "expected_records": 3}]
    )
    dataset = result["datasets"][0]
    assert dataset["invalid_records"] == 2
    assert dataset["count_matches"] is False
    assert result["training_ready"] is False


def test_empty_or_absent_training_dataset_is_not_ready(tmp_path):
    from piper_train.tools.audit_zero_shot_inputs import audit_datasets

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert not audit_datasets([])["training_ready"]
    assert not audit_datasets([{"id": "train", "role": "train", "path": str(empty)}])[
        "training_ready"
    ]


def test_verified_embedding_requires_matching_encoder_and_hash(tmp_path):
    from piper_train.embedding_cache import save_verified
    from piper_train.tools.audit_zero_shot_inputs import audit_datasets

    vector = tmp_path / "embedding.npy"
    normalized = tmp_path / "normalized.npy"
    np.save(normalized, np.zeros(1000, dtype=np.float32))
    from piper_train.embedding_cache import file_sha256

    save_verified(
        vector,
        np.ones(192),
        {
            "version": 1,
            "encoder_sha256": "a" * 64,
            "dimension": 192,
            "audio_sha256": file_sha256(normalized),
            "source_sr": 22050,
            "target_sr": 16000,
            "resampler": "test",
            "fbank_version": "test",
            "pooling": "whole-utterance",
        },
    )
    row = {
        "speaker": "x",
        "phoneme_ids": [1, 2],
        "audio_path": "missing.wav",
        "audio_norm_path": normalized.name,
        "audio_spec_path": "missing.spec.pt",
        "speaker_embedding_path": vector.name,
    }
    manifest = tmp_path / "dataset.jsonl"
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    specs = [{"id": "train", "role": "train", "path": str(manifest)}]
    good = audit_datasets(specs, encoder_sha256="a" * 64)
    wrong = audit_datasets(specs, encoder_sha256="b" * 64)
    assert good["datasets"][0]["embedding_unverified"] == 0
    assert wrong["datasets"][0]["embedding_unverified"] == 1
    np.save(normalized, np.ones(1000, dtype=np.float32))
    stale = audit_datasets(specs, encoder_sha256="a" * 64)
    assert stale["datasets"][0]["embedding_unverified"] == 1


def test_model_id_limits_and_required_f0_are_audited(tmp_path):
    from piper_train.tools.audit_zero_shot_inputs import audit_datasets

    manifest = tmp_path / "dataset.jsonl"
    rows = [
        {"speaker": "x", "speaker_id": 0, "language_id": 0, "phoneme_ids": [185]},
        {"speaker": "y", "speaker_id": 3692, "language_id": 8, "phoneme_ids": [2]},
        {
            "speaker": "z",
            "speaker_id": 0,
            "language_id": 0,
            "phoneme_ids": [2],
            "audio_spec_path": "abc.spec.pt",
        },
    ]
    manifest.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    report = audit_datasets(
        [
            {
                "id": "train",
                "role": "train",
                "path": str(manifest),
                "num_symbols": 185,
                "num_languages": 8,
                "num_speakers": 3692,
                "f0_directory": str(tmp_path / "f0"),
            }
        ]
    )
    assert report["datasets"][0]["invalid_records"] == 2
    assert report["datasets"][0]["missing_by_field"]["f0_path"] == 1
    assert not report["audio_hash_overlap_fully_checked"]


def test_malformed_onnx_is_reported_as_invalid(tmp_path):
    from piper_train.tools.audit_zero_shot_inputs import audit_artifacts

    path = tmp_path / "invalid.onnx"
    path.write_bytes(b"not an ONNX protobuf")
    result = audit_artifacts([{"id": "bad", "path": str(path), "kind": "onnx"}])
    assert result[0]["status"] == "invalid"
