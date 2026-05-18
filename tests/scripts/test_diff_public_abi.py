"""Unit tests for scripts/diff_public_abi.py (M3.1)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "diff_public_abi.py"


def _load():
    spec = importlib.util.spec_from_file_location("diff_public_abi", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dpa():
    return _load()


def test_added_only_is_compatible(dpa):
    baseline = {"symbols": [{"name": "a", "signature": "void a()"}]}
    current = {
        "symbols": [
            {"name": "a", "signature": "void a()"},
            {"name": "b", "signature": "int b()"},
        ]
    }
    sections = dpa.diff_c(baseline, current)
    report = dpa.DiffReport(sections=sections)
    assert not report.has_breaking
    section = sections[0]
    assert section.added == ["b"]
    assert not section.removed
    assert not section.changed


def test_removal_is_breaking(dpa):
    baseline = {"symbols": [{"name": "a", "signature": "void a()"}]}
    current = {"symbols": []}
    sections = dpa.diff_c(baseline, current)
    report = dpa.DiffReport(sections=sections)
    assert report.has_breaking
    assert sections[0].removed == ["a"]


def test_signature_change_is_breaking(dpa):
    baseline = {"symbols": [{"name": "a", "signature": "void a()"}]}
    current = {"symbols": [{"name": "a", "signature": "int a()"}]}
    sections = dpa.diff_c(baseline, current)
    report = dpa.DiffReport(sections=sections)
    assert report.has_breaking
    assert sections[0].changed[0][0] == "a"


def test_struct_field_change_is_breaking(dpa):
    baseline = {
        "structs": [
            {"name": "S", "fields": [{"name": "x", "type": "int"}]}
        ]
    }
    current = {
        "structs": [
            {"name": "S", "fields": [{"name": "x", "type": "long"}]}
        ]
    }
    sections = dpa.diff_c(baseline, current)
    # Sections come back in (symbols, structs, enums, constants) order.
    structs = [s for s in sections if s.surface == "c-structs"][0]
    assert structs.changed


def test_enum_value_change_is_breaking(dpa):
    baseline = {
        "enums": [
            {"name": "E", "values": [{"name": "A", "value": 0}]}
        ]
    }
    current = {
        "enums": [
            {"name": "E", "values": [{"name": "A", "value": 1}]}
        ]
    }
    sections = dpa.diff_c(baseline, current)
    enums = [s for s in sections if s.surface == "c-enums"][0]
    assert enums.changed


def test_swift_declaration_diff(dpa):
    baseline = {
        "declarations": [
            {"usr": "s:5PiperPlus6speakFC", "signature": "func speak()"}
        ]
    }
    current = {
        "declarations": [
            {"usr": "s:5PiperPlus6speakFC", "signature": "func speak() throws"}
        ]
    }
    sections = dpa.diff_swift(baseline, current)
    assert sections[0].changed


def test_kotlin_declaration_diff(dpa):
    baseline = {
        "declarations": [
            {"declaration": "fun phonemize(text: String): PhonemeResult"}
        ]
    }
    current = {
        "declarations": [
            {"declaration": "fun phonemize(text: String, lang: String): PhonemeResult"}
        ]
    }
    sections = dpa.diff_kotlin(baseline, current)
    # Treated as a new declaration since the canonical key changed entirely.
    assert sections[0].added or sections[0].removed


def test_bootstrap_baseline_never_breaks(dpa, tmp_path):
    baseline_file = tmp_path / "base.json"
    current_file = tmp_path / "cur.json"
    baseline_file.write_text(json.dumps({"symbols": [], "structs": []}))
    current_file.write_text(
        json.dumps({"symbols": [{"name": "x", "signature": "void x()"}]})
    )
    args = dpa.build_parser().parse_args([
        "diff",
        "--surface", "c",
        "--baseline", str(baseline_file),
        "--current", str(current_file),
    ])
    rc = args.func(args)
    assert rc == 0  # bootstrap mode + only additions


def test_breaking_fails_unless_allow_flag(dpa, tmp_path):
    baseline_file = tmp_path / "base.json"
    current_file = tmp_path / "cur.json"
    baseline_file.write_text(
        json.dumps({"symbols": [{"name": "a", "signature": "void a()"}]})
    )
    current_file.write_text(json.dumps({"symbols": []}))
    args = dpa.build_parser().parse_args([
        "diff",
        "--surface", "c",
        "--baseline", str(baseline_file),
        "--current", str(current_file),
    ])
    assert args.func(args) == 1
    args = dpa.build_parser().parse_args([
        "diff",
        "--surface", "c",
        "--baseline", str(baseline_file),
        "--current", str(current_file),
        "--allow-breaking",
    ])
    assert args.func(args) == 0


def test_render_markdown_reports_bootstrap(dpa):
    sections = dpa.diff_c(
        {"symbols": []},
        {"symbols": [{"name": "a", "signature": "void a()"}]},
    )
    report = dpa.DiffReport(sections=sections, bootstrap=True)
    md = dpa.render_markdown(report)
    assert "Bootstrap mode" in md


def test_render_markdown_no_changes_message(dpa):
    sections = dpa.diff_c(
        {"symbols": [{"name": "a", "signature": "void a()"}]},
        {"symbols": [{"name": "a", "signature": "void a()"}]},
    )
    report = dpa.DiffReport(sections=sections)
    md = dpa.render_markdown(report)
    assert "No ABI changes detected" in md


def test_fixtures_load(dpa):
    for surface in ("c", "swift", "kotlin"):
        fx = REPO_ROOT / "tests" / "fixtures" / "public-abi" / f"{surface}.json"
        data = json.loads(fx.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
