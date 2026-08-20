"""v11 A′: 担体化 harmonic-plus-noise head の構造保証テスト。

docs/design/zero-shot-v11-harmonic-head-design.md §4 (gaming 封鎖) / §5
(プロトタイプ実測 = ここの期待値) / §8 R4 (conj 罠の fixture 化)。

固定する契約 (いずれも「学習圧力ではなく構造」の検証なので、モデルは
ランダム初期化 + 敵対的入力で測る):

* **構造 comb-HNR**: ゲインが敵対的 (i.i.d. N(0,1)) でも担体枝の
  comb-HNR@1-3kHz は F0=220Hz で ≥10dB / F0=120Hz で ≥8dB
  (実測 42.4 / 35.6dB — 設計 doc §5.1。frame 格子 + 固定 Hann k=5 平滑が
  保証の本体)。
* **alias 相殺 (conj 罠)**: 解析重み conj(H_k) の 2-band 描画で band 端
  (2756.25Hz) の鏡像 spur ≤ −90dB。重みを H_k のまま使う (Im 符号反転) と
  alias が強め合う — スパイクで実際に踏んだバグの regression fixture
  (設計 doc §5.2 / §8 R4)。
* **noise 枝はトーンを偽造できない**: F0 同期 AM という最悪ケースの σ でも
  comb-HNR ≤ 2dB (実測 0.19-0.54dB — バイパス経路 #2 の閉鎖)。
* **「無視 = 音が出ない」**: 担体ゲイン 0 では voiced 帯域 (≤2.7kHz) に
  エネルギーを出す経路が存在しない (band1-3 自由 head は PQMF stopband
  −99dB で構造的に届かない)。concat 注入 (S-2c) との本質的な差。
* **F0 predictor への勾配遮断**: recon 経路の勾配は F0 predictor に届かない
  (FastPitch 型 — predictor は GT 回帰のみで学習)。
* **default off = v10b bit 互換**: state_dict / forward とも無影響。
"""

from __future__ import annotations

import math

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import (  # noqa: E402
    PQMF,
    CarrierHead,
    MBiSTFTGenerator,
    carrier_source_regularization,
)
from piper_train.vits.models import SynthesizerTrn  # noqa: E402


SR = 22050
HOP = 256  # frame 格子 hop → 86.133 Hz
SUB_UP = 64  # frame → subband サンプル (SR/4)
HEAD_UP = 16  # frame → head 格子
BAND_EDGE = SR / 4 / 2.0  # 2756.25 Hz


# ---------------------------------------------------------------------------
# 測定ヘルパ (診断 doc と同方式の comb-HNR。numpy のみ — 微分不能)
# ---------------------------------------------------------------------------


def comb_hnr_db(
    wav: np.ndarray,
    f0_frames: np.ndarray,
    band: tuple[float, float] = (1000.0, 3000.0),
    n_fft: int = 4096,
    fft_hop: int = 1024,
) -> float:
    """voiced フレームの 調波 bin 電力 / 中間 bin 電力 [dB]。"""
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


def band_energy(wav: np.ndarray, lo: float, hi: float) -> float:
    wav = np.asarray(wav, dtype=np.float64).reshape(-1)
    spec = np.abs(np.fft.rfft(wav)) ** 2
    freqs = np.fft.rfftfreq(len(wav), 1.0 / SR)
    sel = (freqs >= lo) & (freqs < hi)
    return float(spec[sel].sum())


_PQMF = PQMF()


def _fullband_from_bands(s0: torch.Tensor, s1: torch.Tensor) -> np.ndarray:
    """(band0, band1) の subband 波形 → fullband (band2/3 = 0)。"""
    z = torch.zeros(s0.size(0), 4, s0.size(-1))
    z[:, 0:1] = s0
    z[:, 1:2] = s1
    with torch.no_grad():
        return _PQMF.synthesis(z)[0, 0].numpy()


def _head(M: int = 32, seed: int = 0) -> CarrierHead:
    torch.manual_seed(seed)
    head = CarrierHead(in_channels=256, pqmf=_PQMF, n_harmonics=M)
    head.eval()
    return head


# ---------------------------------------------------------------------------
# (i) 構造 comb-HNR — 敵対的 i.i.d. ゲインでも comb が立つ
# ---------------------------------------------------------------------------


def _adversarial_comb_hnr(f0_hz: float, seconds: float = 6.0) -> float:
    head = _head()
    T = int(seconds * SR / HOP)
    f0 = torch.full((1, 1, T), f0_hz)
    vals = []
    for seed in range(3):
        g = torch.Generator().manual_seed(seed)
        raw = torch.randn(1, 2 * head.n_harmonics, T, generator=g)
        with torch.no_grad():
            s0, s1 = head.synthesize_from_gains(raw, f0)
        wav = _fullband_from_bands(s0, s1)
        vals.append(comb_hnr_db(wav, f0[0, 0].numpy()))
    vals.sort()
    return vals[1]  # median of 3 seeds


def test_adversarial_iid_gains_keep_comb_structure_at_f0_220():
    """ゲインが最悪 (i.i.d. ランダム) でも comb-HNR@1-3kHz ≥ 10dB (実測 ~42dB)。

    これが「A3 を学習圧力に頼らず構造で遮断」の中心的検証 — 担体枝は
    調波間にエネルギーを置く自由度を持たない。
    """
    assert _adversarial_comb_hnr(220.0) >= 10.0


def test_adversarial_iid_gains_keep_comb_structure_at_low_f0_120():
    """低 F0 (120Hz、調波中間点 60Hz) でも固定 Hann k=5 平滑で ≥ 8dB
    (実測 ~35.6dB。平滑なしだと 12.9dB、F0=90 では 5.2dB に落ちる —
    設計 doc §5.1 の格子 + 平滑が保証の本体)。
    """
    assert _adversarial_comb_hnr(120.0) >= 8.0


# ---------------------------------------------------------------------------
# (ii) band 端 alias 相殺と conj(H_k) regression (設計 doc §8 R4)
# ---------------------------------------------------------------------------


def _tone_alias_ratio_db(head: CarrierHead, f: float, m: int = 12) -> float:
    """単一倍音 (m 次、f = m·F0) を描画し、鏡像 spur / 主峰 [dB] を返す。"""
    T = int(6.0 * SR / HOP)
    f0 = torch.full((1, 1, T), f / m)
    raw = torch.zeros(1, 2 * head.n_harmonics, T)
    raw[0, m - 1] = 1.0  # a_m = 1 (定数はゲイン平滑で不変)
    with torch.no_grad():
        s0, s1 = head.synthesize_from_gains(raw, f0)
    wav = _fullband_from_bands(s0, s1)
    spec = np.abs(np.fft.rfft(wav * np.hanning(len(wav)))) ** 2
    freqs = np.fft.rfftfreq(len(wav), 1.0 / SR)
    f_alias = 2 * BAND_EDGE - f

    def peak_db(fc: float, half: float = 40.0) -> float:
        sel = (freqs > fc - half) & (freqs < fc + half)
        return 10.0 * math.log10(spec[sel].max() + 1e-30)

    return peak_db(f_alias) - peak_db(f)


def test_band_edge_alias_is_cancelled_below_minus_90db():
    """2-band 解析重み描画で band 端をまたぐ倍音の鏡像 spur ≤ −90dB。

    素朴 band0 単独描画は f=2700Hz で −1.4dB (設計 doc §5.2) — A′ 修正の
    根拠であり、この閾値が緩むと A3 帯域上部 (2.2-3kHz) が使えなくなる。
    """
    head = _head()
    for f in (2400.0, 2500.0, 2600.0, 2700.0, 2800.0, 2900.0):
        ratio = _tone_alias_ratio_db(head, f)
        assert ratio <= -90.0, f"alias at {f}Hz: {ratio:.1f} dB"


def test_wrong_conjugation_makes_aliases_reinforce():
    """conj(H_k) を H_k に取り違える (Im 符号反転) と alias が強め合う。

    F.conv1d は相関なので解析出力の複素重みは conj(H_k) — スパイク中に
    実際に踏んだ罠 (+16dB、設計 doc §5.2 / §9 E1c) の regression fixture。
    """
    good = _head()
    bad = _head()
    with torch.no_grad():
        bad.h_table[1].neg_()  # ImH0 → −ImH0 (= conj を外す)
        bad.h_table[3].neg_()  # ImH1
    f = 2700.0
    good_ratio = _tone_alias_ratio_db(good, f)
    bad_ratio = _tone_alias_ratio_db(bad, f)
    assert bad_ratio > -20.0, f"wrong-sign alias unexpectedly small: {bad_ratio}"
    assert bad_ratio - good_ratio > 50.0


# ---------------------------------------------------------------------------
# (iii) noise 枝はトーンを構造的に偽造できない (バイパス #1/#2 の閉鎖)
# ---------------------------------------------------------------------------


def _gen(**overrides) -> MBiSTFTGenerator:
    torch.manual_seed(0)
    kwargs = {
        "initial_channel": 192,
        "resblock": "2",
        "resblock_kernel_sizes": (3, 5, 7),
        "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 256,
        "upsample_kernel_sizes": (16, 16),
        "gin_channels": 512,
        "use_f0_path": True,
    }
    kwargs.update(overrides)
    return MBiSTFTGenerator(**kwargs)


@pytest.mark.parametrize("f0_hz", [220.0, 320.0])
def test_noise_branch_cannot_forge_tones_even_with_f0_synced_sigma(f0_hz):
    """σ を F0 同期 AM (循環定常ノイズ = 最悪ケース) にしても comb-HNR ≤ 2dB。

    frame ごと独立な複素位相は OLA 後もコヒーレンスを持たない — noise 枝が
    担体の代わりに voiced 調波を出す道はない (実測 0.19-0.54dB、§5.1 #4)。
    """
    gen = _gen(use_carrier_head=True)
    gen.eval()
    T = int(6.0 * SR / HOP)
    t_head = torch.arange(T * HEAD_UP, dtype=torch.float32)
    head_rate = SR / (HOP / HEAD_UP)
    am = 1.0 + torch.cos(2 * math.pi * f0_hz * t_head / head_rate)
    log_sigma = torch.log(am.clamp(min=1e-6)).reshape(1, 1, -1).expand(1, 9, -1)
    torch.manual_seed(3)
    noise = torch.randn(1, 18, T * HEAD_UP)
    with torch.no_grad():
        wav0 = gen.carrier_noise_band0(log_sigma.contiguous(), noise)
    wav0 = wav0.reshape(1, 1, -1)[..., : T * SUB_UP]
    wav = _fullband_from_bands(wav0, torch.zeros_like(wav0))
    hnr = comb_hnr_db(wav, np.full(T, f0_hz))
    assert hnr <= 2.0, f"noise branch forged a comb: {hnr:.2f} dB"


# ---------------------------------------------------------------------------
# hard cap / 固定平滑 (構造要素が学習で外せないこと)
# ---------------------------------------------------------------------------


def test_harmonics_above_the_3khz_hard_cap_are_structurally_silent():
    head = _head()
    T = 100
    f0 = torch.full((1, 1, T), 250.0)
    raw = torch.zeros(1, 2 * head.n_harmonics, T)
    raw[0, 12] = 100.0  # m=13 → 3250Hz > f_max=3000 (mask=0、taper 外)
    with torch.no_grad():
        s0, s1 = head.synthesize_from_gains(raw, f0)
    assert float(s0.abs().max()) == 0.0
    assert float(s1.abs().max()) == 0.0


def test_carrier_is_hard_gated_by_vuv():
    head = _head()
    T = 100
    f0 = torch.zeros(1, 1, T)  # 全 unvoiced
    raw = torch.ones(1, 2 * head.n_harmonics, T)
    with torch.no_grad():
        s0, s1 = head.synthesize_from_gains(raw, f0)
    assert float(s0.abs().max()) == 0.0
    assert float(s1.abs().max()) == 0.0


def test_gain_smoothing_and_tables_are_fixed_buffers():
    """平滑 Hann / H_k テーブルは buffer (学習不可) — モデルが構造保証を
    学習で外せないこと。学習パラメータは gain_net のみ。"""
    head = _head()
    param_names = {n for n, _ in head.named_parameters()}
    assert param_names == {"gain_net.weight", "gain_net.bias"}
    buffer_names = {n for n, _ in head.named_buffers()}
    assert {"smooth_w", "m_idx", "h_table"} <= buffer_names
    # 平滑は DC gain 1 (定数ゲインを変えない)
    assert torch.allclose(head.smooth_w.sum(dim=-1), torch.ones(64, 1))


# ---------------------------------------------------------------------------
# (vi) 「無視 = 音が出ない」 — 担体ゲイン 0 で voiced 帯域が構造的に無音
# ---------------------------------------------------------------------------


def test_ignoring_the_carrier_silences_the_voiced_band():
    """担体ゲイン 0 (+ noise 0) では ≤1.5kHz にエネルギーを出す経路がない。

    band1-3 の自由 head は PQMF stopband (−99dB) で構造的に届かない
    (設計 doc §4.1 #5)。これが concat 注入 (S-2c、係数 0 で F0 と無関係な
    出力が可能 = v10b smoke の追従率 0.0) との本質的な差【設計 doc §6】。
    """
    gen = _gen(use_carrier_head=True)
    gen.eval()
    T = 172
    torch.manual_seed(1)
    z = torch.randn(1, 192, T)
    g = torch.randn(1, 512, 1)
    f0 = torch.full((1, 1, T), 220.0)
    zero_noise = torch.zeros(1, 18, T * HEAD_UP)

    with torch.no_grad():
        gen.carrier_head.gain_net.weight.zero_()
        gen.carrier_head.gain_net.bias.zero_()
        muted, _ = gen(z, g=g, f0=f0, carrier_noise=zero_noise)
        gen.carrier_head.gain_net.weight.normal_(0.0, 0.5)
        active, _ = gen(z, g=g, f0=f0, carrier_noise=zero_noise)

    muted_wav = muted[0, 0].numpy()
    active_wav = active[0, 0].numpy()
    muted_ratio = band_energy(muted_wav, 100.0, 1500.0) / band_energy(
        muted_wav, 100.0, SR / 2
    )
    active_ratio = band_energy(active_wav, 100.0, 1500.0) / band_energy(
        active_wav, 100.0, SR / 2
    )
    assert muted_ratio < 1e-3, f"voiced band leaked without carrier: {muted_ratio}"
    assert active_ratio > 100 * muted_ratio


# ---------------------------------------------------------------------------
# (iv) default off = v10b bit 互換
# ---------------------------------------------------------------------------


SEGMENT_FRAMES = 32

BASE = {
    "n_vocab": 40,
    "spec_channels": 513,
    "segment_size": SEGMENT_FRAMES,
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
}


def _model(seed: int = 0, **overrides) -> SynthesizerTrn:
    torch.manual_seed(seed)
    kwargs = dict(BASE)
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


def _batch(batch: int = 2, phonemes: int = 12, frames: int = 64, seed: int = 1):
    g = torch.Generator().manual_seed(seed)
    x = torch.randint(1, 40, (batch, phonemes), generator=g)
    x_lengths = torch.full((batch,), phonemes, dtype=torch.long)
    spec = torch.randn(batch, 513, frames, generator=g).abs()
    spec_lengths = torch.full((batch,), frames, dtype=torch.long)
    emb = torch.nn.functional.normalize(torch.randn(batch, 192, generator=g), dim=-1)
    return x, x_lengths, spec, spec_lengths, emb


def _f0(batch: int = 2, frames: int = 64, hz: float = 210.0):
    f0 = torch.full((batch, 1, frames), hz)
    f0[:, :, ::5] = 0.0
    return f0


def test_off_by_default_is_bit_compatible_with_v10b():
    """use_carrier_head=False (default) は構築 RNG・state_dict・forward の
    全てで無影響 — v10b (S-2) の ckpt / 挙動と bit 互換。"""
    m_default = _model(use_f0_path=True)
    m_explicit = _model(use_f0_path=True, use_carrier_head=False)

    sd_a, sd_b = m_default.state_dict(), m_explicit.state_dict()
    assert list(sd_a.keys()) == list(sd_b.keys())
    assert not any("carrier" in k for k in sd_a)
    for k in sd_a:
        torch.testing.assert_close(sd_a[k], sd_b[k], atol=0, rtol=0)

    # S-2c (head_proj / phase_template) は default では従来どおり存在
    assert hasattr(m_default.dec, "head_proj")
    assert m_default.dec.subband_conv_post.out_channels == 4 * (16 + 2)

    for m in (m_default, m_explicit):
        m.train()
    args = _batch()
    torch.manual_seed(7)
    out_a = m_default(*args[:4], None, speaker_embeddings=args[4], f0=_f0())
    torch.manual_seed(7)
    out_b = m_explicit(*args[:4], None, speaker_embeddings=args[4], f0=_f0())
    torch.testing.assert_close(out_a.waveform, out_b.waveform, atol=0, rtol=0)


def test_carrier_on_replaces_s2c_and_shrinks_the_band0_head():
    model = _model(use_f0_path=True, use_carrier_head=True)
    dec = model.dec
    assert hasattr(dec, "carrier_head")
    assert not hasattr(dec, "head_proj")
    assert not hasattr(dec, "phase_template")
    # band0 = log σ 9ch のみ、band1-3 = mag/phase 18ch × 3
    assert dec.subband_conv_post.out_channels == 9 + 3 * (16 + 2)
    # S-2a (f0_feat) と S-2p (predictor) はそのまま共存
    assert hasattr(dec, "f0_feat")
    assert hasattr(model, "f0_predictor")


def test_carrier_requires_the_f0_path():
    with pytest.raises(ValueError, match="use_f0_path"):
        _gen(use_carrier_head=True, use_f0_path=False)


def test_carrier_rejects_trainable_pqmf_synthesis():
    """alias 相殺は canonical PQMF が前提 (設計 doc §4.1 #6 / §8 R5)。"""
    with pytest.raises(ValueError, match="canonical"):
        _gen(use_carrier_head=True, trainable_pqmf_synthesis=True)


# ---------------------------------------------------------------------------
# forward 形状 / 学習配線
# ---------------------------------------------------------------------------


def test_generator_forward_shapes_and_energies():
    gen = _gen(use_carrier_head=True)
    gen.train()
    T = 32
    z = torch.randn(2, 192, T)
    g = torch.randn(2, 512, 1)
    f0 = torch.full((2, 1, T), 200.0)
    f0[:, :, ::4] = 0.0
    full, sub = gen(z, g=g, f0=f0)
    assert full.shape == (2, 1, T * 256)
    assert sub.shape == (2, 4, T * 64)
    assert torch.isfinite(full).all()
    # L_src / 縮退監視用の枝エネルギーが stash されている
    e_h, e_n = gen.last_carrier_energies
    assert e_h.shape == (2, T) and e_n.shape == (2, T)
    assert (e_h >= 0).all() and (e_n >= 0).all()


def test_generator_forward_runs_under_bf16_autocast():
    """bf16 autocast 下でも oscillator は fp32 固定で走り、出力が有限。"""
    gen = _gen(use_carrier_head=True)
    gen.train()
    T = 32
    z = torch.randn(1, 192, T)
    g = torch.randn(1, 512, 1)
    f0 = torch.full((1, 1, T), 200.0)
    with torch.autocast(device_type="cpu", dtype=torch.bfloat16):
        full, _sub = gen(z, g=g, f0=f0)
    assert torch.isfinite(full.float()).all()


def test_recon_gradient_reaches_the_gains_but_not_the_f0_predictor():
    """(vii) recon 経路の勾配は gain_net / σ head に流れ、F0 predictor には
    流れない (detach、FastPitch 型 — predictor は GT 回帰のみで学習)。"""
    model = _model(use_f0_path=True, use_carrier_head=True)
    model.train()
    x, x_lengths, spec, spec_lengths, emb = _batch()
    out = model(
        x,
        x_lengths,
        spec,
        spec_lengths,
        None,
        speaker_embeddings=emb,
        f0=_f0(),
        f0_pred_prob=1.0,  # decoder は予測 F0 (detach 済) を消費
    )
    model.zero_grad(set_to_none=True)
    out.waveform.pow(2).mean().backward()

    pred_grad = sum(
        float(p.grad.abs().sum())
        for p in model.f0_predictor.parameters()
        if p.grad is not None
    )
    assert pred_grad == 0.0, "recon gradient leaked into the F0 predictor"

    gain = model.dec.carrier_head.gain_net
    assert gain.weight.grad is not None
    assert float(gain.weight.grad.abs().sum()) > 0.0


def test_infer_runs_with_the_carrier_head():
    model = _model(use_f0_path=True, use_carrier_head=True)
    model.eval()
    x = torch.randint(1, 40, (1, 10))
    x_lengths = torch.tensor([10])
    emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
    with torch.no_grad():
        out = model.infer(x, x_lengths, speaker_embeddings=emb)
    assert out.audio.dim() == 3
    assert torch.isfinite(out.audio).all()


# ---------------------------------------------------------------------------
# L_src hinge (実装のみ、default off — 設計 doc §4.3)
# ---------------------------------------------------------------------------


def test_source_regularization_is_zero_when_the_carrier_dominates():
    e_h = torch.full((1, 4), 10.0)
    e_n = torch.full((1, 4), 1.0)
    f0 = torch.full((1, 1, 4), 200.0)
    assert float(carrier_source_regularization(e_h, e_n, f0)) == 0.0


def test_source_regularization_penalizes_noise_flooding_on_voiced_frames():
    e_h = torch.full((1, 4), 1.0)
    e_n = torch.full((1, 4), 100.0)
    f0 = torch.full((1, 1, 4), 200.0)
    loss = carrier_source_regularization(e_h, e_n, f0)
    assert float(loss) == pytest.approx(math.log(100.0), rel=1e-3)
    # 緩い τ は正常な breathiness に勾配を出さない (hinge)
    relaxed = carrier_source_regularization(e_h, e_n, f0, tau=10.0)
    assert float(relaxed) == 0.0


def test_source_regularization_ignores_unvoiced_frames():
    e_h = torch.tensor([[1.0, 1.0]])
    e_n = torch.tensor([[100.0, 1.0]])
    f0 = torch.tensor([[[0.0, 200.0]]])  # 氾濫フレームは unvoiced
    assert float(carrier_source_regularization(e_h, e_n, f0)) == 0.0


class TestLightningWiring:
    """lightning が carrier head を実際に配線していることの pin。

    Phase A 実装時に「CLI は受理するが SynthesizerTrn に渡らない」silent
    欠落が起きた (workflow レーン分担の隙間) — 配線をテストで固定する。
    """

    def test_hparams_reach_synthesizer(self):
        from piper_train.vits.lightning import VitsModel

        model = VitsModel(
            num_symbols=50,
            num_speakers=2,
            sample_rate=22050,
            dataset=None,
            batch_size=1,
            use_f0_path=True,
            use_carrier_head=True,
            carrier_harmonics=24,
            no_wavlm=True,
            use_wavlm_discriminator=False,
        )
        assert model.model_g.use_carrier_head is True
        assert model.model_g.dec.use_carrier_head is True

    def test_src_reg_loss_wired(self):
        """c_src_reg > 0 で loss_gen_all に L_src が入る配線の存在検査。"""
        from pathlib import Path

        src = Path("piper_train/vits/lightning.py").read_text(encoding="utf-8")
        assert "carrier_source_regularization(" in src
        assert "c_src_reg > 0" in src.replace("self.hparams.", "")
