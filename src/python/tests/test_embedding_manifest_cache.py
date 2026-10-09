"""Real extraction wrappers with deterministic frontend/session fixtures."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="extraction fixtures require torch")
pytest.importorskip("torchaudio", reason="extraction frontend requires torchaudio")

from piper_train import extract_speaker_embedding as ese  # noqa: E402


pytestmark = pytest.mark.unit


class Encoder:
    def __init__(self, path):
        self._model_path = str(path)
        self.calls = 0
        self.invalid = False

    def get_inputs(self):
        return [SimpleNamespace(name="features")]

    def get_outputs(self):
        return [SimpleNamespace(name="embedding")]

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def run(self, _outputs, feeds):
        self.calls += 1
        rows = next(iter(feeds.values())).shape[0]
        return [np.full((rows, 192), np.nan if self.invalid else 1.0, dtype=np.float32)]


@pytest.fixture
def fixture_data(tmp_path, monkeypatch):
    ds = tmp_path / "dataset"
    ds.mkdir()
    model = tmp_path / "encoder.onnx"
    model.write_bytes(b"encoder-v1")

    def frontend(self, index):
        entry, _path, key = self.items[index]
        fb = (
            torch.ones((2, self.fixed_frames, 80))
            if self.fixed_frames
            else torch.ones((8, 80))
        )
        return entry, fb, key, True

    monkeypatch.setattr(ese._FbankDataset, "__getitem__", frontend)
    return ds, Encoder(model)


def write_entries(ds, names):
    rows = []
    for index, name in enumerate(names):
        path = ds / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"audio-{index}".encode())
        rows.append({"audio_norm_path": name, "speaker_id": index})
    (ds / "dataset.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return rows


def read_entries(ds):
    return [
        json.loads(line) for line in (ds / "dataset.jsonl").read_text().splitlines()
    ]


@pytest.mark.parametrize("fixed,padded", [(400, False), (0, False), (0, True)])
def test_collision_custom_directory_cache_provenance_and_rerun(
    fixture_data, tmp_path, fixed, padded
):
    ds, encoder = fixture_data
    write_entries(ds, ["a/same.pt", "b/same.pt"])
    output = tmp_path / "custom"
    options = {
        "dataset_dir": ds,
        "output_dir": output,
        "num_workers": 0,
        "fixed_frames": fixed,
        "use_batch_infer": padded,
    }
    ese.extract_per_utterance(encoder, **options)
    paths = [(ds / row["speaker_embedding_path"]).resolve() for row in read_entries(ds)]
    assert len(set(paths)) == 2
    assert all(path.parent == output for path in paths)
    for path in paths:
        vector = np.load(path)
        assert vector.shape == (192,) and np.linalg.norm(vector) == pytest.approx(1)
        metadata = json.loads(path.with_suffix(".json").read_text())
        assert metadata["encoder_sha256"] and metadata["audio_sha256"]
        assert metadata["embedding_sha256"] and metadata["version"] == 1
    calls = encoder.calls
    ese.extract_per_utterance(encoder, **options)
    assert encoder.calls == calls
    # A corrupted numerical cache cannot be accepted merely because it exists.
    np.save(paths[0], np.zeros(192, dtype=np.float32))
    ese.extract_per_utterance(encoder, **options)
    assert encoder.calls > calls


def test_missing_only_aborts_without_modifying_manifest(fixture_data):
    ds, encoder = fixture_data
    original = '{"audio_norm_path":"missing.pt"}\n'
    (ds / "dataset.jsonl").write_text(original)
    with pytest.raises(RuntimeError, match="failed"):
        ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    assert (ds / "dataset.jsonl").read_text() == original


def test_partial_failure_never_publishes_missing_embedding(fixture_data):
    ds, encoder = fixture_data
    rows = write_entries(ds, ["good.pt"])
    rows.append(
        {"audio_norm_path": "missing.pt", "speaker_embedding_path": "ghost.npy"}
    )
    (ds / "dataset.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    updated = read_entries(ds)
    assert (ds / updated[0]["speaker_embedding_path"]).exists()
    assert "speaker_embedding_path" not in updated[1]


def test_invalid_encoder_output_aborts_without_manifest_change(fixture_data):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    original = (ds / "dataset.jsonl").read_bytes()
    encoder.invalid = True
    with pytest.raises(RuntimeError, match="failed"):
        ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    assert (ds / "dataset.jsonl").read_bytes() == original


def test_dry_run_preserves_files_and_reports_legacy_cache(fixture_data):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    cache = ds / "speaker_embeddings"
    cache.mkdir()
    np.save(cache / "good.npy", np.ones(192))
    before = {str(p): p.read_bytes() for p in ds.rglob("*") if p.is_file()}
    report = ese.extract_per_utterance(
        encoder, dataset_dir=ds, num_workers=0, dry_run=True
    )
    assert report["reextract"] == report["legacy"] == 1
    assert encoder.calls == 0
    assert before == {str(p): p.read_bytes() for p in ds.rglob("*") if p.is_file()}


def test_shards_are_stable_and_finalize_requires_all_results(fixture_data):
    ds, encoder = fixture_data
    write_entries(ds, ["a.pt", "b.pt"])
    original = (ds / "dataset.jsonl").read_bytes()
    ese.extract_per_utterance(
        encoder,
        dataset_dir=ds,
        num_workers=0,
        shard=0,
        num_shards=2,
        update_jsonl=False,
    )
    assert (ds / "dataset.jsonl").read_bytes() == original
    with pytest.raises(RuntimeError, match="incomplete"):
        ese.extract_per_utterance(
            encoder, dataset_dir=ds, num_workers=0, finalize_only=True
        )
    assert (ds / "dataset.jsonl").read_bytes() == original
    ese.extract_per_utterance(
        encoder,
        dataset_dir=ds,
        num_workers=0,
        shard=1,
        num_shards=2,
        update_jsonl=False,
    )
    calls = encoder.calls
    ese.extract_per_utterance(
        encoder, dataset_dir=ds, num_workers=0, finalize_only=True
    )
    assert encoder.calls == calls
    assert all(
        (ds / row["speaker_embedding_path"]).exists() for row in read_entries(ds)
    )


def test_cli_dry_run_never_constructs_onnx_session(fixture_data, monkeypatch, capsys):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    before = (ds / "dataset.jsonl").read_bytes()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not construct an encoder session")

    monkeypatch.setattr(ese.onnxruntime, "InferenceSession", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "extract",
            "--encoder",
            encoder._model_path,
            "--dataset-dir",
            str(ds),
            "--per-utterance",
            "--dry-run-cache",
        ],
    )
    ese.main()
    assert json.loads(capsys.readouterr().out)["reextract"] == 1
    assert (ds / "dataset.jsonl").read_bytes() == before
    assert not (ds / "speaker_embeddings").exists()


def test_encoder_audio_or_settings_change_prevents_cache_reuse(fixture_data):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    options = {"dataset_dir": ds, "num_workers": 0}
    ese.extract_per_utterance(encoder, **options)
    for path, data in [
        (Path(encoder._model_path), b"encoder-v2"),
        (ds / "good.pt", b"audio-v2"),
    ]:
        before = encoder.calls
        path.write_bytes(data)
        ese.extract_per_utterance(encoder, **options)
        assert encoder.calls > before
    before = encoder.calls
    ese.extract_per_utterance(encoder, **options, fixed_frames=0)
    assert encoder.calls > before


@pytest.mark.parametrize(
    "changed", [{"batch_size": 1}, {"chunk_batch": 1}, {"use_length_sort": False}]
)
def test_batch_recipe_change_invalidates_cache(fixture_data, changed):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    report = ese.extract_per_utterance(
        encoder, dataset_dir=ds, num_workers=0, dry_run=True, **changed
    )
    assert report["reextract"] == 1 and report["reuse"] == 0


def test_cli_finalize_uses_the_requested_extraction_recipe(
    fixture_data, monkeypatch, capsys
):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    ese.extract_per_utterance(
        encoder,
        dataset_dir=ds,
        num_workers=0,
        batch_size=1,
        chunk_batch=1,
        update_jsonl=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "extract",
            "--encoder",
            encoder._model_path,
            "--dataset-dir",
            str(ds),
            "--per-utterance",
            "--finalize-manifest",
            "--batch-size",
            "1",
            "--chunk-batch",
            "1",
        ],
    )
    ese.main()
    assert json.loads(capsys.readouterr().out)["reuse"] == 1
    assert (ds / read_entries(ds)[0]["speaker_embedding_path"]).is_file()


@pytest.mark.parametrize(
    "damage", ["list-metadata", "missing-metadata", "zero-with-valid-hash"]
)
def test_corrupt_cache_is_reextracted_even_with_a_matching_file_hash(
    fixture_data, damage
):
    from piper_train.embedding_cache import file_sha256

    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    path = ds / read_entries(ds)[0]["speaker_embedding_path"]
    sidecar = path.with_suffix(".json")
    if damage == "list-metadata":
        sidecar.write_text("[]")
    elif damage == "missing-metadata":
        sidecar.unlink()
    else:
        np.save(path, np.zeros(192, dtype=np.float32))
        metadata = json.loads(sidecar.read_text())
        metadata["embedding_sha256"] = file_sha256(path)
        sidecar.write_text(json.dumps(metadata))
    before = encoder.calls
    ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    assert encoder.calls > before
    assert np.linalg.norm(
        np.load(ds / read_entries(ds)[0]["speaker_embedding_path"])
    ) == pytest.approx(1)


def test_per_speaker_paths_are_dataset_relative_and_workers_execute(
    fixture_data, monkeypatch, tmp_path
):
    ds, encoder = fixture_data
    write_entries(ds, ["sub/audio.pt"])
    seen = []

    def load(path):
        seen.append(Path(path))
        assert Path(path) == ds / "sub/audio.pt"
        return torch.ones(22050 * 4)

    monkeypatch.setattr(ese, "load_audio_norm_tensor", load)
    monkeypatch.setattr(
        ese,
        "_load_audio_from_pt",
        lambda path, **kwargs: np.ones((8, 80), dtype=np.float32),
    )
    ese.extract_from_dataset(encoder, ds, tmp_path / "speaker", workers=2)
    assert seen and (tmp_path / "speaker/speaker_0.npy").exists()
    with pytest.raises(ValueError, match="workers"):
        ese.extract_from_dataset(encoder, ds, tmp_path / "speaker", workers=0)


def test_failed_atomic_save_cannot_publish_manifest_path(fixture_data, monkeypatch):
    ds, encoder = fixture_data
    write_entries(ds, ["good.pt"])
    original = (ds / "dataset.jsonl").read_bytes()

    def failing_save(*_args):
        raise OSError("simulated interrupted save")

    monkeypatch.setattr(ese, "save_verified", failing_save)
    with pytest.raises(RuntimeError, match="failed"):
        ese.extract_per_utterance(encoder, dataset_dir=ds, num_workers=0)
    assert (ds / "dataset.jsonl").read_bytes() == original


@pytest.mark.parametrize("fixed,padded", [(400, False), (0, False), (0, True)])
def test_inference_failure_is_recorded_without_losing_other_successes(
    fixture_data, fixed, padded
):
    ds, encoder = fixture_data
    write_entries(ds, ["a.pt", "b.pt"])
    run = encoder.run
    calls = 0

    def interrupted(_outputs, feeds):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("encoder unavailable on first batch")
        return run(_outputs, feeds)

    encoder.run = interrupted
    ese.extract_per_utterance(
        encoder,
        dataset_dir=ds,
        num_workers=0,
        batch_size=1,
        fixed_frames=fixed,
        use_batch_infer=padded,
    )
    rows = read_entries(ds)
    assert "speaker_embedding_path" not in rows[0]
    assert (ds / rows[1]["speaker_embedding_path"]).exists()
