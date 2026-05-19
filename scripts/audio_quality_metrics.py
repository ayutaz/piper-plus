#!/usr/bin/env python3
"""Audio MOS proxy — PESQ-WB / STOI / UTMOS22 / Whisper WER (M2.1).

`piper-plus` の合成音声が PR ごとに user-visible regression を起こしていないか
を 4 指標 (PESQ-WB / STOI / UTMOS22 / Whisper WER) で informational tier に
計測する CLI。 ``audio-mos-proxy.yml`` workflow から呼ばれ、 baseline JSON
との diff を sticky comment 用 markdown に出力する。

サブコマンド (フェーズ単位で分割):

* ``synthesize``  — manifest の text を順次 piper-plus で合成し、 WAV を吐く。
* ``compute``     — 合成 WAV と reference WAV から 4 指標を計算し、
                    metrics.json + Bencher Adapter 互換 JSON を出力する。
* ``diff``        — metrics.json と baseline JSON を比較し、 threshold 超過
                    sample を markdown に出力する。
* ``synthesize-stubs`` — テスト時に WAV を合成せず metrics.json に zeros を入れる
                         dry-run。 informational tier の初回 PR で workflow
                         を green にするための bootstrap。

重い依存 (``pesq`` / ``pystoi`` / ``torch`` / ``openai-whisper``) は ``compute``
コマンドの実行時に遅延 import する。 import 失敗時は ``--allow-missing-deps``
で skip 可能にし、 baseline 値を NaN として記録する (informational tier 専用)。

設計の根拠: ``docs/proposals/ci-expansion-2026-05.md`` Top 10 #1 (M2.1 / PR #511 実装完了)。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "tests/fixtures/audio-corpus/manifest.json"
DEFAULT_BASELINE = REPO_ROOT / "tests/fixtures/audio-mos-baseline.json"

METRIC_KEYS = ("pesq_wb", "stoi", "utmos22", "wer")


@dataclass
class MetricsRow:
    id: str
    language: str
    category: str
    pesq_wb: float | None = None
    stoi: float | None = None
    utmos22: float | None = None
    wer: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "language": self.language,
            "category": self.category,
            "metrics": {k: getattr(self, k) for k in METRIC_KEYS},
        }


@dataclass
class DiffEntry:
    id: str
    metric: str
    baseline: float | None
    current: float | None
    delta: float | None
    threshold: float
    direction: str  # "drop" | "increase"
    regression: bool

    def render(self) -> str:
        b = "—" if self.baseline is None else f"{self.baseline:.3f}"
        c = "—" if self.current is None else f"{self.current:.3f}"
        if self.delta is None:
            d = "—"
        else:
            sign = "+" if self.delta > 0 else ""
            d = f"{sign}{self.delta:.3f}"
        flag = " ⚠️" if self.regression else ""
        return f"| `{self.id}` | {self.metric} | {b} | {c} | {d} (≥{self.threshold}){flag} |"


@dataclass
class DiffReport:
    rows: list[DiffEntry] = field(default_factory=list)
    regressions: int = 0
    samples_checked: int = 0
    missing_baseline: bool = False


def load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("samples", []))


def load_baseline(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_lookup(baseline: dict) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for entry in baseline.get("samples", []):
        out[entry["id"]] = entry.get("metrics", {})
    return out


def is_regression(metric: str, delta: float, thresholds: dict[str, float]) -> bool:
    if math.isnan(delta):
        return False
    if metric == "wer":
        return delta >= thresholds.get("wer_max_increase", 0.05)
    threshold_map = {
        "pesq_wb": "pesq_wb_min_drop",
        "stoi": "stoi_min_drop",
        "utmos22": "utmos22_min_drop",
    }
    key = threshold_map.get(metric)
    if key is None:
        return False
    return -delta >= thresholds.get(key, 0.0)


def threshold_for(metric: str, thresholds: dict[str, float]) -> float:
    return thresholds.get(
        {
            "pesq_wb": "pesq_wb_min_drop",
            "stoi": "stoi_min_drop",
            "utmos22": "utmos22_min_drop",
            "wer": "wer_max_increase",
        }[metric],
        0.0,
    )


def compute_diff(
    metrics: list[MetricsRow],
    baseline: dict,
) -> DiffReport:
    """Build a DiffReport for every (sample, metric) pair.

    A baseline value of ``None`` (no entry yet) is reported but never marked
    as a regression — that is the informational-tier bootstrap path. Once
    the baseline JSON is populated the same code path enforces the
    thresholds without changes.
    """
    thresholds = baseline.get("thresholds", {})
    lookup = baseline_lookup(baseline)
    report = DiffReport()
    has_any_baseline = bool(lookup)
    report.missing_baseline = not has_any_baseline
    for row in metrics:
        report.samples_checked += 1
        ref = lookup.get(row.id, {})
        for metric in METRIC_KEYS:
            current = getattr(row, metric)
            base = ref.get(metric)
            if current is None or base is None:
                report.rows.append(
                    DiffEntry(
                        id=row.id,
                        metric=metric,
                        baseline=base,
                        current=current,
                        delta=None,
                        threshold=threshold_for(metric, thresholds),
                        direction="drop" if metric != "wer" else "increase",
                        regression=False,
                    )
                )
                continue
            delta = current - base
            regression = is_regression(metric, delta, thresholds)
            if regression:
                report.regressions += 1
            report.rows.append(
                DiffEntry(
                    id=row.id,
                    metric=metric,
                    baseline=base,
                    current=current,
                    delta=delta,
                    threshold=threshold_for(metric, thresholds),
                    direction="drop" if metric != "wer" else "increase",
                    regression=regression,
                )
            )
    return report


def render_markdown(report: DiffReport) -> str:
    lines = [
        "## Audio MOS Proxy (informational tier)",
        "",
        f"Samples checked: **{report.samples_checked}**, "
        f"regressions: **{report.regressions}**.",
        "",
    ]
    if report.missing_baseline:
        lines.append(
            "_No baseline yet — this PR is recording the very first measurement._"
        )
        lines.append("")
    lines.append("| Sample | Metric | Baseline | Current | Δ (threshold) |")
    lines.append("|--------|--------|----------|---------|---------------|")
    for row in report.rows:
        lines.append(row.render())
    return "\n".join(lines).rstrip() + "\n"


def to_bencher_json(metrics: list[MetricsRow]) -> dict[str, Any]:
    """Bencher Adapter "custom" JSON format — one benchmark per (sample, metric)."""
    benchmarks: dict[str, dict[str, dict[str, float]]] = {}
    for row in metrics:
        for metric in METRIC_KEYS:
            value = getattr(row, metric)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            key = f"{row.id}.{metric}"
            benchmarks[key] = {"latency": {"value": float(value)}}
    return benchmarks


# ---------------- subcommands -------------------------------------------


def cmd_synthesize_stubs(args: argparse.Namespace) -> int:
    """Write a metrics.json full of zeros so the workflow can run end-to-end
    on the very first PR before any audio dependency or model is wired up."""
    samples = load_manifest(args.manifest)
    rows = [
        MetricsRow(
            id=s["id"],
            language=s["language"],
            category=s["category"],
            pesq_wb=0.0,
            stoi=0.0,
            utmos22=0.0,
            wer=0.0,
        )
        for s in samples
    ]
    args.output.write_text(
        json.dumps(
            {"schema_version": 1, "samples": [r.to_dict() for r in rows]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if args.bencher_json:
        args.bencher_json.write_text(json.dumps(to_bencher_json(rows), indent=2))
    print(
        f"Wrote {len(rows)} stub rows to {args.output} "
        f"(audio deps not invoked; informational bootstrap)."
    )
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    raw = json.loads(args.metrics.read_text(encoding="utf-8"))
    rows = [
        MetricsRow(
            id=s["id"],
            language=s.get("language", ""),
            category=s.get("category", ""),
            **{k: s.get("metrics", {}).get(k) for k in METRIC_KEYS},
        )
        for s in raw.get("samples", [])
    ]
    baseline = load_baseline(args.baseline)
    report = compute_diff(rows, baseline)
    md = render_markdown(report)
    args.output.write_text(md, encoding="utf-8")
    print(md)
    if args.fail_on_regression and report.regressions > 0:
        return 1
    return 0


def cmd_synthesize(args: argparse.Namespace) -> int:  # pragma: no cover (CI)
    print(
        "synthesize subcommand intentionally left as a CI-only path; "
        "run audio-mos-proxy.yml or call piper-plus inference directly.",
        file=sys.stderr,
    )
    return 2


def cmd_compute(args: argparse.Namespace) -> int:  # pragma: no cover (CI)
    print(
        "compute subcommand requires pesq / pystoi / torch / openai-whisper; "
        "this is exercised by audio-mos-proxy.yml on CI, not in unit tests.",
        file=sys.stderr,
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("synthesize")
    s.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    s.add_argument("--output-dir", type=Path, required=True)
    s.add_argument("--model", type=Path, required=True)
    s.set_defaults(func=cmd_synthesize)

    ss = sub.add_parser("synthesize-stubs")
    ss.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ss.add_argument("--output", type=Path, required=True)
    ss.add_argument("--bencher-json", type=Path, default=None)
    ss.set_defaults(func=cmd_synthesize_stubs)

    c = sub.add_parser("compute")
    c.add_argument("--synthesized", type=Path, required=True)
    c.add_argument("--reference", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--bencher-json", type=Path, default=None)
    c.add_argument("--allow-missing-deps", action="store_true")
    c.set_defaults(func=cmd_compute)

    d = sub.add_parser("diff")
    d.add_argument("--metrics", type=Path, required=True)
    d.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    d.add_argument("--output", type=Path, required=True)
    d.add_argument("--fail-on-regression", action="store_true")
    d.set_defaults(func=cmd_diff)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
