#!/usr/bin/env python3
"""The ORT optimized-model cache must be published by rename (issue #686).

`docs/spec/ort-session-contract.toml` `[cache.concurrency]` requires every
implementation to point ORT at a per-writer TEMP path and then rename that onto
`.opt.onnx`, rather than letting ORT write the shared file directly.

All four implementations did the latter. Two sessions created concurrently for
the same model therefore asked ORT to write the same file at once; on Windows
the second open is denied and the session constructor throws:

    [ErrorCode:Fail] Load model from ...\\zero-shot-test.cpu.opt.onnx failed:
    system error number 13

xUnit runs test collections in parallel, so `csharp-tests (windows-latest)` hit
it in ZeroShotE2ETests while 1453 other tests passed -- which is why it read as
an intermittent flake for months rather than a defect.

This gate asserts, per implementation:

  1. ORT is pointed at a temp path, NOT at the shared cache path;
  2. the temp is published with an atomic rename;
  3. the sentinel is written AFTER the rename, never before -- writing it first
     would advertise a cache that is not there yet;
  4. the unique part of the temp name comes from a process-local COUNTER.

Check 4 exists because the two obvious alternatives were measured to fail: a
nanosecond clock returned the same value for two consecutive calls (Rust), and
a 32-bit truncated UUID collided 6 times in 200,000 draws. Both would move the
race inside the process instead of removing it.

Exit codes: 0 = every implementation publishes by rename, 1 = at least one
does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from gate_source import strip_comments

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs/spec/ort-session-contract.toml"

# Per implementation:
#   temp_assign   -- ORT is handed the temp, with the variable named
#   rename        -- the atomic publish call, with both operands
#   counter       -- the process-local monotonic source
#   forbidden     -- handing ORT the shared cache path (the original defect)
IMPLS: dict[str, dict[str, object]] = {
    "python-train": {
        "file": "src/python/piper_train/ort_utils.py",
        "temp_assign": "opts.optimized_model_filepath = str(_temp_cache_path)",
        "rename": "os.replace(_temp_cache_path, cache_path)",
        "counter": "_TEMP_CACHE_SEQ = itertools.count()",
        "forbidden": [
            "opts.optimized_model_filepath = str(cache_path)",
        ],
        "test_file": "src/python/tests/test_ort_utils.py",
        "tests": [
            "def test_ort_is_pointed_at_a_temp_not_the_cache_path(",
            "def test_two_writers_get_distinct_temp_paths(",
            "def test_sentinel_is_not_written_when_the_rename_fails(",
        ],
    },
    "python-runtime": {
        "file": "src/python_run/piper_plus/voice.py",
        "temp_assign": "sess_options.optimized_model_filepath = str(temp_cache_path)",
        "rename": "os.replace(temp_cache_path, cache_path)",
        "counter": "_TEMP_CACHE_SEQ = itertools.count()",
        "forbidden": [
            "sess_options.optimized_model_filepath = str(cache_path)",
        ],
        "test_file": "src/python_run/tests/test_runtime.py",
        "tests": [
            "def test_runtime_cache_points_ort_at_a_temp_then_publishes(",
            "def test_runtime_cache_temp_paths_differ_between_writers(",
            "def test_runtime_cache_lost_rename_race_does_not_fail_the_load(",
        ],
    },
    "csharp": {
        "file": "src/csharp/PiperPlus.Core/Inference/SessionFactory.cs",
        "temp_assign": "options.OptimizedModelFilePath = tempOptimizedPath;",
        "rename": "File.Move(tempOptimizedPath, optimizedPath, overwrite: true);",
        "counter": "Interlocked.Increment(ref tempCacheSeq)",
        "forbidden": [
            "options.OptimizedModelFilePath = optimizedPath;",
        ],
        "test_file": None,
        "tests": [],
    },
    "rust": {
        "file": "src/rust/piper-core/src/engine.rs",
        "temp_assign": "Some(&temp_optimized_path),",
        "rename": "std::fs::rename(&temp_optimized_path, &optimized_path)",
        "counter": "COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed)",
        "forbidden": [
            "Some(&optimized_path),\n        )?;",
        ],
        "test_file": "src/rust/piper-core/src/engine.rs",
        "tests": [
            "fn temp_cache_path_is_not_the_shared_cache_path(",
            "fn temp_cache_paths_differ_between_writers(",
            "fn temp_cache_path_carries_the_process_id(",
        ],
    },
}

CONTRACT_REQUIREMENTS = [
    "\n[cache.concurrency]\n",
    'unique_source = "process_local_monotonic_counter"',
    'on_rename_failure = "discard_temp_and_continue"',
    "rename_is_atomic_within_directory = true",
]

# A timestamp-derived unique part is specifically banned: it was measured to
# repeat within one process.
BANNED_UNIQUE_SOURCES = [
    ("subsec_nanos", "a nanosecond clock repeated for two consecutive calls"),
    ("uuid4().hex[:8]", "32 bits collided 6 times in 200,000 draws"),
    ('Guid.NewGuid().ToString("N")[..8]', "32 bits is too few"),
]


def _read(rel: str) -> str | None:
    """Read a source file with its comments removed.

    Required in both directions here: a REQUIRED idiom must not be satisfied
    by a comment mentioning it, and a BANNED idiom must not be reported
    because a comment explains why it was rejected -- this gate's own
    `BANNED_UNIQUE_SOURCES` entries are named in the comments that document
    the measurements, so an unstripped read fires on all four
    implementations.
    """
    path = REPO_ROOT / rel
    if not path.is_file():
        return None
    return strip_comments(path.read_text(encoding="utf-8"), path.suffix)


def _sentinel_after_rename(source: str, rename: str, sentinel_markers: list[str]) -> bool:
    """True when the sentinel write appears AFTER the rename in the same block."""
    try:
        rename_at = source.index(rename)
    except ValueError:
        return False
    for marker in sentinel_markers:
        at = source.find(marker, rename_at)
        if at != -1:
            return True
    return False


SENTINEL_MARKERS = [
    'sentinel_path.write_text("ok")',
    'File.WriteAllText(sentinelPath, "ok");',
    'std::fs::write(&sentinel_path, b"ok")',
]


def main() -> int:
    failures: list[str] = []

    contract = _read(str(CONTRACT.relative_to(REPO_ROOT)))
    if contract is None:
        failures.append(f"contract missing: {CONTRACT}")
    else:
        for needle in CONTRACT_REQUIREMENTS:
            if needle not in contract:
                failures.append(
                    f"contract: [cache.concurrency] no longer declares "
                    f"{needle.strip()!r}"
                )

    for impl, spec in sorted(IMPLS.items()):
        rel = str(spec["file"])
        source = _read(rel)
        if source is None:
            failures.append(f"{impl}: file not found: {rel}")
            continue

        temp_assign = str(spec["temp_assign"])
        if temp_assign not in source:
            failures.append(
                f"{impl} ({rel}): ORT is not handed a temp path "
                f"(expected {temp_assign!r})"
            )

        for forbidden in spec["forbidden"]:  # type: ignore[union-attr]
            if str(forbidden) in source:
                failures.append(
                    f"{impl} ({rel}): ORT is pointed at the SHARED cache path "
                    f"({str(forbidden)!r}); a concurrent writer collides on it"
                )

        rename = str(spec["rename"])
        if rename not in source:
            failures.append(
                f"{impl} ({rel}): no atomic publish (expected {rename!r}); "
                "without the rename the temp is never promoted and the cache "
                "is never built"
            )
        elif not _sentinel_after_rename(source, rename, SENTINEL_MARKERS):
            failures.append(
                f"{impl} ({rel}): the sentinel is not written after the "
                "rename; writing it first advertises a cache that is not "
                "there, and the next run fails loading it"
            )

        counter = str(spec["counter"])
        if counter not in source:
            failures.append(
                f"{impl} ({rel}): the temp name's unique part does not come "
                f"from a process-local counter (expected {counter!r})"
            )

        for banned, why in BANNED_UNIQUE_SOURCES:
            if banned in source:
                failures.append(
                    f"{impl} ({rel}): temp name uses {banned!r} -- {why}"
                )

        test_rel = spec["test_file"]
        if test_rel is None:
            continue
        tests = _read(str(test_rel))
        if tests is None:
            failures.append(f"{impl}: test file not found: {test_rel}")
            continue
        for name in spec["tests"]:  # type: ignore[union-attr]
            if str(name) not in tests:
                failures.append(
                    f"{impl} ({test_rel}): missing test {str(name)!r}; "
                    "deleting it would reduce this to a presence check"
                )

    # Anti-vacuity: the table itself must stay populated, and every pattern
    # must be specific enough that it cannot match a declaration.
    if len(IMPLS) < 4:
        failures.append(
            f"gate covers only {len(IMPLS)} implementations; all 4 must be listed"
        )
    for impl, spec in sorted(IMPLS.items()):
        rename = str(spec["rename"])
        if not re.search(r"[(,]", rename):
            failures.append(
                f"{impl}/rename: pattern {rename!r} names no operands, so it "
                "could match something other than the publish call"
            )

    if failures:
        print("ORT cache concurrency: FAIL")
        for line in failures:
            print(f"  - {line}")
        print()
        print("Contract: docs/spec/ort-session-contract.toml [cache.concurrency]")
        return 1

    print(f"ORT cache concurrency: OK ({len(IMPLS)} implementations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
