"""Run real CLI subprocesses and inspect WAV and timing artifacts."""

import argparse
import json
import subprocess
import tempfile
import wave
from pathlib import Path


def run(runtime, executable, model, root):
    command = (
        ["dotnet", str(executable)]
        if executable.suffix == ".dll"
        else [str(executable)]
    )
    base = command + ["--model", str(model), "--config", str(model) + ".json"]
    record = {"phoneme_ids": [1] + [10, 0, 11, 0] * 8 + [2]}
    stdin = (json.dumps(record) + "\n") * 2

    def invoke(args, text=stdin):
        result = subprocess.run(
            base + args,
            input=text,
            stdin=subprocess.DEVNULL if text is None else None,
            text=True,
            capture_output=True,
            check=False,
            cwd=root,
            timeout=120,
        )
        if result.returncode:
            raise RuntimeError(
                f"CLI failed ({result.returncode}): {result.stderr}\n{result.stdout}"
            )

    def check_wav(path):
        with wave.open(str(path)) as wav:
            assert wav.getnframes() > 0, f"empty WAV: {path}"

    if runtime == "rust":
        invoke([])
        for name in ("1.wav", "2.wav"):
            check_wav(root / name)
        # No model duration requirement: the configured boundary causes actual
        # separate inference and an exact zero-filled inter-phrase gap.
        invoke(
            ["--output-file", "silence.wav", "--phoneme-silence", "a 0.25"],
            json.dumps(record) + "\n",
        )
        with wave.open(str(root / "silence.wav")) as wav:
            assert b"\0\0" * 4000 in wav.readframes(wav.getnframes()), (
                "missing requested silence gap"
            )
    else:
        for mode in ("stdin", "batch") if runtime == "go" else ("stdin",):
            if mode == "batch":
                (root / "batch.jsonl").write_text(stdin, encoding="utf-8")
            for fmt in ("json", "tsv", "srt"):
                prefix = f"{mode}-{fmt}"
                args = [
                    "--output-dir",
                    str(root),
                    "--output-timing",
                    str(root / f"{prefix}.{fmt}"),
                    "--timing-format",
                    fmt,
                ]
                if runtime == "csharp":
                    args += ["--json-input"]
                if mode == "batch":
                    args += ["--batch", str(root / "batch.jsonl")]
                invoke(args, None if mode == "batch" else stdin)
                for index in (1, 2):
                    timing = root / f"{prefix}_{index:03d}.{fmt}"
                    assert timing.stat().st_size > 0, f"missing timing: {timing}"
                    if fmt == "json":
                        data = json.loads(timing.read_text(encoding="utf-8"))
                        assert data["phonemes"] and data["sample_rate"] == 16000
                    check_wav(
                        root
                        / (
                            f"{index - 1}.wav"
                            if runtime == "csharp"
                            else f"line_{index:03d}.wav"
                        )
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=["rust", "go", "csharp"], required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(
        prefix=f"piper-{args.runtime}-consumer-"
    ) as directory:
        run(
            args.runtime,
            args.executable.resolve(),
            args.model.resolve(),
            Path(directory),
        )
    print(f"{args.runtime}: CLI WAV/timing consumer checks passed")


if __name__ == "__main__":
    main()
