#!/usr/bin/env python3
"""Trivy SARIF severity gate (F2).

`trivy-container-scan.yml` は Trivy が出力した SARIF を parse して
CRITICAL があれば PR を block する。 従来はこの logic が 2 つの workflow step
に inline python heredoc として重複しており、 かつ severity を
``runs[].results[].properties.tags`` から読んでいた。 Trivy SARIF は severity
tag を **rule 側** (``runs[].tool.driver.rules[].properties.tags``) に置き、
result 側の ``properties`` には ``github/alertNumber`` / ``github/alertUrl``
しか載らないため、 この gate は構造的に常に CRITICAL=0 を返す no-op だった。
本 script はその severity 解決を一箇所に集約し、 unit test で pin する。

Severity 解決順 (最初に決定した source を採用):
  1. result → rule 解決後の ``rule.properties.tags`` の severity 名
     (実測: 3 SARIF / 全 46 rule が この形式で severity を持つ)
  2. ``result.properties.tags`` の severity 名
     (旧 gate が読もうとしていた場所。 Trivy は出力しないが、 他 tool /
      将来の Trivy が置いた場合に取りこぼさないよう superset として受理)
  3. ``result.message.text`` の ``Severity: X`` 行
     (実測: 188 result 全件で 1. と完全一致。 rule が引けない場合の保険)
  4. ``security-severity`` (CVSS 数値文字列) の band 変換
     — rule 側 → result 側 の順。 実測で MEDIUM rule に 8.0 が付く例が
     あり band は HIGH/MEDIUM 間で信頼できないため最終手段としてのみ使う
  5. いずれも解決できなければ UNKNOWN (**block しない**)

``result.level`` は severity source として使わない。 Trivy は
CRITICAL / HIGH の双方を ``level="error"`` に潰すため、 level から
CRITICAL を推定すると HIGH が全部 block される (実測 webui heavy scan で
HIGH 42 件)。 level は breakdown の補助表示にのみ使う。

result → rule の join key は SARIF producer によって形が違う:
  * 生の Trivy 出力          … ``ruleId`` + ``ruleIndex``
  * GitHub code-scanning API … ``ruleId`` + ``rule: {id, index}``
両方 (と ``tool.extensions[].rules`` 配置) を受理する。

Exit codes:
  0 -- --fail-on 以上の severity なし (HIGH / MEDIUM / LOW は report のみ)
  1 -- --fail-on 以上の severity を検出 (gate blocked)
  2 -- SARIF が存在しない / parse できない (gate broken)

SARIF は直前の Trivy step が生成するため、 「無い」 = scan が壊れている。
旧 inline gate はこれを 「findings 無し」 として exit 0 にしており、 output
path の typo 一つで gate が恒久的に無効化されうる (F2 と同じ失敗クラス)
ため、 default では hard failure にした。 旧 lenient 挙動が必要な場合のみ
``--allow-unreadable`` で exit 0 に戻せる (その場合も ::warning:: を出す)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from platform_utils import force_utf8_output


force_utf8_output()

# 深刻度の高い順。 --fail-on は 「その severity 以上」 を block する
# (default CRITICAL は最上位なので 「CRITICAL のみ block」 と等価)。
SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
SEVERITY_NAMES = frozenset(SEVERITY_ORDER)
BLOCKABLE = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# Trivy の message.text は "Severity: HIGH" 行を含む (fallback 3)。
MESSAGE_SEVERITY_RE = re.compile(r"^Severity:\s*([A-Za-z]+)\s*$", re.MULTILINE)

# CVSS v3 base score → severity band (fallback 4)。
CVSS_BANDS = ((9.0, "CRITICAL"), (7.0, "HIGH"), (4.0, "MEDIUM"), (0.1, "LOW"))

# CRITICAL の内訳をログに出す上限 (SARIF が数百件でもログを潰さない)。
MAX_LISTED = 20


def _severity_from_tags(container: Any) -> str | None:
    """``properties.tags`` から severity 名を 1 つ拾う。"""
    if not isinstance(container, dict):
        return None
    props = container.get("properties", {})
    if not isinstance(props, dict):
        return None
    for tag in props.get("tags", []) or []:
        if isinstance(tag, str) and tag.upper() in SEVERITY_NAMES:
            return tag.upper()
    return None


def _severity_from_cvss(container: Any) -> str | None:
    """``properties["security-severity"]`` (CVSS 文字列) を band 変換。"""
    if not isinstance(container, dict):
        return None
    props = container.get("properties", {})
    if not isinstance(props, dict):
        return None
    raw = props.get("security-severity")
    if raw is None:
        return None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    for threshold, name in CVSS_BANDS:
        if score >= threshold:
            return name
    return None


def _severity_from_message(result: dict[str, Any]) -> str | None:
    """``message.text`` の ``Severity:`` 行から severity 名を拾う。"""
    message = result.get("message", {})
    text = message.get("text") if isinstance(message, dict) else None
    if not isinstance(text, str):
        return None
    match = MESSAGE_SEVERITY_RE.search(text)
    if match and match.group(1).upper() in SEVERITY_NAMES:
        return match.group(1).upper()
    return None


def build_rule_index(run: dict[str, Any]) -> tuple[dict[str, dict], list[dict]]:
    """1 つの run から (id → rule, 位置引き用 driver rules) を作る。

    ``tool.driver.rules`` に加えて ``tool.extensions[].rules`` も id 表に
    取り込む (SARIF は extension 側に rule を置くことを許容する)。
    位置 index は SARIF 仕様上 toolComponent 依存だが Trivy は driver
    のみを使うため driver の配列だけを対象にする。
    """
    tool = run.get("tool", {})
    tool = tool if isinstance(tool, dict) else {}
    driver = tool.get("driver", {})
    driver_rules = driver.get("rules", []) if isinstance(driver, dict) else []
    driver_rules = [r for r in driver_rules if isinstance(r, dict)]

    by_id: dict[str, dict] = {}
    containers = [driver_rules]
    for ext in tool.get("extensions", []) or []:
        if isinstance(ext, dict):
            containers.append(
                [r for r in ext.get("rules", []) or [] if isinstance(r, dict)]
            )
    for rules in containers:
        for rule in rules:
            rule_id = rule.get("id")
            if isinstance(rule_id, str) and rule_id not in by_id:
                by_id[rule_id] = rule
    return by_id, driver_rules


def resolve_rule(
    result: dict[str, Any],
    by_id: dict[str, dict],
    driver_rules: list[dict],
) -> dict[str, Any] | None:
    """result から対応する rule を引く (id 優先 → index fallback)。

    id は CVE-ID そのもので曖昧さが無いため優先する。 index は
    toolComponent 相対の位置参照で、 producer 差 (生 Trivy の
    ``ruleIndex`` / GitHub API の ``rule.index``) を吸収する。
    """
    rule_ref = result.get("rule")
    rule_ref = rule_ref if isinstance(rule_ref, dict) else {}

    for candidate in (result.get("ruleId"), rule_ref.get("id")):
        if isinstance(candidate, str) and candidate in by_id:
            return by_id[candidate]

    for candidate in (result.get("ruleIndex"), rule_ref.get("index")):
        if isinstance(candidate, bool) or not isinstance(candidate, int):
            continue
        if 0 <= candidate < len(driver_rules):
            return driver_rules[candidate]
    return None


def classify(
    result: dict[str, Any], by_id: dict[str, dict], driver_rules: list[dict]
) -> str:
    """1 result の severity を module docstring の順序で解決する。"""
    rule = resolve_rule(result, by_id, driver_rules)
    for severity in (
        _severity_from_tags(rule),
        _severity_from_tags(result),
        _severity_from_message(result),
        _severity_from_cvss(rule),
        _severity_from_cvss(result),
    ):
        if severity:
            return severity
    return "UNKNOWN"


def tally(data: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    """SARIF 全体を走査して severity 別件数と、 blocking 候補の説明行を返す。"""
    counts = dict.fromkeys(SEVERITY_ORDER, 0)
    details: dict[str, list[str]] = {name: [] for name in SEVERITY_ORDER}

    runs = data.get("runs", []) if isinstance(data, dict) else []
    for run in runs:
        if not isinstance(run, dict):
            continue
        by_id, driver_rules = build_rule_index(run)
        for result in run.get("results", []) or []:
            if not isinstance(result, dict):
                continue
            severity = classify(result, by_id, driver_rules)
            counts[severity] += 1
            rule_id = (
                result.get("ruleId") or (result.get("rule") or {}).get("id") or "?"
            )
            level = result.get("level", "?")
            details[severity].append(f"{rule_id} (level={level})")
    return counts, details


def report(counts: dict[str, int], details: dict[str, list[str]], fail_on: str) -> None:
    """severity breakdown を stdout に出す (監査可能なログを常に残す)。"""
    total = sum(counts.values())
    breakdown = "  ".join(f"{name}={counts[name]}" for name in SEVERITY_ORDER)
    print(f"Trivy SARIF severity breakdown: {breakdown}  (total results={total})")

    if counts["UNKNOWN"]:
        # severity を 1 つも解決できなかった result。 block はしないが
        # 「gate が読めていない」 兆候なので必ず可視化する。
        print(
            f"::warning::{counts['UNKNOWN']} result(s) had no resolvable severity "
            "(counted as UNKNOWN, never blocking)"
        )

    threshold = SEVERITY_ORDER.index(fail_on)
    for name in BLOCKABLE[: threshold + 1]:
        for line in details[name][:MAX_LISTED]:
            print(f"  [{name}] {line}")
        extra = len(details[name]) - MAX_LISTED
        if extra > 0:
            print(f"  [{name}] ... and {extra} more")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sarif", type=Path, help="Trivy が出力した SARIF ファイル")
    parser.add_argument(
        "--fail-on",
        default="CRITICAL",
        choices=BLOCKABLE,
        type=str.upper,
        help="この severity 以上を検出したら exit 1 (default: CRITICAL)",
    )
    parser.add_argument(
        "--allow-unreadable",
        action="store_true",
        help="SARIF が無い / 壊れている場合に exit 0 で通す (旧 inline gate 互換)",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    try:
        data = json.loads(args.sarif.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        note = f"SARIF unreadable ({args.sarif}): {exc}"
        if args.allow_unreadable:
            print(f"::warning::{note}; treating as no findings (--allow-unreadable)")
            return 0
        print(
            f"::error::{note}. The SARIF is produced by the immediately preceding "
            "Trivy step, so its absence means the scan broke — failing loudly "
            "instead of silently passing the gate.",
            file=sys.stderr,
        )
        return 2

    if not isinstance(data, dict):
        print(f"::error::SARIF root is not an object ({args.sarif})", file=sys.stderr)
        return 2 if not args.allow_unreadable else 0

    counts, details = tally(data)
    report(counts, details, args.fail_on)

    threshold = SEVERITY_ORDER.index(args.fail_on)
    blocking = sum(counts[name] for name in BLOCKABLE[: threshold + 1])
    if blocking:
        print(
            f"::error::{blocking} finding(s) at or above {args.fail_on} — failing.",
            file=sys.stderr,
        )
        return 1
    print(f"No findings at or above {args.fail_on} — pass.")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
