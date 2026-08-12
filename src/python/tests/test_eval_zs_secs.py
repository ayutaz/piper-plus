"""Tests for piper_train.tools.eval_zs_secs (cross-utt SECS 評価ハーネス).

背景 (docs/design/zero-shot-v10-roadmap.md A-1e): same-utt SECS は SCL Goodhart
で膨張する (0.775 誤報の既知事故) ため、cross-utterance SECS + ceiling/floor
正規化転写率を 1 コマンドで出す標準ツールを新設した。本テストは
compute_secs_report の数学 (手計算一致) と CLI 契約 (JSON 構造 / exclude-ref
除外 / floor 無し null) を pin する。
"""

from __future__ import annotations

import json
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
    """synth/speaker/floor の wav ディレクトリ (中身は空ファイルで十分)。"""
    dirs = {}
    for name, stems in (
        ("synth", ["s1", "s2"]),
        ("spk", ["r1", "r2", "r3"]),
        ("floor", ["f1"]),
    ):
        d = tmp_path / name
        d.mkdir()
        for stem in stems:
            (d / f"{stem}.wav").write_bytes(b"")
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
