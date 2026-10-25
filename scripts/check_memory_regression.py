#!/usr/bin/env python3
"""Per-language peak RSS regression gate (memory-regression.yml).

Reads one ``scripts/benchmark.py --format json`` result per language from
``--results-dir`` and compares its ``peak_memory_mb`` against
``tests/fixtures/memory-baseline.json``.

The gate fails (exit 1) when, for any language:

* the peak RSS grew by more than ``threshold_pct`` over the baseline
  (``WARN`` was the old name for this; it never failed the job),
* the result file is missing or has no ``peak_memory_mb`` (``MISSING``), or
* the baseline has no value for it (``NO-BASELINE``).

The last two used to be a ``SKIP`` that never failed, which kept the job
green while every baseline entry was ``null``.

Usage
-----
    uv run python scripts/check_memory_regression.py --results-dir memory-results
    # After an intended change, write the observed values into the baseline
    uv run python scripts/check_memory_regression.py --results-dir memory-results --update-baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = REPO_ROOT / "tests" / "fixtures" / "memory-baseline.json"
LANGUAGES = ("ja", "en", "zh", "es", "fr", "pt")
FAILING_STATUSES = frozenset({"FAIL", "MISSING", "NO-BASELINE"})


def _observed_mb(results_dir: Path, lang: str) -> float | None:
    path = results_dir / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"WARN: could not read {path}: {exc}", file=sys.stderr)
        return None
    if isinstance(data, list):
        data = data[0] if data else {}
    value = data.get("peak_memory_mb") if isinstance(data, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def compare(baseline: dict, results_dir: Path) -> list[dict]:
    threshold = float(baseline["threshold_pct"])
    rows = []
    for lang in LANGUAGES:
        base_mb = baseline.get("languages", {}).get(lang, {}).get("peak_memory_mb")
        obs_mb = _observed_mb(results_dir, lang)
        delta = None
        if obs_mb is None:
            status = "MISSING"
        elif not base_mb:
            status = "NO-BASELINE"
        else:
            delta = (obs_mb - base_mb) / base_mb
            status = "FAIL" if delta > threshold else "OK"
        rows.append(
            {
                "lang": lang,
                "baseline_mb": base_mb,
                "observed_mb": obs_mb,
                "delta_pct": delta,
                "status": status,
            }
        )
    return rows


def render_markdown(rows: list[dict], threshold: float) -> str:
    def mb(value):
        return "n/a" if value is None else f"{value:.1f}"

    lines = [
        "## Memory regression (per-language)",
        "",
        f"Threshold: +{threshold * 100:.0f}% peak RSS vs baseline.",
        "",
        "| Status | Lang | Baseline (MB) | Observed (MB) | Delta |",
        "|--------|------|---------------|---------------|-------|",
    ]
    for r in rows:
        delta = "n/a" if r["delta_pct"] is None else f"{r['delta_pct'] * 100:+.2f}%"
        lines.append(
            f"| {r['status']} | {r['lang']} | {mb(r['baseline_mb'])} | {mb(r['observed_mb'])} | {delta} |"
        )
    failing = sum(1 for r in rows if r["status"] in FAILING_STATUSES)
    lines += [
        "",
        f"Summary: {failing} failing / {len(rows) - failing} ok.",
        "",
        "_MISSING means the benchmark produced no peak_memory_mb; NO-BASELINE means "
        "tests/fixtures/memory-baseline.json has no value. Both fail the job, like FAIL. "
        "After an intended change, update the baseline in the same PR._",
    ]
    return "\n".join(lines) + "\n"


def update_baseline(baseline: dict, rows: list[dict]) -> dict:
    missing = [r["lang"] for r in rows if r["observed_mb"] is None]
    if missing:
        raise ValueError("no observed value for: " + ", ".join(missing))
    for r in rows:
        baseline["languages"].setdefault(r["lang"], {})["peak_memory_mb"] = round(
            r["observed_mb"], 1
        )
    return baseline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-dir", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--output", type=Path, help="Write the Markdown report here.")
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the observed values into the baseline instead of comparing.",
    )
    args = ap.parse_args(argv)

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    rows = compare(baseline, args.results_dir)

    if args.update_baseline:
        try:
            update_baseline(baseline, rows)
        except ValueError as exc:
            print(f"ERROR: refusing to update the baseline; {exc}", file=sys.stderr)
            return 1
        args.baseline.write_text(
            json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Updated baseline: {args.baseline}", file=sys.stderr)
        return 0

    report = render_markdown(rows, float(baseline["threshold_pct"]))
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")

    failing = [r for r in rows if r["status"] in FAILING_STATUSES]
    if failing:
        print(
            "ERROR: "
            + ", ".join(f"{r['lang']} ({r['status']})" for r in failing),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
