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


class TestJsonInputSpeakerEmbedding:
    """`--json-input` JSONL entries の `speaker_embedding` 受理 (zero-shot parity).

    Rust / Go / C# は JSONL の `speaker_embedding` field を抽出して
    `synthesize_ids_to_raw` に渡す。 Python が同 field を無視すると
    cross-runtime zero-shot parity matrix から脱落する (Issue: this gap).
    本テストは subprocess + PiperVoice.load monkeypatch で
    `__main__.py:288` の forward を pin する。
    """

    @staticmethod
    def _write_mock_sitecustomize(tmp_path: Path, kwargs_dump: Path) -> Path:
        """sitecustomize.py: PiperVoice.load を差し替え、 kwargs を JSON dump する."""
        site_dir = tmp_path / "sitepkg"
        site_dir.mkdir()
        helper = site_dir / "sitecustomize.py"
        helper.write_text(
            f"""
import json
from pathlib import Path

import piper
from piper.inference_config import InferenceConfig as _IC

_DUMP = Path(r{str(kwargs_dump)!r})


class _FakeConfig:
    sample_rate = 22050
    num_symbols = 256
    num_speakers = 1


class _FakeVoice:
    def __init__(self):
        self.config = _FakeConfig()

    def synthesize_ids_to_raw(self, phoneme_ids, **kwargs):
        record = {{
            "phoneme_ids": list(phoneme_ids),
            "speaker_id": kwargs.get("speaker_id"),
            "language_id": kwargs.get("language_id"),
        }}
        emb = kwargs.get("speaker_embedding")
        if emb is None:
            record["speaker_embedding"] = None
        else:
            import numpy as _np
            arr = _np.asarray(emb)
            record["speaker_embedding"] = {{
                "is_ndarray": isinstance(emb, _np.ndarray),
                "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "first": float(arr.reshape(-1)[0]) if arr.size else None,
            }}
        _DUMP.write_text(json.dumps(record))
        # 16-bit PCM zeros, 100 samples
        return b"\\x00\\x00" * 100


def _fake_load(model_path, config_path=None, use_cuda=False):
    return _FakeVoice()


piper.PiperVoice.load = staticmethod(_fake_load)
# Re-bind the name imported into piper.__main__ if already imported
try:
    import piper.__main__ as _m
    _m.PiperVoice = piper.PiperVoice
except Exception:
    pass
""",
            encoding="utf-8",
        )
        return site_dir

    def _run_with_mock(
        self, tmp_path: Path, line: str, out_file: Path
    ) -> tuple[subprocess.CompletedProcess, dict]:
        kwargs_dump = tmp_path / "kwargs.json"
        site_dir = self._write_mock_sitecustomize(tmp_path, kwargs_dump)

        env = {
            **dict(__import__("os").environ),
            "PYTHONPATH": str(site_dir)
            + __import__("os").pathsep
            + __import__("os").environ.get("PYTHONPATH", ""),
        }
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "piper",
                "--model",
                str(MODEL),
                "--config",
                str(CONFIG),
                "--json-input",
                "--output_file",
                str(out_file),
            ],
            input=line + "\n",
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=env,
        )
        recorded = json.loads(kwargs_dump.read_text()) if kwargs_dump.exists() else {}
        return proc, recorded

    @pytest.mark.xfail(
        reason=(
            "Production bug: src/python_run/piper/__main__.py:288 does not "
            "extract entry['speaker_embedding'] from JSONL. To be fixed in "
            "a separate task; this xfail pins the expected forwarding contract."
        ),
        strict=True,
    )
    def test_speaker_embedding_field_extracted_from_jsonl(self, tmp_path):
        """JSONL entry の `speaker_embedding` (192-dim) が voice 呼び出しに forward される."""
        out = tmp_path / "out.wav"
        embedding = [0.0] * 192
        line = json.dumps(
            {
                "phoneme_ids": CANONICAL_IDS,
                "speaker_embedding": embedding,
            }
        )
        proc, recorded = self._run_with_mock(tmp_path, line, out)
        assert proc.returncode == 0, proc.stderr
        assert recorded.get("phoneme_ids") == CANONICAL_IDS
        emb_record = recorded.get("speaker_embedding")
        assert emb_record is not None, (
            "speaker_embedding field was not forwarded to voice call; "
            "JSON input path drops entry['speaker_embedding']"
        )
        assert emb_record["is_ndarray"] is True
        # flatten 後 192 要素であること (shape は (192,) または (1,192) を許容)
        flat_size = 1
        for d in emb_record["shape"]:
            flat_size *= d
        assert flat_size == 192, (
            f"expected 192 elements, got shape {emb_record['shape']}"
        )
        assert emb_record["first"] == 0.0

    def test_speaker_embedding_missing_field_uses_speaker_id(self, tmp_path):
        """speaker_embedding 未指定なら speaker_id 経路を維持 (後方互換)."""
        out = tmp_path / "out.wav"
        line = json.dumps(
            {
                "phoneme_ids": CANONICAL_IDS,
                "speaker_id": 0,
                "language_id": 0,
            }
        )
        proc, recorded = self._run_with_mock(tmp_path, line, out)
        assert proc.returncode == 0, proc.stderr
        assert recorded.get("speaker_id") == 0
        assert recorded.get("speaker_embedding") is None


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
