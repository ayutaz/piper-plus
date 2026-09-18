#!/usr/bin/env python3
"""End-to-end gate for the C++ CLI's ``--output-timing`` flag (issue #652).

Issue #652 was reported against the CLI, not the library: ``--output-timing``
was accepted, ``--debug`` printed ``Extracted timing for 38 phonemes``, and
then no file appeared and no ``Wrote phoneme timing to ...`` line was logged.
The cause was in ``piper.cpp`` (per-phrase timings were never forwarded to the
caller's ``SynthesisResult``), but the *symptom* the reporter could observe
lived entirely in ``main.cpp``'s write path:

    if (runConfig.outputTimingPath && result.hasTimingInfo) { ...write... }

Nothing in CI ever ran the CLI binary with ``--output-timing``. The gtest
suites added in PR #658 drive ``textToAudio`` / the C API directly, so they
cover the propagation but not this gate, the JSON/TSV writers invoked from it,
or the flag parsing in front of it. ``main.cpp`` has no test-reachable entry
point at all, which is why the reporter's exact command had to be turned into
a CI step instead of another unit test.

What each case defends, and how it fails if the defence is removed:

``single_sentence_json``
    The reporter's own command. Fails with "timing file was not created" the
    moment timing stops reaching the final result.

``multi_unit_offsets``
    ``start_ms == 0`` must occur EXACTLY once across the whole file. With
    ``--phoneme-silence`` the line is split into phrases, so several
    ``synthesize`` calls contribute; if the concatenation offset is dropped and
    each unit's timings stay relative to itself, a second entry starts at 0 and
    this case fails while every per-unit assertion still holds. This is the
    cheapest CLI-visible signature of an offset regression, and the case also
    asserts how many inferences ran so it cannot decay into a single-unit run.

``tsv_format``
    The TSV writer is reached only from ``main.cpp``, so no unit test can see
    a change to its header or column count.

``missing_timing_is_diagnosed``
    When ``--output-timing`` is requested and no timing is available, the CLI
    must say so. Before this gate it wrote nothing and exited 0 -- byte-for-byte
    the same observable behaviour as the #652 bug, which is why the reporter
    could not tell a broken build from a model without a ``durations`` output.

``no_flag_writes_nothing``
    Guards the opposite direction: the writer must stay behind the flag.

Anti-vacuity: the fixture model must declare a ``durations`` output (byte scan)
and the binary must report it under ``--debug``. Without both checks this whole
file would pass on a model that cannot produce timing at all -- the same
"the gate goes green because its subject is absent" shape as #652 / #659.

Exit codes: 0 = all cases passed, 1 = at least one case failed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The reporter's text (issue #652), kept verbatim including the accent.
REPORTER_TEXT = "Hola, esta es una prueba de sincronización."
MULTI_SENTENCE_TEXT = "Hola mundo. Adios amigo. Buenos dias."
# Split into phrases by --phoneme-silence so the CLI runs several inferences.
MULTI_UNIT_TEXT = "Hola mundo. Adios amigo."

TSV_HEADER = (
    "phoneme\tstart_ms\tend_ms\tduration_ms\tstart\tend\tstart_frame\tend_frame"
)

# Rust/Go emit `ph_0` / `p0` instead of phoneme names (#656). The C++ path uses
# the PUA reverse map and must never degrade to that shape.
PLACEHOLDER_RE = re.compile(r"^(?:ph_\d+|p\d+)$")

BINARY_CANDIDATES = (
    "build/piper-plus",
    "build-full/piper-plus",
    "build/piper",
    "build-full/piper",
)

DEFAULT_MODEL = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"


class CaseFailure(Exception):
    """A single case failed. Message is reported verbatim."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise CaseFailure(message)


def find_binary(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for rel in BINARY_CANDIDATES:
        path = REPO_ROOT / rel
        if path.is_file():
            return path
    return None


def run_cli(
    binary: Path,
    model: Path,
    config: Path,
    text: str,
    workdir: Path,
    *,
    timing_path: Path | None = None,
    timing_format: str | None = None,
    debug: bool = False,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI exactly as a user would, feeding `text` on stdin."""
    cmd = [
        str(binary),
        "--model",
        str(model),
        "--config",
        str(config),
        "--language",
        "es",
        "--output_file",
        str(workdir / "out.wav"),
    ]
    if timing_path is not None:
        cmd += ["--output-timing", str(timing_path)]
    if timing_format is not None:
        cmd += ["--timing-format", timing_format]
    if debug:
        cmd.append("--debug")
    if extra_args:
        cmd += extra_args

    return subprocess.run(
        cmd,
        input=text + "\n",
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=300,
    )


def wav_info(path: Path) -> tuple[int, float]:
    with wave.open(str(path)) as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
    return rate, (frames / rate if rate else 0.0)


def assert_timing_json(payload: dict, wav: Path, *, label: str) -> list[dict]:
    """Shared structural assertions for one timing JSON document."""
    for key in ("phonemes", "total_duration_ms", "sample_rate", "frame_shift_ms"):
        _check(key in payload, f"{label}: timing JSON is missing key '{key}'")

    entries = payload["phonemes"]
    _check(
        isinstance(entries, list) and len(entries) > 0,
        f"{label}: 'phonemes' is empty -- the CLI wrote a timing file with no "
        "entries, which is the #652 symptom one layer further in",
    )

    for index, entry in enumerate(entries):
        for key in (
            "phoneme",
            "start_ms",
            "end_ms",
            "duration_ms",
            "start_frame",
            "end_frame",
        ):
            _check(key in entry, f"{label}: entry {index} is missing key '{key}'")
        name = entry["phoneme"]
        _check(
            isinstance(name, str) and name != "",
            f"{label}: entry {index} has an empty phoneme name",
        )
        _check(
            not PLACEHOLDER_RE.match(name),
            f"{label}: entry {index} phoneme is the placeholder '{name}' "
            "instead of a phoneme name (see #656 for the Rust/Go shape)",
        )
        _check(
            entry["start_ms"] >= 0.0,
            f"{label}: entry {index} has a negative start_ms {entry['start_ms']}",
        )
        _check(
            entry["end_ms"] >= entry["start_ms"],
            f"{label}: entry {index} ends before it starts "
            f"({entry['end_ms']} < {entry['start_ms']})",
        )

    starts = [entry["start_ms"] for entry in entries]
    for index in range(1, len(starts)):
        _check(
            starts[index] >= starts[index - 1],
            f"{label}: start_ms goes backwards at entry {index} "
            f"({starts[index]} < {starts[index - 1]})",
        )

    max_end = max(entry["end_ms"] for entry in entries)
    _check(
        abs(payload["total_duration_ms"] - max_end) < 1e-6,
        f"{label}: total_duration_ms {payload['total_duration_ms']} does not "
        f"match the largest end_ms {max_end}",
    )

    rate, duration_sec = wav_info(wav)
    _check(
        payload["sample_rate"] == rate,
        f"{label}: timing sample_rate {payload['sample_rate']} does not match "
        f"the WAV's {rate}",
    )
    _check(
        payload["frame_shift_ms"] > 0.0,
        f"{label}: frame_shift_ms must be positive, got "
        f"{payload['frame_shift_ms']}",
    )
    # One-sided only: timing is known to run SHORT of the real audio (#653),
    # so a lower bound would fail for reasons unrelated to this gate.
    _check(
        max_end <= duration_sec * 1000.0 + 1.0,
        f"{label}: timing extends to {max_end} ms, past the {duration_sec * 1000.0} "
        "ms of audio actually written",
    )
    return entries


# ── cases ────────────────────────────────────────────────────────────────


def case_single_sentence_json(binary: Path, model: Path, config: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        timing = workdir / "timing.json"
        proc = run_cli(
            binary, model, config, REPORTER_TEXT, workdir,
            timing_path=timing, debug=True,
        )
        log = proc.stdout + proc.stderr
        _check(proc.returncode == 0, f"CLI exited {proc.returncode}\n{log}")

        # Anti-vacuity: the run must have had timing to write in the first place.
        _check(
            "Model supports duration output" in log,
            "the fixture model did not report duration support, so this gate "
            f"would pass vacuously\n{log}",
        )
        _check(
            "Extracted timing for" in log,
            f"no 'Extracted timing for N phonemes' line in --debug output\n{log}",
        )
        # The reporter's missing line.
        _check(
            "Wrote phoneme timing to" in log,
            "the CLI never logged 'Wrote phoneme timing to ...' -- this is the "
            f"exact #652 symptom\n{log}",
        )
        _check(
            timing.is_file() and timing.stat().st_size > 0,
            "the timing file was not created (or is empty) even though "
            "--output-timing was passed -- this is issue #652",
        )
        entries = assert_timing_json(
            json.loads(timing.read_text(encoding="utf-8")),
            workdir / "out.wav",
            label="single_sentence_json",
        )
        return f"{len(entries)} phonemes, file {timing.stat().st_size} bytes"


def case_multi_unit_offsets(binary: Path, model: Path, config: Path) -> str:
    """Concatenation offsets survive a run with more than one inference.

    Plain multi-sentence text is NOT enough: the C++ text path phonemizes a
    whole stdin line into a single unit, so `Hola mundo. Adios amigo.` runs one
    inference and exercises no offset at all. Measured while building this
    gate: zeroing ConcatCursor::seconds()/frames() left that input's output
    byte-identical. `--phoneme-silence` splits the line into phrases, which is
    what actually produces several synthesize() calls from the CLI.

    The unit count is therefore asserted, not assumed -- otherwise this case
    would silently decay back into a duplicate of single_sentence_json.
    """
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        timing = workdir / "timing.json"
        proc = run_cli(
            binary, model, config, MULTI_UNIT_TEXT, workdir,
            timing_path=timing, debug=True,
            extra_args=["--phoneme-silence", "l", "0.3"],
        )
        log = proc.stdout + proc.stderr
        _check(proc.returncode == 0, f"CLI exited {proc.returncode}\n{log}")
        _check(timing.is_file(), "the timing file was not created (#652)")

        units = log.count("Extracted timing for")
        _check(
            units >= 2,
            f"only {units} inference(s) produced timing, so no concatenation "
            "offset was exercised and this case cannot detect an offset "
            "regression. --phoneme-silence must split the input into phrases.",
        )

        entries = assert_timing_json(
            json.loads(timing.read_text(encoding="utf-8")),
            workdir / "out.wav",
            label="multi_unit_offsets",
        )

        # The concatenation guard. Only the first unit may start at 0; if the
        # accumulated offset is dropped, every unit restarts from its own zero.
        # Verified by mutation: zeroing the cursor turns this count into 2.
        zeros = [i for i, e in enumerate(entries) if e["start_ms"] == 0.0]
        _check(
            len(zeros) == 1,
            f"{len(zeros)} entries start at 0 ms (indices {zeros}); exactly one "
            "may, otherwise per-unit timings were concatenated without applying "
            "the emitted-sample offset",
        )
        _check(
            zeros[0] == 0,
            f"the entry starting at 0 ms is at index {zeros[0]}, not the first",
        )
        return (
            f"{len(entries)} phonemes across {units} units, single zero offset"
        )


def case_tsv_format(binary: Path, model: Path, config: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        timing = workdir / "timing.tsv"
        proc = run_cli(
            binary, model, config, MULTI_SENTENCE_TEXT, workdir,
            timing_path=timing, timing_format="tsv",
        )
        log = proc.stdout + proc.stderr
        _check(proc.returncode == 0, f"CLI exited {proc.returncode}\n{log}")
        _check(timing.is_file(), "the TSV timing file was not created (#652)")

        lines = timing.read_text(encoding="utf-8").splitlines()
        _check(len(lines) >= 2, f"TSV has {len(lines)} line(s), expected a header + rows")
        _check(
            lines[0] == TSV_HEADER,
            f"TSV header changed.\n  expected: {TSV_HEADER!r}\n  actual:   {lines[0]!r}",
        )

        previous_start = -1.0
        max_start = 0.0
        for number, line in enumerate(lines[1:], start=2):
            columns = line.split("\t")
            _check(
                len(columns) == 8,
                f"TSV line {number} has {len(columns)} columns, expected 8",
            )
            _check(
                not PLACEHOLDER_RE.match(columns[0]),
                f"TSV line {number} phoneme is the placeholder '{columns[0]}'",
            )
            start, end = float(columns[1]), float(columns[2])
            _check(end >= start, f"TSV line {number} ends before it starts")
            _check(
                start >= previous_start,
                f"TSV line {number} start_ms {start} goes backwards",
            )
            previous_start = start
            max_start = max(max_start, start)

        # Anti-vacuity for the locale half of this case: a digit-group
        # separator only appears past 1000, so a run whose timings all stay
        # under a second would parse cleanly even from a locale-dependent
        # writer. MULTI_SENTENCE_TEXT is long enough; assert that it stayed so.
        _check(
            max_start >= 1000.0,
            f"the largest start_ms is {max_start}, below the 1000 ms digit-"
            "grouping boundary, so this case cannot detect a locale-dependent "
            "numeric format. Lengthen MULTI_SENTENCE_TEXT.",
        )
        return f"{len(lines) - 1} rows, header exact, max start {max_start:.0f} ms"


def case_missing_timing_is_diagnosed(binary: Path, model: Path, config: Path) -> str:
    """--output-timing with nothing to write must not fail silently.

    Empty input produces no synthesis, so `hasTimingInfo` stays false and the
    write path is skipped. Before this gate the CLI then produced no file, no
    message and exit 0 -- indistinguishable from the #652 bug for a user.
    """
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        timing = workdir / "timing.json"
        proc = run_cli(binary, model, config, "", workdir, timing_path=timing)
        log = proc.stdout + proc.stderr
        _check(proc.returncode == 0, f"CLI exited {proc.returncode}\n{log}")
        _check(
            not timing.exists(),
            "a timing file was created for input that produced no phonemes",
        )
        _check(
            "--output-timing" in log and "no phoneme timing" in log.lower(),
            "the CLI skipped the timing write without saying why. Requesting "
            "--output-timing and receiving neither a file nor a diagnostic is "
            "exactly what made #652 hard to identify.\n" + log,
        )
        return "diagnostic emitted, no file written"


def case_no_flag_writes_nothing(binary: Path, model: Path, config: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        stray = workdir / "timing.json"
        proc = run_cli(binary, model, config, "Hola mundo.", workdir)
        log = proc.stdout + proc.stderr
        _check(proc.returncode == 0, f"CLI exited {proc.returncode}\n{log}")
        _check(
            not stray.exists(),
            "a timing file appeared without --output-timing being passed",
        )
        _check(
            "Wrote phoneme timing to" not in log,
            f"the CLI logged a timing write without --output-timing\n{log}",
        )
        return "no timing side effects"


CASES = (
    ("single_sentence_json", case_single_sentence_json),
    ("multi_unit_offsets", case_multi_unit_offsets),
    ("tsv_format", case_tsv_format),
    ("missing_timing_is_diagnosed", case_missing_timing_is_diagnosed),
    ("no_flag_writes_nothing", case_no_flag_writes_nothing),
)


def model_declares_durations(model: Path) -> bool:
    """Byte-scan the ONNX for a ``durations`` output name.

    Cheap stand-in for parsing the graph: if the fixture model were replaced by
    one exported without the pre-ceil ``durations`` output, every case above
    would still be structurally satisfiable while testing nothing.
    """
    return b"durations" in model.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", help="path to the piper-plus CLI binary")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--config", help="model config JSON (default: <model>.json)")
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="exit 0 when the binary or model is absent (local convenience; CI "
        "must NOT pass this, or a missing build would silently pass the gate)",
    )
    args = parser.parse_args()

    binary = find_binary(args.binary)
    model = Path(args.model)
    config = Path(args.config) if args.config else Path(str(model) + ".json")

    missing = []
    if binary is None:
        missing.append(f"CLI binary (looked for {', '.join(BINARY_CANDIDATES)})")
    if not model.is_file():
        missing.append(f"model {model}")
    if not config.is_file():
        missing.append(f"model config {config}")

    if missing:
        detail = "; ".join(missing)
        if args.allow_skip:
            print(f"[skip] not available: {detail}")
            return 0
        print(f"ERROR: cannot run the CLI timing gate: {detail}", file=sys.stderr)
        print(
            "Build the CLI first (cmake --build build) or pass --allow-skip to "
            "make this a local no-op.",
            file=sys.stderr,
        )
        return 1

    if not model_declares_durations(model):
        print(
            f"ERROR: {model} does not declare a 'durations' output, so the "
            "timing gate cannot mean anything",
            file=sys.stderr,
        )
        return 1

    print(f"binary: {binary}")
    print(f"model:  {model}")

    failures = []
    executed = 0
    for name, case in CASES:
        try:
            detail = case(binary, model, config)
        except CaseFailure as failure:
            failures.append((name, str(failure)))
            print(f"  FAIL {name}: {failure}")
        except Exception as error:  # noqa: BLE001 - report, do not mask
            failures.append((name, f"{type(error).__name__}: {error}"))
            print(f"  ERROR {name}: {type(error).__name__}: {error}")
        else:
            print(f"  ok   {name}: {detail}")
        executed += 1

    if executed != len(CASES):
        print(
            f"ERROR: ran {executed} of {len(CASES)} cases",
            file=sys.stderr,
        )
        return 1

    if failures:
        print(
            f"\nFAILED: {len(failures)} of {len(CASES)} CLI timing cases",
            file=sys.stderr,
        )
        return 1

    print(f"\nOK: all {len(CASES)} CLI timing cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
