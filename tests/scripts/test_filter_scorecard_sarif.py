"""Unit tests for scripts/filter_scorecard_sarif.py.

The filter exists because OpenSSF Scorecard scores an action reference 0
unless it is SHA-pinned, while this repository's own gate
(`scripts/check_action_pins.py`) declares full SemVer an allowed pin form.
789 of 937 Scorecard findings restated that settled disagreement and buried
the 148 findings nobody had ruled on.

What these tests actually protect is the *guards*. A SARIF filter that
silently stops matching is the same defect class as the gates repaired in
#628 / #629: it looks green precisely when it has stopped working. So the
bulk of the coverage below is "does it fail loudly when its assumptions
break", not "does it drop the right rows on a happy path".
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "filter_scorecard_sarif.py"


def _result(rule_id: str, text: str, line: int = 1) -> dict:
    return {
        "ruleId": rule_id,
        "level": "error",
        "message": {"text": text},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": ".github/workflows/ci.yml"},
                    "region": {"startLine": line, "endLine": line},
                }
            }
        ],
        "partialFingerprints": {"primaryLocationLineHash": f"deadbeef{line:08x}:1"},
    }


def _pin(kind: str, line: int = 1) -> dict:
    return _result(
        "PinnedDependenciesID",
        f"score is 0: {kind} not pinned by hash\nRemediation tip: ...",
        line,
    )


def _sarif(results: list[dict], rule_ids: list[str] | None = None) -> dict:
    ids = rule_ids if rule_ids is not None else ["PinnedDependenciesID", "TokenPermissionsID"]
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "Scorecard", "rules": [{"id": i} for i in ids]}},
                "results": results,
            }
        ],
    }


BASE_RESULTS = [
    _pin("GitHub-owned GitHubAction", 10),
    _pin("third-party GitHubAction", 20),
    _pin("pipCommand", 30),
    _pin("containerImage", 40),
    _pin("npmCommand", 50),
    _result("TokenPermissionsID", "score is 0: jobLevel 'contents' permission set to 'write'", 60),
]


@pytest.fixture(scope="module")
def mod():
    # Ensure platform_utils is importable from scripts/
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("filter_scorecard_sarif", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_drops_only_github_action_findings(mod):
    filtered, stats = mod.filter_sarif(_sarif(copy.deepcopy(BASE_RESULTS)))
    kept = filtered["runs"][0]["results"]
    assert stats["total_before"] == 6
    assert stats["total_after"] == 4
    assert stats["dropped"] == 2
    texts = [r["message"]["text"] for r in kept]
    assert not any("GitHubAction" in t for t in texts)
    assert sum("pipCommand" in t for t in texts) == 1
    assert sum("containerImage" in t for t in texts) == 1
    assert sum("npmCommand" in t for t in texts) == 1


def test_non_pinned_rules_are_never_touched(mod):
    filtered, _ = mod.filter_sarif(_sarif(copy.deepcopy(BASE_RESULTS)))
    kept = filtered["runs"][0]["results"]
    assert sum(r["ruleId"] == "TokenPermissionsID" for r in kept) == 1


def test_zero_dropped_is_not_an_error(mod):
    """A fully SHA-pinned repo legitimately yields no action-pin findings."""
    results = [r for r in copy.deepcopy(BASE_RESULTS) if "GitHubAction" not in r["message"]["text"]]
    filtered, stats = mod.filter_sarif(_sarif(results))
    assert stats["dropped"] == 0
    assert stats["total_after"] == 4
    assert len(filtered["runs"][0]["results"]) == 4


def test_kind_counts_are_reported(mod):
    _, stats = mod.filter_sarif(_sarif(copy.deepcopy(BASE_RESULTS)))
    assert stats["kind:GitHub-owned GitHubAction"] == 1
    assert stats["kind:third-party GitHubAction"] == 1
    assert stats["kind:pipCommand"] == 1


# --------------------------------------------------------------------------
# Guard 1 — rule renamed upstream
# --------------------------------------------------------------------------


def test_guard_rule_missing_from_driver(mod):
    sarif = _sarif(copy.deepcopy(BASE_RESULTS), rule_ids=["PinnedDepsV2", "TokenPermissionsID"])
    with pytest.raises(mod.FilterError, match="not declared in tool.driver.rules"):
        mod.filter_sarif(sarif)


def test_guard_rule_missing_mentions_remedy(mod):
    sarif = _sarif(copy.deepcopy(BASE_RESULTS), rule_ids=["TokenPermissionsID"])
    with pytest.raises(mod.FilterError, match="TARGET_RULE"):
        mod.filter_sarif(sarif)


# --------------------------------------------------------------------------
# Guard 2 — message reformatted upstream
# --------------------------------------------------------------------------


def test_guard_unparseable_message(mod):
    results = copy.deepcopy(BASE_RESULTS)
    results[0]["message"]["text"] = "Pinned-Dependencies: action uses a mutable tag"
    with pytest.raises(mod.FilterError, match="expected message shape"):
        mod.filter_sarif(_sarif(results))


def test_guard_unparseable_message_is_not_silently_dropped(mod):
    """An unclassifiable finding must never be treated as droppable."""
    results = copy.deepcopy(BASE_RESULTS)
    results[0]["message"]["text"] = "totally new wording about GitHubAction"
    assert mod.should_drop(results[0]) is False


# --------------------------------------------------------------------------
# Guard 4 — refuse to emit an empty SARIF
# --------------------------------------------------------------------------


def test_guard_refuses_to_empty_the_sarif(mod):
    results = [_pin("GitHub-owned GitHubAction", 10), _pin("third-party GitHubAction", 20)]
    with pytest.raises(mod.FilterError, match="removed all"):
        mod.filter_sarif(_sarif(results))


def test_empty_input_is_not_an_error(mod):
    """No results at all is not the same as 'we deleted them'."""
    _, stats = mod.filter_sarif(_sarif([]))
    assert stats["total_before"] == 0
    assert stats["total_after"] == 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_writes_filtered_output(mod, tmp_path):
    src = tmp_path / "results.sarif"
    dst = tmp_path / "filtered.sarif"
    src.write_text(json.dumps(_sarif(copy.deepcopy(BASE_RESULTS))), encoding="utf-8")
    assert mod.run([str(src), "-o", str(dst)]) == 0
    out = json.loads(dst.read_text(encoding="utf-8"))
    assert len(out["runs"][0]["results"]) == 4
    # input untouched when -o is given
    assert len(json.loads(src.read_text(encoding="utf-8"))["runs"][0]["results"]) == 6


def test_cli_overwrites_in_place_by_default(mod, tmp_path):
    src = tmp_path / "results.sarif"
    src.write_text(json.dumps(_sarif(copy.deepcopy(BASE_RESULTS))), encoding="utf-8")
    assert mod.run([str(src)]) == 0
    assert len(json.loads(src.read_text(encoding="utf-8"))["runs"][0]["results"]) == 4


def test_cli_guard_failure_exits_nonzero(mod, tmp_path):
    src = tmp_path / "results.sarif"
    src.write_text(
        json.dumps(_sarif(copy.deepcopy(BASE_RESULTS), rule_ids=["Other"])), encoding="utf-8"
    )
    assert mod.run([str(src)]) == 1
    # the input must survive a guard failure so CI can inspect it
    assert len(json.loads(src.read_text(encoding="utf-8"))["runs"][0]["results"]) == 6


def test_cli_rejects_invalid_json(mod, tmp_path):
    src = tmp_path / "results.sarif"
    src.write_text("{not json", encoding="utf-8")
    assert mod.run([str(src)]) == 1


def test_cli_rejects_missing_file(mod, tmp_path):
    assert mod.run([str(tmp_path / "nope.sarif")]) == 1
