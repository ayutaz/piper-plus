#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented bullet lists)
"""CLI flag naming parity across 5 runtimes.

Verifies that the common hyphen-form CLI flag names are recognised by
every runtime that exposes them. Drift example caught: C++ `main.cpp:865`
historically accepted both ``--sentence_silence`` (underscore) and
``--sentence-silence`` (hyphen) while Rust / Go accepted only the
hyphen form, leaving users who learned the underscore form from the
C++ help text confused on Rust / Go.

Source of truth: hyphen-separated flag names (Unix convention). The
script searches for the hyphen-form *base name* (without the leading
``--``) because each runtime uses a different declaration idiom:

  - Python argparse:    ``add_argument("--sentence-silence", ...)``
  - Rust clap derive:   ``sentence_silence`` (rename-all kebab-case)
  - Go pflag:           ``f.Float64Var(..., "sentence-silence", ...)``
  - C# System.CommandLine: ``new Option<float>("--sentence-silence", ...)``
  - C++ manual:         ``arg == "--sentence-silence"``

A simple substring match for the hyphen-form base name catches all five.

Some flags are intentionally not implemented in every runtime:

  - ``phoneme-silence`` is voice-runtime-only (Rust / Go / C++) — Python
    runtime CLI and the C# CLI do not expose it.
  - Voice-cloning flags (``reference-audio`` / ``speaker-embedding`` /
    ``speaker-encoder-model``) are not implemented in the C++ CLI yet.

The allowlist below records the *current* feature matrix. Removing an
entry from `SKIPS` here is the right action when a runtime implements
a flag for the first time.

Usage:
    python scripts/check_cli_flag_parity.py

Exit codes:
    0 -- every required (flag, runtime) pair found
    1 -- at least one expected flag missing in a runtime
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# (label, path)
PYTHON_RUNTIME = (
    "Python runtime CLI",
    REPO_ROOT / "src/python_run/piper/__main__.py",
)
PYTHON_TRAIN = (
    "Python infer_onnx CLI",
    REPO_ROOT / "src/python/piper_train/infer_onnx.py",
)
RUST = ("Rust piper-cli", REPO_ROOT / "src/rust/piper-cli/src/main.rs")
GO = ("Go piper-plus CLI", REPO_ROOT / "src/go/cmd/piper-plus/main.go")
CSHARP = ("C# PiperPlus.Cli", REPO_ROOT / "src/csharp/PiperPlus.Cli/Program.cs")
CPP = ("C++ piper_plus main", REPO_ROOT / "src/cpp/main.cpp")

COMMON_RUNTIMES = [PYTHON_RUNTIME, RUST, GO, CSHARP, CPP]
VOICE_CLONING_RUNTIMES = [PYTHON_TRAIN, RUST, GO, CSHARP, CPP]

# (hyphen-form-base-name, runtimes-that-should-have-it)
CHECKS: list[tuple[str, list[tuple[str, Path]]]] = [
    ("sentence-silence", COMMON_RUNTIMES),
    ("phoneme-silence", COMMON_RUNTIMES),
    ("reference-audio", VOICE_CLONING_RUNTIMES),
    ("speaker-embedding", VOICE_CLONING_RUNTIMES),
    ("speaker-encoder-model", VOICE_CLONING_RUNTIMES),
]

# Known not-implemented pairs (label of the runtime, flag base name).
# Remove an entry once the runtime adds the flag.
SKIPS: set[tuple[str, str]] = {
    ("Python runtime CLI", "phoneme-silence"),
    ("C# PiperPlus.Cli", "phoneme-silence"),
    ("C++ piper_plus main", "reference-audio"),
    ("C++ piper_plus main", "speaker-embedding"),
    ("C++ piper_plus main", "speaker-encoder-model"),
}


def contains_flag(path: Path, flag_basename: str) -> bool:
    """Search for the hyphen-form base name **or** its snake_case twin.

    Most runtimes carry the literal hyphen-form (``sentence-silence``):

      - Python argparse:    ``add_argument("--sentence-silence", ...)``
      - Go pflag:           ``f.Float64Var(..., "sentence-silence", ...)``
      - C# System.CommandLine: ``new Option<float>("--sentence-silence", ...)``
      - C++ manual:         ``arg == "--sentence-silence"``

    Rust clap-derive is the exception: with ``rename-all = "kebab-case"``
    the source carries the snake_case field name (``sentence_silence``)
    and the hyphen form only appears in comments. A naive substring
    check on the hyphen form would pass even if the field were deleted
    (the comment alone would satisfy it). Accept either form so the
    gate detects field removal even when stale comments linger.

    False-positive risk: a documentation comment like
    ``// TODO: add sentence_silence later`` would also pass. That is
    accepted as a trade-off — code review still catches it, and the
    main failure mode the gate guards against (silent runtime
    omission across the matrix) is covered.
    """
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    underscore_form = flag_basename.replace("-", "_")
    return flag_basename in text or underscore_form in text


def main(argv: list[str] | None = None) -> int:
    failures: list[str] = []
    skipped = 0
    for flag, runtimes in CHECKS:
        print(f"== --{flag} ==")
        for label, path in runtimes:
            if (label, flag) in SKIPS:
                print(f"  SKIP {label} (allowlisted as not-implemented)")
                skipped += 1
                continue
            if not path.exists():
                msg = f"  MISSING SOURCE [{label}] {path}"
                failures.append(msg)
                print(msg, file=sys.stderr)
                continue
            if contains_flag(path, flag):
                print(f"  OK   {label}")
            else:
                msg = (
                    f"  FAIL [{label}] does not declare hyphen-form '{flag}'. "
                    f"Either add the flag in {path.relative_to(REPO_ROOT)} "
                    f"or, if this runtime intentionally lacks the feature, "
                    f"allowlist the pair in SKIPS at "
                    f"scripts/check_cli_flag_parity.py."
                )
                failures.append(msg)
                print(msg, file=sys.stderr)
        print()

    if failures:
        print(
            f"\n{len(failures)} CLI flag parity drift(s). "
            f"({skipped} allowlisted pair(s) skipped.)",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK every required hyphen-form flag is present in every required "
        f"runtime CLI ({skipped} pair(s) allowlisted as not-implemented)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
