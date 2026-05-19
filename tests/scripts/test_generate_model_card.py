"""Unit tests for scripts/generate_model_card.py (M3.2)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_model_card.py"
DATA_SOURCES = REPO_ROOT / "data-sources.yml"


def _load():
    spec = importlib.util.spec_from_file_location("generate_model_card", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gmc():
    return _load()


def test_canonical_yaml_loads(gmc):
    meta, datasets = gmc.load_yaml(DATA_SOURCES)
    assert meta["schema_version"] == 1
    assert len(datasets) >= 6
    ids = {d.id for d in datasets}
    assert {"libritts-r", "aishell-3", "cml-tts-es", "cml-tts-fr", "cml-tts-pt"} <= ids


def test_validate_passes_on_canonical(gmc, capsys):
    args = gmc.build_parser().parse_args([
        "validate", "--input", str(DATA_SOURCES),
    ])
    rc = args.func(args)
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_validate_catches_missing_attribution(gmc, tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "schema_version: 1\n"
        "datasets:\n"
        "  - id: x\n"
        "    title: X\n"
        "    license: {spdx: MIT, verified: true, url: 'https://x'}\n"
        "    source: {url: 'https://y', commit_or_version: v1}\n"
        "    attribution_required: true\n"
        "    attribution_text: ''\n"
    )
    args = gmc.build_parser().parse_args(["validate", "--input", str(bad)])
    assert args.func(args) == 1


def test_validate_catches_duplicate_id(gmc, tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "schema_version: 1\n"
        "datasets:\n"
        "  - id: x\n"
        "    title: X\n"
        "    license: {spdx: MIT, verified: true, url: 'https://x'}\n"
        "    source: {url: 'https://y', commit_or_version: v1}\n"
        "    attribution_required: false\n"
        "  - id: x\n"
        "    title: X2\n"
        "    license: {spdx: MIT, verified: true, url: 'https://x'}\n"
        "    source: {url: 'https://y', commit_or_version: v1}\n"
        "    attribution_required: false\n"
    )
    args = gmc.build_parser().parse_args(["validate", "--input", str(bad)])
    assert args.func(args) == 1


def test_validate_rejects_unsupported_schema(gmc, tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("schema_version: 99\ndatasets: []\n")
    args = gmc.build_parser().parse_args(["validate", "--input", str(bad)])
    with pytest.raises(SystemExit):
        args.func(args)


def test_generate_writes_both_files(gmc, tmp_path):
    out_card = tmp_path / "MODEL_CARD.md"
    out_attr = tmp_path / "LICENSE_ATTRIBUTIONS.md"
    args = gmc.build_parser().parse_args([
        "generate",
        "--input", str(DATA_SOURCES),
        "--model-card", str(out_card),
        "--attributions", str(out_attr),
    ])
    rc = args.func(args)
    assert rc == 0
    assert "Training data" in out_card.read_text(encoding="utf-8")
    assert "License attributions" in out_attr.read_text(encoding="utf-8")


def test_generate_is_deterministic(gmc, tmp_path):
    """Calling generate twice with the same input must produce byte-identical files."""
    out_a = tmp_path / "a"
    out_a.mkdir()
    out_b = tmp_path / "b"
    out_b.mkdir()
    for d in (out_a, out_b):
        args = gmc.build_parser().parse_args([
            "generate",
            "--input", str(DATA_SOURCES),
            "--model-card", str(d / "MODEL_CARD.md"),
            "--attributions", str(d / "LICENSE_ATTRIBUTIONS.md"),
        ])
        args.func(args)
    assert (out_a / "MODEL_CARD.md").read_bytes() == (out_b / "MODEL_CARD.md").read_bytes()
    assert (out_a / "LICENSE_ATTRIBUTIONS.md").read_bytes() == (
        out_b / "LICENSE_ATTRIBUTIONS.md"
    ).read_bytes()


def test_unverified_license_emits_warning(gmc, tmp_path):
    out_card = tmp_path / "MODEL_CARD.md"
    out_attr = tmp_path / "LICENSE_ATTRIBUTIONS.md"
    args = gmc.build_parser().parse_args([
        "generate",
        "--input", str(DATA_SOURCES),
        "--model-card", str(out_card),
        "--attributions", str(out_attr),
    ])
    args.func(args)
    text = out_card.read_text(encoding="utf-8")
    # moe-speech-20speakers has verified: false in the canonical YAML.
    assert "pending maintainer review" in text
    assert "moe-speech-20speakers" in text


def test_used_only_in_filter(gmc, tmp_path):
    out_card = tmp_path / "MODEL_CARD.md"
    out_attr = tmp_path / "LICENSE_ATTRIBUTIONS.md"
    args = gmc.build_parser().parse_args([
        "generate",
        "--input", str(DATA_SOURCES),
        "--model", "tsukuyomi-6lang-v2",
        "--model-card", str(out_card),
        "--attributions", str(out_attr),
    ])
    args.func(args)
    text = out_card.read_text(encoding="utf-8")
    # Tsukuyomi corpus has `used_only_in: [tsukuyomi-6lang-v2, ...]` so it
    # should appear. Datasets without `used_only_in` are always included.
    assert "tsukuyomi-chan-corpus" in text


def test_used_only_in_excludes_other_model(gmc, tmp_path):
    out_card = tmp_path / "MODEL_CARD.md"
    out_attr = tmp_path / "LICENSE_ATTRIBUTIONS.md"
    args = gmc.build_parser().parse_args([
        "generate",
        "--input", str(DATA_SOURCES),
        "--model", "non-existent-model",
        "--model-card", str(out_card),
        "--attributions", str(out_attr),
    ])
    args.func(args)
    text = out_card.read_text(encoding="utf-8")
    # `tsukuyomi-chan-corpus` is locked to its used_only_in list, so any
    # other model must omit it. Datasets with no `used_only_in` are still
    # included because they are model-agnostic.
    assert "tsukuyomi-chan-corpus" not in text
    assert "libritts-r" in text
