"""Unit tests for scripts/check_trivy_sarif.py (F2).

回帰対象: 旧 inline gate は severity を ``results[].properties.tags`` から
読んでいたが、 Trivy は severity tag を ``tool.driver.rules[].properties.tags``
に置くため CRITICAL が常に 0 になり gate が no-op だった。
``test_rules_level_tags_*`` がその形を pin する。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_trivy_sarif.py"

if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_module():
    spec = importlib.util.spec_from_file_location("check_trivy_sarif", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def _rule(rule_id: str, severity: str, cvss: str = "7.5") -> dict:
    """実 Trivy SARIF の rule shape (severity tag は rule 側)。"""
    return {
        "id": rule_id,
        "defaultConfiguration": {"level": "error"},
        "properties": {
            "tags": [severity, "security", "vulnerability"],
            "security-severity": cvss,
        },
    }


def _result(rule_id: str, index: int, level: str, severity: str) -> dict:
    """実 Trivy SARIF の result shape (properties に severity tag は無い)。"""
    return {
        "ruleId": rule_id,
        "ruleIndex": index,
        "level": level,
        "message": {
            "text": (
                f"Package: demo\nInstalled Version: 1.0\nVulnerability {rule_id}\n"
                f"Severity: {severity}\nFixed Version: 1.1"
            )
        },
        "properties": {"github/alertNumber": 1, "github/alertUrl": "https://x"},
    }


def _sarif(rules: list[dict], results: list[dict]) -> dict:
    return {
        "version": "2.1.0",
        "runs": [
            {"tool": {"driver": {"name": "Trivy", "rules": rules}}, "results": results}
        ],
    }


def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "trivy.sarif"
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return path


def _run(gate, path: Path, *extra: str) -> int:
    return gate.main([str(path), *extra])


# --- 実 shape: severity tag は rule 側 (旧 gate が読めなかった形) -------------


def test_rules_level_tags_high_only_passes(gate, tmp_path, capsys):
    """HIGH / MEDIUM / LOW は report のみで block しない (既存の保守的方針)。"""
    sarif = _sarif(
        [
            _rule("CVE-1", "HIGH"),
            _rule("CVE-2", "MEDIUM", "5.3"),
            _rule("CVE-3", "LOW", "2"),
        ],
        [
            _result("CVE-1", 0, "error", "HIGH"),
            _result("CVE-2", 1, "warning", "MEDIUM"),
            _result("CVE-3", 2, "note", "LOW"),
        ],
    )
    rc = _run(gate, _write(tmp_path, sarif))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CRITICAL=0" in out
    assert "HIGH=1" in out
    assert "MEDIUM=1" in out
    assert "LOW=1" in out
    assert "UNKNOWN=0" in out


def test_rules_level_tags_critical_blocks(gate, tmp_path, capsys):
    """rule 側 tag の CRITICAL を検出できる (F2 の回帰 guard)。"""
    sarif = _sarif(
        [_rule("CVE-BAD", "CRITICAL", "9.8"), _rule("CVE-OK", "HIGH")],
        [
            _result("CVE-BAD", 0, "error", "CRITICAL"),
            _result("CVE-OK", 1, "error", "HIGH"),
        ],
    )
    rc = _run(gate, _write(tmp_path, sarif))
    captured = capsys.readouterr()
    assert rc == 1
    assert "CRITICAL=1" in captured.out
    assert "[CRITICAL] CVE-BAD" in captured.out
    assert "at or above CRITICAL" in captured.err


def test_error_level_high_is_not_counted_as_critical(gate, tmp_path, capsys):
    """level="error" は CRITICAL/HIGH 双方に付くため CRITICAL 推定に使わない。"""
    sarif = _sarif([_rule("CVE-H", "HIGH")], [_result("CVE-H", 0, "error", "HIGH")])
    rc = _run(gate, _write(tmp_path, sarif))
    assert rc == 0
    assert "CRITICAL=0" in capsys.readouterr().out


def test_github_api_rule_reference_shape(gate, tmp_path, capsys):
    """GitHub code-scanning API 経由の SARIF は rule:{id,index} 形式を使う。"""
    result = _result("CVE-BAD", 0, "error", "CRITICAL")
    del result["ruleId"]
    del result["ruleIndex"]
    result["rule"] = {"id": "CVE-BAD", "index": 0}
    rc = _run(
        gate, _write(tmp_path, _sarif([_rule("CVE-BAD", "CRITICAL", "9.8")], [result]))
    )
    assert rc == 1
    assert "CRITICAL=1" in capsys.readouterr().out


def test_rules_under_tool_extensions(gate, tmp_path, capsys):
    """rule が tool.extensions[].rules 側に置かれた SARIF も解決できる。"""
    sarif = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {"name": "Trivy"},
                    "extensions": [
                        {"name": "trivy", "rules": [_rule("CVE-BAD", "CRITICAL")]}
                    ],
                },
                "results": [_result("CVE-BAD", 0, "error", "CRITICAL")],
            }
        ],
    }
    assert _run(gate, _write(tmp_path, sarif)) == 1
    assert "CRITICAL=1" in capsys.readouterr().out


# --- 旧 buggy shape: severity tag が result 側 -------------------------------


def test_old_shape_result_level_tags_still_detected(gate, tmp_path, capsys):
    """旧 gate が想定していた result 側 tag も superset として受理する。"""
    result = {
        "ruleId": "CVE-BAD",
        "level": "error",
        "properties": {"tags": ["CRITICAL", "security"]},
    }
    assert _run(gate, _write(tmp_path, _sarif([], [result]))) == 1
    assert "CRITICAL=1" in capsys.readouterr().out


def test_message_text_fallback_when_rule_missing(gate, tmp_path, capsys):
    """rule が引けない場合は message.text の "Severity:" 行に fallback する。"""
    rc = _run(
        gate, _write(tmp_path, _sarif([], [_result("CVE-BAD", 0, "error", "CRITICAL")]))
    )
    assert rc == 1
    assert "CRITICAL=1" in capsys.readouterr().out


def test_unresolvable_severity_is_unknown_and_warns(gate, tmp_path, capsys):
    """severity source が 1 つも無い result は UNKNOWN 扱いで block しない。"""
    rc = _run(
        gate, _write(tmp_path, _sarif([], [{"ruleId": "CVE-?", "level": "error"}]))
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "UNKNOWN=1" in out
    assert "::warning::" in out
    assert "no resolvable severity" in out


# --- 空 / 壊れた入力 ---------------------------------------------------------


def test_empty_runs_passes(gate, tmp_path, capsys):
    rc = _run(gate, _write(tmp_path, {"version": "2.1.0", "runs": []}))
    out = capsys.readouterr().out
    assert rc == 0
    assert "total results=0" in out
    assert "No findings at or above CRITICAL" in out


def test_run_without_results_passes(gate, tmp_path, capsys):
    rc = _run(gate, _write(tmp_path, _sarif([], [])))
    assert rc == 0
    assert "total results=0" in capsys.readouterr().out


# --------------------------------------------------------------------------
# ruleIndex / rule.index による join
#
# 生 trivy-action 出力が `ruleId` を落として index 参照だけを載せた場合に
# severity を引けなくなると、 CRITICAL が UNKNOWN に落ちて gate をすり抜ける。
# 手元の SARIF は全て GitHub code-scanning API 経由の composite で、 この
# 経路の実データが無いため合成 fixture で pin する。
# --------------------------------------------------------------------------


def test_index_only_join_detects_critical(gate, tmp_path, capsys):
    """ruleId 無し / ruleIndex のみ (生 trivy-action 側の shape)。"""
    rules = [_rule("CVE-2026-9999", "CRITICAL", "9.8")]
    result = {"ruleIndex": 0, "level": "error", "message": {"text": "no severity here"}}
    assert _run(gate, _write(tmp_path, _sarif(rules, [result]))) == 1
    assert "CRITICAL" in capsys.readouterr().out


def test_rule_index_object_join_detects_critical(gate, tmp_path, capsys):
    """ruleId 無し / `rule: {index: N}` のみ (GitHub API 側の shape)。"""
    rules = [_rule("CVE-2026-9999", "CRITICAL", "9.8")]
    result = {
        "rule": {"index": 0},
        "level": "error",
        "message": {"text": "no severity here"},
    }
    assert _run(gate, _write(tmp_path, _sarif(rules, [result]))) == 1
    assert "CRITICAL" in capsys.readouterr().out


def test_out_of_range_rule_index_is_unknown_not_indexerror(gate, tmp_path, capsys):
    """範囲外 index で IndexError を投げず UNKNOWN に落ちること。"""
    rules = [_rule("CVE-2026-1111", "HIGH")]
    result = {"ruleIndex": 7, "level": "error", "message": {"text": "no severity here"}}
    rc = _run(gate, _write(tmp_path, _sarif(rules, [result])))
    assert rc == 0
    assert "UNKNOWN" in capsys.readouterr().out


def test_unknown_rule_id_falls_through_to_index(gate, tmp_path, capsys):
    """id が rules に無い場合は index fallback が使われること。"""
    rules = [_rule("CVE-2026-9999", "CRITICAL", "9.8")]
    result = {
        "ruleId": "CVE-2026-NOT-IN-RULES",
        "ruleIndex": 0,
        "level": "error",
        "message": {"text": "no severity here"},
    }
    assert _run(gate, _write(tmp_path, _sarif(rules, [result]))) == 1


def test_malformed_json_exits_2(gate, tmp_path, capsys):
    rc = _run(gate, _write(tmp_path, "{not json"))
    assert rc == 2
    assert "::error::SARIF unreadable" in capsys.readouterr().err


def test_missing_file_exits_2(gate, tmp_path, capsys):
    rc = _run(gate, tmp_path / "does-not-exist.sarif")
    err = capsys.readouterr().err
    assert rc == 2
    assert "::error::SARIF unreadable" in err
    assert "the scan broke" in err


def test_missing_file_with_allow_unreadable_exits_0(gate, tmp_path, capsys):
    """旧 inline gate 互換の lenient 経路 (workflow では使わない)。"""
    rc = _run(gate, tmp_path / "does-not-exist.sarif", "--allow-unreadable")
    out = capsys.readouterr().out
    assert rc == 0
    assert "::warning::SARIF unreadable" in out


def test_non_object_root_exits_2(gate, tmp_path, capsys):
    rc = _run(gate, _write(tmp_path, [1, 2, 3]))
    assert rc == 2
    assert "root is not an object" in capsys.readouterr().err


# --- --fail-on ---------------------------------------------------------------


def test_fail_on_high_blocks_high_and_critical(gate, tmp_path, capsys):
    sarif = _sarif(
        [_rule("CVE-H", "HIGH"), _rule("CVE-M", "MEDIUM", "5.3")],
        [
            _result("CVE-H", 0, "error", "HIGH"),
            _result("CVE-M", 1, "warning", "MEDIUM"),
        ],
    )
    rc = _run(gate, _write(tmp_path, sarif), "--fail-on", "HIGH")
    captured = capsys.readouterr()
    assert rc == 1
    assert "[HIGH] CVE-H" in captured.out
    assert "at or above HIGH" in captured.err


def test_fail_on_is_case_insensitive(gate, tmp_path):
    sarif = _sarif([_rule("CVE-H", "HIGH")], [_result("CVE-H", 0, "error", "HIGH")])
    assert _run(gate, _write(tmp_path, sarif), "--fail-on", "high") == 1


def test_cvss_fallback_bands_critical(gate, tmp_path, capsys):
    """tags も message も無いが security-severity >= 9.0 なら CRITICAL 扱い。"""
    rule = {"id": "CVE-X", "properties": {"security-severity": "9.8"}}
    rc = _run(
        gate, _write(tmp_path, _sarif([rule], [{"ruleId": "CVE-X", "level": "error"}]))
    )
    assert rc == 1
    assert "CRITICAL=1" in capsys.readouterr().out
