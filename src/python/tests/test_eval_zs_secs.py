"""Tests for piper_train.tools.eval_zs_secs (cross-utt SECS 評価ハーネス).

背景 (docs/design/zero-shot-v10-roadmap.md A-1e): same-utt SECS は SCL Goodhart
で膨張する (0.775 誤報の既知事故) ため、cross-utterance SECS + ceiling/floor
正規化転写率を 1 コマンドで出す標準ツールを新設した。本テストは
compute_secs_report の数学 (手計算一致) と CLI 契約 (JSON 構造 / exclude-ref
除外 / floor 無し null) を pin する。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from piper_train.tools import eval_zs_secs
from piper_train.tools.eval_zs_secs import collect_wavs, compute_secs_report


SQRT2_INV = 1.0 / np.sqrt(2.0)


@pytest.mark.unit
class TestComputeSecsReport:
    """既知の埋め込みベクトルで各指標が手計算と一致することを検証する。"""

    def _base_inputs(self):
        synth = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float64)
        # r3 = [1, 1, 0] は未正規化 → 内部 L2 正規化の検証を兼ねる
        refs = np.array([[0, 0, 1], [1, 1, 0]], dtype=np.float64)
        ref_emb = np.array([1, 0, 0], dtype=np.float64)
        floor = np.array([[0, 0, -1]], dtype=np.float64)
        return synth, refs, ref_emb, floor

    def test_hand_computed_values(self):
        synth, refs, ref_emb, floor = self._base_inputs()
        r = compute_secs_report(synth, refs, ref_emb=ref_emb, floor_embs=floor)

        # cross = mean(cos(s1,r2)=0, cos(s1,r3)=1/sqrt2, cos(s2,r2)=0,
        #              cos(s2,r3)=1/sqrt2) = 1/(2*sqrt2)
        assert r["cross_utt_secs"] == pytest.approx(SQRT2_INV / 2, abs=1e-9)
        # same = mean(cos(s1,ref)=1, cos(s2,ref)=0) = 0.5
        assert r["same_utt_secs"] == pytest.approx(0.5, abs=1e-9)
        # ceiling = cos(r2, r3) = 0 (自己ペアは含めない)
        assert r["ceiling"] == pytest.approx(0.0, abs=1e-9)
        # floor = mean(cos(r2,f)= -1, cos(r3,f)=0) = -0.5
        assert r["floor"] == pytest.approx(-0.5, abs=1e-9)
        # normalized = (cross - floor) / (ceiling - floor)
        expected_nt = (SQRT2_INV / 2 + 0.5) / 0.5
        assert r["normalized_transfer"] == pytest.approx(expected_nt, abs=1e-9)
        assert r["n_synth"] == 2
        assert r["n_refs"] == 2

    def test_no_floor_gives_null(self):
        synth, refs, ref_emb, _ = self._base_inputs()
        r = compute_secs_report(synth, refs, ref_emb=ref_emb, floor_embs=None)
        assert r["floor"] is None
        assert r["normalized_transfer"] is None
        # cross / same / ceiling は floor と独立に計算される
        assert r["cross_utt_secs"] == pytest.approx(SQRT2_INV / 2, abs=1e-9)
        assert r["ceiling"] == pytest.approx(0.0, abs=1e-9)

    def test_no_ref_gives_null_same_utt(self):
        synth, refs, _, floor = self._base_inputs()
        r = compute_secs_report(synth, refs, ref_emb=None, floor_embs=floor)
        assert r["same_utt_secs"] is None
        assert r["normalized_transfer"] is not None

    def test_ceiling_excludes_self_pairs(self):
        """ceiling は distinct pair のみ (自己類似 1.0 を含めると膨張する)。"""
        synth = np.array([[1, 0]], dtype=np.float64)
        refs = np.array([[1, 0], [1, 0], [0, 1]], dtype=np.float64)
        r = compute_secs_report(synth, refs)
        # pairs: (0,1)=1, (0,2)=0, (1,2)=0 → 1/3 (自己ペアを含むと 1/2 になる)
        assert r["ceiling"] == pytest.approx(1.0 / 3.0, abs=1e-9)

    def test_single_ref_ceiling_is_none(self):
        synth = np.array([[1, 0]], dtype=np.float64)
        refs = np.array([[1, 0]], dtype=np.float64)
        floor = np.array([[0, 1]], dtype=np.float64)
        r = compute_secs_report(synth, refs, floor_embs=floor)
        assert r["ceiling"] is None
        assert r["normalized_transfer"] is None  # ceiling 無しでは定義できない

    def test_degenerate_ceiling_equals_floor(self):
        """ceiling == floor では正規化転写率は未定義 (ゼロ除算防止)。"""
        synth = np.array([[1, 0]], dtype=np.float64)
        refs = np.array([[1, 0], [1, 0]], dtype=np.float64)  # ceiling = 1.0
        floor = np.array([[1, 0]], dtype=np.float64)  # floor = 1.0
        r = compute_secs_report(synth, refs, floor_embs=floor)
        assert r["normalized_transfer"] is None

    def test_unnormalized_inputs_are_normalized(self):
        """入力ベクトルのスケールは結果に影響しない (内部 L2 正規化)。"""
        synth = np.array([[10, 0]], dtype=np.float64)
        refs = np.array([[0, 3], [5, 5]], dtype=np.float64)
        r = compute_secs_report(synth, refs)
        assert r["cross_utt_secs"] == pytest.approx(SQRT2_INV / 2, abs=1e-9)
        assert r["ceiling"] == pytest.approx(SQRT2_INV, abs=1e-9)


# ---------------------------------------------------------------------------
# CLI レベル (embedding 抽出をモンキーパッチして JSON 構造を検証)
# ---------------------------------------------------------------------------

# encoder ONNX パスの stem → {wav stem → embedding}
_EMB_TABLES = {
    "campplus_model": {
        "s1": [1, 0, 0],
        "s2": [0, 1, 0],
        "r1": [1, 0, 0],
        "r2": [0, 0, 1],
        "r3": [1, 1, 0],
        "f1": [0, 0, -1],
    },
    "ecapa_model": {
        "s1": [1, 0, 0],
        "s2": [1, 0, 0],
        "r1": [1, 0, 0],
        "r2": [1, 0, 0],
        "r3": [1, 0, 0],
        "f1": [0, 1, 0],
    },
}


def _fake_preprocess(wav_path, target_sr=16000):
    # fbank の代わりに stem をキーとして流す (encoder 非依存キャッシュの検証も兼ねる)
    return Path(wav_path).stem


def _fake_extract(session, fbank):
    return np.array(_EMB_TABLES[session.tag][fbank], dtype=np.float32)


def _fake_create_session(encoder_path):
    return SimpleNamespace(tag=Path(encoder_path).stem)


@pytest.fixture
def wav_dirs(tmp_path):
    """synth/speaker/floor の wav ディレクトリ (中身は stem 固有バイト列)。

    §8 の計画された pin 更新 (phase_a_spec.md): E-5(ii) の content-hash 除外 +
    synth↔実音声 取り違え guard の導入後、全ファイル空バイトだと exclude-ref が
    r1/r2/r3 全てと hash 一致し、synth も実音声と同一内容になって guard が誤爆
    する。stem をバイト列にして「stem がキー」という fixture の意味は不変。
    """
    dirs = {}
    for name, stems in (
        ("synth", ["s1", "s2"]),
        ("spk", ["r1", "r2", "r3"]),
        ("floor", ["f1"]),
    ):
        d = tmp_path / name
        d.mkdir()
        for stem in stems:
            (d / f"{stem}.wav").write_bytes(stem.encode())
        dirs[name] = d
    return dirs


@pytest.fixture
def patched_cli(monkeypatch):
    monkeypatch.setattr(eval_zs_secs, "preprocess_audio", _fake_preprocess)
    monkeypatch.setattr(eval_zs_secs, "extract_embedding", _fake_extract)
    monkeypatch.setattr(eval_zs_secs, "_create_session", _fake_create_session)


@pytest.mark.unit
class TestCli:
    def test_dual_encoder_json_structure(self, wav_dirs, patched_cli, tmp_path, capsys):
        json_out = tmp_path / "report.json"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs["synth"]),
                "--speaker-utts",
                str(wav_dirs["spk"]),
                "--exclude-ref",
                str(wav_dirs["spk"] / "r1.wav"),
                "--floor-refs",
                str(wav_dirs["floor"]),
                "--encoder",
                "campplus_model.onnx",
                "--encoder2",
                "ecapa_model.onnx",
                "--json-out",
                str(json_out),
            ]
        )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert set(report["encoders"].keys()) == {"campplus", "encoder2"}

        cam = report["encoders"]["campplus"]
        # exclude-ref r1 除外後の cross set = {r2, r3} → 手計算値
        assert cam["cross_utt_secs"] == pytest.approx(SQRT2_INV / 2, abs=1e-6)
        assert cam["same_utt_secs"] == pytest.approx(0.5, abs=1e-6)
        assert cam["ceiling"] == pytest.approx(0.0, abs=1e-6)
        assert cam["floor"] == pytest.approx(-0.5, abs=1e-6)
        expected_nt = (SQRT2_INV / 2 + 0.5) / 0.5
        assert cam["normalized_transfer"] == pytest.approx(expected_nt, abs=1e-6)
        assert cam["n_synth"] == 2
        assert cam["n_refs"] == 2

        # 第 2 encoder は独立に抽出・レポートされる
        ecapa = report["encoders"]["encoder2"]
        assert ecapa["cross_utt_secs"] == pytest.approx(1.0, abs=1e-6)
        assert ecapa["ceiling"] == pytest.approx(1.0, abs=1e-6)
        assert ecapa["floor"] == pytest.approx(0.0, abs=1e-6)
        assert ecapa["normalized_transfer"] == pytest.approx(1.0, abs=1e-6)

        out = capsys.readouterr().out
        assert "cross-utterance SECS report" in out
        assert "campplus" in out and "encoder2" in out
        # 正規化転写率の強調表示と same-utt の判定使用禁止注記
        assert ">>>" in out
        assert "判定使用禁止" in out

    def test_single_encoder_no_ref_no_floor(self, wav_dirs, patched_cli, tmp_path):
        json_out = tmp_path / "report.json"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs["synth"]),
                "--speaker-utts",
                str(wav_dirs["spk"]),
                "--encoder",
                "campplus_model.onnx",
                "--json-out",
                str(json_out),
            ]
        )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert set(report["encoders"].keys()) == {"campplus"}
        cam = report["encoders"]["campplus"]
        assert cam["same_utt_secs"] is None  # --exclude-ref なし
        assert cam["floor"] is None  # --floor-refs なし
        assert cam["normalized_transfer"] is None
        assert cam["n_refs"] == 3  # 除外なしで r1/r2/r3 全部

    def test_exclude_ref_outside_speaker_dir(self, wav_dirs, patched_cli, tmp_path):
        """speaker-utts 外の exclude-ref は除外なし + same-utt 参照として使用。"""
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        ref = ext_dir / "r1.wav"
        ref.write_bytes(b"")
        json_out = tmp_path / "report.json"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs["synth"]),
                "--speaker-utts",
                str(wav_dirs["spk"]),
                "--exclude-ref",
                str(ref),
                "--encoder",
                "campplus_model.onnx",
                "--json-out",
                str(json_out),
            ]
        )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        cam = report["encoders"]["campplus"]
        assert cam["n_refs"] == 3  # 除外は発生しない
        assert cam["same_utt_secs"] == pytest.approx(0.5, abs=1e-6)

    def test_empty_synth_dir_fails(self, wav_dirs, patched_cli, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(SystemExit, match="no wav files"):
            eval_zs_secs.main(
                [
                    "--synth-dir",
                    str(empty),
                    "--speaker-utts",
                    str(wav_dirs["spk"]),
                    "--encoder",
                    "campplus_model.onnx",
                ]
            )

    def test_too_few_refs_after_exclusion_fails(self, patched_cli, tmp_path):
        """除外後 2 発話未満は ceiling が定義できないためエラー。"""
        synth = tmp_path / "synth"
        synth.mkdir()
        (synth / "s1.wav").write_bytes(b"")
        spk = tmp_path / "spk"
        spk.mkdir()
        (spk / "r1.wav").write_bytes(b"")
        (spk / "r2.wav").write_bytes(b"")
        with pytest.raises(SystemExit, match="need >= 2 speaker utterances"):
            eval_zs_secs.main(
                [
                    "--synth-dir",
                    str(synth),
                    "--speaker-utts",
                    str(spk),
                    "--exclude-ref",
                    str(spk / "r1.wav"),
                    "--encoder",
                    "campplus_model.onnx",
                ]
            )

    def test_missing_exclude_ref_fails(self, wav_dirs, patched_cli, tmp_path):
        with pytest.raises(SystemExit, match="not found"):
            eval_zs_secs.main(
                [
                    "--synth-dir",
                    str(wav_dirs["synth"]),
                    "--speaker-utts",
                    str(wav_dirs["spk"]),
                    "--exclude-ref",
                    str(tmp_path / "nope.wav"),
                    "--encoder",
                    "campplus_model.onnx",
                ]
            )


@pytest.mark.unit
class TestCollectWavs:
    def test_sorted_and_wav_only(self, tmp_path):
        (tmp_path / "b.wav").write_bytes(b"")
        (tmp_path / "a.wav").write_bytes(b"")
        (tmp_path / "c.txt").write_bytes(b"")
        wavs = collect_wavs(tmp_path)
        assert [p.name for p in wavs] == ["a.wav", "b.wav"]

    def test_missing_dir_fails(self, tmp_path):
        with pytest.raises(SystemExit, match="not a directory"):
            collect_wavs(tmp_path / "missing")


# ---------------------------------------------------------------------------
# zs-eval-v2: gap_same_minus_cross / baseline 比較 (goodhart_flag) /
# --require-encoder2 (docs/spec/zs-eval-contract.md の制度化)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGapSameMinusCross:
    """gap = same_utt − cross_utt。SCL Goodhart で膨らむ成分の直接観測。"""

    def test_gap_is_same_minus_cross(self):
        synth = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float64)
        refs = np.array([[0, 0, 1], [1, 1, 0]], dtype=np.float64)
        ref_emb = np.array([1, 0, 0], dtype=np.float64)
        r = compute_secs_report(synth, refs, ref_emb=ref_emb)
        # same = 0.5, cross = 1/(2*sqrt2)
        assert r["gap_same_minus_cross"] == pytest.approx(0.5 - SQRT2_INV / 2, abs=1e-9)

    def test_gap_null_without_ref(self):
        synth = np.array([[1, 0, 0]], dtype=np.float64)
        refs = np.array([[0, 0, 1], [1, 1, 0]], dtype=np.float64)
        r = compute_secs_report(synth, refs)
        assert "gap_same_minus_cross" in r  # null 明示 (キー欠落ではない)
        assert r["gap_same_minus_cross"] is None


def _mk_report(campplus: dict | None = None, encoder2: dict | None = None) -> dict:
    encoders = {}
    if campplus is not None:
        encoders["campplus"] = campplus
    if encoder2 is not None:
        encoders["encoder2"] = encoder2
    return {"encoders": encoders}


@pytest.mark.unit
class TestCompareWithBaseline:
    """Goodhart 判定: primary Δ >= +0.02 かつ encoder2 Δ < +0.01 で flag。

    Phase 0 Arm B (CAM++ +0.023 / ECAPA +0.002 = Goodhart 棄却) の判定基準を
    そのまま制度化する (zero-shot-warm-restart-diagnostics-phase0-1.md §3)。
    """

    def test_goodhart_true_when_only_primary_moves(self):
        # Arm B 実測値の再現: CAM++ +0.023 / ECAPA +0.002
        cur = _mk_report({"cross_utt_secs": 0.653}, {"cross_utt_secs": 0.502})
        base = _mk_report({"cross_utt_secs": 0.630}, {"cross_utt_secs": 0.500})
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["goodhart_flag"] is True
        assert c["deltas"]["campplus"]["cross_utt_secs"] == pytest.approx(0.023)
        assert c["deltas"]["encoder2"]["cross_utt_secs"] == pytest.approx(0.002)

    def test_goodhart_false_when_encoder2_follows(self):
        cur = _mk_report({"cross_utt_secs": 0.660}, {"cross_utt_secs": 0.520})
        base = _mk_report({"cross_utt_secs": 0.630}, {"cross_utt_secs": 0.500})
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["goodhart_flag"] is False

    def test_goodhart_false_when_primary_below_threshold(self):
        cur = _mk_report({"cross_utt_secs": 0.645}, {"cross_utt_secs": 0.500})
        base = _mk_report({"cross_utt_secs": 0.630}, {"cross_utt_secs": 0.500})
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["goodhart_flag"] is False

    def test_goodhart_null_without_encoder2(self):
        cur = _mk_report({"cross_utt_secs": 0.653})
        base = _mk_report({"cross_utt_secs": 0.630})
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["goodhart_flag"] is None

    def test_gap_widening_detected(self):
        cur = _mk_report({"cross_utt_secs": 0.65, "gap_same_minus_cross": 0.06})
        base = _mk_report({"cross_utt_secs": 0.64, "gap_same_minus_cross": 0.04})
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["gap_widened_encoders"] == ["campplus"]
        assert c["deltas"]["campplus"]["gap_same_minus_cross"] == pytest.approx(0.02)

    def test_gap_from_v1_baseline_without_gap_field(self):
        """v1 schema (gap field なし) でも same/cross から gap を復元して比較。"""
        cur = _mk_report({"cross_utt_secs": 0.65, "gap_same_minus_cross": 0.06})
        base = _mk_report({"cross_utt_secs": 0.64, "same_utt_secs": 0.68})  # gap 0.04
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["deltas"]["campplus"]["gap_same_minus_cross"] == pytest.approx(0.02)
        assert c["gap_widened_encoders"] == ["campplus"]

    def test_gap_delta_null_when_unmeasured(self):
        cur = _mk_report({"cross_utt_secs": 0.65})
        base = _mk_report({"cross_utt_secs": 0.64})
        c = eval_zs_secs.compare_with_baseline(cur, base)
        assert c["deltas"]["campplus"]["gap_same_minus_cross"] is None
        assert c["gap_widened_encoders"] == []


@pytest.mark.unit
class TestCliEvalV2:
    """CLI 契約: schema v2 / --require-encoder2 / --baseline-json。"""

    def _run(self, wav_dirs, tmp_path, extra):
        json_out = tmp_path / "report.json"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs["synth"]),
                "--speaker-utts",
                str(wav_dirs["spk"]),
                "--exclude-ref",
                str(wav_dirs["spk"] / "r1.wav"),
                "--encoder",
                "campplus_model.onnx",
                "--json-out",
                str(json_out),
                *extra,
            ]
        )
        return rc, json_out

    def _write_baseline(self, tmp_path, campplus, encoder2=None):
        base = {"encoders": {"campplus": campplus}}
        if encoder2 is not None:
            base["encoders"]["encoder2"] = encoder2
        p = tmp_path / "baseline.json"
        p.write_text(json.dumps(base), encoding="utf-8")
        return p

    def test_schema_v3_fields_always_present(self, wav_dirs, patched_cli, tmp_path):
        # §8 の計画された pin 更新: Phase A で schema v2 → v3 (field 追加のみ)
        rc, json_out = self._run(wav_dirs, tmp_path, ["--encoder2", "ecapa_model.onnx"])
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert report["schema"] == "zs-eval-v3"
        assert report["goodhart_flag"] is None  # baseline なしでは判定不能
        cam = report["encoders"]["campplus"]
        assert cam["gap_same_minus_cross"] == pytest.approx(
            0.5 - SQRT2_INV / 2, abs=1e-6
        )

    def test_gap_null_explicit_without_ref(self, wav_dirs, patched_cli, tmp_path):
        json_out = tmp_path / "report.json"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs["synth"]),
                "--speaker-utts",
                str(wav_dirs["spk"]),
                "--encoder",
                "campplus_model.onnx",
                "--json-out",
                str(json_out),
            ]
        )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        cam = report["encoders"]["campplus"]
        assert cam["same_utt_secs"] is None
        assert "gap_same_minus_cross" in cam  # 未計測でも null 明示
        assert cam["gap_same_minus_cross"] is None

    def test_require_encoder2_exits_2(self, wav_dirs, patched_cli, tmp_path):
        rc, _ = self._run(wav_dirs, tmp_path, ["--require-encoder2"])
        assert rc == 2

    def test_require_encoder2_passes_with_encoder2(
        self, wav_dirs, patched_cli, tmp_path
    ):
        rc, _ = self._run(
            wav_dirs, tmp_path, ["--require-encoder2", "--encoder2", "ecapa_model.onnx"]
        )
        assert rc == 0

    def test_no_encoder2_warns_goodhart_blind(
        self, wav_dirs, patched_cli, tmp_path, caplog
    ):
        with caplog.at_level(logging.WARNING):
            rc, _ = self._run(wav_dirs, tmp_path, [])
        assert rc == 0
        assert "Goodhart 検知不能" in caplog.text

    def test_baseline_goodhart_flag_true(self, wav_dirs, patched_cli, tmp_path, caplog):
        # 現在値 (fake embs): campplus cross=0.3536 / encoder2 cross=1.0
        # baseline を campplus Δ=+0.0236 (>= +0.02) / encoder2 Δ=+0.005 (< +0.01)
        # になるよう設定 → Goodhart flag
        baseline = self._write_baseline(
            tmp_path,
            {"cross_utt_secs": 0.33, "gap_same_minus_cross": 0.15},
            {"cross_utt_secs": 0.995, "gap_same_minus_cross": 0.0},
        )
        with caplog.at_level(logging.WARNING):
            rc, json_out = self._run(
                wav_dirs,
                tmp_path,
                ["--encoder2", "ecapa_model.onnx", "--baseline-json", str(baseline)],
            )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert report["goodhart_flag"] is True
        comp = report["baseline_comparison"]
        assert comp["goodhart_flag"] is True
        assert comp["deltas"]["campplus"]["cross_utt_secs"] == pytest.approx(
            SQRT2_INV / 2 - 0.33, abs=1e-6
        )
        assert "Goodhart" in caplog.text

    def test_baseline_both_encoders_up_no_flag(self, wav_dirs, patched_cli, tmp_path):
        # encoder2 Δ=+0.02 >= +0.01 → 両 encoder 同調 = Goodhart ではない
        baseline = self._write_baseline(
            tmp_path,
            {"cross_utt_secs": 0.33, "gap_same_minus_cross": 0.15},
            {"cross_utt_secs": 0.98, "gap_same_minus_cross": 0.0},
        )
        rc, json_out = self._run(
            wav_dirs,
            tmp_path,
            ["--encoder2", "ecapa_model.onnx", "--baseline-json", str(baseline)],
        )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert report["goodhart_flag"] is False

    def test_baseline_gap_widening_warns(self, wav_dirs, patched_cli, tmp_path, caplog):
        # 現在の campplus gap = 0.5 - 0.3536 = 0.1464。baseline gap 0.10 →
        # Δgap = +0.046 >= +0.01 で警告 (Δcross = +0.0036 < +0.02 なので
        # goodhart 条件とは独立に発火することも確認)
        baseline = self._write_baseline(
            tmp_path, {"cross_utt_secs": 0.35, "gap_same_minus_cross": 0.10}
        )
        with caplog.at_level(logging.WARNING):
            rc, json_out = self._run(
                wav_dirs, tmp_path, ["--baseline-json", str(baseline)]
            )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert report["baseline_comparison"]["gap_widened_encoders"] == ["campplus"]
        assert "拡大" in caplog.text

    def test_baseline_json_missing_fails(self, wav_dirs, patched_cli, tmp_path):
        with pytest.raises(SystemExit, match="baseline-json not found"):
            self._run(
                wav_dirs, tmp_path, ["--baseline-json", str(tmp_path / "nope.json")]
            )


# ---------------------------------------------------------------------------
# zs-eval-v3 (Phase A 評価アップグレード、docs/design/zero-shot-v10b-quality-plan.md
# §2 E-1〜E-8 / scratchpad phase_a_spec.md §4-§6.5):
#   - manifest (ファイル名 + sha256 pin、E-5(i))
#   - exclude-ref の content-hash 除外 + synth↔実音声 取り違え guard (E-5(ii))
#   - above_ceiling_flag / cross_exceeds_ceiling (E-7(iii)、goodhart_flag とは別 field)
#   - band / comb / prosody ブロック統合 (E-1〜E-4、default ON + --skip-acoustics)
#   - stdout headline = normalized_transfer (E-7(i)、raw SECS headline 禁止)
#   - v2 → v3 は field 追加のみの後方互換
# TDD red で実装より先に追加 — 実装完了までは fail が正常。
# 既存 (v1/v2) のテストは変更しない (§8 の計画された pin 更新は実装 commit で行う)。
# ---------------------------------------------------------------------------


# fake table (exclude r1 + floor) での campplus normalized_transfer 手計算値:
# (cross 1/(2*sqrt2) - floor -0.5) / (ceiling 0.0 - floor -0.5) = 1.70711
EXPECTED_NT_CAMPPLUS = (SQRT2_INV / 2 + 0.5) / 0.5


def _sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(x) -> bool:
    import math

    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


@pytest.fixture
def wav_dirs_unique(tmp_path):
    """wav_dirs と同じ stem 構成で、各ファイルに固有バイト列を持たせた fixture。

    E-5(ii) の content-hash 除外は「同一内容かどうか」が意味を持つため、
    ファイル内容を明示制御する v3 専用 fixture を持つ (既存 wav_dirs も §8 の
    pin 更新で stem 固有バイト列に変更済み — 本 fixture は v3 テスト群を既存
    fixture の内容選択に結合させないための独立コピー)。中身は非 wav バイト
    なので音響解析は不能 → band/comb/prosody は null 縮退 (§4.7) のまま
    SECS 経路と manifest だけを検証する。
    """
    dirs = {}
    for name, stems in (
        ("synth", ["s1", "s2"]),
        ("spk", ["r1", "r2", "r3"]),
        ("floor", ["f1"]),
    ):
        d = tmp_path / name
        d.mkdir()
        for stem in stems:
            (d / f"{stem}.wav").write_bytes(f"dummy-bytes:{stem}".encode())
        dirs[name] = d
    return dirs


def _run_v3_cli(
    wav_dirs,
    tmp_path,
    extra=(),
    *,
    exclude_r1=True,
    floor=True,
    encoder2=False,
):
    """v3 追加テスト用の共通 CLI runner。json_out を読み戻して (rc, report) を返す。"""
    json_out = tmp_path / "report_v3.json"
    argv = [
        "--synth-dir",
        str(wav_dirs["synth"]),
        "--speaker-utts",
        str(wav_dirs["spk"]),
        "--encoder",
        "campplus_model.onnx",
        "--json-out",
        str(json_out),
    ]
    if exclude_r1:
        argv += ["--exclude-ref", str(wav_dirs["spk"] / "r1.wav")]
    if floor:
        argv += ["--floor-refs", str(wav_dirs["floor"])]
    if encoder2:
        argv += ["--encoder2", "ecapa_model.onnx"]
    argv += list(extra)
    rc = eval_zs_secs.main(argv)
    report = None
    if json_out.exists():
        report = json.loads(json_out.read_text(encoding="utf-8"))
    return rc, report


def _write_harmonic_wav(path: Path, f0: float, seed: int, duration: float = 1.2):
    """pyin / STFT 解析が通る倍音音声 wav を書く (test_measure_band_noise と同型)。

    高調波 + 微小白色雑音 (全帯域ノイズ床の保証 + ファイル間バイト差の保証)。
    """
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
    """実解析 (band/comb/prosody) を通す本物の倍音 wav 群。

    stem は fake embedding table (_EMB_TABLES) と共用。f0/seed をファイルごとに
    変えて全ファイルのバイト列を確実に異ならせる (synth↔実音声 sha256 一致
    guard を誤爆させないため)。module scope で pyin 実行コストを抑える
    (テストはどれもファイルを変更しない)。
    """
    root = tmp_path_factory.mktemp("zs_eval_v3_harmonic")
    specs = {
        "synth": [("s1", 150.0), ("s2", 160.0)],
        "spk": [("r1", 170.0), ("r2", 180.0), ("r3", 190.0)],
        "floor": [("f1", 210.0)],
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


@pytest.mark.unit
class TestSchemaV3Shape:
    """§4.2: v3 トップレベル構造 (追加 field は null 明示、キー欠落禁止)。"""

    def test_schema_v3_fields_always_present(
        self, wav_dirs_unique, patched_cli, tmp_path
    ):
        rc, report = _run_v3_cli(
            wav_dirs_unique, tmp_path, exclude_r1=False, floor=True, encoder2=True
        )
        assert rc == 0
        assert report["schema"] == "zs-eval-v3"
        for key in (
            "band",
            "comb",
            "prosody",
            "manifest",
            "above_ceiling_flag",
            "goodhart_flag",
        ):
            assert key in report, f"v3 で必須のトップレベル key: {key}"
        # ダミーバイト列 (非 wav) は音響解析不能 → ブロックは null 明示 (§4.7 縮退)
        assert report["band"] is None
        assert report["comb"] is None
        assert report["prosody"] is None
        # encoder ブロックの v3 追加 field (E-7(iii))
        for enc in ("campplus", "encoder2"):
            assert "cross_exceeds_ceiling" in report["encoders"][enc]
        manifest = report["manifest"]
        for key in (
            "synth",
            "speaker_utts",
            "excluded_by_hash",
            "floor_refs",
            "floor_selection_note",
            "exclude_ref",
            "encoders",
            "synthesis",
        ):
            assert key in manifest, f"manifest 必須 key: {key}"
        assert manifest["exclude_ref"] is None  # --exclude-ref なし
        assert manifest["excluded_by_hash"] == []
        assert manifest["synthesis"] is None  # --meta-json なし
        assert manifest["floor_selection_note"] is None


@pytest.mark.unit
class TestManifestSha256:
    """E-5(i): synth/speaker/floor/encoders の全群がファイル名 + sha256 で pin される。"""

    def test_manifest_sha256(self, wav_dirs_unique, patched_cli, tmp_path):
        enc1 = tmp_path / "campplus_model.onnx"
        enc1.write_bytes(b"fake-campplus-onnx-bytes")
        enc2 = tmp_path / "ecapa_model.onnx"
        enc2.write_bytes(b"fake-ecapa-onnx-bytes")
        json_out = tmp_path / "report.json"
        note = "same-lang 近接話者 5 名 (テスト用 note)"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs_unique["synth"]),
                "--speaker-utts",
                str(wav_dirs_unique["spk"]),
                "--exclude-ref",
                str(wav_dirs_unique["spk"] / "r1.wav"),
                "--floor-refs",
                str(wav_dirs_unique["floor"]),
                "--floor-selection-note",
                note,
                "--encoder",
                str(enc1),
                "--encoder2",
                str(enc2),
                "--json-out",
                str(json_out),
            ]
        )
        assert rc == 0
        manifest = json.loads(json_out.read_text(encoding="utf-8"))["manifest"]

        assert manifest["synth"]["dir"] == str(wav_dirs_unique["synth"])
        synth_files = {e["file"]: e["sha256"] for e in manifest["synth"]["files"]}
        assert set(synth_files) == {"s1.wav", "s2.wav"}
        for name, digest in synth_files.items():
            assert digest == _sha256_of(wav_dirs_unique["synth"] / name)

        # speaker_utts は除外後の cross set (r1 は exclude_ref 側に記録)
        spk_files = {e["file"]: e["sha256"] for e in manifest["speaker_utts"]["files"]}
        assert set(spk_files) == {"r2.wav", "r3.wav"}
        for name, digest in spk_files.items():
            assert digest == _sha256_of(wav_dirs_unique["spk"] / name)

        floor_files = {e["file"]: e["sha256"] for e in manifest["floor_refs"]["files"]}
        assert set(floor_files) == {"f1.wav"}
        assert floor_files["f1.wav"] == _sha256_of(wav_dirs_unique["floor"] / "f1.wav")
        assert manifest["floor_selection_note"] == note

        ex = manifest["exclude_ref"]
        assert ex["file"] == "r1.wav"
        assert ex["sha256"] == _sha256_of(wav_dirs_unique["spk"] / "r1.wav")

        encs = manifest["encoders"]
        assert Path(encs["campplus"]["path"]).name == "campplus_model.onnx"
        assert encs["campplus"]["sha256"] == _sha256_of(enc1)
        assert encs["encoder2"]["sha256"] == _sha256_of(enc2)


@pytest.mark.unit
class TestContentHashGuards:
    """E-5(ii): path ではなく内容 (sha256) での除外 + 取り違え SystemExit。"""

    def test_exclude_ref_by_content_hash(self, wav_dirs_unique, patched_cli, tmp_path):
        """パスが違う同一内容の exclude-ref でも cross set から除外される。

        既存の test_exclude_ref_outside_speaker_dir (path 不一致 → 除外なし) の
        v3 置換仕様: 内容一致なら speaker-utts 内の同一ファイルを除外する。
        """
        ext = tmp_path / "ext"
        ext.mkdir()
        # stem を r1 に合わせ fake embedding table を共用 (path は spk 外)
        ref_copy = ext / "r1.wav"
        ref_copy.write_bytes((wav_dirs_unique["spk"] / "r1.wav").read_bytes())
        json_out = tmp_path / "report.json"
        rc = eval_zs_secs.main(
            [
                "--synth-dir",
                str(wav_dirs_unique["synth"]),
                "--speaker-utts",
                str(wav_dirs_unique["spk"]),
                "--exclude-ref",
                str(ref_copy),
                "--encoder",
                "campplus_model.onnx",
                "--json-out",
                str(json_out),
            ]
        )
        assert rc == 0
        report = json.loads(json_out.read_text(encoding="utf-8"))
        cam = report["encoders"]["campplus"]
        # 内容一致で spk/r1.wav が除外され cross set = {r2, r3}
        assert cam["n_refs"] == 2
        assert cam["cross_utt_secs"] == pytest.approx(SQRT2_INV / 2, abs=1e-6)
        # exclude-ref は same-utt 参照としては引き続き使用される
        assert cam["same_utt_secs"] == pytest.approx(0.5, abs=1e-6)
        excluded = report["manifest"]["excluded_by_hash"]
        assert [e["file"] for e in excluded] == ["r1.wav"]
        assert excluded[0]["sha256"] == _sha256_of(wav_dirs_unique["spk"] / "r1.wav")

    @pytest.mark.parametrize("source", ["spk", "floor"])
    def test_synth_identical_to_real_fails(
        self, source, wav_dirs_unique, patched_cli, tmp_path
    ):
        """synth と実音声の sha256 一致は eval 全体を無効化する → SystemExit。

        合成物と実音声の取り違えは ceiling 系すべてを汚染するため
        警告では足りない (§4.3【決定 D15】)。
        """
        src_file = {"spk": "r2.wav", "floor": "f1.wav"}[source]
        (wav_dirs_unique["synth"] / "s1.wav").write_bytes(
            (wav_dirs_unique[source] / src_file).read_bytes()
        )
        with pytest.raises(SystemExit) as excinfo:
            eval_zs_secs.main(
                [
                    "--synth-dir",
                    str(wav_dirs_unique["synth"]),
                    "--speaker-utts",
                    str(wav_dirs_unique["spk"]),
                    "--floor-refs",
                    str(wav_dirs_unique["floor"]),
                    "--encoder",
                    "campplus_model.onnx",
                ]
            )
        assert excinfo.value.code not in (None, 0)

    def test_duplicate_speaker_utts_warns_only(self, patched_cli, tmp_path, caplog):
        """speaker-utts 内部の重複 sha256 は警告のみ (ceiling 膨張の注意喚起)。"""
        synth = tmp_path / "synth"
        synth.mkdir()
        (synth / "s1.wav").write_bytes(b"dummy-bytes:s1")
        spk = tmp_path / "spk"
        spk.mkdir()
        (spk / "r1.wav").write_bytes(b"dummy-bytes:r1")
        (spk / "r2.wav").write_bytes(b"dup-payload")
        (spk / "r3.wav").write_bytes(b"dup-payload")  # r2 と同一内容
        with caplog.at_level(logging.WARNING):
            rc = eval_zs_secs.main(
                [
                    "--synth-dir",
                    str(synth),
                    "--speaker-utts",
                    str(spk),
                    "--encoder",
                    "campplus_model.onnx",
                ]
            )
        assert rc == 0  # fail にはしない
        text = caplog.text
        assert (
            ("重複" in text) or ("duplicate" in text.lower()) or ("sha" in text.lower())
        )


@pytest.mark.unit
class TestAboveCeilingFlag:
    """E-7(iii): SECS > ceiling は録音特性複製の疑い — 独立 flag として制度化。"""

    def test_above_ceiling_flag_true(
        self, wav_dirs_unique, patched_cli, tmp_path, caplog, capsys
    ):
        with caplog.at_level(logging.WARNING):
            rc, report = _run_v3_cli(wav_dirs_unique, tmp_path, encoder2=True)
        assert rc == 0
        # fake table: campplus cross 0.3536 > ceiling 0.0 /
        #             encoder2 cross 1.0 = ceiling 1.0 (超えない)
        assert report["encoders"]["campplus"]["cross_exceeds_ceiling"] is True
        assert report["encoders"]["encoder2"]["cross_exceeds_ceiling"] is False
        # トップレベル flag は primary (campplus) の値
        assert report["above_ceiling_flag"] is True
        err = capsys.readouterr().err
        assert "録音特性" in (caplog.text + err)

    def test_goodhart_flag_meaning_unchanged_by_above_ceiling(
        self, wav_dirs_unique, patched_cli, tmp_path
    ):
        """above_ceiling が true でも goodhart_flag の意味 (baseline Δ 判定) は不変。

        baseline なし → null のまま (test_schema_v2_fields_always_present が
        pin する v2 解釈の非汚染、§4.5【決定 D13】)。
        """
        rc, report = _run_v3_cli(wav_dirs_unique, tmp_path, encoder2=True)
        assert rc == 0
        assert report["above_ceiling_flag"] is True
        assert report["goodhart_flag"] is None


@pytest.mark.unit
class TestNormalizedTransferSignGuard:
    """E-5(iii): ceiling <= floor では normalized_transfer は定義しない。"""

    def test_ceiling_below_floor_nulls_transfer(self, caplog):
        synth = np.array([[1, 0]], dtype=np.float64)
        refs = np.array([[1, 0], [-1, 0]], dtype=np.float64)  # ceiling = -1
        floor = np.array([[0, 1]], dtype=np.float64)  # floor = 0
        with caplog.at_level(logging.WARNING):
            r = compute_secs_report(synth, refs, floor_embs=floor)
        assert r["ceiling"] == pytest.approx(-1.0, abs=1e-9)
        assert r["floor"] == pytest.approx(0.0, abs=1e-9)
        # 現行実装は |denom| > 1e-6 のみで通してしまう (負の denom で
        # 符号が反転した「正規化」値が出る) — v3 では null + 警告
        assert r["normalized_transfer"] is None
        assert "floor" in caplog.text


@pytest.mark.unit
class TestMetaJsonAndSkipAcoustics:
    """E-5(iii) 合成条件の固定 + §4.7 acoustics toggle。"""

    def test_meta_json_embedded(self, wav_dirs_unique, patched_cli, tmp_path):
        meta = {
            "noise_scale": 0.667,
            "noise_scale_w": 0.5,
            "seed": 1234,
            "texts": ["t0", "t1"],
        }
        meta_path = tmp_path / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        rc, report = _run_v3_cli(
            wav_dirs_unique, tmp_path, ["--meta-json", str(meta_path)]
        )
        assert rc == 0
        # verbatim 埋め込み (加工しない)
        assert report["manifest"]["synthesis"] == meta

    def test_meta_json_non_object_fails(self, wav_dirs_unique, patched_cli, tmp_path):
        meta_path = tmp_path / "meta.json"
        meta_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            _run_v3_cli(wav_dirs_unique, tmp_path, ["--meta-json", str(meta_path)])
        # argparse の usage error (code 2) ではなく実装の明示 SystemExit であること
        assert excinfo.value.code not in (None, 0, 2)

    def test_skip_acoustics_nulls_blocks(
        self, harmonic_wav_dirs, patched_cli, tmp_path
    ):
        """実 wav でも --skip-acoustics なら band/comb/prosody は計算しない。

        (解析不能による null 縮退と区別するため、解析可能な wav で検証する。)
        """
        rc, report = _run_v3_cli(harmonic_wav_dirs, tmp_path, ["--skip-acoustics"])
        assert rc == 0
        assert report["band"] is None
        assert report["comb"] is None
        assert report["prosody"] is None


@pytest.mark.unit
class TestAcousticsIntegration:
    """E-1〜E-4 の eval JSON 統合 (数値の数学は各モジュールのテストが担保。

    ここでは非 null・有限性・形状のみ検証する — phase_a_spec.md §6.5)。
    """

    def test_acoustics_real_wav_end_to_end(
        self, harmonic_wav_dirs, patched_cli, tmp_path, capsys
    ):
        rc, report = _run_v3_cli(harmonic_wav_dirs, tmp_path)
        assert rc == 0

        band = report["band"]
        assert band is not None
        # E-5(iv): CLI/契約/harness の帯域統一 (4-9kHz) を JSON params で pin
        assert band["params"]["hi_band_hz"] == [4000, 9000]
        assert band["params"]["shelf_band_hz"] == [5500, 8500]
        vec = band["synth"]["band_db_1khz"]
        assert len(vec) == 11
        assert all(_finite(v) for v in vec)
        assert _finite(band["synth"]["voiced_hi_excess_db_median"])  # 旧指標互換
        hi = band["synth"]["hi_ref_frame_db"]  # E-2 per-frame 分布
        assert _finite(hi["median"])
        assert _finite(hi["frac_above_median_plus_6db"])
        assert len(band["delta"]["band_delta_vs_real_1khz"]) == 11
        assert _finite(band["delta"]["shelf_voiced_max_delta_db"])

        comb = report["comb"]
        assert comb is not None
        assert comb["params"]["grid_hz"] == pytest.approx(172.265625)
        assert {e["file"] for e in comb["per_file"]} >= {"s1.wav", "s2.wav"}
        for e in comb["per_file"]:
            assert _finite(e["comb_excess_db"])
            assert _finite(e["hf_autocorr_lag128"])
            assert _finite(e["hf_autocorr_lag256"])
        assert _finite(comb["synth"]["comb_excess_db_median"])
        # real (speaker-utts) は GT anchor の文脈表示用 (gate は synth のみ)
        assert _finite(comb["real"]["comb_excess_db_median"])

        prosody = report["prosody"]
        assert prosody is not None
        for key in (
            "f0_median_hz",
            "f0_std_hz",
            "f0_range_p5_p95_hz",
            "voiced_energy_std_db",
            "syllable_nuclei_per_sec",
        ):
            assert key in prosody["synth"], f"prosody 統計 key: {key}"
        # synth f0 = 150/160Hz の倍音音声 → group median は既知レンジ
        assert 100.0 < prosody["synth"]["f0_median_hz"] < 250.0
        assert _finite(prosody["delta"]["f0_std_hz"])  # synth − real の記述統計差

        out = capsys.readouterr().out
        assert "comb_excess_db" in out  # §4.4 acoustics サマリの stdout 表示

    def test_baseline_v3_acoustics_delta(
        self, harmonic_wav_dirs, patched_cli, tmp_path
    ):
        """v3 baseline (band/comb あり) なら acoustics Δ を情報表示する (§4.6)。"""
        baseline = {
            "schema": "zs-eval-v3",
            "encoders": {"campplus": {"cross_utt_secs": 0.30}},
            "band": {
                "synth": {"voiced_hi_excess_db_median": -12.0},
                "delta": {"shelf_voiced_max_delta_db": 3.0},
            },
            "comb": {
                "synth": {
                    "comb_excess_db_median": 4.0,
                    "hf_autocorr_lag128_median": 0.15,
                    "hf_autocorr_lag256_median": 0.10,
                }
            },
        }
        baseline_path = tmp_path / "baseline_v3.json"
        baseline_path.write_text(
            json.dumps(baseline, ensure_ascii=False), encoding="utf-8"
        )
        rc, report = _run_v3_cli(
            harmonic_wav_dirs, tmp_path, ["--baseline-json", str(baseline_path)]
        )
        assert rc == 0
        acoustics = report["baseline_comparison"]["acoustics"]
        assert acoustics is not None
        for key in (
            "comb_excess_db_median",
            "hf_autocorr_lag128_median",
            "hf_autocorr_lag256_median",
            "voiced_hi_excess_db_median",
            "shelf_voiced_max_delta_db",
        ):
            assert key in acoustics, f"acoustics Δ key: {key}"
            assert acoustics[key] is None or _finite(acoustics[key])


@pytest.mark.unit
class TestStdoutHeadline:
    """E-7(i): stdout の主役は normalized_transfer (raw SECS headline 禁止)。"""

    def test_headline_is_normalized_transfer(
        self, wav_dirs_unique, patched_cli, tmp_path, capsys
    ):
        rc, _ = _run_v3_cli(wav_dirs_unique, tmp_path, encoder2=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "(zs-eval-v3)" in out  # schema 明示のタイトル行
        headline_lines = [ln for ln in out.splitlines() if "HEADLINE" in ln]
        assert len(headline_lines) == 1
        hl = headline_lines[0]
        assert "normalized_transfer" in hl
        assert "campplus" in hl
        assert "encoder2" in hl
        assert f"{EXPECTED_NT_CAMPPLUS:.4f}" in hl  # 1.7071 (手計算値)
        # headline は既存テーブル (raw SECS 列) より前に出る
        assert out.index("HEADLINE") < out.index("cross_utt")
        # raw SECS を単独 headline にしない旨の注記 (契約 §2)
        assert "raw SECS" in out
        # above_ceiling の常時表示 + acoustics ブロック (null なら n/a 表示)
        assert "above_ceiling" in out
        assert "acoustics" in out


@pytest.mark.unit
class TestBackwardCompatV3:
    """v3 は v2 からの field 追加のみ (v2 の読み手と既存の手計算値を壊さない)。"""

    V2_ENCODER_FIELDS = frozenset(
        {
            "cross_utt_secs",
            "same_utt_secs",
            "gap_same_minus_cross",
            "ceiling",
            "floor",
            "normalized_transfer",
            "n_synth",
            "n_refs",
        }
    )

    def test_v2_fields_and_values_survive(self, wav_dirs_unique, patched_cli, tmp_path):
        baseline = {
            "schema": "zs-eval-v2",
            "encoders": {
                "campplus": {"cross_utt_secs": 0.33, "gap_same_minus_cross": 0.15}
            },
        }
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        rc, report = _run_v3_cli(
            wav_dirs_unique, tmp_path, ["--baseline-json", str(baseline_path)]
        )
        assert rc == 0
        assert report["schema"] == "zs-eval-v3"  # §8 の計画された pin 更新
        cam = report["encoders"]["campplus"]
        assert set(cam) >= self.V2_ENCODER_FIELDS
        # v2 の手計算値が v3 でも不変 (追加のみの互換)
        assert cam["cross_utt_secs"] == pytest.approx(SQRT2_INV / 2, abs=1e-6)
        assert cam["same_utt_secs"] == pytest.approx(0.5, abs=1e-6)
        assert cam["ceiling"] == pytest.approx(0.0, abs=1e-6)
        assert cam["floor"] == pytest.approx(-0.5, abs=1e-6)
        assert cam["normalized_transfer"] == pytest.approx(
            EXPECTED_NT_CAMPPLUS, abs=1e-6
        )
        comp = report["baseline_comparison"]
        assert {"goodhart_flag", "gap_widened_encoders", "deltas"} <= set(comp)
        # v2 baseline (音響ブロックなし) では acoustics Δ は null 明示 (§4.6)
        assert "acoustics" in comp
        assert comp["acoustics"] is None
