"""Integration tests for `python -m piper --json-input` JSONL phoneme_ids path.

PR #511 Phase 2 で `src/python_run/piper/__main__.py:260-317` に追加した
JSONL phoneme_ids 経路 (G2P を bypass する cross-runtime parity contract)
を CLI subprocess で end-to-end 検証する。 Rust / Go / C# / C++ / WASM の
類似テストと対称な coverage を担保する (cross-runtime parity 監査で本経路
の Python 単独 CLI test が欠落していたため Phase 2 で追加)。

test model `test/models/multilingual-test-medium.onnx` が存在しないと
collection 時点で SKIP される。
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
CONFIG = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx.json"

# tests/fixtures/audio-corpus/parity/phoneme_ids.jsonl の 1 行目と一致。
# fixture が更新されたら本テストも更新するよう byte-for-byte で pin。
CANONICAL_IDS = [1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2]


pytestmark = pytest.mark.skipif(
    not MODEL.exists(),
    reason=f"test model not available at {MODEL}",
)


def _run_piper(args, stdin_text: str | bytes, *, binary: bool = False):
    """Spawn `python -m piper <args>` with stdin piped."""
    kwargs = {
        "input": stdin_text,
        "capture_output": True,
        "timeout": 120,
        "check": False,
    }
    if not binary:
        kwargs["text"] = True
    return subprocess.run(  # noqa: S603 — sys.executable / args are trusted
        [sys.executable, "-m", "piper", *args],
        **kwargs,
    )


def _read_wav_meta(path: Path) -> dict:
    with wave.open(str(path), "rb") as wf:
        return {
            "channels": wf.getnchannels(),
            "sample_width": wf.getsampwidth(),
            "sample_rate": wf.getframerate(),
            "frames": wf.getnframes(),
        }


def test_json_input_writes_valid_wav_file(tmp_path):
    """`--json-input` で 1 行 JSONL を受け、 `--output_file` に WAV を書く."""
    out = tmp_path / "out.wav"
    line = json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0})
    proc = _run_piper(
        [
            "--model",
            str(MODEL),
            "--config",
            str(CONFIG),
            "--json-input",
            "--output_file",
            str(out),
        ],
        stdin_text=line + "\n",
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists(), proc.stderr
    meta = _read_wav_meta(out)
    assert meta["channels"] == 1
    assert meta["sample_width"] == 2
    assert meta["sample_rate"] == 22050
    assert meta["frames"] > 0


def test_json_input_to_stdout_sink(tmp_path):
    """`--output_file -` で stdout に RIFF/WAVE バイナリを書く.

    `__main__.py:269-273` の `config.output_file != "-"` 判定で
    single_output=None に落ち、 stdout sink ブランチに合流する。
    """
    line = json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0})
    proc = _run_piper(
        [
            "--model",
            str(MODEL),
            "--config",
            str(CONFIG),
            "--json-input",
            "--output_file",
            "-",
        ],
        stdin_text=(line + "\n").encode("utf-8"),
        binary=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert proc.stdout.startswith(b"RIFF"), (
        f"stdout must contain a WAV with a RIFF header; got {proc.stdout[:8]!r}"
    )
    assert proc.stdout[8:12] == b"WAVE"
    # data chunk size (44-byte standard header) と body の整合性を pin
    declared_size = struct.unpack_from("<I", proc.stdout, 40)[0]
    assert len(proc.stdout) - 44 == declared_size


def test_json_input_per_line_output_file_overrides_cli_flag(tmp_path):
    """JSONL の `output_file` field は CLI `--output_file` を上書きする contract.

    `__main__.py:292-295` (entry.output_file > output_dir > single_output) の
    precedence を Rust / Go / C# / C++ と対称に pin する。
    """
    cli_out = tmp_path / "should-not-be-written.wav"
    line_out = tmp_path / "per-line.wav"
    line = json.dumps(
        {
            "phoneme_ids": CANONICAL_IDS,
            "language_id": 0,
            "output_file": str(line_out),
        }
    )
    proc = _run_piper(
        [
            "--model",
            str(MODEL),
            "--config",
            str(CONFIG),
            "--json-input",
            "--output_file",
            str(cli_out),
        ],
        stdin_text=line + "\n",
    )
    assert proc.returncode == 0, proc.stderr
    assert line_out.exists(), "per-line output_file must be honoured"
    meta = _read_wav_meta(line_out)
    assert meta["frames"] > 0


def test_json_input_multi_line_directory_mode(tmp_path):
    """`--output_dir` mode で複数行 JSONL を受け、 1 行 1 WAV を書く."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    lines = [
        json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0}),
        json.dumps({"phoneme_ids": [1, 10, 2], "language_id": 0}),  # minimal
    ]
    proc = _run_piper(
        [
            "--model",
            str(MODEL),
            "--config",
            str(CONFIG),
            "--json-input",
            "--output_dir",
            str(out_dir),
        ],
        stdin_text="\n".join(lines) + "\n",
    )
    assert proc.returncode == 0, proc.stderr
    wavs = sorted(out_dir.glob("*.wav"))
    assert len(wavs) == 2, f"expected 2 WAVs, got {wavs}"
    for w in wavs:
        assert _read_wav_meta(w)["frames"] > 0
