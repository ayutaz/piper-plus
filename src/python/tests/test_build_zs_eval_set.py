"""Zero-shot evaluation set builder: pinned audio, references and texts."""

import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.unit


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def sources(tmp_path):
    """One zip-backed corpus and one plain directory corpus."""
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    audio = {name: f"RIFF-{name}".encode() for name in ("a_000", "a_001", "a_002")}
    with zipfile.ZipFile(zip_dir / "a.zip", "w") as archive:
        for name, data in audio.items():
            archive.writestr(f"data/a/wav/{name}.wav", data)
    plain = tmp_path / "plain"
    plain.mkdir()
    audio["b_000"] = b"RIFF-b_000"
    (plain / "b_000.wav").write_bytes(audio["b_000"])
    return {"zips": zip_dir, "plain": plain}, audio


def _spec(audio):
    def zipped(role, name):
        return {
            "role": role,
            "file": f"{role}_{name}.wav",
            "sha256": _sha(audio[name]),
            "source": "zips",
            "zip": "a.zip",
            "member": f"data/a/wav/{name}.wav",
        }

    return {
        "schema": "zs-eval-set-v1",
        "name": "fixture",
        "sources": {"zips": {"kind": "zip-dir"}, "plain": {"kind": "dir"}},
        "groups": {
            "ja_a": {
                "references": ["speaker_a_000.wav"],
                "files": [
                    zipped("speaker", "a_000"),
                    zipped("speaker", "a_001"),
                    {
                        "role": "floor",
                        "file": "floor_b_000.wav",
                        "sha256": _sha(audio["b_000"]),
                        "source": "plain",
                        "member": "b_000.wav",
                    },
                ],
            }
        },
        "clips": [
            {
                "id": f"ja_a_r0_t{i}",
                "group": "ja_a",
                "reference": 0,
                "text": text,
                "phoneme_ids": [1, 10, 2],
                "language_id": 0,
                "speaker_id": 0,
            }
            for i, text in enumerate(["こんにちは", "ありがとう", "さようなら"])
        ],
    }


def _embed(path: Path) -> np.ndarray:
    vector = np.ones(192, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def test_materialize_copies_audio_and_writes_test_jsonl(tmp_path, sources):
    from piper_train.tools.build_zs_eval_set import materialize

    roots, audio = sources
    out = tmp_path / "set"
    materialize(_spec(audio), roots, out, _embed)

    group = out / "groups" / "ja_a"
    assert (group / "speaker" / "speaker_a_001.wav").read_bytes() == audio["a_001"]
    assert (group / "floor" / "floor_b_000.wav").read_bytes() == audio["b_000"]
    assert np.load(group / "ref0.npy").shape == (192,)

    rows = [
        json.loads(line)
        for line in (out / "test.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["id"] for row in rows] == ["ja_a_r0_t0", "ja_a_r0_t1", "ja_a_r0_t2"]
    assert rows[0]["text"] == "こんにちは"
    assert rows[0]["speaker_embedding_path"] == "groups/ja_a/ref0.npy"
    assert rows[0]["reference_audio_paths"] == ["groups/ja_a/speaker/speaker_a_000.wav"]

    record = json.loads((out / "set.json").read_text(encoding="utf-8"))
    assert record["name"] == "fixture"
    assert record["groups"]["ja_a"]["embeddings"][0]["sha256"] == _sha(
        (group / "ref0.npy").read_bytes()
    )


def test_test_jsonl_is_accepted_by_evaluation_manifest(tmp_path, sources):
    from piper_train.evaluation_manifest import create_manifest, load_manifest
    from piper_train.tools.build_zs_eval_set import materialize

    roots, audio = sources
    out = tmp_path / "set"
    materialize(_spec(audio), roots, out, _embed)
    model = tmp_path / "model.ckpt"
    model.write_bytes(b"model")
    create_manifest(
        source_path=out / "test.jsonl",
        output_path=tmp_path / "manifest.json",
        models={"torch-ema": model},
        sample_rate=22050,
        asr_revision="a" * 40,
        source_revision="b" * 40,
    )
    manifest = load_manifest(tmp_path / "manifest.json")
    assert len(manifest["clips"]) == 3


def test_hash_mismatch_is_rejected_and_nothing_is_published(tmp_path, sources):
    from piper_train.tools.build_zs_eval_set import materialize

    roots, audio = sources
    spec = _spec(audio)
    spec["groups"]["ja_a"]["files"][1]["sha256"] = "0" * 64
    out = tmp_path / "set"
    with pytest.raises(ValueError, match="sha256"):
        materialize(spec, roots, out, _embed)
    assert not out.exists()
    assert list(tmp_path.glob("set*")) == []


def test_nonempty_output_is_rejected(tmp_path, sources):
    from piper_train.tools.build_zs_eval_set import materialize

    roots, audio = sources
    out = tmp_path / "set"
    out.mkdir()
    (out / "old.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        materialize(_spec(audio), roots, out, _embed)
    assert (out / "old.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "mutation",
    ["reference-index", "reference-not-speaker", "unknown-group", "unknown-source"],
)
def test_inconsistent_spec_is_rejected(tmp_path, sources, mutation):
    from piper_train.tools.build_zs_eval_set import materialize

    roots, audio = sources
    spec = _spec(audio)
    if mutation == "reference-index":
        spec["clips"][0]["reference"] = 1
    elif mutation == "reference-not-speaker":
        spec["groups"]["ja_a"]["references"] = ["floor_b_000.wav"]
    elif mutation == "unknown-group":
        spec["clips"][0]["group"] = "ja_missing"
    else:
        spec["groups"]["ja_a"]["files"][0]["source"] = "missing"
    with pytest.raises(ValueError):
        materialize(spec, roots, tmp_path / "set", _embed)
    assert not (tmp_path / "set").exists()
