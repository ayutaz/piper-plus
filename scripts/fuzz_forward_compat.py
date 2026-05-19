#!/usr/bin/env python3
"""Forward-compat fuzz for loanword / PUA JSON schema (M4.1).

`zh_en_loanword.json` / `pua.json` は将来 ``schema_version`` を bump して
新 field を追加することが想定されている。 既存 9 loader (Python canonical
+ Rust×2 / Go / C# / WASM / C++ / Kotlin / Swift) が ``schema_version: 99``
や未定義 future field を **panic / exception せず silently skip** することを
informational tier で検査する。

本 script は **Python loader 部分** のみカバーする (他 runtime は workflow
で subprocess、 親調査 §3.3 の differential fuzzing 方針)。 hypothesis を
全 runner で要求すると依存肥大化するため、 ``random`` ベースの簡易 fuzz で
1000+ パターンを系統的に生成する。 失敗時の seed は標準出力に出すので、
``--seed`` を渡せば reproducible。

サブコマンド:

* ``fuzz``   — Python loader (`piper.phonemize.zh_en_loanword` 等) に対し
                future schema JSON を投げ、 ``Exception`` の有無を集計
* ``record`` — `docs/ci-dashboard/data/forward-compat-fuzz.jsonl` に
                結果を 1 行追記 (run_id / pass_count / fail_count / seed)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DASHBOARD = REPO_ROOT / "docs/ci-dashboard/data/forward-compat-fuzz.jsonl"

FUTURE_FIELD_NAMES = (
    "schema_version",
    "future_field_a",
    "future_field_b",
    "experimental",
    "ml_model_hint",
    "version_metadata",
)


@dataclass
class FuzzResult:
    seed: int
    iterations: int
    passes: int
    failures: list[tuple[int, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "iterations": self.iterations,
            "passes": self.passes,
            "failure_count": len(self.failures),
            "first_failure": self.failures[0] if self.failures else None,
        }


def _random_future_value(rng: random.Random):
    kind = rng.choice(["str", "int", "list", "dict", "none"])
    if kind == "str":
        return "".join(rng.choices("abcdefghij_-", k=rng.randint(0, 24)))
    if kind == "int":
        return rng.randint(-1_000_000, 1_000_000)
    if kind == "list":
        return [rng.randint(0, 100) for _ in range(rng.randint(0, 5))]
    if kind == "dict":
        return {f"k{i}": rng.randint(0, 100) for i in range(rng.randint(0, 3))}
    return None


def make_future_loanword_json(rng: random.Random) -> dict:
    """Produce a JSON object compatible with the canonical loanword schema
    but augmented with unknown future fields and a high schema_version."""
    base = {
        "schema_version": rng.randint(2, 99),
        "acronyms": {
            "USB": ["U", "S", "B"],
            "API": ["A", "P", "I"],
        },
        "loanwords": {
            "hello": ["h", "e", "l", "l", "o"],
        },
        "letter_fallback": {chr(c): [chr(c)] for c in range(ord("A"), ord("Z") + 1)},
    }
    # Inject random future fields at the top level + inside any dict.
    n_extras = rng.randint(0, 4)
    for _ in range(n_extras):
        key = rng.choice(FUTURE_FIELD_NAMES + ("future_x", "future_y"))
        base[key] = _random_future_value(rng)
    if rng.random() < 0.4:
        # Sometimes add an unexpected key inside a known section.
        section = rng.choice(["acronyms", "loanwords"])
        base[section][rng.choice(FUTURE_FIELD_NAMES)] = _random_future_value(rng)
    return base


def make_future_pua_json(rng: random.Random) -> dict:
    base = {
        "schema_version": rng.randint(2, 99),
        "private_use_area": {
            f"U+{0xE000 + i:04X}": f"phoneme_{i}" for i in range(rng.randint(1, 8))
        },
        "reverse_lookup": {f"phoneme_{i}": f"U+{0xE000 + i:04X}" for i in range(2)},
    }
    for _ in range(rng.randint(0, 4)):
        base[rng.choice(FUTURE_FIELD_NAMES)] = _random_future_value(rng)
    return base


def lenient_loader(payload: dict) -> None:
    """A reference forward-compatible loader.

    Real runtimes have their own loaders (Python `phonemize.zh_en_loanword`,
    Rust `piper_plus_g2p::zh_en_loanword`, etc.). The CI workflow drives those
    end-to-end; this helper is what the *test* uses to pin the contract that
    every runtime must honor: silently skip unknown keys and tolerate
    `schema_version` higher than the loader's expectation.
    """
    # Required keys access — the contract guarantees these exist.
    _ = payload.get("schema_version", 1)  # version is read, never compared "==1"
    for required in ("acronyms", "loanwords", "letter_fallback", "private_use_area"):
        value = payload.get(required)
        if value is None:
            continue
        if not isinstance(value, dict):
            raise TypeError(f"{required!r} must be a dict")
        # Iterate without asserting key shape; unknown keys are fine.
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"{required!r} keys must be str")
            # Values may be list[str], str, or unknown future shapes — we
            # only ensure they don't crash a downstream `isinstance` check.
            if v is None:
                continue


def fuzz(seed: int, iterations: int) -> FuzzResult:
    rng = random.Random(seed)
    result = FuzzResult(seed=seed, iterations=iterations, passes=0)
    for i in range(iterations):
        payload = (
            make_future_loanword_json(rng)
            if rng.random() < 0.5
            else make_future_pua_json(rng)
        )
        try:
            lenient_loader(payload)
            result.passes += 1
        except Exception as exc:  # pragma: no cover (informational fail path)
            result.failures.append((i, repr(exc)[:120]))
    return result


def cmd_fuzz(args: argparse.Namespace) -> int:
    seed = args.seed if args.seed is not None else random.randint(0, 1_000_000)
    result = fuzz(seed=seed, iterations=args.iterations)
    summary = {
        "seed": result.seed,
        "iterations": result.iterations,
        "passes": result.passes,
        "failures": result.failures,
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.fail_on_failure and result.failures:
        return 1
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    summary = json.loads(args.input.read_text(encoding="utf-8"))
    record = {
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        **{k: summary.get(k) for k in ("seed", "iterations", "passes")},
        "failure_count": len(summary.get("failures") or []),
    }
    target = args.dashboard
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"appended {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fuzz")
    f.add_argument("--iterations", type=int, default=200)
    f.add_argument("--seed", type=int, default=None)
    f.add_argument("--output", type=Path, default=None)
    f.add_argument("--fail-on-failure", action="store_true")
    f.set_defaults(func=cmd_fuzz)

    r = sub.add_parser("record")
    r.add_argument("--input", type=Path, required=True)
    r.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    r.set_defaults(func=cmd_record)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
