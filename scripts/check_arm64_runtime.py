"""Run a release archive in an emulated Debian ARM64 consumer container.

No build directories or host libraries are mounted. Logs, exact Docker commands,
input hashes, image identity and parsed WAV results are retained in --output-dir.
QEMU execution is a compatibility check and does not measure device performance.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT = "こんにちは、今日はいい天気ですね。"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_wav(path: Path) -> dict:
    """Require a nonempty mono PCM16 waveform with nonzero audio samples."""
    with wave.open(str(path), "rb") as wav:
        rate, frames = wav.getframerate(), wav.getnframes()
        if (
            wav.getnchannels() != 1
            or wav.getsampwidth() != 2
            or rate != 22050
            or frames <= 0
        ):
            raise ValueError("Expected nonempty mono 22050 Hz PCM16 WAV")
        samples = array.array("h", wav.readframes(frames))
        if len(samples) != frames or not any(samples):
            raise ValueError("Empty, truncated or silent waveform")
    return {
        "sample_rate": rate,
        "frames": frames,
        "duration_seconds": frames / rate,
        "sha256": sha256(path),
    }


def run_logged(command: list[str], output: Path, label: str) -> str:
    """Retain commands and both streams, including on error or timeout."""
    (output / f"{label}.command.json").write_text(
        json.dumps(command, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        for stream in ("stdout", "stderr"):
            value = getattr(exc, stream) or ""
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            (output / f"{label}.{stream}.log").write_text(value, encoding="utf-8")
        raise ValueError(f"{label} timed out") from exc
    (output / f"{label}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (output / f"{label}.stderr.log").write_text(result.stderr, encoding="utf-8")
    (output / f"{label}.exit.txt").write_text(
        str(result.returncode) + "\n", encoding="utf-8"
    )
    if result.returncode:
        raise ValueError(
            f"{label} failed with exit {result.returncode}; see {output}/{label}.stderr.log"
        )
    return result.stdout


def check_runtime(
    archive: Path, model: Path, config: Path, suite: str, output: Path
) -> dict:
    """Test --help and Japanese inference using one exact, unmodified archive."""
    for path in (archive, model, config):
        if not path.is_file():
            raise ValueError(f"Missing input: {path}")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "output.wav").exists() or (output / "result.json").exists():
        raise ValueError(f"Use a fresh output directory: {output}")
    inputs = {
        "archive": sha256(archive),
        "model": sha256(model),
        "config": sha256(config),
    }
    image = f"debian:{suite}"
    run_logged(["docker", "pull", "--platform", "linux/arm64", image], output, "pull")
    identity = json.loads(
        run_logged(
            ["docker", "image", "inspect", "--platform", "linux/arm64", image],
            output,
            "image",
        )
    )[0]
    if identity["Architecture"] != "arm64":
        raise ValueError("Consumer image must be ARM64")
    script = r"""
set -eu
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive
if [ "$1" = bullseye ]; then
  sed -i 's|deb.debian.org/debian-security|archive.debian.org/debian-security|g' /etc/apt/sources.list
fi
apt-get update
apt-get install --yes --no-install-recommends libstdc++6 libgcc-s1
uname -m
getconf GNU_LIBC_VERSION
tar xzf /input/archive.tar.gz -C /tmp
mkdir /tmp/consumer
cd /tmp/consumer
ldd /tmp/piper-plus/bin/piper-plus
/tmp/piper-plus/bin/piper-plus --help
echo PIPER_HELP_OK
/tmp/piper-plus/bin/piper-plus --model /model/model.onnx --config /model/model.onnx.json --language ja --text "$2" --output_file /out/output.wav
echo PIPER_SYNTH_OK
"""
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--ulimit",
        "core=0",
    ]
    for source, target, readonly in (
        (archive, "/input/archive.tar.gz", True),
        (model, "/model/model.onnx", True),
        (config, "/model/model.onnx.json", True),
        (output, "/out", False),
    ):
        mount = f"type=bind,source={source.resolve()},target={target}"
        command.extend(["--mount", mount + (",readonly" if readonly else "")])
    command.extend([image, "sh", "-ec", script, "arm64-smoke", suite, TEXT])
    stdout = run_logged(command, output, "container")
    if "PIPER_HELP_OK" not in stdout or "PIPER_SYNTH_OK" not in stdout:
        raise ValueError("Missing successful --help/inference markers")
    report = {
        "suite": suite,
        "platform": "linux/arm64",
        "emulated": True,
        "image_id": identity["Id"],
        "image_digests": identity.get("RepoDigests", []),
        "input_sha256": inputs,
        "text": TEXT,
        "help": "success",
        "synthesis": "success",
        "wav": check_wav(output / "output.wav"),
        "scope": "Debian userland compatibility under QEMU; no Raspberry Pi hardware or performance claim",
    }
    (output / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--suite", required=True, choices=("bullseye", "bookworm", "trixie")
    )
    parser.add_argument(
        "--model", type=Path, default=ROOT / "test/models/multilingual-test-medium.onnx"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "test/models/multilingual-test-medium.onnx.json",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = check_runtime(
            args.archive, args.model, args.config, args.suite, args.output_dir
        )
    except (OSError, ValueError, wave.Error, EOFError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
