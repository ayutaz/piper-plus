#!/usr/bin/env python3
# Wave 5-6 — Asymmetric latency gate (short vs medium text).
#
# Why: 既存 RTF regression gate (rtf-regression.yml) は短/中/長 text の
#   それぞれに symmetric な ±10% 閾値を当てているが、 Duration Predictor の
#   instability は「短い text で長い text より latency が大きく出る」 という
#   directional regression の signal となる。 short / medium の P50 ratio を
#   別途 track し、 ratio > 2.0 で Duration Predictor / 推論 path に異常が
#   入った可能性を warn する。
#
# How to apply: tests/fixtures/multi-runtime-rtf-baseline.json の各 runtime
#   について short / medium の latency_p50_ms ratio を計算。 ratio > 2.0 で
#   warn (Duration Predictor instability の hint)、 ratio > 3.0 で fail。
#   wasm のような null (baseline 未確立) は skip。

from __future__ import annotations

import json
import sys
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "fixtures" / "multi-runtime-rtf-baseline.json"

WARN_RATIO = 2.0
FAIL_RATIO = 3.0


def main() -> int:
    if not BASELINE.exists():
        print(f"::warning::baseline JSON missing: {BASELINE}", file=sys.stderr)
        return 0

    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    runtimes = data.get("runtimes", {})
    if not runtimes:
        print(f"::warning::no 'runtimes' key in {BASELINE}", file=sys.stderr)
        return 0

    warnings: list[str] = []
    errors: list[str] = []
    ok_count = 0

    for runtime_name, runtime_data in sorted(runtimes.items()):
        short_p50 = runtime_data.get("short", {}).get("latency_p50_ms")
        medium_p50 = runtime_data.get("medium", {}).get("latency_p50_ms")

        if short_p50 is None or medium_p50 is None or medium_p50 == 0:
            # baseline 未確立 (wasm 等) — skip
            continue

        ratio = short_p50 / medium_p50

        if ratio >= FAIL_RATIO:
            errors.append(
                f"  - {runtime_name}: short/medium P50 ratio={ratio:.2f} "
                f"(short={short_p50}ms, medium={medium_p50}ms) ≥ fail {FAIL_RATIO}"
            )
        elif ratio >= WARN_RATIO:
            warnings.append(
                f"  - {runtime_name}: short/medium P50 ratio={ratio:.2f} "
                f"(short={short_p50}ms, medium={medium_p50}ms) ≥ warn {WARN_RATIO}"
            )
        else:
            ok_count += 1

    for w in warnings:
        print(f"::warning::Asymmetric latency:{w[4:]}")

    if errors:
        print("::error::Asymmetric latency gate failed:")
        for e in errors:
            print(e)
        print()
        print(
            "short_p50 が medium_p50 の 3 倍以上 = Duration Predictor の "
            "instability や warmup 不足の signal の可能性。 推論 path /"
            " noise_scale / model export config を確認してください。"
        )
        return 1

    print(
        f"[check_asymmetric_latency] OK — {ok_count} runtime(s) within ratio "
        f"< {WARN_RATIO}, {len(warnings)} warning(s), 0 errors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
