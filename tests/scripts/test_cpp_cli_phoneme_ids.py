"""Integration tests for the C++ piper CLI `--json-input` phoneme_ids path.

PR #511 Phase 2 で `src/cpp/main.cpp:processLine` に追加した JSONL
phoneme_ids 抽出経路 (and the new `piper::phonemeIdsToWavFile` helper) を、
build 済みの `./build/piper` バイナリを subprocess で起動して end-to-end
検証する。 C++ gtest 側 (test_streaming_raw_phonemes.cpp) が API レベル
の単体テストを担当する一方、 本ファイルは CLI レイヤー (3 つの outputType
分岐 / text vs phoneme_ids 排他 / error path) を spawn-based で pin する。

CI で C++ 環境が無いランナー (Python-only matrix) では本テストは collection
段階で SKIP される (`./build/piper` の存在チェック)。
"""

from __future__ import annotations

import json
import struct
import subprocess
import wave
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BIN = REPO_ROOT / "build" / "piper"
MODEL = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
CONFIG = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx.json"

# `^ a _ i _ u _ e _ o _ $` — same canonical fixture as
# tests/fixtures/audio-corpus/parity/phoneme_ids.jsonl, kept inline so the
# integration test does not silently drift if the fixture changes.
CANONICAL_IDS = [1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2]


pytestmark = pytest.mark.skipif(
    not BIN.exists() or not MODEL.exists(),
    reason=(
        "build/piper or test model not found — "
        "run `cmake --build build --target piper` first"
    ),
)


def _run_cli(args, stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — args/BIN are trusted local paths
        [str(BIN), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _read_wav_meta(path: Path) -> dict:
    with wave.open(str(path), "rb") as wf:
        return {
            "channels": wf.getnchannels(),
            "sample_width": wf.getsampwidth(),
            "sample_rate": wf.getframerate(),
            "frames": wf.getnframes(),
        }


def test_cli_phoneme_ids_to_file_outputs_valid_wav(tmp_path):
    out = tmp_path / "out.wav"
    line = json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0})
    proc = _run_cli(
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
    assert out.exists()
    meta = _read_wav_meta(out)
    assert meta["channels"] == 1
    assert meta["sample_width"] == 2
    assert meta["sample_rate"] == 22050
    assert meta["frames"] > 0


def test_cli_phoneme_ids_to_stdout(tmp_path):
    line = json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0})
    # `-` is shorthand for stdout. text=False so we can capture raw bytes.
    proc = subprocess.run(  # noqa: S603 — args/BIN are trusted local paths
        [
            str(BIN),
            "--model",
            str(MODEL),
            "--config",
            str(CONFIG),
            "--json-input",
            "--output_file",
            "-",
        ],
        input=(line + "\n").encode("utf-8"),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    # First 4 bytes must be "RIFF" — the WAV magic
    assert proc.stdout.startswith(b"RIFF"), (
        f"stdout must contain a WAV with a RIFF header; got {proc.stdout[:8]!r}"
    )
    # data chunk size declared in WAV header should match payload tail
    chunk_size = struct.unpack_from("<I", proc.stdout, 40)[0]
    assert len(proc.stdout) - 44 == chunk_size


def test_cli_phoneme_ids_takes_precedence_over_text(tmp_path):
    """If both `phoneme_ids` and `text` are present in one JSONL line,
    the new C++ phoneme_ids path must win (G2P bypass)."""
    out = tmp_path / "out.wav"
    line = json.dumps(
        {
            "phoneme_ids": CANONICAL_IDS,
            "text": "this text would otherwise drive G2P",
            "language_id": 0,
        }
    )
    proc = _run_cli(
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
    assert out.exists()
    # Strategy A short-text padding still applies; the duration should be
    # consistent with the 12-ID input, not the 8-word English text path.
    meta = _read_wav_meta(out)
    assert meta["frames"] > 0
    # 12 IDs × hop_length / sample_rate is well below 5 seconds. If the text
    # path were used instead, the synthesized audio would be 1-2 seconds longer.
    duration_sec = meta["frames"] / meta["sample_rate"]
    assert duration_sec < 3.0, f"unexpected duration {duration_sec:.2f}s"


def test_cli_phoneme_ids_to_directory(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    line = json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0})
    proc = _run_cli(
        [
            "--model",
            str(MODEL),
            "--config",
            str(CONFIG),
            "--json-input",
            "--output_dir",
            str(out_dir),
        ],
        stdin_text=line + "\n",
    )
    assert proc.returncode == 0, proc.stderr
    wavs = list(out_dir.glob("*.wav"))
    assert len(wavs) == 1
    meta = _read_wav_meta(wavs[0])
    assert meta["frames"] > 0


def test_cli_phoneme_ids_per_line_output_file_overrides_cli_flag(tmp_path):
    """JSONL entry's `output_file` field must take precedence over the
    CLI `--output_file` flag, mirroring the Rust / C# / Go contract."""
    cli_out = tmp_path / "should-not-be-written.wav"
    line_out = tmp_path / "per-line.wav"
    line = json.dumps(
        {
            "phoneme_ids": CANONICAL_IDS,
            "language_id": 0,
            "output_file": str(line_out),
        }
    )
    proc = _run_cli(
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


def test_cli_phoneme_ids_missing_field_falls_back_to_text_requirement(tmp_path):
    """A JSONL line with neither `phoneme_ids` nor `text` should fail
    because the text field is still required when phoneme_ids is absent.
    Captures the contract that the new code path does not break the legacy
    text-only mode."""
    out = tmp_path / "out.wav"
    line = json.dumps({"language_id": 0})  # neither phoneme_ids nor text
    proc = _run_cli(
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
    assert proc.returncode != 0, "missing both fields must fail"
    assert not out.exists() or out.stat().st_size == 0


def test_cli_phoneme_ids_multi_line_stdin_directory_mode(tmp_path):
    """Multiple JSONL lines in directory-output mode should produce one
    WAV per utterance."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    lines = [
        json.dumps({"phoneme_ids": CANONICAL_IDS, "language_id": 0}),
        json.dumps({"phoneme_ids": [1, 10, 2], "language_id": 0}),  # minimal
    ]
    proc = _run_cli(
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
        meta = _read_wav_meta(w)
        assert meta["frames"] > 0
