"""Unit tests for scripts/check_voice_catalog_parity.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_voice_catalog_parity.py"
NOTICE_KEY = "ja_JP-tsukuyomi-chan-medium"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_voice_catalog_parity", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


@pytest.fixture(scope="module")
def canonical(gate):
    return gate.load_canonical()


def _copy_mirrors(tmp_path: Path, mirrors: dict[str, Path]) -> dict[str, Path]:
    copies: dict[str, Path] = {}
    for index, (label, path) in enumerate(mirrors.items()):
        copy = tmp_path / f"mirror{index}{path.suffix}"
        copy.write_bytes(path.read_bytes())
        copies[label] = copy
    return copies


def test_repository_mirrors_are_in_sync(gate):
    assert gate.main() == 0


def test_canonical_tsukuyomi_entry_has_notice(canonical):
    entry = canonical[NOTICE_KEY]
    assert entry["notice"], "the Tsukuyomi-chan entry must carry the usage notice"
    joined = "\n".join(entry["notice"])
    assert "Piper Plus:つくよみちゃん" in joined
    assert "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan" in joined
    assert entry["onnx_file"] in entry["notice_files"]


@pytest.mark.parametrize("table", ["MIRRORS", "NOTICE_MIRRORS"])
def test_removing_a_notice_line_from_any_mirror_fails(gate, canonical, tmp_path, table):
    full_dir = tmp_path / "full"
    notice_dir = tmp_path / "notice"
    full_dir.mkdir()
    notice_dir.mkdir()
    mirrors = _copy_mirrors(full_dir, gate.MIRRORS)
    notice_mirrors = _copy_mirrors(notice_dir, gate.NOTICE_MIRRORS)
    assert gate.main(mirrors=mirrors, notice_mirrors=notice_mirrors) == 0, (
        "copied mirrors must pass before the mutation"
    )

    line = canonical[NOTICE_KEY]["notice"][-1]
    targets = mirrors if table == "MIRRORS" else notice_mirrors
    for label, path in targets.items():
        text = gate.normalize_mirror_text(path.read_text(encoding="utf-8"))
        assert line in text, label
        path.write_text(text.replace(line, "removed"), encoding="utf-8")
        assert gate.main(mirrors=mirrors, notice_mirrors=notice_mirrors) == 1, label
        path.write_text(text, encoding="utf-8")


def test_unicode_escaped_mirror_matches(gate, canonical, tmp_path):
    entry = canonical[NOTICE_KEY]
    escaped = "\n".join(
        line.encode("ascii", "backslashreplace").decode("ascii")
        for line in [*entry["notice"], *entry["notice_files"], entry["repo_id"]]
    )
    assert "\\u" in escaped
    mirror = tmp_path / "escaped.js"
    mirror.write_text(escaped, encoding="utf-8")
    assert gate.check_notice_entry(NOTICE_KEY, entry, "escaped", mirror) == []


@pytest.mark.parametrize("bad", ['say "hi"', "back\\slash", "   "])
def test_canonical_notice_line_must_be_literal_safe(gate, bad):
    entry = {"notice": [bad], "notice_files": ["x.onnx"]}
    assert gate.validate_canonical_notice("k", entry)


def test_notice_without_notice_files_is_rejected(gate):
    assert gate.validate_canonical_notice("k", {"notice": ["ok"]})


def test_canonical_drift_is_reported(gate, tmp_path):
    data = json.loads(gate.CANONICAL.read_text(encoding="utf-8"))
    data["voice_catalog"][NOTICE_KEY]["notice"].append("a line no mirror has")
    canonical_copy = tmp_path / "vectors.json"
    canonical_copy.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert gate.main(canonical_path=canonical_copy) == 1
