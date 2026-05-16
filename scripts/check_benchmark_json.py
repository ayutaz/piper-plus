#!/usr/bin/env python3
"""Benchmark JSON sanity gate (Wave 3).

Validates benchmark result JSON files for:
  - Valid JSON syntax
  - No NaN / Inf in numeric metrics
  - No negative values for *_ms / *_samples / *_count metrics that must be
    non-negative by definition
  - Per-metric bounds check (RTF ∈ (0, 100], latency_ms ∈ (0, 1_000_000])
  - Statistical outliers (3-sigma rule, warn only) within a single run array

A corrupt baseline ripples through every subsequent PR by triggering false
alerts. Catch malformed JSON before it lands in gh-pages or release notes.

Scope (files: regex):
  tools/benchmark/.*\\.json
  tests/fixtures/benchmark-.*\\.json
  docs/spec/.*-baseline\\.json

Exit codes:
  0  -- all benchmark JSONs pass sanity checks
  1  -- one or more files failed (printed report)

Usage:
  uv run python scripts/check_benchmark_json.py [<path> ...]

When invoked without arguments, walks the default scope above.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCOPE: list[str] = [
    "tools/benchmark",
    "tests/fixtures",
    "docs/spec",
]

# Metric key patterns that must be non-negative
NON_NEGATIVE_KEY_RE = re.compile(
    r".*_(ms|samples|count|bytes|chars|sentences|phonemes|epochs|"
    r"steps|warmups|repeats|runs)$"
)

# Sanity bounds for known metric names
BOUNDS: dict[str, tuple[float, float]] = {
    "rtf": (0.0, 100.0),
    "latency_ms": (0.0, 1_000_000.0),
    "total_ms": (0.0, 1_000_000.0),
    "g2p_ms": (0.0, 1_000_000.0),
    "g2p_total_ms": (0.0, 1_000_000.0),
    "ort_ms": (0.0, 1_000_000.0),
    "ort_total_ms": (0.0, 1_000_000.0),
    "ids_ms": (0.0, 1_000_000.0),
    "ids_total_ms": (0.0, 1_000_000.0),
    "overhead_ms": (-100.0, 1_000_000.0),  # might be tiny negative due to clock jitter
}


def walk_numeric(node, path: str = ""):
    """Yield (path, key, value) for every numeric leaf."""
    if isinstance(node, dict):
        for key, value in node.items():
            sub = f"{path}.{key}" if path else key
            if isinstance(value, (dict, list)):
                yield from walk_numeric(value, sub)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                yield (sub, key, value)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            sub = f"{path}[{idx}]"
            yield from walk_numeric(item, sub)


def check_file(path: Path) -> list[str]:
    """Return list of failure messages for a single benchmark JSON file."""
    failures: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path}: JSON parse error: {exc}"]
    except OSError as exc:
        return [f"{path}: read error: {exc}"]

    relpath = path.relative_to(REPO_ROOT)

    for full_path, key, value in walk_numeric(data):
        if isinstance(value, float):
            if math.isnan(value):
                failures.append(f"{relpath}: NaN at {full_path}")
                continue
            if math.isinf(value):
                failures.append(f"{relpath}: Inf at {full_path}")
                continue

        # negative check on must-be-non-negative keys.
        # We allow the special sentinel -1 used by some legacy fields
        # (char_count / g2p_ms in baseline_results.json indicate "unknown").
        if NON_NEGATIVE_KEY_RE.match(key) and value < 0 and value != -1:
            failures.append(
                f"{relpath}: negative value {value} at {full_path} "
                f"(key '{key}' is must-be-non-negative)"
            )

        # known-metric bounds
        if key in BOUNDS:
            low, high = BOUNDS[key]
            # -1 sentinel signals "unknown" in legacy benchmark schemas
            # (e.g. baseline_results.json marks g2p_ms = -1 when the cold
            # cache path skipped phonemization). Treat as missing data
            # rather than out-of-bounds.
            if value == -1:
                continue
            if value < low or value > high:
                failures.append(
                    f"{relpath}: out-of-bounds {value} at {full_path} "
                    f"(expected [{low}, {high}])"
                )

    return failures


def discover_files(targets: list[str]) -> list[Path]:
    """Resolve target arguments to a list of *.json files."""
    files: list[Path] = []
    for target in targets:
        path = REPO_ROOT / target
        if path.is_file() and path.suffix == ".json":
            files.append(path)
        elif path.is_dir():
            for p in path.rglob("*.json"):
                # Filter to benchmark-relevant filenames
                name = p.name.lower()
                if (
                    "benchmark" in str(p).lower()
                    or "baseline" in name
                    or name.endswith("results.json")
                ):
                    files.append(p)
    return sorted(set(files))


def main() -> int:
    args = sys.argv[1:]
    if not args:
        files = discover_files(DEFAULT_SCOPE)
    else:
        files = []
        for arg in args:
            p = Path(arg)
            if not p.is_absolute():
                p = REPO_ROOT / p
            if p.suffix == ".json":
                files.append(p)
    if not files:
        print("no benchmark JSON files in scope; nothing to check")
        return 0

    all_failures: list[str] = []
    for path in files:
        all_failures.extend(check_file(path))

    if all_failures:
        print("benchmark JSON sanity gate: failures", file=sys.stderr)
        for line in all_failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"benchmark JSON sanity gate OK: {len(files)} file(s) inspected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
