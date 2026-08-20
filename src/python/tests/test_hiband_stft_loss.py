"""v11 柱 2: 高域 band-weighted GT 参照 MR-STFT loss (--c-hiband-stft) の TDD。

docs/design/zero-shot-v10b-residual-noise-diagnosis.md §3 (A2') の対策 (ii):
mel L1 / 既存 STFT loss は 6-11kHz に実質盲目で、GAN がこの帯域にノイズを
置くのを許した (trainable PQMF ドリフト事故で band3 +6.9dB)。GT waveform を
教師とする magnitude 回帰項で 6-11kHz (特に 9-11kHz を 2 倍の厚み) を監督する。

契約上の位置づけ (docs/spec/zs-eval-contract.md §2):
- GT 教師回帰 = mel / sub-band STFT / MRD と同族の**例外形** (禁止事項 4 の
  対象外)。E-4 コム指標や measure_band_noise 等の評価メトリクスの loss 化では
  ない (EVAL メトリクス import の隔離は scripts/check_zs_metric_isolation.py
  が機械的に強制する)。
"""

from __future__ import annotations

import math

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.stft_loss import HighBandSTFTLoss  # noqa: E402


SR = 22050
_T = 16384


def _sine(freq_hz: float, n: int = _T, amp: float = 0.5) -> torch.Tensor:
    t = torch.arange(n, dtype=torch.float32) / SR
    return (amp * torch.sin(2 * math.pi * freq_hz * t)).reshape(1, 1, -1)


def _bandpassed_noise(
    lo_hz: float, hi_hz: float, seed: int, n: int = _T, rms: float = 0.05
) -> torch.Tensor:
    """FFT マスクで [lo, hi] Hz に帯域制限した白色雑音 (RMS 正規化)。"""
    gen = torch.Generator().manual_seed(seed)
    noise = torch.randn(n, generator=gen)
    spec = torch.fft.rfft(noise)
    freqs = torch.fft.rfftfreq(n, d=1.0 / SR)
    spec[(freqs < lo_hz) | (freqs > hi_hz)] = 0
    out = torch.fft.irfft(spec, n=n)
    out = out / out.pow(2).mean().sqrt().clamp(min=1e-12) * rms
    return out.reshape(1, 1, -1)


# ---------------------------------------------------------------------------
# (i) 帯域重みの形状 — 6-9kHz = 1、9-11kHz = 2 (厚く)、<6kHz = 0
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBandWeightShape:
    def test_weight_zero_below_6khz_and_heavier_above_9khz(self):
        loss = HighBandSTFTLoss(sample_rate=SR)
        for sub in loss.stft_losses:
            w = sub.band_weight
            freqs = torch.linspace(0.0, SR / 2, w.numel())

            def w_at(hz: float, freqs=freqs, w=w) -> float:
                return float(w[int(torch.argmin((freqs - hz).abs()))])

            assert w_at(1000.0) == 0.0, "<6kHz は重み 0 (mel が監督する帯域)"
            assert w_at(3000.0) == 0.0
            assert w_at(5000.0) == 0.0
            assert w_at(7000.0) > 0.0, "6-9kHz に重みがない"
            assert w_at(10000.0) > w_at(7000.0), (
                "9-11kHz が 6-9kHz より厚くない (診断 doc §3: band3 8.3-11kHz が"
                "ドリフトの主戦場、特に 9-11kHz を厚く監督する)"
            )

    def test_weight_is_a_buffer_not_a_parameter(self):
        """重みは固定 (学習で動かせる自由度にしない — gaming 面を増やさない)。"""
        loss = HighBandSTFTLoss(sample_rate=SR)
        assert list(loss.parameters()) == []
        for sub in loss.stft_losses:
            assert "band_weight" in dict(sub.named_buffers())


# ---------------------------------------------------------------------------
# (ii) ゼロ点 / 構造検証 — 高域ノイズにだけ反応する
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLossStructure:
    def test_identical_signals_give_zero_loss(self):
        loss = HighBandSTFTLoss(sample_rate=SR)
        y = _sine(1000.0)
        assert float(loss(y, y)) < 1e-6

    def test_high_band_noise_raises_the_loss(self):
        """[構造検証] GT に無い 9-11kHz ノイズを乗せた fake は loss が上がる。

        A2' 事故の再現形: decoder が band3 (8.3-11kHz) にノイズを生成しても
        mel L1 はほぼ盲目だった。本 loss はそれを直接罰する。
        """
        loss = HighBandSTFTLoss(sample_rate=SR)
        y = _sine(1000.0)
        clean = float(loss(y, y))
        dirty = float(loss(y + _bandpassed_noise(9000.0, 11000.0, seed=0), y))
        assert dirty > clean + 0.1, (
            f"9-11kHz noise floor did not raise the loss ({clean:.4f} -> {dirty:.4f})"
        )

    def test_low_band_error_is_much_cheaper_than_high_band_error(self):
        """帯域選択性: 同 RMS のノイズでも <6kHz は 6-11kHz より桁違いに安い。

        (低域は mel L1 / sub-band STFT の持ち場 — 本 loss が低域まで引っ張ると
        既存 loss との係数バランスを壊す)
        """
        loss = HighBandSTFTLoss(sample_rate=SR)
        y = _sine(1000.0)
        lo = float(loss(y + _bandpassed_noise(1000.0, 3000.0, seed=1), y))
        hi = float(loss(y + _bandpassed_noise(9000.0, 11000.0, seed=1), y))
        assert hi > 5.0 * max(lo, 1e-6), (
            f"band selectivity lost: low-band {lo:.4f} vs high-band {hi:.4f}"
        )

    def test_gradient_reaches_the_generated_waveform(self):
        loss = HighBandSTFTLoss(sample_rate=SR)
        y = _sine(800.0)
        x = (y + _bandpassed_noise(9000.0, 11000.0, seed=2)).requires_grad_(True)
        loss(x, y).backward()
        assert x.grad is not None
        assert torch.isfinite(x.grad).all()
        assert float(x.grad.abs().sum()) > 0.0

    def test_accepts_2d_and_3d_waveforms(self):
        loss = HighBandSTFTLoss(sample_rate=SR)
        y3 = _sine(500.0)
        x3 = y3 + _bandpassed_noise(9500.0, 10500.0, seed=3)
        v3 = float(loss(x3, y3))
        v2 = float(loss(x3.squeeze(1), y3.squeeze(1)))
        assert v3 == pytest.approx(v2, rel=1e-6)


# ---------------------------------------------------------------------------
# (iii) CLI / lightning 配線 — default 0 = off (v10b bit 互換)
# ---------------------------------------------------------------------------


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestCliAndLightningWiring:
    def test_cli_default_is_off(self):
        assert _parse_train_args().c_hiband_stft == 0.0

    def test_cli_opt_in_parses(self):
        assert _parse_train_args(("--c-hiband-stft", "0.5")).c_hiband_stft == 0.5

    def test_lightning_default_hparam_is_off(self):
        model = _vits_model()
        assert model.hparams.c_hiband_stft == 0.0

    def test_lightning_owns_the_loss_module(self):
        model = _vits_model()
        assert isinstance(model.hiband_stft_loss, HighBandSTFTLoss)

    def test_training_step_guards_and_wires_the_loss(self):
        """source 検査 pin: `c_hiband_stft > 0` guard の内側で
        `hiband_stft_loss(...)` が `loss_gen_all` に加算されていること。

        default off では挙動が一切変わらないため、この統合点を見る pin だけが
        「実装したが加算し忘れた」mutation を検出できる
        (test_lightning_wires_flow_logdet_into_kl_loss と同型)。
        """
        import inspect
        import re

        from piper_train.vits import lightning as lightning_mod

        src = inspect.getsource(lightning_mod)
        m = re.search(r"if self\.hparams\.c_hiband_stft > 0:", src)
        assert m, "lightning に c_hiband_stft > 0 の opt-in guard がない"
        window = src[m.end() : m.end() + 500]
        assert "self.hiband_stft_loss(" in window, "guard 内で loss が呼ばれていない"
        assert "loss_gen_all" in window, "loss_gen_all への加算が配線されていない"


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = dict(
        num_symbols=97,
        num_speakers=2,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-5,
        use_wavlm_discriminator=False,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
    )
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)
