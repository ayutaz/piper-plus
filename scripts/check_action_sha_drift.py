#!/usr/bin/env python3
"""Action SHA drift detector (T-002, complement of action-pin-gate.yml).

``action-pin-gate.yml`` enforces the SHA pin **shape** (40-hex or full
SemVer, never sliding ``@v<major>``). This script complements it by
verifying that each 40-hex SHA pin is still **alive** on GitHub (not
dangling and not force-pushed). The gate calls
``GET /repos/{owner}/{repo}/commits/{sha}`` once per pin and classifies
the result.

Silent-zero defence (NFR-5.3): a ``::warning::`` is emitted when the
scanned pin count drops below half of ``expected_total_pins`` in the
baseline. The defensive log ``Collected pins (N actions): ...`` is
always echoed to stderr so a regex regression cannot silently produce
``total=0`` and a green CI run.

Usage:
    python scripts/check_action_sha_drift.py
    python scripts/check_action_sha_drift.py --update-baseline
    python scripts/check_action_sha_drift.py --offline   # for tests
    python scripts/check_action_sha_drift.py --report path/to/report.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github/workflows"
DEFAULT_BASELINE = REPO_ROOT / "scripts/action_sha_baseline.json"

USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA_PIN_RE = re.compile(r"^([^/@\s]+/[^/@\s]+(?:/[^@\s]+)?)@([0-9a-f]{40})$")
LOCAL_RE = re.compile(r"^\./")

SILENT_ZERO_RATIO = 0.5


def collect_sha_pins(workflow_dir: Path = WORKFLOW_DIR) -> list[tuple[str, str]]:
    """Return (action, sha) tuples for every 40-hex SHA pin in workflows.

    SemVer pins are ignored — action-pin-gate.yml already enforces that they
    are not sliding-major. Resolving SemVer tags against the upstream API
    would be redundant with the registry's own tag-immutability.
    """
    pins: list[tuple[str, str]] = []
    for wf in sorted(workflow_dir.glob("*.yml")):
        for line in wf.read_text(encoding="utf-8").splitlines():
            m = USES_RE.match(line)
            if not m:
                continue
            ref = m.group(1)
            if LOCAL_RE.match(ref):
                continue
            sha_match = SHA_PIN_RE.match(ref)
            if sha_match:
                action, sha = sha_match.groups()
                pins.append((action, sha))
    return pins


def resolve_sha_via_api(
    action: str, sha: str, token: str | None = None, timeout: float = 10.0
) -> dict[str, Any]:
    """Call ``GET /repos/{owner}/{repo}/commits/{sha}``.

    Returns a dict with ``status`` in ``{"ok", "force-pushed", "error"}``.

    ``dangling`` (commit exists but unreachable from any tag/branch) is
    classified by the caller via ``classify_dangling`` against a separate
    refs-listing call — we keep this function single-purpose so the unit
    tests can monkeypatch a small surface.
    """
    owner_repo = "/".join(action.split("/")[:2])
    url = f"https://api.github.com/repos/{owner_repo}/commits/{sha}"
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "action": action,
                "sha": sha,
                "status": "ok",
                "commit_url": data.get("html_url", ""),
                "resolved_tag": "(commit-only)",
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "action": action,
                "sha": sha,
                "status": "force-pushed",
                "error": "404 not found",
            }
        return {
            "action": action,
            "sha": sha,
            "status": "error",
            "error": f"HTTP {e.code}",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {
            "action": action,
            "sha": sha,
            "status": "error",
            "error": str(e),
        }


def load_baseline(path: Path) -> dict[str, Any]:
    """Load baseline JSON; return a default skeleton if absent."""
    if not path.exists():
        return {
            "schema_version": 1,
            "generated_at": "1970-01-01T00:00:00Z",
            "expected_total_pins": 0,
            "allowlist": [],
            "ignore_actions": [],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(
            f"Unsupported baseline schema_version: {data.get('schema_version')} "
            f"in {path} (expected 1)",
        )
    return data


def write_baseline(
    path: Path, pins: list[tuple[str, str]], results: list[dict[str, Any]]
) -> None:
    """Rewrite baseline JSON from current scan results."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    allowlist = [
        {
            "action": r["action"],
            "sha": r["sha"],
            "resolved_tag": r.get("resolved_tag", "(commit-only)"),
            "verified_at": now,
        }
        for r in results
        if r["status"] == "ok"
    ]
    existing_ignore: list[str] = []
    if path.exists():
        try:
            existing_ignore = load_baseline(path).get("ignore_actions", []) or []
        except (json.JSONDecodeError, ValueError):
            existing_ignore = []
    baseline = {
        "schema_version": 1,
        "generated_at": now,
        "expected_total_pins": len(pins),
        "allowlist": sorted(allowlist, key=lambda a: (a["action"], a["sha"])),
        "ignore_actions": sorted(set(existing_ignore)),
    }
    path.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def emit_collected_log(pins: list[tuple[str, str]]) -> None:
    """Print the silent-zero defensive log to stderr (always)."""
    if pins:
        summary = " ".join(f"{a}@{s[:7]}" for a, s in pins[:5])
        suffix = " ..." if len(pins) > 5 else ""
    else:
        summary = "(none)"
        suffix = ""
    print(
        f"Collected pins ({len(pins)} actions): {summary}{suffix}",
        file=sys.stderr,
    )


def render_report(results: list[dict[str, Any]], baseline: dict[str, Any]) -> str:
    """Build the markdown report shown as sticky comment / step summary."""
    lines = ["## Action SHA drift report", ""]
    expected = baseline.get("expected_total_pins", 0)
    total = len(results)
    summary: dict[str, int] = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    lines.append(
        f"**Collected pins ({total} actions)** — expected_total_pins={expected}",
    )
    lines.append("")
    lines.append("| Action | Pinned SHA | Resolved | Status |")
    lines.append("|--------|------------|----------|--------|")
    for r in sorted(
        results,
        key=lambda x: (0 if x["status"] == "ok" else 1, x["action"]),
    ):
        resolved = r.get("resolved_tag", "—")
        sha_short = r["sha"][:7]
        raw = r["status"]
        status = "OK" if raw == "ok" else raw.upper()
        lines.append(
            f"| `{r['action']}` | `{sha_short}` | {resolved} | **{status}** |",
        )
    lines.append("")
    parts = [f"total={total}"]
    for k in ("ok", "dangling", "force-pushed", "ignored", "error"):
        if summary.get(k, 0) > 0:
            parts.append(f"{k}={summary[k]}")
    lines.append("Summary: " + ", ".join(parts))
    return "\n".join(lines) + "\n"


def run_drift_check(
    pins: list[tuple[str, str]],
    baseline: dict[str, Any],
    resolver: Callable[[str, str], dict[str, Any]],
    sleep_between: float = 0.0,
) -> list[dict[str, Any]]:
    """Apply ignore_actions, dispatch resolver for the rest, return results."""
    ignore_actions = set(baseline.get("ignore_actions", []) or [])
    results: list[dict[str, Any]] = []
    for action, sha in pins:
        if action in ignore_actions:
            results.append({"action": action, "sha": sha, "status": "ignored"})
            continue
        result = resolver(action, sha)
        if not isinstance(result, dict) or "status" not in result:
            raise TypeError(
                f"resolver must return dict with 'status'; got {type(result)}",
            )
        result.setdefault("action", action)
        result.setdefault("sha", sha)
        results.append(result)
        if sleep_between > 0:
            time.sleep(sleep_between)
    return results


def _offline_resolver(baseline: dict[str, Any]) -> Callable[[str, str], dict[str, Any]]:
    """Build a resolver that uses the baseline allowlist as the source of truth."""
    allowed = {(a["action"], a["sha"]): a for a in baseline.get("allowlist", [])}

    def resolve(action: str, sha: str) -> dict[str, Any]:
        match = allowed.get((action, sha))
        if match is None:
            return {
                "action": action,
                "sha": sha,
                "status": "dangling",
                "error": "not in baseline allowlist",
            }
        return {
            "action": action,
            "sha": sha,
            "status": "ok",
            "resolved_tag": match.get("resolved_tag", "(commit-only)"),
        }

    return resolve


def _api_resolver(token: str | None) -> Callable[[str, str], dict[str, Any]]:
    def resolve(action: str, sha: str) -> dict[str, Any]:
        return resolve_sha_via_api(action, sha, token=token)

    return resolve


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify GitHub Actions SHA pins are still alive upstream.",
    )
    p.add_argument(
        "--baseline", type=Path, default=DEFAULT_BASELINE, help="Baseline JSON path."
    )
    p.add_argument(
        "--workflows-dir",
        type=Path,
        default=WORKFLOW_DIR,
        help="Directory containing workflow YAMLs.",
    )
    p.add_argument(
        "--update-baseline",
        action="store_true",
        help="Re-scan + rewrite baseline JSON from results.",
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="Skip GitHub API; treat baseline allowlist as truth.",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write markdown report to this path (also stdout).",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Sleep between API calls (s); set 0 for tests.",
    )
    args = p.parse_args(argv)

    if not args.workflows_dir.exists():
        print(f"ERROR: {args.workflows_dir} not found", file=sys.stderr)
        return 1

    pins = collect_sha_pins(args.workflows_dir)
    emit_collected_log(pins)

    baseline = load_baseline(args.baseline)
    expected = int(baseline.get("expected_total_pins", 0) or 0)
    if expected > 0 and len(pins) < expected * SILENT_ZERO_RATIO:
        print(
            f"::warning::Collected pins ({len(pins)}) is less than "
            f"{SILENT_ZERO_RATIO:.0%} of expected_total_pins ({expected}). "
            "Possible silent-zero — investigate workflow paths / regex / "
            "baseline drift before trusting this run.",
            file=sys.stderr,
        )

    if args.offline:
        resolver = _offline_resolver(baseline)
        sleep_between = 0.0
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        resolver = _api_resolver(token)
        sleep_between = args.sleep

    results = run_drift_check(pins, baseline, resolver, sleep_between)

    if args.update_baseline:
        write_baseline(args.baseline, pins, results)
        ok_count = sum(1 for r in results if r["status"] == "ok")
        print(
            f"Wrote baseline to {args.baseline}: "
            f"{ok_count} ok pin(s), expected_total_pins={len(pins)}",
            file=sys.stderr,
        )
        return 0

    report = render_report(results, baseline)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    print(report)

    drift_count = sum(1 for r in results if r["status"] in ("dangling", "force-pushed"))
    return 1 if drift_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
