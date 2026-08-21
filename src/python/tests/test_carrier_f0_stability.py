"""v11 A′: 予測 F0 の frame-rate ノイズ (ジッタ + V/UV 明滅) と担体の統合契約。

smoke arm H (2026-08-20) のすり抜けの再発防止。既存の ``test_carrier_head.py``
は担体に「きれいな一定 F0」しか与えておらず、実パイプラインで担体が食うのは
F0 predictor の出力だった。predictor の入力は attn 展開した enc_p hidden =
symbol 格子 (JA 実測 ~1.6 frame/symbol) なので、その誤差は自然韻律
(≲10Hz 変調) ではなく **frame-rate のジッタ + V/UV 明滅**として現れる
(instance 実測: median 26Hz/frame、孤立 1-frame unvoiced が数 frame おき)。
担体は F0 を忠実に FM/AM 描画するため、このノイズは倍音 m で m 倍に拡大され
調波構造を潰した (comb-HNR 5.2dB。F0 58ms 平滑のみで 13.2dB、V/UV 込み一定で
46dB に回復 — 設計 doc §5.3 E2 は静的 cent シフトのみ検証しており動的ジッタが
盲点)。

固定する契約:

* **実パイプライン相当の統合**: full decoder forward + 一定 F0 で出力調波が
  m·F0 の位置に立ち comb-HNR ≥ 10dB (Phase D gate と同値)。
* **予測 F0 の構造安定化**: ``_predicted_f0_hz`` (use_carrier_head 時のみ) が
  固定 58ms box 平滑 + V/UV 多数決を適用し、predictor ノイズが担体に届かない。
* **GT F0 (teacher forcing) と v10b (use_carrier_head=False) は bit 不変**。
* **安定化込みで predictor ノイズ下でも comb-HNR ≥ 10dB** (すり抜けた穴を
  E2E で塞ぐ)。
"""

from __future__ import annotations

import math

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import PQMF, MBiSTFTGenerator  # noqa: E402
from piper_train.vits.models import SynthesizerTrn  # noqa: E402


SR = 22050
HOP = 256  # frame 格子 hop → 86.133 Hz
HEAD_UP = 16


# ---------------------------------------------------------------------------
# 測定ヘルパ (test_carrier_head.py と同方式の comb-HNR)
# ---------------------------------------------------------------------------


def comb_hnr_db(
    wav: np.ndarray,
    f0_frames: np.ndarray,
    band: tuple[float, float] = (1000.0, 3000.0),
    n_fft: int = 2048,
    fft_hop: int = 512,
) -> float:
    """voiced フレームの 調波 bin 電力 / 中間 bin 電力 [dB]。

    窓長は canonical プロトコル (``measure_comb_hnr``: n_fft 2048) に合わせる
    — F0 が時変する信号では窓内の F0 移動が smear になるため、窓長は閾値の
    一部 (4096 だと同一信号で 3-4dB 厳しく出る)。
    """
    wav = np.asarray(wav, dtype=np.float64).reshape(-1)
    win = np.hanning(n_fft + 1)[:n_fft]
    df = SR / n_fft
    ph, pm = 0.0, 0.0
    used = 0
    for start in range(0, len(wav) - n_fft, fft_hop):
        center = start + n_fft // 2
        fi = min(int(center // HOP), len(f0_frames) - 1)
        f0v = float(f0_frames[fi])
        if f0v < 50.0:
            continue
        spec = np.abs(np.fft.rfft(wav[start : start + n_fft] * win)) ** 2
        m_lo = max(1, int(np.ceil(band[0] / f0v)))
        m_hi = int(np.floor(band[1] / f0v))
        if m_hi < m_lo:
            continue
        for m in range(m_lo, m_hi + 1):
            bh = round(m * f0v / df)
            bm = round((m + 0.5) * f0v / df)
            if bm + 1 >= len(spec):
                continue
            ph += spec[bh - 1 : bh + 2].sum()
            pm += spec[bm - 1 : bm + 2].sum()
        used += 1
    if pm <= 0 or used == 0:
        return float("nan")
    return 10.0 * math.log10(ph / pm)


def spectral_peaks(wav: np.ndarray, fmax: float = 2700.0, n_peaks: int = 8):
    """パワースペクトルの局所ピーク上位 n の周波数 [Hz] (昇順)。"""
    wav = np.asarray(wav, dtype=np.float64).reshape(-1)
    spec = np.abs(np.fft.rfft(wav * np.hanning(len(wav)))) ** 2
    freqs = np.fft.rfftfreq(len(wav), 1.0 / SR)
    sel = (freqs > 100.0) & (freqs <= fmax)
    spec, freqs = spec[sel], freqs[sel]
    lm = np.zeros_like(spec, dtype=bool)
    lm[1:-1] = (spec[1:-1] > spec[:-2]) & (spec[1:-1] > spec[2:])
    idx = np.argsort(spec * lm)[::-1][:n_peaks]
    return sorted(float(freqs[i]) for i in idx)


def _gen(seed: int = 0) -> MBiSTFTGenerator:
    torch.manual_seed(seed)
    return MBiSTFTGenerator(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        gin_channels=512,
        use_f0_path=True,
        use_carrier_head=True,
    )


BASE = {
    "n_vocab": 40,
    "spec_channels": 513,
    "segment_size": 32,
    "inter_channels": 192,
    "hidden_channels": 192,
    "filter_channels": 256,
    "n_heads": 2,
    "n_layers": 2,
    "kernel_size": 3,
    "p_dropout": 0.0,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 256,
    "upsample_kernel_sizes": (16, 16),
    "n_speakers": 4,
    "gin_channels": 512,
    "prosody_dim": 0,
    "use_f0_path": True,
}


def _model(seed: int = 0, **overrides) -> SynthesizerTrn:
    torch.manual_seed(seed)
    kwargs = dict(BASE)
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


def _predictor_grade_noise(T: int, seed: int = 3):
    """undertrained F0 predictor の出力を模す敵対的 (log_f0, vuv_logit)。

    smoke arm H 実測に合わせる: log 域 σ=0.08 の i.i.d. ジッタ (≈±18Hz、
    frame 間 |diff| median ~17Hz) + 7 frame おきの孤立 1-frame unvoiced。
    """
    g = torch.Generator().manual_seed(seed)
    log_f0 = math.log(220.0) + 0.08 * torch.randn(1, 1, T, generator=g)
    vuv_logit = torch.full((1, 1, T), 4.0)
    vuv_logit[:, :, ::7] = -4.0
    return log_f0, vuv_logit


def _voiced_runs(f0: np.ndarray) -> list[int]:
    """voiced/unvoiced の run-length 列 (先頭 run から交互)。"""
    v = (f0 > 1.0).astype(np.int8)
    runs: list[int] = []
    count = 1
    for a, b in zip(v[:-1], v[1:], strict=True):
        if a == b:
            count += 1
        else:
            runs.append(count)
            count = 1
    runs.append(count)
    return runs


# ---------------------------------------------------------------------------
# (i) 実パイプライン相当の統合 pin: full forward + 一定 F0 → 調波が m·F0 に立つ
# ---------------------------------------------------------------------------


def test_full_decoder_constant_f0_draws_harmonics_at_multiples():
    """担体を鳴らした full forward の出力ピークが 220·m に立ち comb ≥ 10dB。

    smoke デバッグ時のローカル再現実験 (comb 51dB、全ピーク m·220±1Hz) の
    テスト化 — CarrierHead 単体ではなく forward 統合 (x_frame 格子 / f0 配線 /
    subband 合成) を貫通で固定する。
    """
    gen = _gen()
    gen.eval()
    T = int(6.0 * SR / HOP)
    torch.manual_seed(1)
    z = torch.randn(1, 192, T)
    g = torch.randn(1, 512, 1)
    f0 = torch.full((1, 1, T), 220.0)
    zero_noise = torch.zeros(1, 18, T * HEAD_UP)
    with torch.no_grad():
        gen.carrier_head.gain_net.weight.normal_(0.0, 0.5)
        full, _ = gen(z, g=g, f0=f0, carrier_noise=zero_noise)
    wav = full[0, 0].numpy()

    assert comb_hnr_db(wav, f0[0, 0].numpy()) >= 10.0
    peaks = spectral_peaks(wav)
    assert peaks, "no spectral peaks found"
    for freq in peaks:
        mult = freq / 220.0
        assert abs(mult - round(mult)) < 0.05, (
            f"peak at {freq:.1f}Hz is not a 220Hz harmonic (x{mult:.3f})"
        )


# ---------------------------------------------------------------------------
# (ii) 予測 F0 の構造安定化 (_predicted_f0_hz、use_carrier_head 時のみ)
# ---------------------------------------------------------------------------


def test_stabilizer_bounds_the_frame_jitter_of_predicted_f0():
    """予測 F0 の frame 間ジッタが担体に届く前に有界化される。

    入力 (predictor ノイズ模擬) は voiced 内 |diff| median ~17Hz。58ms box
    平滑後は ~3.4Hz (理論値 0.674·√2·σ/k) — 契約は ≤ 5Hz。自然な韻律遷移
    (アクセント ~100ms スケール) はこの平滑で保存される。
    """
    model = _model(use_carrier_head=True)
    log_f0, vuv_logit = _predictor_grade_noise(T=400)
    f0 = model._predicted_f0_hz(log_f0, vuv_logit)[0, 0].numpy()

    voiced = f0 > 1.0
    d = np.abs(np.diff(f0))
    both = voiced[1:] & voiced[:-1]
    assert both.sum() > 100
    med = float(np.median(d[both]))
    assert med <= 5.0, f"stabilized F0 still jitters: median |diff| = {med:.1f}Hz"


def test_stabilizer_removes_isolated_single_frame_vuv_flips():
    """孤立 1-frame の V/UV 明滅 (担体のぶつ切り = AM 側波帯) が除去される。

    instance 実測で constant_voiced (明滅あり) 15.4dB vs constant_all 46dB —
    明滅は担体の調波保証を ~30dB 損なう支配的要因。真の障害音 (≥3 frame の
    閉鎖) は多数決 (k=5) で保存される。
    """
    model = _model(use_carrier_head=True)
    log_f0, vuv_logit = _predictor_grade_noise(T=400)
    f0 = model._predicted_f0_hz(log_f0, vuv_logit)[0, 0].numpy()

    runs = _voiced_runs(f0)
    assert min(runs[1:-1], default=5) >= 2, (
        f"single-frame V/UV runs survived stabilization: runs={runs[:20]}..."
    )

    # 真の unvoiced 区間 (≥3 frame) は保存される
    vuv_long = torch.full((1, 1, 60), 4.0)
    vuv_long[:, :, 20:26] = -4.0  # 6 frame の閉鎖
    f0_long = model._predicted_f0_hz(torch.full((1, 1, 60), math.log(220.0)), vuv_long)
    kept = (f0_long[0, 0, 21:25] < 1.0).all()
    assert bool(kept), "a genuine >=3-frame unvoiced closure was voiced over"


def test_gt_f0_teacher_forcing_path_is_untouched():
    """GT F0 (teacher forcing) は自然韻律そのもの — 安定化を通さず bit 不変。"""
    model = _model(use_carrier_head=True)
    T = 64
    torch.manual_seed(2)
    f0_gt = (200.0 + 30.0 * torch.randn(1, 1, T)).clamp(min=0.0)
    f0_gt[:, :, ::5] = 0.0
    log_f0, vuv_logit = _predictor_grade_noise(T)
    out = model._f0_for_decoder(f0_gt, log_f0, vuv_logit, f0_pred_prob=0.0)
    torch.testing.assert_close(out, f0_gt, atol=0, rtol=0)


def test_v10b_predicted_f0_is_bit_compatible_without_the_carrier():
    """use_carrier_head=False (v10b S-2) では従来式 exp(clamp)·vuv と bit 一致。

    v11 の全 opt-in flag に共通の「off = v10b bit 互換」契約 — 安定化は
    担体 (F0 を忠実に FM する消費者) がいる時だけ入る。
    """
    model = _model(use_carrier_head=False)
    log_f0, vuv_logit = _predictor_grade_noise(T=100)
    got = model._predicted_f0_hz(log_f0, vuv_logit)
    expected = torch.exp(log_f0.clamp(min=math.log(50.0), max=math.log(1100.0))) * (
        torch.sigmoid(vuv_logit) > 0.5
    ).to(log_f0.dtype)
    torch.testing.assert_close(got, expected, atol=0, rtol=0)


# ---------------------------------------------------------------------------
# (iii) E2E: predictor ノイズ下でも担体の comb が立つ (すり抜けた穴の閉鎖)
# ---------------------------------------------------------------------------


def test_carrier_comb_survives_an_undertrained_f0_predictor():
    """predictor ノイズ → _predicted_f0_hz → dec full forward で担体 comb ≥ 10dB。

    これが smoke arm H で落ちた実パイプライン相当の統合経路 (unit test は
    きれいな一定 F0 しか通しておらず green のまますり抜けた)。安定化なしでは
    ジッタが倍音 m で拡大され担体でも 2.7dB に潰れる (instance 実測
    actual 5.2dB と同水準)。安定化後は 14.2dB (instance smooth5 13.2dB と
    同水準) — gate 10dB に対し red/green とも十分なマージン。

    担体寄与は「gains zero の forward との差分」で単離する — ランダム初期化の
    band1-3 / σ head は untrained junk で中間 bin を埋めるが、実モデルでは
    recon 損失の監督下にあり、ここで固定したい契約は担体枝の構造だけ。差分は
    forward 全配線 (x_frame 格子 → gain_net → 描画 → PQMF) を通る。
    """
    model = _model(use_carrier_head=True)
    model.eval()
    T = int(6.0 * SR / HOP)
    log_f0, vuv_logit = _predictor_grade_noise(T)
    with torch.no_grad():
        f0_dec = model._predicted_f0_hz(log_f0, vuv_logit)

    torch.manual_seed(1)
    z = torch.randn(1, 192, T)
    g = torch.randn(1, 512, 1)
    zero_noise = torch.zeros(1, 18, T * HEAD_UP)
    with torch.no_grad():
        model.dec.carrier_head.gain_net.weight.zero_()
        model.dec.carrier_head.gain_net.bias.zero_()
        muted, _ = model.dec(z, g=g, f0=f0_dec, carrier_noise=zero_noise)
        model.dec.carrier_head.gain_net.weight.normal_(0.0, 0.5)
        active, _ = model.dec(z, g=g, f0=f0_dec, carrier_noise=zero_noise)

    carrier = (active - muted)[0, 0].numpy()
    hnr = comb_hnr_db(carrier, f0_dec[0, 0].numpy())
    assert hnr >= 10.0, f"carrier comb collapsed under predictor noise: {hnr:.2f}dB"
