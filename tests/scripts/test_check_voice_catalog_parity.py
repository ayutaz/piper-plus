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


@pytest.mark.parametrize("table", ["MIRRORS", "ALIAS_MIRRORS", "NOTICE_MIRRORS"])
def test_removing_a_notice_line_from_any_mirror_fails(gate, canonical, tmp_path, table):
    copies = _copy_all(gate, tmp_path)
    assert _run(gate, copies) == 0, "copied mirrors must pass before the mutation"

    line = canonical[NOTICE_KEY]["notice"][-1]
    for label, path in copies[table].items():
        text = gate.normalize_mirror_text(path.read_text(encoding="utf-8"))
        assert line in text, label
        path.write_text(text.replace(line, "removed"), encoding="utf-8")
        assert _run(gate, copies) == 1, label
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


def _all_mirrors(gate) -> dict[str, dict[str, Path]]:
    return {
        "MIRRORS": gate.MIRRORS,
        "ALIAS_MIRRORS": gate.ALIAS_MIRRORS,
        "NOTICE_MIRRORS": gate.NOTICE_MIRRORS,
    }


def _copy_all(gate, tmp_path: Path) -> dict[str, dict[str, Path]]:
    copies: dict[str, dict[str, Path]] = {}
    for table, mirrors in _all_mirrors(gate).items():
        target = tmp_path / table
        target.mkdir()
        copies[table] = _copy_mirrors(target, mirrors)
    return copies


def _run(gate, copies: dict[str, dict[str, Path]]) -> int:
    return gate.main(
        mirrors=copies["MIRRORS"],
        alias_mirrors=copies["ALIAS_MIRRORS"],
        notice_mirrors=copies["NOTICE_MIRRORS"],
    )


def _names(entry: dict) -> list[str]:
    return [entry["key"], *entry["aliases"]]


def test_canonical_catalog_models_list_their_repo_id_as_an_alias(canonical):
    for key, entry in canonical.items():
        assert entry["repo_id"] in entry["aliases"], key


@pytest.mark.parametrize("table", ["MIRRORS", "ALIAS_MIRRORS"])
def test_removing_any_name_from_a_mirror_fails(gate, canonical, tmp_path, table):
    """Every key and every alias is required, not just one of them."""
    copies = _copy_all(gate, tmp_path)
    assert _run(gate, copies) == 0, "copied mirrors must pass before the mutation"

    for label, path in copies[table].items():
        original = path.read_text(encoding="utf-8")
        text = gate.normalize_mirror_text(original)
        for key, entry in canonical.items():
            for name in _names(entry):
                quoted = [q for q in (f'"{name}"', f"'{name}'") if q in text]
                assert quoted, f"{label}: {key} name {name!r} must be a string literal"
                mutated = text
                for literal in quoted:
                    mutated = mutated.replace(literal, '"removed-name"')
                path.write_text(mutated, encoding="utf-8")
                assert _run(gate, copies) == 1, f"{label}: removing {name!r} must fail"
        path.write_text(original, encoding="utf-8")


def test_a_name_inside_a_longer_literal_does_not_count(gate, canonical, tmp_path):
    """`"ja-tsukuyomi"` must not satisfy the alias `tsukuyomi`."""
    entry = canonical[NOTICE_KEY]
    mirror = tmp_path / "partial.rs"
    mirror.write_text(
        "\n".join(
            [
                # The repo inside a URL: present, but not as the repo-ID alias.
                f'"https://huggingface.co/{entry["repo_id"]}/resolve/main"',
                f'"{entry["onnx_file"]}"',
                f'"{entry["config_file"]}"',
                *(f'"x-{name}"' for name in _names(entry)),
            ]
        ),
        encoding="utf-8",
    )
    failures = gate.check_alias_entry(NOTICE_KEY, entry, "partial", mirror)
    name_failures = [f for f in failures if "not found as a string literal" in f]
    assert len(name_failures) == len(_names(entry))


def test_canonical_drift_is_reported(gate, tmp_path):
    data = json.loads(gate.CANONICAL.read_text(encoding="utf-8"))
    data["voice_catalog"][NOTICE_KEY]["notice"].append("a line no mirror has")
    canonical_copy = tmp_path / "vectors.json"
    canonical_copy.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert gate.main(canonical_path=canonical_copy) == 1
