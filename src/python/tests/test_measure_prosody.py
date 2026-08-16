"""Tests for piper_train.tools.measure_prosody (E-3 韻律記述統計 + delta).

canonical 数式の出典: ``scripts/zs-quality-anatomy/anatomy.py`` (F0/エネルギー系、
pyin fmin=70/fmax=600/frame=2048/hop=256)。v10b plan §1 の実測 baseline
(GT std 47-74Hz / r2 std 29-41Hz) はこの設定で測られた。数値閾値は canonical
数式の再現実装に同一の合成信号を通した実測で事前検証済み (導出コメント参照)。

教訓① (絶対): 対象モジュールの全指標は評価専用 (EVAL-ONLY)。F0/エネルギー統計は
微分可能化が容易で「韻律 loss」への流用誘惑が最も強い — docs/spec/zs-eval-contract.md
§2 禁止事項 4 で恒久禁止 (S-2 の GT 参照 pitch predictor 回帰 loss のみ例外境界)。
本テストは「測る数学」を pin するだけで、pass/fail 判定 (事前登録閾値) はツールに
実装しない (測定と判定の分離)。

ヘルパは他テストファイルと共有ヘルパへ昇格せず複製する方針 (テスト間の暗黙結合を
避ける)。SR=22050、seed 固定。
"""

from __future__ import annotations

import numpy as np
import pytest

from piper_train.tools.acoustic_frames import analyze_frames
from piper_train.tools.measure_prosody import (
    prosody_delta,
    prosody_group_summary,
    prosody_stats,
)


SR = 22050


# ---------------------------------------------------------------------------
# 合成信号ヘルパ
# ---------------------------------------------------------------------------


def _white_noise(duration: float = 3.0, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(int(SR * duration))


def _vibrato_voice(
    duration: float = 3.0,
    f0_center: float = 330.0,
    dev_hz: float = 60.0,
    rate_hz: float = 1.0,
    n_harmonics: int = 8,
) -> np.ndarray:
    """f0(t) = f0_center + dev·sin(2π·rate·t) の倍音音声 (位相積分で合成)。

    rate=1Hz を既定とする: pyin の解析窓 2048 samples (93ms) 内の f0 変化が
    2π·rate·dev·0.093 ≈ 35Hz に収まり追従できる。rate=3Hz では窓内変化 ~50Hz
    超で推定が圧縮され median +15Hz / range -12Hz のバイアスを実測 (canonical
    再現での事前検証)。
    """
    t = np.arange(int(SR * duration)) / SR
    if rate_hz > 0 and dev_hz > 0:
        phase = (
            2
            * np.pi
            * (
                f0_center * t
                - dev_hz / (2 * np.pi * rate_hz) * np.cos(2 * np.pi * rate_hz * t)
            )
        )
    else:
        phase = 2 * np.pi * f0_center * t
    wav = np.zeros_like(t)
    for k in range(1, n_harmonics + 1):
        gain = 10 ** (-6.0 * np.log2(k) / 20) if k > 1 else 1.0
        wav += gain * np.sin(k * phase)
    return wav / np.abs(wav).max() * 0.5


def _chirp_voice(
    duration: float = 2.5,
    f_lo: float = 250.0,
    f_hi: float = 450.0,
    n_harmonics: int = 8,
) -> np.ndarray:
    """f0 が f_lo → f_hi へ線形に glide する倍音音声 (韻律レンジの既知カーブ)。"""
    t = np.arange(int(SR * duration)) / SR
    k_rate = (f_hi - f_lo) / duration
    phase = 2 * np.pi * (f_lo * t + 0.5 * k_rate * t**2)
    wav = np.zeros_like(t)
    for k in range(1, n_harmonics + 1):
        gain = 10 ** (-6.0 * np.log2(k) / 20) if k > 1 else 1.0
        wav += gain * np.sin(k * phase)
    return wav / np.abs(wav).max() * 0.5


def _assert_tree_equal(a, b, path: str = "$") -> None:
    """dict / list / ndarray / scalar / None を再帰的に厳密比較 (NaN==NaN 扱い)。"""
    if isinstance(a, dict):
        assert isinstance(b, dict), f"{path}: type mismatch {type(b)}"
        assert set(a) == set(b), f"{path}: key mismatch {set(a) ^ set(b)}"
        for k in a:
            _assert_tree_equal(a[k], b[k], f"{path}.{k}")
    elif a is None:
        assert b is None, f"{path}: {b!r} != None"
    elif isinstance(a, str):
        assert a == b, f"{path}: {a!r} != {b!r}"
    else:
        np.testing.assert_array_equal(np.asarray(a), np.asarray(b), err_msg=path)


# ---------------------------------------------------------------------------
# E-3: 韻律統計
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProsodyStats:
    def test_vibrato_f0_std_matches_first_principles(self):
        """既知 F0 カーブ (vibrato 330±60Hz @1Hz) で統計が解析値と一致する。

        導出 (正弦振動の arcsine 分布):
        - std = dev/√2 = 60/√2 = 42.43Hz (正弦の実効値)
        - p5-p95 range = 2·dev·sin(0.45π) = 118.54Hz
          (P(sinθ≤x) = 1/2 + arcsin(x)/π → p95 は arcsin(x)=0.45π)
        - median = f0_center = 330Hz (対称分布)
        canonical 再現 (pyin fmin=70/fmax=600/frame=2048/hop=256) での実測:
        std=41.95 / range=117.1 / med=331.1。許容幅 (±5/±12/±8) は仕様 §6.4 の
        登録値で、pyin の推定粒度・端点効果を含む。
        """
        fa = analyze_frames(_vibrato_voice(), SR)
        assert fa is not None
        stats = prosody_stats(fa)
        assert stats is not None
        assert stats["f0_std_hz"] == pytest.approx(60.0 / np.sqrt(2.0), abs=5.0)
        assert stats["f0_range_p5_p95_hz"] == pytest.approx(
            2 * 60.0 * np.sin(0.45 * np.pi), abs=12.0
        )
        assert stats["f0_median_hz"] == pytest.approx(330.0, abs=8.0)

    def test_chirp_glide_range_matches_first_principles(self):
        """線形 chirp (250→450Hz) で range/std が一様分布の解析値と一致する。

        導出 (一様分布 span=200Hz):
        - p5-p95 range = 0.9·span = 180Hz
        - std = span/√12 = 57.74Hz
        canonical 再現での実測: range=180.3 / std=57.89 (双方 0.3% 以内)。
        許容 ±20 (仕様 §6.4) / ±6 (std は range と同率の 10% 幅)。
        """
        fa = analyze_frames(_chirp_voice(), SR)
        assert fa is not None
        stats = prosody_stats(fa)
        assert stats is not None
        assert stats["f0_range_p5_p95_hz"] == pytest.approx(180.0, abs=20.0)
        assert stats["f0_std_hz"] == pytest.approx(200.0 / np.sqrt(12.0), abs=6.0)

    def test_flat_f0_near_zero_std(self):
        """定常 f0=330Hz → std ~0 (平板韻律の検出 = 指標のゼロ点)。

        v10b の課題「韻律の平板さ」を数値化する側のゼロ点。canonical 再現での
        実測: std=0.68 / range=1.9 (pyin の量子化粒度のみ)。閾値 5 / 15Hz は
        仕様 §6.4 (実測の 7 倍マージン、gate 登録値 std≥45Hz とは 9 倍離れる)。
        """
        fa = analyze_frames(_vibrato_voice(duration=2.5, dev_hz=0.0), SR)
        assert fa is not None
        stats = prosody_stats(fa)
        assert stats is not None
        assert stats["f0_std_hz"] < 5.0
        assert stats["f0_range_p5_p95_hz"] < 15.0

    def test_delta_is_signed_synth_minus_real(self):
        """prosody_delta の向きと符号の pin: delta = synth − real (単純差)。

        負の f0_std delta = 「synth が real より平板」— v10b の報告文脈で
        符号を取り違えると診断が反転するため exact に pin する。null-safe
        (どちらか None → None) も仕様 §3.3。
        """
        synth = {
            "f0_median_hz": 250.0,
            "f0_std_hz": 30.0,
            "f0_range_p5_p95_hz": 100.0,
            "voiced_energy_std_db": None,
        }
        real = {
            "f0_median_hz": 240.0,
            "f0_std_hz": 50.0,
            "f0_range_p5_p95_hz": 160.0,
            "voiced_energy_std_db": 3.0,
        }
        delta = prosody_delta(synth, real)
        assert delta["f0_std_hz"] == pytest.approx(-20.0)  # synth の方が平板
        assert delta["f0_range_p5_p95_hz"] == pytest.approx(-60.0)
        assert delta["f0_median_hz"] == pytest.approx(+10.0)  # synth の方が高い
        assert delta["voiced_energy_std_db"] is None  # null-safe

    def test_group_summary_is_median(self):
        """グループ集計 = 各統計の median across clips の exact pin (仕様 §3.3)。"""
        stats = [
            {"f0_std_hz": 30.0, "f0_median_hz": 200.0},
            {"f0_std_hz": 50.0, "f0_median_hz": 210.0},
            {"f0_std_hz": 90.0, "f0_median_hz": None},
        ]
        summary = prosody_group_summary(stats)
        assert summary["f0_std_hz"] == pytest.approx(50.0)  # median (外れ値耐性)
        assert summary["f0_median_hz"] == pytest.approx(205.0)  # None は除外
        assert summary["n_clips"] == 3

    def test_unvoiced_only_input_graceful_none(self):
        """有声フレームゼロ (白色雑音) → 例外を出さず None (graceful degradation)。

        canonical 再現での実測: pyin は白色雑音 1s で voiced=0 フレーム →
        prosody_stats は voiced <10 で None を返す (仕様 §3.2)。
        """
        fa = analyze_frames(_white_noise(duration=1.0, seed=5), SR)
        assert fa is not None  # 1s ≥ 0.5s なので解析自体は成立
        assert prosody_stats(fa) is None

    def test_prosody_stats_deterministic(self):
        """同一入力 2 回 → 同一出力 (manifest への数値 pin の前提条件)。"""
        wav = _vibrato_voice(duration=2.0)
        fa1 = analyze_frames(wav, SR)
        fa2 = analyze_frames(wav.copy(), SR)
        assert fa1 is not None and fa2 is not None
        s1 = prosody_stats(fa1)
        s2 = prosody_stats(fa2)
        assert s1 is not None and s2 is not None
        _assert_tree_equal(s1, s2)
