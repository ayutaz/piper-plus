"""H-2b: PQMF の taps 可変化 + 学習可能合成フィルタの TDD テスト。

docs/design/zero-shot-v10b-quality-plan.md §3.1 H-2 (b)。容疑 2 (PQMF 帯域境界の
エイリアス非相殺、taps=62 の広い遷移帯域) への対策レバー。

**なぜ「stopband が改善した」だけでは受け入れ基準にならないか (実測)** —
plan §3.1 H-2 のテスト仕様は「taps=126 の stopband 減衰が taps=62 より改善」だが、
canonical の ``(cutoff_ratio=0.142, beta=9.0)`` を据え置いて taps だけ 62→126 に
すると:

    band filter stopband   -99.2 dB  ->  -110.0 dB   (**改善**)
    round-trip SNR          64.0 dB  ->    16.1 dB   (**48 dB 悪化**)
    sum|G_k|^2 ripple        0.01 dB ->     1.80 dB  (power-complementary 崩壊)

つまり **stopband 単独を基準にすると「改善」判定でフィルタバンクを壊せる**。
遷移帯域が半分に狭まるとバンド間のオーバーラップが不足し、近接完全再構成
(near-PR) の前提が崩れるため。これは受け入れ基準 -90dB→5dB の緩和で PQMF バグを
15 ヶ月制度化した事故 (docs/design/zero-shot-noise-root-cause-pqmf.md §4) と
同型の罠なので、本ファイルは **taps ごとに (cutoff_ratio, beta) を再設計した
preset のみを許可し、全 preset に対して再構成 gate を課す**。

co-design した preset (``PQMF_DESIGN``、2026-08-17 実測):

    taps=62  (0.1420, 9.00)  round-trip 64.05 dB  stopband  -99.2 dB  ripple 0.010 dB
    taps=126 (0.1336, 9.50)  round-trip 65.17 dB  stopband -107.1 dB  ripple 0.015 dB

= taps=126 は再構成を保ったまま stopband を 7.9 dB 改善する (band-edge トーンの
round-trip は 59.1 → 55.0 dB でやや低下するが 50 dB gate 内)。
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import PQMF, PQMF_DESIGN  # noqa: E402


SR = 22050
_N = 32768
BAND_EDGES_HZ = (2756.25, 5512.5, 8268.75)


def _white(seed: int, n: int = _N) -> "torch.Tensor":
    gen = torch.Generator().manual_seed(seed)
    return torch.randn(1, 1, n, generator=gen)


def _roundtrip_snr_db(pqmf: PQMF, x: "torch.Tensor") -> float:
    """analysis→synthesis の SNR。端は FIR 過渡なので taps 分を捨てる。"""
    trim = 4 * pqmf.taps
    with torch.no_grad():
        x_hat = pqmf.synthesis(pqmf.analysis(x))
    ref = x[..., trim:-trim]
    err = ref - x_hat[..., trim:-trim]
    return float(10 * torch.log10(ref.pow(2).sum() / err.pow(2).sum()))


def _band_stopband_db(pqmf: PQMF, nfft: int = 16384) -> float:
    """実際に登録されている合成フィルタから測る stopband 減衰 [dB]。

    設計式を再実装せず buffer/parameter を直接 FFT するので、係数生成の
    バグも含めて捕まえられる。band k の「隣接バンドより外側」での最大応答を
    band k passband ピーク基準で返す (全 band の worst)。
    """
    g = pqmf.synthesis_filter.detach().squeeze(1).to(torch.float64).numpy()
    m = pqmf.subbands
    mag = np.abs(np.fft.rfft(g, nfft, axis=-1))
    w = np.linspace(0.0, 1.0, mag.shape[-1])  # 正規化周波数 (1.0 = Nyquist)
    worst = -np.inf
    for k in range(m):
        lo, hi, guard = k / m, (k + 1) / m, 1.0 / m
        passband = (w >= lo) & (w <= hi)
        stop = (w < lo - guard) | (w > hi + guard)
        worst = max(worst, 20 * np.log10(mag[k][stop].max() / mag[k][passband].max()))
    return float(worst)


def _power_complementary_ripple_db(pqmf: PQMF, nfft: int = 8192) -> float:
    """sum_k |G_k(w)|^2 のリップル [dB]。near-PR なら ~0 dB (平坦)。"""
    g = pqmf.synthesis_filter.detach().squeeze(1).to(torch.float64).numpy()
    total = (np.abs(np.fft.rfft(g, nfft, axis=-1)) ** 2).sum(axis=0)
    total = total / total[len(total) // 2]
    return float(10 * np.log10(total.max() / total.min()))


# ===========================================================================
# (i) taps 設計 — stopband 改善と再構成保持を「同時に」要求する
# ===========================================================================


@pytest.mark.unit
class TestTapsDesign:
    def test_design_table_covers_62_and_126(self):
        assert PQMF_DESIGN[62] == (0.142, 9.0), "taps=62 は canonical 値から動かせない"
        assert 126 in PQMF_DESIGN, "H-2b の taps=126 preset が存在しない"

    def test_default_taps_is_62_and_unchanged(self):
        """default 構築は v10a と同一 (taps=62 / canonical cutoff, beta)。"""
        pqmf = PQMF()
        assert pqmf.taps == 62
        assert (pqmf.cutoff_ratio, pqmf.beta) == (0.142, 9.0)
        assert pqmf.analysis_filter.shape == (4, 1, 63)

    def test_stopband_improves_with_more_taps(self):
        """[第一原理] taps=126 preset の stopband が taps=62 より 5 dB 以上改善。

        FIR 長を倍にすれば同じ窓族で阻止域減衰は必ず改善する (フィルタ設計の
        第一原理)。実測 -99.2 → -107.1 dB = 7.9 dB 改善。
        """
        s62 = _band_stopband_db(PQMF(taps=62))
        s126 = _band_stopband_db(PQMF(taps=126))
        assert s126 <= s62 - 5.0, (
            f"taps=126 stopband {s126:.2f} dB does not improve on taps=62 "
            f"{s62:.2f} dB by >= 5 dB"
        )

    @pytest.mark.parametrize("taps", sorted(PQMF_DESIGN))
    def test_every_preset_keeps_near_perfect_reconstruction(self, taps):
        """[第一原理] 全 preset で round-trip SNR >= 55 dB。

        tests/test_pqmf.py と同一の canonical 基準。**この gate があるから
        taps を上げても near-PR が壊れない** (下の
        test_naive_taps_bump_* が壊れる側の実測)。実測 64.05 / 65.17 dB。
        """
        snr = _roundtrip_snr_db(PQMF(taps=taps), _white(0))
        assert snr >= 55, f"taps={taps} round-trip {snr:.2f} dB < 55 dB"

    @pytest.mark.parametrize("taps", sorted(PQMF_DESIGN))
    def test_every_preset_passes_band_edge_tones(self, taps):
        """[第一原理] 全 preset で帯域境界トーンの round-trip >= 50 dB。

        境界トーンは位相項/オーバーラップの破綻に最も鋭いプローブ
        (test_pqmf.py と同一基準)。実測 taps=62 59.1 dB / taps=126 55.0 dB。
        """
        pqmf = PQMF(taps=taps)
        t = torch.arange(_N, dtype=torch.float32) / SR
        for freq in BAND_EDGES_HZ:
            tone = torch.sin(2 * math.pi * freq * t).reshape(1, 1, -1)
            snr = _roundtrip_snr_db(pqmf, tone)
            assert snr >= 50, f"taps={taps} tone {freq:.0f} Hz round-trip {snr:.2f} dB"

    @pytest.mark.parametrize("taps", sorted(PQMF_DESIGN))
    def test_every_preset_is_power_complementary(self, taps):
        """[第一原理] sum|G_k|^2 のリップル <= 0.5 dB。

        cosine-modulated near-PR バンクは power-complementary でなければ
        振幅歪みが残る。naive bump が壊すのはまさにここ (1.80 dB)。
        実測 0.010 / 0.015 dB。
        """
        ripple = _power_complementary_ripple_db(PQMF(taps=taps))
        assert ripple <= 0.5, f"taps={taps} sum|G_k|^2 ripple {ripple:.3f} dB"

    def test_naive_taps_bump_improves_stopband_but_destroys_reconstruction(self):
        """[現状実測 pin] 「stopband だけを見る」受け入れ基準が通してしまう壊れ方。

        taps だけ 126 にして cutoff_ratio/beta を canonical 据え置きにすると、
        stopband は **taps=62 より良く** なる (-110.0 vs -99.2 dB) のに
        round-trip は 64.0 → 16.1 dB に崩れる。この 1 本が
        ``PQMF_DESIGN`` (taps ごとの再設計) を必須にしている根拠であり、
        plan §3.1 H-2 のテスト仕様「stopband が改善」を単独基準に採用しては
        いけないことの実測証拠。
        """
        naive = PQMF(taps=126, cutoff_ratio=0.142, beta=9.0)
        assert _band_stopband_db(naive) <= _band_stopband_db(PQMF(taps=62)), (
            "前提が崩れた: naive bump は stopband では勝つはず"
        )
        snr = _roundtrip_snr_db(naive, _white(0))
        assert snr < 30, (
            f"naive taps bump round-trip {snr:.2f} dB — 実測 16.1 dB から大きく "
            f"変わった。設計式か測定が変わっている"
        )
        assert _power_complementary_ripple_db(naive) > 1.0

    def test_unsupported_taps_without_explicit_design_is_rejected(self):
        """co-design されていない taps は明示 (cutoff_ratio, beta) なしでは拒否。

        silent に canonical 値を流用して near-PR を壊す道 (上のテストの壊れ方)
        を構造的に閉じる。
        """
        with pytest.raises(ValueError, match="taps=94"):
            PQMF(taps=94)

    def test_explicit_design_override_allows_any_taps(self):
        """cutoff_ratio と beta を明示すれば任意 taps を構築できる (探索用)。"""
        pqmf = PQMF(taps=94, cutoff_ratio=0.1365, beta=9.5)
        assert pqmf.taps == 94
        assert pqmf.analysis_filter.shape == (4, 1, 95)
        assert _roundtrip_snr_db(pqmf, _white(0)) > 40

    def test_taps_changes_buffer_shapes_only(self):
        """taps は buffer 形状のみを変える (key 集合は不変 = 混同を loud にする)。"""
        assert set(PQMF(taps=62).state_dict()) == set(PQMF(taps=126).state_dict())
        with pytest.raises(RuntimeError):
            PQMF(taps=126).load_state_dict(PQMF(taps=62).state_dict())


# ===========================================================================
# (ii)(iii) trainable synthesis filter
# ===========================================================================


@pytest.mark.unit
class TestTrainableSynthesis:
    def test_default_is_fixed_buffers_only(self):
        """default (off) は v10a 互換: 学習パラメータゼロ、全て buffer。"""
        pqmf = PQMF()
        assert pqmf.trainable_synthesis is False
        assert list(pqmf.parameters()) == []
        assert "synthesis_filter" in dict(pqmf.named_buffers())

    def test_trainable_registers_only_synthesis_as_parameter(self):
        """解析側は固定のまま、合成側だけ Parameter 化 (plan §3.1 H-2b)。"""
        pqmf = PQMF(trainable_synthesis=True)
        params = dict(pqmf.named_parameters())
        buffers = dict(pqmf.named_buffers())
        assert list(params) == ["synthesis_filter"]
        assert "analysis_filter" in buffers and "updown_filter" in buffers
        assert "analysis_filter" not in params

    def test_initial_output_is_bit_identical_to_fixed(self):
        """(ii) canonical 初期化なので初期出力は固定版と bit 一致。"""
        fixed, trainable = PQMF(), PQMF(trainable_synthesis=True)
        assert torch.equal(fixed.synthesis_filter, trainable.synthesis_filter.detach())
        x = _white(3, 8192)
        sub = fixed.analysis(x)
        assert torch.equal(fixed.synthesis(sub), trainable.synthesis(sub))

    def test_gradient_reaches_synthesis_filter(self):
        """合成フィルタに勾配が流れる (= optimizer が実際に更新できる)。"""
        pqmf = PQMF(trainable_synthesis=True)
        sub = _white(4, 8192).repeat(1, 4, 1)[..., :2048]
        pqmf.synthesis(sub).pow(2).mean().backward()
        assert pqmf.synthesis_filter.grad is not None
        assert float(pqmf.synthesis_filter.grad.abs().sum()) > 0.0

    def test_state_dict_interop_between_fixed_and_trainable(self):
        """固定版で学習した ckpt を trainable 版に (逆も) load できる。

        buffer ↔ Parameter で key と shape が変わらないことの固定。
        """
        fixed = PQMF()
        trainable = PQMF(trainable_synthesis=True)
        trainable.load_state_dict(fixed.state_dict())
        with torch.no_grad():
            trainable.synthesis_filter.mul_(1.5)
        fixed.load_state_dict(trainable.state_dict())
        assert torch.allclose(fixed.synthesis_filter, trainable.synthesis_filter.detach())

    def test_reconstruction_gate_applies_to_trainable_and_is_sensitive(self):
        """(iii) 完全再構成性の逸脱監視。

        初期状態は固定版と同一なので 55 dB gate を満たす。さらに合成フィルタを
        **0.5% だけ** 摂動させると SNR が 46 dB に落ちて gate を割る = この
        gate は「学習で合成フィルタが動いたら気付ける」感度を持つ (逸脱量の
        pin: 0.1% → 58.5 dB / 0.5% → 46.0 dB / 1% → 40.1 dB、実測)。
        trainable filter は完全再構成性を失う方向に動くため、学習後の ckpt に
        対して本 gate を再実行することが plan §3.1 H-2b の「逸脱量を監視」。
        """
        x = _white(0)
        pqmf = PQMF(trainable_synthesis=True)
        clean = _roundtrip_snr_db(pqmf, x)
        assert clean >= 55, f"trainable init round-trip {clean:.2f} dB < 55 dB"

        with torch.no_grad():
            gen = torch.Generator().manual_seed(5)
            noise = torch.randn(pqmf.synthesis_filter.shape, generator=gen)
            pqmf.synthesis_filter.add_(noise * 0.005 * pqmf.synthesis_filter.std())
        drifted = _roundtrip_snr_db(pqmf, x)
        assert drifted < 55, (
            f"0.5% perturbation still gives {drifted:.2f} dB — the 55 dB gate "
            f"would be blind to synthesis-filter drift"
        )
        assert drifted < clean - 10

    def test_trainable_with_taps_126(self):
        """taps preset と trainable は直交して組み合わせられる。"""
        pqmf = PQMF(taps=126, trainable_synthesis=True)
        assert pqmf.synthesis_filter.shape == (4, 1, 127)
        assert _roundtrip_snr_db(pqmf, _white(0)) >= 55


# ===========================================================================
# (iv) ONNX export
# ===========================================================================


@pytest.mark.unit
@pytest.mark.parametrize(
    ("taps", "trainable"), [(62, False), (126, False), (62, True), (126, True)]
)
def test_pqmf_synthesis_onnx_export(taps, trainable):
    """(iv) 全組み合わせで synthesis が opset 15 export でき ORT 出力が一致。"""
    ort = pytest.importorskip("onnxruntime")

    class _Wrap(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.pqmf = PQMF(taps=taps, trainable_synthesis=trainable)

        def forward(self, sub):
            return self.pqmf.synthesis(sub)

    model = _Wrap().eval()
    sub = _white(9, 1024).repeat(1, 4, 1)
    with torch.no_grad():
        expected = model(sub)

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
        path = Path(f.name)
    try:
        torch.onnx.export(
            model,
            (sub,),
            str(path),
            opset_version=15,
            input_names=["subbands"],
            output_names=["fullband"],
            dynamic_axes={"subbands": {0: "batch", 2: "time"}, "fullband": {0: "batch", 2: "time"}},
            dynamo=False,
        )
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        got = sess.run(None, {"subbands": sub.numpy()})[0]
        np.testing.assert_allclose(got, expected.numpy(), rtol=1e-4, atol=1e-5)
    finally:
        path.unlink(missing_ok=True)


# ===========================================================================
# MBiSTFTGenerator への配線
# ===========================================================================


@pytest.mark.unit
class TestGeneratorPqmfPlumbing:
    @staticmethod
    def _gen(**overrides):
        from piper_train.vits.mb_istft import MBiSTFTGenerator

        torch.manual_seed(0)
        kwargs = dict(
            initial_channel=32,
            resblock="2",
            resblock_kernel_sizes=(3,),
            resblock_dilation_sizes=((1, 2),),
            upsample_rates=(4, 4),
            upsample_initial_channel=32,
            upsample_kernel_sizes=(16, 16),
        )
        kwargs.update(overrides)
        return MBiSTFTGenerator(**kwargs)

    def test_default_generator_pqmf_is_v10a_compatible(self):
        pqmf = self._gen().pqmf
        assert pqmf.taps == 62 and pqmf.trainable_synthesis is False

    def test_generator_forwards_taps_and_trainable(self):
        gen = self._gen(pqmf_taps=126, trainable_pqmf_synthesis=True)
        assert gen.pqmf.taps == 126
        assert gen.pqmf.trainable_synthesis is True
        assert any("pqmf.synthesis_filter" in n for n, _ in gen.named_parameters())

    def test_explicit_pqmf_instance_wins(self):
        """共有インスタンスを渡した場合は generator 側の taps 指定を無視する。

        lightning.py が ``model_g.dec.pqmf = self.pqmf`` で共有する構成
        (GT analysis と decoder synthesis を同一バンクに保つ) を壊さないため。
        """
        shared = PQMF(taps=126, trainable_synthesis=True)
        gen = self._gen(pqmf=shared, pqmf_taps=62)
        assert gen.pqmf is shared
        assert gen.pqmf.taps == 126

    def test_generator_forward_works_with_taps_126(self):
        gen = self._gen(pqmf_taps=126)
        gen.eval()
        gen.onnx_export_mode = True
        with torch.no_grad():
            out = gen(torch.randn(1, 32, 16))
        assert out.shape == (1, 1, 16 * 256)
