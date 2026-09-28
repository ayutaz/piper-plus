#!/usr/bin/env python3
"""Every runtime must emit timing output with LF, on every platform.

``docs/spec/phoneme-timing-contract.toml`` pins LF --
``[output_formats.tsv].row_separator = "\\n"`` and
``[output_formats.srt].cue_format`` -- so a runtime that lets the platform pick
the separator produces files that byte-differ between Windows and everything
else, for the same model and the same input.

Two runtimes did exactly that, and neither test suite noticed:

* C# used ``StreamWriter.WriteLine`` without assigning ``NewLine``, whose
  default is ``Environment.NewLine`` (CRLF on Windows). The tests normalised
  the difference away -- ``srt.Replace("\\r\\n", "\\n")`` and
  ``lines[N].TrimEnd('\\r')`` -- so the ``windows-latest`` job stayed green.
* The C++ CLI opened the timing file without ``std::ios::binary``, so MSVC's
  text mode translated every ``\\n`` into ``\\r\\n``. The CLI E2E gate excludes
  Windows, so nothing checked the bytes there at all.

A unit test cannot cover this on its own: ``Environment.NewLine`` is already
LF on Linux and macOS, so an output-byte assertion passes on the developer's
machine whether or not the code is correct. What makes the defect detectable
is a check on the MECHANISM -- does the code force LF -- which is what this
gate does, statically, on every platform.

Exit codes: 0 = every runtime forces LF, 1 = at least one relies on the
platform default.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Per runtime: the file that writes timing output, the idiom that forces LF,
# and -- where the platform default is the trap -- a pattern that must NOT
# appear on its own.
RUNTIMES: dict[str, dict[str, object]] = {
    "python": {
        "file": "src/python_run/piper_plus/timing.py",
        # str.join("\n") / f-string literals: the separator is in the source.
        "requires": [r'"\\n"'],
        "forbids": [],
        "note": "LF appears as a literal in the join/format calls",
    },
    "rust": {
        "file": "src/rust/piper-core/src/timing.rs",
        "requires": [r'\\n'],
        "forbids": [],
        "note": "LF is a literal inside write!/format! strings",
    },
    "go": {
        "file": "src/go/piperplus/timing.go",
        "requires": [r'\\n'],
        "forbids": [],
        "note": "LF is a literal; Go has no platform-dependent newline",
    },
    "js": {
        "file": "src/wasm/openjtalk-web/src/timing.js",
        "requires": [r'\\n'],
        "forbids": [r"require\('os'\)", r'os\.EOL'],
        "note": "LF is a literal; os.EOL would be platform-dependent",
    },
    "csharp": {
        "file": "src/csharp/PiperPlus.Core/Inference/TimingWriter.cs",
        # StreamWriter.NewLine defaults to Environment.NewLine, so the
        # assignment is what makes the output platform-independent.
        "requires": [r'writer\.NewLine = "\\n";'],
        "forbids": [r"Environment\.NewLine"],
        "note": "StreamWriter.NewLine must be assigned, not defaulted",
    },
    "cpp": {
        "file": "src/cpp/main.cpp",
        # MSVC text mode rewrites '\n' as "\r\n" on write.
        "requires": [r"ofstream timingFile\(.*ios::binary"],
        "forbids": [],
        "note": "the timing ofstream must be opened in binary mode",
    },
}

# C# creates four writers; every one of them has to go through the factory,
# and three-of-four would only show up on Windows.
CSHARP_WRITER_FILE = "src/csharp/PiperPlus.Core/Inference/TimingWriter.cs"
CSHARP_WRITER_CREATION = re.compile(r"new StreamWriter\(")
CSHARP_FORCE_LF_CALL = re.compile(r"ForceLf\(\s*new StreamWriter\(|ForceLf\(new StreamWriter\(")


def strip_comments(source: str, runtime: str) -> str:
    """Remove line comments so a forbidden idiom named in prose is not a hit."""
    if runtime in {"csharp", "cpp", "rust", "go", "js"}:
        return re.sub(r"//[^\n]*", "", source)
    if runtime == "python":
        source = re.sub(r'"""(?:.|\n)*?"""', "", source)
        return re.sub(r"#[^\n]*", "", source)
    return source


def main() -> int:
    failures: list[str] = []

    for runtime, spec in sorted(RUNTIMES.items()):
        rel = str(spec["file"])
        path = REPO_ROOT / rel
        if not path.is_file():
            failures.append(f"{runtime}: file not found: {rel}")
            continue
        source = path.read_text(encoding="utf-8", errors="replace")

        # ANY of the accepted spellings is enough: a runtime writes the
        # literal one way, not every way.
        accepted = [str(x) for x in spec["requires"]]  # type: ignore[union-attr]
        if accepted and not any(re.search(x, source) for x in accepted):
            failures.append(
                f"{runtime} ({rel}): none of the LF-forcing idioms "
                f"{accepted} appear -- {spec['note']}"
            )

        # Forbidden idioms are checked against code only. The C# fix's own doc
        # comment names Environment.NewLine to explain what it replaces, and a
        # naive scan flagged that comment as the defect.
        code = strip_comments(source, runtime)
        for pattern in spec["forbids"]:  # type: ignore[union-attr]
            if re.search(str(pattern), code):
                failures.append(
                    f"{runtime} ({rel}): uses {pattern!r} in code, which "
                    "resolves to the platform newline"
                )

    # Every C# writer must be wrapped, not just the first one.
    csharp = (REPO_ROOT / CSHARP_WRITER_FILE).read_text(encoding="utf-8", errors="replace")
    created = len(CSHARP_WRITER_CREATION.findall(csharp))
    wrapped = len(CSHARP_FORCE_LF_CALL.findall(csharp))
    # The factory's own signature mentions StreamWriter but does not construct
    # one, so `created` counts only real construction sites.
    if created != wrapped:
        failures.append(
            f"csharp ({CSHARP_WRITER_FILE}): {created} StreamWriter "
            f"construction site(s) but {wrapped} wrapped in ForceLf; an "
            "unwrapped writer emits CRLF on Windows only"
        )

    if failures:
        print(
            f"ERROR: {len(failures)} runtime newline issue(s):",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nThe contract pins LF for every output format. A runtime that "
            "relies on the platform default produces files that byte-differ "
            "on Windows, and a unit test on Linux/macOS cannot see it.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: all {len(RUNTIMES)} runtimes force LF in timing output "
        f"({wrapped}/{created} C# writers wrapped)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
