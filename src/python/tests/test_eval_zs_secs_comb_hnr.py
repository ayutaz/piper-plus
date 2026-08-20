"""eval_zs_secs への comb_hnr ブロック統合テスト (v3 スキーマへの field 追加).

背景 (docs/design/zero-shot-v10b-residual-noise-diagnosis.md §1/§7):
A3 (1-3kHz 調波間ノイズ = がびがびの主犯) の直接測定 comb-HNR を、v10c/v11 の
E 系メトリクスとして eval JSON に常設する。v1→v2→v3 と同じ field 追加のみの
後方互換 (SCHEMA_VERSION は zs-eval-v3 のまま)。既存の band/comb/prosody
テスト (test_eval_zs_secs.py) は変更しない。

測定は**出力自身の F0 トラック** (measure_comb_hnr.comb_hnr) で行う — GT/予測
格子は ±20 cent で崩壊する罠 (v11 head 設計 §5.3 deviation 4)。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from piper_train.tools import eval_zs_secs


# --- test_eval_zs_secs.py と同型の fake encoder (最小コピー、stem がキー) ---

_EMB_TABLES = {
    "campplus_model": {
        "s1": [1, 0, 0],
        "s2": [0, 1, 0],
        "r1": [1, 0, 0],
        "r2": [0, 0, 1],
        "r3": [1, 1, 0],
        "f1": [0, 0, -1],
    },
}


def _fake_preprocess(wav_path, target_sr=16000):
    return Path(wav_path).stem


def _fake_extract(session, fbank):
    return np.array(_EMB_TABLES[session.tag][fbank], dtype=np.float32)


def _fake_create_session(encoder_path):
    return SimpleNamespace(tag=Path(encoder_path).stem)


@pytest.fixture
def patched_cli(monkeypatch):
    monkeypatch.setattr(eval_zs_secs, "preprocess_audio", _fake_preprocess)
    monkeypatch.setattr(eval_zs_secs, "extract_embedding", _fake_extract)
    monkeypatch.setattr(eval_zs_secs, "_create_session", _fake_create_session)


def _write_harmonic_wav(path: Path, f0: float, seed: int, duration: float = 1.2):
    """pyin / STFT 解析が通る倍音 wav (test_eval_zs_secs._write_harmonic_wav と同型)。"""
    import soundfile as sf

    sr = 22050
    t = np.arange(int(sr * duration)) / sr
    wav = np.zeros_like(t)
    for k in range(1, 40):
        f = k * f0
        if f >= sr / 2:
            break
        gain = 10 ** (-12.0 * np.log2(f / f0) / 20)
        wav += gain * np.sin(2 * np.pi * f * t)
    rng = np.random.default_rng(seed)
    wav = wav + 1e-4 * rng.standard_normal(len(t))
    wav = (wav / np.abs(wav).max() * 0.5).astype(np.float32)
    sf.write(str(path), wav, sr)


@pytest.fixture(scope="module")
def harmonic_wav_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("zs_eval_comb_hnr")
    specs = {
        "synth": [("s1", 150.0), ("s2", 160.0)],
        "spk": [("r1", 170.0), ("r2", 180.0), ("r3", 190.0)],
    }
    dirs = {}
    seed = 0
    for name, items in specs.items():
        d = root / name
        d.mkdir()
        for stem, f0 in items:
            _write_harmonic_wav(d / f"{stem}.wav", f0=f0, seed=seed)
            seed += 1
        dirs[name] = d
    return dirs


def _run_cli(wav_dirs, tmp_path, extra=()):
    json_out = tmp_path / "report.json"
    argv = [
        "--synth-dir",
        str(wav_dirs["synth"]),
        "--speaker-utts",
        str(wav_dirs["spk"]),
        "--encoder",
        "campplus_model.onnx",
        "--json-out",
        str(json_out),
        *extra,
    ]
    rc = eval_zs_secs.main(argv)
    report = json.loads(json_out.read_text(encoding="utf-8"))
    return rc, report


def _finite(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


@pytest.mark.unit
class TestCombHnrBlock:
    def test_comb_hnr_block_and_baseline_delta(
        self, harmonic_wav_dirs, patched_cli, tmp_path, capsys
    ):
        """comb_hnr ブロックの形状 + baseline Δ の情報表示 (1 回の実 run に集約)。"""
        baseline = {
            "schema": "zs-eval-v3",
            "encoders": {"campplus": {"cross_utt_secs": 0.30}},
            "comb": {"synth": {"comb_excess_db_median": 4.0}},
            "comb_hnr": {"synth": {"comb_hnr_db_median": 4.6}},
        }
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        rc, report = _run_cli(
            harmonic_wav_dirs, tmp_path, ["--baseline-json", str(baseline_path)]
        )
        assert rc == 0

        block = report["comb_hnr"]
        assert block is not None
        # A3 の帯域 (1-3kHz) と自 F0 トラック規約を params で pin
        assert block["params"]["band_hz"] == [1000.0, 3000.0]
        assert block["params"]["f0_track"] == "self"
        assert {e["file"] for e in block["per_file"]} == {"s1.wav", "s2.wav"}
        for e in block["per_file"]:
            assert _finite(e["comb_hnr_db"])
        assert _finite(block["synth"]["comb_hnr_db_median"])
        # real (speaker-utts) は GT anchor の文脈表示用
        assert _finite(block["real"]["comb_hnr_db_median"])
        # 倍音 wav (ノイズ床 1e-4) は高い comb-HNR を出す (負値なら測定が壊れている)
        assert block["synth"]["comb_hnr_db_median"] > 5.0

        # baseline Δ に comb_hnr_db_median が含まれる (情報表示のみ、flag 化なし)
        acoustics = report["baseline_comparison"]["acoustics"]
        assert "comb_hnr_db_median" in acoustics
        assert _finite(acoustics["comb_hnr_db_median"])

        out = capsys.readouterr().out
        assert "comb_hnr" in out  # stdout サマリにも表示

    def test_skip_acoustics_nulls_comb_hnr(
        self, harmonic_wav_dirs, patched_cli, tmp_path
    ):
        """--skip-acoustics でも key は null 明示で常在 (キー欠落禁止の契約)。"""
        rc, report = _run_cli(harmonic_wav_dirs, tmp_path, ["--skip-acoustics"])
        assert rc == 0
        assert "comb_hnr" in report
        assert report["comb_hnr"] is None

    def test_schema_version_unchanged(self, harmonic_wav_dirs, patched_cli, tmp_path):
        """comb_hnr は field 追加のみ — schema は zs-eval-v3 のまま (後方互換)。"""
        rc, report = _run_cli(harmonic_wav_dirs, tmp_path, ["--skip-acoustics"])
        assert rc == 0
        assert report["schema"] == "zs-eval-v3"
