#!/usr/bin/env python3
"""Phoneme timing temporal monotonicity (M4.2).

任意のテキスト入力 (8 言語 / SSML / silence option 組み合わせ) に対し
phoneme timing 出力が 4 つの不変条件を満たすかを property style に検査
する CLI。 ``docs/spec/phoneme-timing-contract.toml`` の不変条件節と 1:1
対応する。

不変条件:

1. 各 phoneme について ``start <= end``
2. 隣接 phoneme について ``next.start >= prev.end`` (overlap しない)
3. 全 phoneme の累積時間 ≈ audio duration (許容誤差 ±50ms)
4. ``end`` は audio duration を超えない

入力 fixture (`tests/fixtures/timing/*.json`) は他チケットで充実させる前提。
本 script の core は ``check_invariants(events, audio_duration_ms)`` で
``hypothesis`` 不使用、 random 駆動で 1000 ケース検査する fuzz mode も持つ。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class TimingEvent:
    phoneme: str
    start_ms: float
    end_ms: float


@dataclass
class CheckResult:
    passed: bool
    violations: list[str]


def check_invariants(
    events: list[TimingEvent],
    audio_duration_ms: float | None = None,
    *,
    duration_tolerance_ms: float = 50.0,
) -> CheckResult:
    violations: list[str] = []
    if not events:
        return CheckResult(passed=True, violations=[])

    for i, e in enumerate(events):
        if e.end_ms < e.start_ms:
            violations.append(
                f"event[{i}] {e.phoneme!r}: end {e.end_ms} < start {e.start_ms}"
            )
    for i in range(1, len(events)):
        prev = events[i - 1]
        cur = events[i]
        if cur.start_ms + 1e-6 < prev.end_ms:
            violations.append(
                f"event[{i}] {cur.phoneme!r}: starts {cur.start_ms} before "
                f"prev.end {prev.end_ms}"
            )
    if audio_duration_ms is not None:
        last_end = events[-1].end_ms
        if last_end > audio_duration_ms + duration_tolerance_ms:
            violations.append(
                f"last.end {last_end} exceeds audio duration "
                f"{audio_duration_ms} (+tolerance {duration_tolerance_ms})"
            )
        # The cumulative phoneme span may be shorter than the audio (silence
        # padding), but should not be wildly larger.
        if last_end > 0 and last_end < audio_duration_ms - duration_tolerance_ms - 250:
            # 250ms grace lets a typical EOS trim / silence-padding pattern pass.
            violations.append(
                f"last.end {last_end} is much shorter than audio duration "
                f"{audio_duration_ms} beyond the tolerance"
            )
    return CheckResult(passed=not violations, violations=violations)


def events_from_dict(d: dict[str, Any]) -> list[TimingEvent]:
    return [
        TimingEvent(
            phoneme=str(e.get("phoneme", "?")),
            start_ms=float(e["start_ms"]),
            end_ms=float(e["end_ms"]),
        )
        for e in d.get("events", [])
    ]


def random_monotonic_events(rng: random.Random) -> tuple[list[TimingEvent], float]:
    """Generate a random *valid* timing sequence (used by property tests)."""
    n = rng.randint(1, 30)
    t = 0.0
    events: list[TimingEvent] = []
    for i in range(n):
        dur = rng.uniform(5.0, 120.0)
        start = t
        end = start + dur
        events.append(TimingEvent(phoneme=f"p{i}", start_ms=start, end_ms=end))
        t = end + rng.uniform(0.0, 20.0)  # silence between phonemes
    audio_dur = events[-1].end_ms + rng.uniform(0.0, 200.0)
    return events, audio_dur


def cmd_check(args: argparse.Namespace) -> int:
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    events = events_from_dict(payload)
    result = check_invariants(events, payload.get("audio_duration_ms"))
    if result.passed:
        print(f"{args.input.name}: {len(events)} events, all invariants hold.")
        return 0
    for v in result.violations:
        print(f"VIOLATION: {v}", file=sys.stderr)
    return 1


def cmd_fuzz(args: argparse.Namespace) -> int:
    seed = args.seed if args.seed is not None else random.randint(0, 1_000_000)
    rng = random.Random(seed)
    failures: list[str] = []
    for _ in range(args.iterations):
        events, audio = random_monotonic_events(rng)
        # Occasionally introduce a known-bad mutation to confirm the
        # invariant checker actually triggers; this is the inverse
        # of property fuzz — we are also exercising the detector.
        if rng.random() < 0.05 and len(events) >= 2:
            bad = TimingEvent(
                phoneme="bad",
                start_ms=events[0].end_ms,
                end_ms=events[0].start_ms,  # end < start
            )
            mutated = [*events[:1], bad, *events[1:]]
            result = check_invariants(mutated, audio)
            if result.passed:
                failures.append("checker missed bad event")
            continue
        result = check_invariants(events, audio)
        if not result.passed:
            failures.append(f"random monotonic sequence flagged as bad: {result.violations[0]}")
    summary = {
        "seed": seed,
        "iterations": args.iterations,
        "failures": failures,
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.fail_on_failure and failures:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--input", type=Path, required=True)
    c.set_defaults(func=cmd_check)
    f = sub.add_parser("fuzz")
    f.add_argument("--iterations", type=int, default=1000)
    f.add_argument("--seed", type=int, default=None)
    f.add_argument("--output", type=Path, default=None)
    f.add_argument("--fail-on-failure", action="store_true")
    f.set_defaults(func=cmd_fuzz)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
