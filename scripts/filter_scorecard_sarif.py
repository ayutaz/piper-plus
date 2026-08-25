#!/usr/bin/env python3
"""Drop GitHub-Action pin findings from the Scorecard SARIF before upload.

Why
---
OpenSSF Scorecard's ``Pinned-Dependencies`` check scores an action reference
0 unless it is pinned to a 40-hex commit SHA. This repository deliberately
pins by full SemVer instead: ``scripts/check_action_pins.py`` declares
``@v1.2.3`` an *allowed* pin form and hard-fails CI only on sliding major
tags (``@v1``). Both standards are internally coherent -- they are simply
different standards, and the repository has already chosen one.

Uploading both to code scanning means 789 of Scorecard's 937 findings (84%)
restate a policy decision that was already made, and they bury the findings
that do matter: the 41 CodeQL alerts, and the 148 Scorecard findings about
pip / container / npm pinning for which this repository has *no* policy and
*no* other tracker.

Dismissing them does not hold. Scorecard emits
``partialFingerprints.primaryLocationLineHash`` -- a hash of the source line
-- so a Dependabot bump from ``actions/checkout@v6.1.0`` to ``@v6.2.0``
changes the fingerprint and GitHub files a brand-new alert. 679 of these
were dismissed as "won't fix" in 2026-05; by 2026-08, 321 of those exact
``(path, line)`` pairs were open again. Filtering at the source is the only
remedy that survives a Dependabot bump.

Scope
-----
Dropped
    ``PinnedDependenciesID`` results whose message reads
    ``score is 0: <kind> GitHubAction not pinned by hash``. Action pinning is
    governed by ``scripts/check_action_pins.py`` + the ``action-pin-gate``
    workflow, which is *stricter* than Scorecard on the axis this repository
    cares about (it hard-fails sliding majors, which Scorecard cannot
    distinguish) and which reports every baselined exception on each run.
    That gate -- not Scorecard -- is the tracker for action pinning.

Kept
    Everything else, including ``PinnedDependenciesID`` findings about
    ``pipCommand`` / ``containerImage`` / ``npmCommand`` / ``nugetCommand`` /
    ``goCommand`` / ``downloadThenRun``. This repository has no policy on
    those, so Scorecard is their only tracker; dropping them would be
    deciding by omission rather than on purpose.

Note that dropping a result also *closes* the corresponding alert: when an
analysis for the same ``(tool, category, ref)`` no longer reports a finding,
GitHub marks the alert fixed. That is the intended effect here.

Guards
------
A filter that silently matches nothing is the same defect class as the four
CI gates repaired in #629 and the pip-audit gate in #628: it would go green
precisely when it stopped doing its job. So this script fails loudly when its
assumptions stop holding, rather than passing an unfiltered (or empty) SARIF
through:

1. ``PinnedDependenciesID`` must be declared in ``tool.driver.rules``. If
   upstream renames the rule, fail instead of silently dropping nothing.
2. Every ``PinnedDependenciesID`` result must match the expected message
   shape. If upstream reformats the message, fail instead of silently
   letting findings through (or dropping the wrong ones).
3. Only ``PinnedDependenciesID`` results may be dropped; any other rule
   losing results is a bug in this script.
4. The filtered SARIF must retain at least one result. Emitting an empty
   SARIF would close every Scorecard alert at once and look like success.

Zero *dropped* results is NOT an error: it is what a fully SHA-pinned
repository looks like, and guards 1-2 already distinguish that from drift.

Usage
-----
    python scripts/filter_scorecard_sarif.py results.sarif
    python scripts/filter_scorecard_sarif.py results.sarif -o filtered.sarif
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

TARGET_RULE = "PinnedDependenciesID"

# Matches every Pinned-Dependencies message Scorecard emits, capturing the
# dependency kind: "GitHub-owned GitHubAction", "third-party GitHubAction",
# "pipCommand", "containerImage", "npmCommand", "nugetCommand", "goCommand",
# "downloadThenRun". Guard 2 asserts this stays exhaustive.
MESSAGE_RE = re.compile(r"score is 0: (?P<kind>.+?) not pinned by hash")

# Only the GitHub Actions kinds are governed by scripts/check_action_pins.py.
DROP_KIND_RE = re.compile(r"\bGitHubAction\b")


class FilterError(RuntimeError):
    """Raised when a guard fails; the caller turns this into exit 1."""


def _iter_results(sarif: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in sarif.get("runs", []):
        out.extend(run.get("results", []) or [])
    return out


def _declared_rule_ids(sarif: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for run in sarif.get("runs", []):
        driver = run.get("tool", {}).get("driver", {})
        for rule in driver.get("rules", []) or []:
            rid = rule.get("id")
            if rid:
                ids.add(rid)
    return ids


def _message_text(result: dict[str, Any]) -> str:
    return (result.get("message") or {}).get("text", "") or ""


def should_drop(result: dict[str, Any]) -> bool:
    """True when the result is an action-pin finding governed by our own gate."""
    if result.get("ruleId") != TARGET_RULE:
        return False
    match = MESSAGE_RE.search(_message_text(result))
    if match is None:
        # Guard 2 reports this separately; never drop what we cannot classify.
        return False
    return bool(DROP_KIND_RE.search(match.group("kind")))


def filter_sarif(sarif: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Return ``(filtered_sarif, stats)``. Raises FilterError when a guard trips."""
    # --- Guard 1: the rule must still exist upstream -------------------
    declared = _declared_rule_ids(sarif)
    if TARGET_RULE not in declared:
        raise FilterError(
            f"{TARGET_RULE} is not declared in tool.driver.rules "
            f"(saw: {', '.join(sorted(declared)) or '<none>'}).\n"
            "Scorecard likely renamed the rule. Update TARGET_RULE in "
            "scripts/filter_scorecard_sarif.py rather than letting the filter "
            "silently stop matching."
        )

    before = _iter_results(sarif)
    pinned = [r for r in before if r.get("ruleId") == TARGET_RULE]

    # --- Guard 2: the message shape must still parse --------------------
    unparsed = [r for r in pinned if MESSAGE_RE.search(_message_text(r)) is None]
    if unparsed:
        sample = _message_text(unparsed[0]).splitlines()[0][:120]
        raise FilterError(
            f"{len(unparsed)} of {len(pinned)} {TARGET_RULE} result(s) do not match "
            f"the expected message shape {MESSAGE_RE.pattern!r}.\n"
            f"First unmatched message: {sample!r}\n"
            "Scorecard likely reformatted the finding. Update MESSAGE_RE rather "
            "than shipping a filter that no longer classifies what it drops."
        )

    kinds: dict[str, int] = {}
    for r in pinned:
        kind = MESSAGE_RE.search(_message_text(r)).group("kind")  # type: ignore[union-attr]
        kinds[kind] = kinds.get(kind, 0) + 1

    for run in sarif.get("runs", []):
        run["results"] = [r for r in (run.get("results") or []) if not should_drop(r)]

    after = _iter_results(sarif)

    # --- Guard 3: nothing but the target rule may have been dropped -----
    def by_rule(results: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.get("ruleId", "<none>")] = (
                counts.get(r.get("ruleId", "<none>"), 0) + 1
            )
        return counts

    b, a = by_rule(before), by_rule(after)
    collateral = {
        rid: (b[rid], a.get(rid, 0))
        for rid in b
        if rid != TARGET_RULE and a.get(rid, 0) != b[rid]
    }
    if collateral:
        detail = ", ".join(
            f"{rid}: {x} -> {y}" for rid, (x, y) in sorted(collateral.items())
        )
        raise FilterError(
            f"filter dropped results outside {TARGET_RULE} ({detail}). "
            "This is a bug in should_drop()."
        )

    # --- Guard 4: never emit an empty SARIF -----------------------------
    if before and not after:
        raise FilterError(
            f"filtering removed all {len(before)} result(s). An empty SARIF would "
            "close every Scorecard alert at once, which is indistinguishable from "
            "a clean scan. Refusing to write it."
        )

    stats = {
        "total_before": len(before),
        "total_after": len(after),
        "dropped": len(before) - len(after),
        "pinned_deps_total": len(pinned),
    }
    return sarif, {**stats, **{f"kind:{k}": v for k, v in sorted(kinds.items())}}


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sarif", type=Path, help="Scorecard SARIF to filter")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="write here instead of overwriting the input",
    )
    args = parser.parse_args(argv)

    try:
        raw = args.sarif.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR cannot read {args.sarif}: {exc}", file=sys.stderr)
        return 1
    try:
        sarif = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR {args.sarif} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        filtered, stats = filter_sarif(sarif)
    except FilterError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    dest = args.output or args.sarif
    dest.write_text(json.dumps(filtered), encoding="utf-8")

    print(
        f"Scorecard SARIF: {stats['total_before']} result(s) in, "
        f"{stats['total_after']} out ({stats['dropped']} action-pin finding(s) dropped)."
    )
    print(f"  {TARGET_RULE} results seen: {stats['pinned_deps_total']}")
    for key, value in stats.items():
        if key.startswith("kind:"):
            kind = key[len("kind:") :]
            verb = "dropped" if DROP_KIND_RE.search(kind) else "kept"
            print(f"    {value:5d}  {kind}  ({verb})")
    print(f"  wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
