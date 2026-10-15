"""Regressions reproduced on the free Colab T4 with the v2.0.0 source."""

import ast
import json
import os
from pathlib import Path

import pytest


NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks/finetune.ipynb"


def cells():
    return [
        "".join(cell["source"])
        for cell in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
    ]


def normalizer():
    source = next(
        (cell for cell in cells() if "def normalize_single_language_dataset(" in cell),
        None,
    )
    assert source is not None, "Notebook must handle v2.0.0 single-language null IDs"
    function = next(
        node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
    )
    namespace = {"Path": Path, "json": json}
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]), "notebook-normalizer", "exec"
        ),
        namespace,
    )
    return namespace["normalize_single_language_dataset"]


def dataset(tmp_path, config, language_id):
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    entry = {
        "language_id": language_id,
        "phoneme_ids": [1, 3, 0, 2],
        "audio_norm_path": "cached.pt",
    }
    (tmp_path / "dataset.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return entry


@pytest.mark.parametrize("language", ["ja", "en", "zh", "es", "fr", "pt"])
def test_null_single_language_id_becomes_explicit_without_changing_phonemes(
    tmp_path, language
):
    entry = dataset(tmp_path, {"num_speakers": 1}, None)
    normalizer()(tmp_path, language)
    config = json.loads((tmp_path / "config.json").read_text())
    assert config["language_id_map"] == {language: 0}
    result = json.loads((tmp_path / "dataset.jsonl").read_text())
    assert result == {**entry, "language_id": 0}


def test_explicit_multilingual_mapping_is_preserved_byte_for_byte(tmp_path):
    dataset(tmp_path, {"language_id_map": {"en": 0, "ja": 1}}, 1)
    before = [
        (tmp_path / name).read_bytes() for name in ["config.json", "dataset.jsonl"]
    ]
    normalizer()(tmp_path, "ja")
    assert before == [
        (tmp_path / name).read_bytes() for name in ["config.json", "dataset.jsonl"]
    ]


def test_unknown_id_without_mapping_is_rejected_before_writing(tmp_path):
    dataset(tmp_path, {"num_speakers": 1}, 3)
    before = (tmp_path / "dataset.jsonl").read_bytes()
    with pytest.raises(ValueError, match="language"):
        normalizer()(tmp_path, "ja")
    assert (tmp_path / "dataset.jsonl").read_bytes() == before


def test_training_subprocess_does_not_inherit_colab_inline_backend(monkeypatch):
    monkeypatch.setenv("MPLBACKEND", "module://matplotlib_inline.backend_inline")
    source = next(cell for cell in cells() if "MAX_EPOCHS =" in cell)
    exec(
        compile(source, "notebook-training-config", "exec"),
        {"os": os, "SPEAKER_NAME": "test"},
    )
    assert os.environ["MPLBACKEND"].lower() == "agg"


def test_finds_explicit_v2_checkpoint_directory_and_orders_epoch_numerically(tmp_path):
    direct = tmp_path / "checkpoints"
    legacy = tmp_path / "lightning_logs/version_0/checkpoints"
    direct.mkdir()
    legacy.mkdir(parents=True)
    for path in [
        direct / "epoch=9-step=90.ckpt",
        direct / "epoch=10-step=100.ckpt",
        legacy / "epoch=1-step=200.ckpt",
    ]:
        path.touch()
    source = next(
        cell
        for cell in cells()
        if "def extract_epoch(" in cell or "def checkpoint_order(" in cell
    )
    namespace = {"OUTPUT_DIR": str(tmp_path)}
    exec(compile(source, "notebook-checkpoint-discovery", "exec"), namespace)
    assert Path(namespace["FINAL_CHECKPOINT"]) == direct / "epoch=10-step=100.ckpt"


def test_missing_checkpoint_stops_export_instead_of_silently_skipping(tmp_path):
    source = next(
        cell
        for cell in cells()
        if "def extract_epoch(" in cell or "def checkpoint_order(" in cell
    )
    with pytest.raises(FileNotFoundError):
        exec(
            compile(source, "notebook-checkpoint-discovery", "exec"),
            {"OUTPUT_DIR": str(tmp_path)},
        )
