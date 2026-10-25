"""Tests for scripts/check_rulesets.py (no network)."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_rulesets.py"

_spec = importlib.util.spec_from_file_location("check_rulesets", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
sys.modules["check_rulesets"] = gate
_spec.loader.exec_module(gate)

# Every tag in the repository when the tag ruleset was written.
EXISTING_TAGS = """
wasm-g2p-v0.4.2 v2.0.2 v1.13.0 v1.5.5 src/go/v0.2.0 src/go/phonemize/v0.3.0
rust-v0.5.2 rust-g2p-v0.2.0 python-g2p-v0.3.1 openjtalk-binaries-latest
npm-v0.8.2 kotlin-g2p-v1.0.1 go-g2p-v0.3.0 docker-v2.0.2
docker-signatures-v2.0.0 dev-20250610 csharp-v0.5.1
""".split()


@pytest.fixture
def desired() -> dict[str, dict]:
    return gate.load_desired()


def test_repository_files_are_valid(desired: dict[str, dict]) -> None:
    assert gate.validate(desired, EXISTING_TAGS) == []


@pytest.mark.parametrize(
    ("pattern", "ref", "expected"),
    [
        ("refs/tags/v*", "refs/tags/v2.0.2", True),
        ("refs/tags/*-v*", "refs/tags/npm-v0.8.2", True),
        ("refs/tags/*-v*", "refs/tags/src/go/v0.2.0", False),  # `*` stops at `/`
        ("refs/tags/src/go/**", "refs/tags/src/go/phonemize/v0.3.0", True),
        ("refs/tags/*-v*", "refs/tags/openjtalk-binaries-latest", False),
        ("refs/heads/dev*", "refs/heads/dev", True),
        ("refs/heads/dev*", "refs/heads/feature/dev", False),
    ],
)
def test_ref_pattern(pattern: str, ref: str, expected: bool) -> None:
    assert bool(gate.ref_pattern_regex(pattern).match(ref)) is expected


def test_moving_tags_stay_outside(desired: dict[str, dict]) -> None:
    tag = desired[gate.TAG_RULESET]
    for name in gate.MOVING_TAGS:
        assert not gate.ref_covered(tag, f"refs/tags/{name}")


def _errors_after(desired: dict[str, dict], edit) -> list[str]:
    changed = copy.deepcopy(desired)
    edit(changed)
    return gate.validate(changed, EXISTING_TAGS)


def test_missing_required_check_is_reported(desired: dict[str, dict]) -> None:
    def drop(d):
        rule = next(r for r in d["piper-dev"]["rules"] if r["type"] == "required_status_checks")
        rule["parameters"]["required_status_checks"] = [
            c for c in rule["parameters"]["required_status_checks"] if c["context"] == "ci-required"
        ]

    assert any("required-gate/all-workflows" in e for e in _errors_after(desired, drop))


def test_thread_resolution_must_be_required(desired: dict[str, dict]) -> None:
    def off(d):
        rule = next(r for r in d["piper-dev"]["rules"] if r["type"] == "pull_request")
        rule["parameters"]["required_review_thread_resolution"] = False

    assert any("required_review_thread_resolution" in e for e in _errors_after(desired, off))


def test_strict_must_stay_off(desired: dict[str, dict]) -> None:
    def strict(d):
        rule = next(r for r in d["piper-dev"]["rules"] if r["type"] == "required_status_checks")
        rule["parameters"]["strict_required_status_checks_policy"] = True

    assert any("strict" in e for e in _errors_after(desired, strict))


def test_tag_bypass_is_rejected(desired: dict[str, dict]) -> None:
    def bypass(d):
        d["release-tags"]["bypass_actors"] = [
            {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        ]

    assert any("bypass_actors" in e for e in _errors_after(desired, bypass))


def test_uncovered_tag_is_reported(desired: dict[str, dict]) -> None:
    errors = gate.validate(desired, [*EXISTING_TAGS, "release-2027"])
    assert errors == ["release-tags: tag release-2027 is not covered"]


def test_moving_tag_covered_is_reported(desired: dict[str, dict]) -> None:
    def cover(d):
        d["release-tags"]["conditions"]["ref_name"]["include"].append("refs/tags/openjtalk-*")

    assert any("openjtalk-binaries-latest" in e for e in _errors_after(desired, cover))


def _live(want: dict, **extra) -> dict:
    """What the API returns: the payload plus server fields, lists reordered."""
    live = copy.deepcopy(want)
    live.update({"id": 1, "node_id": "x", "source_type": "Repository", "_links": {}}, **extra)
    live["rules"] = list(reversed(live["rules"]))
    return live


def test_live_equal_to_file_has_no_diff(desired: dict[str, dict]) -> None:
    live = {name: _live(want) for name, want in desired.items()}
    diffs, notices = gate.compare(desired, live)
    assert diffs == [] and notices == []


def test_live_difference_is_shown(desired: dict[str, dict]) -> None:
    live = {name: _live(want) for name, want in desired.items()}
    rule = next(r for r in live["piper-dev"]["rules"] if r["type"] == "pull_request")
    rule["parameters"]["required_review_thread_resolution"] = False
    diffs, _ = gate.compare(desired, live)
    assert len(diffs) == 1
    assert '-        "required_review_thread_resolution": false,' in diffs[0]
    assert '+        "required_review_thread_resolution": true,' in diffs[0]


def test_missing_live_ruleset_is_a_diff(desired: dict[str, dict]) -> None:
    live = {"piper-dev": _live(desired["piper-dev"])}
    diffs, _ = gate.compare(desired, live)
    assert len(diffs) == 1 and "live/(none)" in diffs[0]


def test_hidden_bypass_actors_is_skipped_with_notice(desired: dict[str, dict]) -> None:
    live = {name: _live(want) for name, want in desired.items()}
    del live["release-tags"]["bypass_actors"]
    diffs, notices = gate.compare(desired, live)
    assert diffs == []
    assert notices == ["release-tags: bypass_actors is not visible to this token; not compared"]


def test_file_name_must_match_ruleset_name(tmp_path: Path, desired: dict[str, dict]) -> None:
    (tmp_path / "other.json").write_text(json.dumps(desired["piper-dev"]), encoding="utf-8")
    with pytest.raises(ValueError, match="file name"):
        gate.load_desired(tmp_path)


def test_unknown_field_is_rejected(tmp_path: Path, desired: dict[str, dict]) -> None:
    data = {**desired["piper-dev"], "id": 6120897}
    (tmp_path / "piper-dev.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected"):
        gate.load_desired(tmp_path)
