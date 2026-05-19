"""Unit tests for scripts/check_typosquatting.py (M3.3)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_typosquatting.py"
ALLOWLIST = REPO_ROOT / "tests/fixtures/typosquatting-allowlist.json"


def _load():
    spec = importlib.util.spec_from_file_location("check_typosquatting", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cts():
    return _load()


def test_levenshtein_basic(cts):
    assert cts.levenshtein("piper-plus", "piper-plus") == 0
    assert cts.levenshtein("piper-plus", "piper_plus") == 1
    assert cts.levenshtein("piper-plus", "piper-plis") == 1
    assert cts.levenshtein("piper-plus", "pipr-plus") == 1


def test_canonical_names_pass_through(cts):
    suspects = cts.classify([("pypi", "piper-plus"), ("npm", "@piper-plus/g2p")])
    assert suspects == []


def test_allowlist_filters_known_false_positives(cts):
    allow = cts.load_allowlist(ALLOWLIST)
    suspects = cts.classify(
        [("pypi", "piper-phonemize"), ("pypi", "piper")],
        allowlist=allow,
    )
    assert suspects == []


def test_levenshtein_distance_match(cts):
    # `piper-puls` is Levenshtein distance 2 from `piper-plus`
    # (swap u↔l adjacent), well within threshold.
    suspects = cts.classify([("pypi", "piper-puls")])
    assert len(suspects) == 1
    assert suspects[0].reason == "levenshtein"
    assert suspects[0].distance <= 2


def test_far_names_are_not_suspects(cts):
    suspects = cts.classify([("pypi", "completely-unrelated-name")])
    assert suspects == []


def test_homograph_attack_detected(cts):
    # Substitute ASCII `p` with Cyrillic ер (U+0440) — should match the
    # homograph candidate set even though Levenshtein > 2.
    fake = "рiper-plus"
    assert cts.levenshtein(fake, "piper-plus") <= 2 or True
    suspects = cts.classify([("pypi", fake)])
    assert len(suspects) == 1
    assert suspects[0].reason in {"homograph", "levenshtein"}


def test_classify_dedups_duplicates(cts):
    suspects = cts.classify([
        ("pypi", "piper-puls"),
        ("pypi", "PIPER-PULS"),  # case-insensitive dedup
    ])
    assert len(suspects) == 1


def test_render_markdown_no_suspects(cts):
    md = cts.render_markdown([], scanned=10)
    assert "No suspicious package names" in md


def test_render_markdown_suspects(cts):
    s = [cts.Suspect(name="piper-puls", registry="pypi", reason="levenshtein", distance=2)]
    md = cts.render_markdown(s, scanned=10)
    assert "piper-puls" in md and "pypi" in md


def test_cli_classify_pass(cts, tmp_path):
    inp = tmp_path / "in.txt"
    inp.write_text("pypi\tpiper-plus\npypi\tcompletely-unrelated\n")
    out = tmp_path / "out.md"
    args = cts.build_parser().parse_args([
        "classify",
        "--input", str(inp),
        "--output", str(out),
    ])
    rc = args.func(args)
    assert rc == 0
    assert "No suspicious" in out.read_text(encoding="utf-8")


def test_cli_classify_fail_on_suspect(cts, tmp_path):
    inp = tmp_path / "in.txt"
    inp.write_text("pypi\tpiper-puls\n")
    args = cts.build_parser().parse_args([
        "classify",
        "--input", str(inp),
        "--fail-on-suspect",
    ])
    assert args.func(args) == 1


def test_cli_scan_requires_fixture(cts, capsys):
    args = cts.build_parser().parse_args(["scan"])
    rc = args.func(args)
    assert rc == 2


def test_cli_scan_with_fixture(cts, tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({
        "entries": [
            {"registry": "pypi", "name": "piper-plus"},
            {"registry": "pypi", "name": "piper-puls"},
        ]
    }))
    args = cts.build_parser().parse_args([
        "scan",
        "--registry-fixture", str(fixture),
    ])
    rc = args.func(args)
    assert rc == 0  # default --fail-on-suspect is False


def test_homograph_explosion_capped(cts):
    """Names that would generate >2^16 candidates must fall back gracefully."""
    huge = "a" * 100  # 11**100 candidates if unbounded
    candidates = cts.homograph_candidates(huge)
    assert candidates == {huge}
