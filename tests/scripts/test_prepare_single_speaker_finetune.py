import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts/prepare_single_speaker_finetune.py"
)
spec = importlib.util.spec_from_file_location("prepare_ft", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs(tmp_path, ids=(1, 3, 0, 2), language_id=0):
    source = tmp_path / "prepared"
    source.mkdir()
    source_config = {
        "num_speakers": 1,
        "language_id_map": {"ja": 0, "en": 1},
        "phoneme_id_map": {"_": [0], "^": [1], "$": [2], "a": [3], "b": [4]},
    }
    base = {
        **source_config,
        "num_speakers": 571,
        "num_symbols": 5,
        "phoneme_id_map": {"_": [0], "^": [1], "$": [2], "a": [4], "b": [3]},
        "language_id_map": {"en": 0, "ja": 1},
        "speaker_id_map": {},
    }
    (source / "config.json").write_text(json.dumps(source_config), encoding="utf-8")
    (tmp_path / "base.json").write_text(json.dumps(base), encoding="utf-8")
    entry = {
        "phoneme_ids": list(ids),
        "prosody_features": [None] * len(ids),
        "language_id": language_id,
        "audio_norm_path": "audio.pt",
        "audio_spec_path": "audio.spec.pt",
    }
    (source / "dataset.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    for name in ["audio.pt", "audio.spec.pt"]:
        (source / name).write_bytes(b"cached audio")
    return source, tmp_path / "base.json", tmp_path / "result"


def test_preserves_phoneme_and_language_identity_despite_equal_vocab_size(tmp_path):
    source, base, output = inputs(tmp_path)
    module.prepare(source, base, output)
    result = json.loads((output / "dataset.jsonl").read_text(encoding="utf-8"))
    assert result["phoneme_ids"] == [1, 4, 0, 2]
    assert result["language_id"] == 1
    assert result["prosody_features"] == [None] * 4
    assert Path(result["audio_norm_path"]) == source / "audio.pt"
    config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    assert config["num_speakers"] == 1
    assert config["phoneme_id_map"]["a"] == [4]


def test_rejects_untrained_token_without_creating_output(tmp_path):
    source, base, output = inputs(tmp_path, ids=(4,))
    config = json.loads(base.read_text(encoding="utf-8"))
    config["phoneme_id_map"].pop("b")
    base.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="b"):
        module.prepare(source, base, output)
    assert not output.exists()


def test_rejects_missing_audio_before_writing_dataset(tmp_path):
    source, base, output = inputs(tmp_path)
    (source / "audio.spec.pt").unlink()
    with pytest.raises(ValueError, match=r"audio\.spec\.pt"):
        module.prepare(source, base, output)
    assert not output.exists()


def test_does_not_overwrite_existing_prepared_dataset(tmp_path):
    source, base, output = inputs(tmp_path)
    output.mkdir()
    with pytest.raises(FileExistsError):
        module.prepare(source, base, output)


def test_accepts_preprocessor_cache_paths_relative_to_working_directory(
    tmp_path, monkeypatch
):
    source, base, output = inputs(tmp_path)
    entry = json.loads((source / "dataset.jsonl").read_text(encoding="utf-8"))
    entry["audio_norm_path"] = "prepared/audio.pt"
    entry["audio_spec_path"] = "prepared/audio.spec.pt"
    (source / "dataset.jsonl").write_text(json.dumps(entry), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    module.prepare(source, base, output)
    result = json.loads((output / "dataset.jsonl").read_text(encoding="utf-8"))
    assert Path(result["audio_norm_path"]) == source / "audio.pt"
    assert Path(result["audio_spec_path"]) == source / "audio.spec.pt"


def test_rejects_ambiguous_cache_locations(tmp_path, monkeypatch):
    source, base, output = inputs(tmp_path)
    entry = json.loads((source / "dataset.jsonl").read_text(encoding="utf-8"))
    entry["audio_norm_path"] = "prepared/audio.pt"
    (source / "dataset.jsonl").write_text(json.dumps(entry), encoding="utf-8")
    duplicate = source / "prepared"
    duplicate.mkdir()
    (duplicate / "audio.pt").write_bytes(b"different audio")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="ambiguous cache"):
        module.prepare(source, base, output)
    assert not output.exists()
