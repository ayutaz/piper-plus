#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring example uses 2-space JSON indent)
"""Convert ``scripts/benchmark.py`` JSON output to the schema consumed by
``benchmark-action/github-action-benchmark``.

github-action-benchmark's ``customSmallerIsBetter`` tool expects a JSON
array of metric objects::

    [
      {"name": "RTF (en)",         "unit": "ratio", "value": 0.078},
      {"name": "Latency P50 (en)", "unit": "ms",    "value": 27.0},
      ...
    ]

``benchmark.py`` returns a list of per-model result dicts that include
keys like ``rtf``, ``latency_p50_ms``, ``latency_p95_ms``,
``cold_start_ms``, ``peak_memory_mb``, ``model_size_mb``, etc. This
script flattens those into the action-benchmark schema, restricted to
metrics where *smaller is better* (the only ones that the
``customSmallerIsBetter`` tool can correctly alert on for regressions).

Usage::

    uv run python scripts/benchmark_to_action_bench.py \\
        benchmark_results.json --output benchmark_action.json

Multiple model entries are disambiguated with the ``model`` field as a
suffix (e.g. ``RTF (multilingual-test-medium.onnx)``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Metrics where smaller is better. Each tuple is
#     (benchmark.py key, display name, unit).
SMALLER_IS_BETTER_METRICS = [
    ("rtf", "RTF", "ratio"),
    ("latency_p50_ms", "Latency P50", "ms"),
    ("latency_p95_ms", "Latency P95", "ms"),
    ("cold_start_ms", "Cold Start", "ms"),
    ("peak_memory_mb", "Peak Memory", "MB"),
    ("model_size_mb", "Model Size", "MB"),
]


def _format_name(display: str, suffix: str, language: str | None) -> str:
    """Build a per-metric display name including model + language hint."""
    parts = [display]
    extras = []
    if language:
        extras.append(language)
    if suffix:
        extras.append(suffix)
    if extras:
        parts.append("(" + ", ".join(extras) + ")")
    return " ".join(parts)


def convert(records: list[dict]) -> list[dict]:
    """Flatten benchmark.py records to action-benchmark metric entries."""
    metrics: list[dict] = []
    multi = len(records) > 1

    for record in records:
        suffix = record.get("model", "") if multi else ""
        language = record.get("test_language")

        for key, display, unit in SMALLER_IS_BETTER_METRICS:
            if key not in record:
                continue
            value = record[key]
            if value is None:
                continue
            metrics.append(
                {
                    "name": _format_name(display, suffix, language),
                    "unit": unit,
                    "value": float(value),
                }
            )

    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "input",
        type=Path,
        help="Path to benchmark.py --format=json output",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the action-benchmark JSON",
    )
    args = parser.parse_args(argv)

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        # benchmark.py with a single --model returns a 1-element list
        # wrapped in an object by format_json. Tolerate either shape.
        # Review #458: ``raw.get("results") or [raw]`` was misclassifying
        # ``{"results": []}`` (empty list is falsy → wrapper treated as a
        # single record). Explicit key check distinguishes "no results"
        # from "single record".
        if "results" in raw and isinstance(raw["results"], list):
            records = raw["results"]
        else:
            records = [raw]
    else:
        records = list(raw)

    metrics = convert(records)
    if not metrics:
        print(
            "ERROR: no smaller-is-better metrics found in input",
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(metrics)} metric(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
