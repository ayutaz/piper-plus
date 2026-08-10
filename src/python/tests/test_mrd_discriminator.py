"""Tests for MRD (multi-resolution spectrogram discriminator) — v9.

背景 (docs/design/zero-shot-noise-root-cause-pqmf.md §3 副次要因 1):
既存の discriminator 構成 (MPD/MSD = 波形、WavLM = 16kHz リサンプル) には
5-11kHz の線形周波数スペクトル微細構造を判別できるものが無く、multi-speaker
学習で当該帯域が「平均エネルギーだけ合ったノイズ」に落ちるのを許していた。
MRD は 22.05kHz ネイティブの magnitude STFT を 3 解像度で判別してこの盲点を塞ぐ。

Covers:
1. forward の 4-tuple 契約 (MultiPeriodDiscriminator 互換、feature_loss/
   generator_loss/discriminator_loss にそのまま渡せる)
2. batch-concat 最適化の等価性 (y/y_hat を別々に forward した結果と一致)
3. 勾配疎通 (y_hat 側)
4. spectrogram の fp32 強制 (bf16 autocast 下でも — bf16 cuFFT 事故 3dcabd57 対策)
5. 損失関数との統合 (有限値)
6. CLI surface (--use-mrd / --c-mrd)
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.losses import (  # noqa: E402
    discriminator_loss,
    feature_loss,
    generator_loss,
)
from piper_train.vits.models import (  # noqa: E402
    DiscriminatorR,
    MultiResolutionSpectrogramDiscriminator,
)


@pytest.fixture(scope="module")
def mrd():
    m = MultiResolutionSpectrogramDiscriminator()
    m.eval()
    return m


@pytest.fixture
def audio_pair():
    torch.manual_seed(0)
    y = torch.randn(2, 1, 16384)
    y_hat = torch.randn(2, 1, 16384)
    return y, y_hat


@pytest.mark.unit
class TestForwardContract:
    def test_four_tuple_shapes(self, mrd, audio_pair):
        y, y_hat = audio_pair
        with torch.no_grad():
            y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(y, y_hat)
        assert len(y_d_rs) == len(y_d_gs) == 3, "3 resolutions"
        assert len(fmap_rs) == len(fmap_gs) == 3
        for s_r, s_g in zip(y_d_rs, y_d_gs):
            assert s_r.shape == s_g.shape
            assert s_r.shape[0] == y.shape[0]
        for f_r, f_g in zip(fmap_rs, fmap_gs):
            assert len(f_r) == len(f_g) == 6  # 5 convs + conv_post
            for a, b in zip(f_r, f_g):
                assert a.shape == b.shape

    def test_batch_concat_equivalence(self, mrd, audio_pair):
        """batch-concat forward は y/y_hat を別々に forward した結果と一致する。"""
        y, y_hat = audio_pair
        with torch.no_grad():
            y_d_rs, y_d_gs, _, _ = mrd(y, y_hat)
            # 別々に forward (real 側のみ取り出す)
            sep_r = [mrd.discriminators[i](y)[0] for i in range(3)]
            sep_g = [mrd.discriminators[i](y_hat)[0] for i in range(3)]
        for a, b in zip(y_d_rs, sep_r):
            assert torch.allclose(a, b, atol=1e-5)
        for a, b in zip(y_d_gs, sep_g):
            assert torch.allclose(a, b, atol=1e-5)

    def test_gradient_flows_to_generated(self, mrd):
        y = torch.randn(1, 1, 8192)
        y_hat = torch.randn(1, 1, 8192, requires_grad=True)
        _, y_d_gs, _, fmap_gs = mrd(y, y_hat)
        loss_g, _ = generator_loss(y_d_gs)
        loss_g.backward()
        assert y_hat.grad is not None
        assert float(y_hat.grad.abs().sum()) > 0


@pytest.mark.unit
class TestSpectrogramPrecision:
    def test_spectrogram_fp32_under_autocast(self):
        """bf16 autocast 下でも STFT は fp32 で計算される (cuFFT bf16 事故対策)。"""
        d = DiscriminatorR((512, 50, 240))
        x = torch.randn(1, 1, 4096)
        with torch.autocast("cpu", dtype=torch.bfloat16):
            spec = d.spectrogram(x)
        assert spec.dtype == torch.float32

    def test_spectrogram_shape(self):
        d = DiscriminatorR((1024, 120, 600))
        x = torch.randn(2, 1, 12000)
        spec = d.spectrogram(x)
        assert spec.shape[0] == 2
        assert spec.shape[1] == 1024 // 2 + 1  # onesided bins

    def test_covers_full_band(self):
        """MRD の STFT は Nyquist (11.025kHz) までの全帯域を見る。

        WavLM disc (16kHz リサンプル、8kHz 上限) との違いの pin。
        帯域限定入力 (9-10kHz トーン) がスペクトログラムに現れることを確認。
        """
        import math

        d = DiscriminatorR((1024, 120, 600))
        sr = 22050
        t = torch.arange(8192, dtype=torch.float32) / sr
        tone = torch.sin(2 * math.pi * 9500 * t).reshape(1, 1, -1)
        spec = d.spectrogram(tone)
        freqs = torch.linspace(0, sr / 2, spec.shape[1])
        band_9to10k = spec[0, (freqs > 9000) & (freqs < 10000)].mean()
        band_1to2k = spec[0, (freqs > 1000) & (freqs < 2000)].mean()
        assert float(band_9to10k) > 10 * float(band_1to2k), (
            "9.5kHz tone must be visible in the 9-10kHz bins"
        )


@pytest.mark.unit
class TestLossIntegration:
    def test_losses_finite(self, mrd, audio_pair):
        y, y_hat = audio_pair
        y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(y, y_hat)
        loss_d, _, _ = discriminator_loss(y_d_rs, [g.detach() for g in y_d_gs])
        loss_g, _ = generator_loss(y_d_gs)
        loss_fm = feature_loss(fmap_rs, fmap_gs)
        for name, v in [("disc", loss_d), ("gen", loss_g), ("fm", loss_fm)]:
            assert torch.isfinite(v), f"loss_{name} is not finite"


@pytest.mark.unit
def test_cli_advertises_mrd_flags():
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(
        [
            "--dataset-dir", "/tmp/x",
            "--batch-size", "1",
            "--use-mrd",
            "--c-mrd", "0.5",
        ]
    )
    assert args.use_mrd is True
    assert args.c_mrd == 0.5


@pytest.mark.unit
def test_mrd_default_off():
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1"])
    assert args.use_mrd is False
