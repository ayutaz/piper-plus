#!/usr/bin/env python3
"""End-to-end gate: the C++ CLI strips control characters before it reads a text.

Contract: ``docs/spec/input-sanitize-contract.toml`` (runtime ``cpp``).
Cases: ``tests/fixtures/g2p/input_sanitize_cases.json`` (the Spanish word
cases and the pipeline cases), plus CLI-only cases below.

``main.cpp`` has no test-reachable entry point (see
``scripts/test_cpp_cli_timing.py``), so this runs the built binary. Each case
synthesizes the clean and the dirty text with ``noise_scale`` and ``noise_w``
at 0 and compares the number of frames in the WAV files.

Inputs, each a separate path in ``processLine``:

``--text``
    A command-line argument cannot hold a NUL, so DEL (removed by the same
    rule) stands in for it.
``stdin``
    One line of plain text, NUL included.
``jsonl``
    ``--json-input`` with the text as a JSON string, NUL included.

CLI-only cases, which fail if ``main.cpp`` reads the raw line:

``custom_dict``
    The custom dictionary is applied before phonemizing; a control character
    inside the word made it miss.
``ssml_after_del``
    SSML is detected from the line; a control character in front of
    ``<speak>`` made the markup read as words.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "g2p" / "input_sanitize_cases.json"
DEFAULT_MODEL = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
BINARY_CANDIDATES = ("build/piper-plus", "build-full/piper-plus", "build/piper")


def find_binary(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for rel in BINARY_CANDIDATES:
        path = REPO_ROOT / rel
        if path.is_file():
            return path
    return None


def load_cases() -> list[tuple[str, str, str]]:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = [
        (f"es {c['control']}", c["clean"], c["dirty"])
        for c in doc["word_cases"]
        if c["language"] == "es"
    ]
    cases += [(c["name"], c["clean"], c["dirty"]) for c in doc["pipeline_cases"]]
    if len(cases) < 6:
        raise SystemExit(f"{FIXTURE} has too few Spanish / pipeline cases")
    return cases


class Cli:
    def __init__(self, binary: Path, model: Path, workdir: Path) -> None:
        self.binary = binary
        self.model = model
        self.workdir = workdir
        self.count = 0

    def frames(self, text: str, mode: str, extra: list[str] | None = None) -> int:
        self.count += 1
        out = self.workdir / f"out-{self.count}.wav"
        cmd = [
            str(self.binary),
            "--model",
            str(self.model),
            "--config",
            str(self.model) + ".json",
            "--language",
            "es",
            "--noise_scale",
            "0",
            "--noise_w",
            "0",
            "--no-warmup",
            "-q",
            "--output_file",
            str(out),
            *(extra or []),
        ]
        stdin: bytes | None = None
        if mode == "text":
            cmd += ["--text", text.replace("\0", "\x7f")]
        elif mode == "stdin":
            stdin = text.encode("utf-8") + b"\n"
        elif mode == "jsonl":
            cmd.append("--json-input")
            stdin = json.dumps({"text": text}).encode("utf-8") + b"\n"
        else:
            raise ValueError(mode)
        proc = subprocess.run(cmd, input=stdin, capture_output=True, timeout=120, check=False)
        if proc.returncode != 0 or not out.is_file():
            raise RuntimeError(
                f"CLI failed (rc={proc.returncode}) for {text!r} [{mode}]:\n"
                + proc.stderr.decode("utf-8", "replace")[-2000:]
            )
        with wave.open(str(out), "rb") as w:
            return w.getnframes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--binary", help="path to the piper-plus CLI")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    args = parser.parse_args()

    binary = find_binary(args.binary)
    model = Path(args.model)
    if binary is None or not model.is_file():
        print(f"FAIL: binary ({args.binary}) or model ({model}) not found", file=sys.stderr)
        return 1

    failures: list[str] = []
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        cli = Cli(binary, model, workdir)
        dict_path = workdir / "dict.json"
        dict_path.write_text(
            '{"version":"2.0","entries":{"hola":{"pronunciation":"pero","priority":9}}}',
            encoding="utf-8",
        )

        def compare(label: str, clean: str, dirty: str, mode: str, extra=None) -> None:
            nonlocal checked
            checked += 1
            want = cli.frames(clean, mode, extra)
            got = cli.frames(dirty, mode, extra)
            if got != want:
                failures.append(f"{label} [{mode}]: {got} frames, want {want} ({dirty!r})")

        for label, clean, dirty in load_cases():
            for mode in ("text", "stdin", "jsonl"):
                compare(label, clean, dirty, mode)

        dict_args = ["--custom-dict", str(dict_path)]
        for mode in ("text", "stdin", "jsonl"):
            compare("custom_dict", "hola", "ho\0la", mode, dict_args)
        if cli.frames("hola", "text", dict_args) == cli.frames("hola", "text"):
            failures.append("custom_dict: the dictionary did not change the reading of 'hola'")

        # SSML is detected for --text and stdin only (not for --json-input).
        for mode in ("text", "stdin"):
            compare("ssml_after_del", "<speak>hola</speak>", "\x7f<speak>hola</speak>", mode)

    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"{checked - len(failures)}/{checked} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
