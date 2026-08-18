"""v10b Phase B — H-3: 高周波数分解能 spectral 監督 (MRD への resolution 追加)。

背景 (docs/design/zero-shot-v10b-quality-plan.md §1.1 A1 / §3.1 H-3):
残存「ざらつき」の主犯はフレーム格子由来の**定常トーンコム** (172.27Hz =
SR/128 の整数倍、歯の幅 ~10.8Hz)。既存 MRD/MR-STFT の周波数分解能ではこの幅の
コムに構造的に鈍感で、係数増強では消えない (v9→v10a-r2 で +3.6-4.5 →
+4.1-4.7dB と不変)。H-1/H-2 が構造対策、H-3 は「残ったコム/棚に勾配を当てる」補完。

**設計の第一原理 (受け入れ基準の出所)**:
STFT の実効周波数分解能は Δf = SR / win_length で決まる (n_fft の zero-pad は
スペクトルを補間するだけで分解能を上げない)。既存 MRD の最良は
(2048, 240, 1200) → Δf = 22050/1200 = 18.4Hz で、10.8Hz 幅の歯は 1 bin 未満に
潰れる。歯を分離するには win_length ≥ SR/10.8 ≈ 2042 が必要 → **win = n_fft =
4096 (Δf = 5.4Hz、歯 ~2 bin、歯間 32 bin)**。長窓は時間分解能を犠牲にするが、
対象のコムは §1.1 で「定常」と実測済みなので構造的に整合する。

**置換ではなく追加** (plan H-3 のリスク欄)。また E-8 gate (評価メトリクスの
学習流用の恒久禁止) に抵触しないよう、**コム物理量そのもの (SR/128 格子超過)
は loss にしない** — GT 比較の敵対的監督だけを増やす。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

SR = 22050
# §1.1 A1 の実測値: コム系列の間隔と歯の幅
COMB_SPACING_HZ = SR / 128  # 172.27Hz
COMB_TOOTH_WIDTH_HZ = SR / 2048  # 10.77Hz (解剖時の STFT bin 幅)


def _presets():
    from piper_train.vits import models

    presets = getattr(models, "MRD_HIRES_RESOLUTIONS", None)
    if presets is None:
        pytest.fail(
            "piper_train.vits.models.MRD_HIRES_RESOLUTIONS が未実装 "
            "(H-3: 高分解能 resolution の preset 表)"
        )
    return presets


def _mrd(**kwargs):
    from piper_train.vits.models import MultiResolutionSpectrogramDiscriminator

    return MultiResolutionSpectrogramDiscriminator(**kwargs)


def _n_frames(n_fft: int, hop: int, n_samples: int) -> int:
    """DiscriminatorR.spectrogram のフレーム数 (center=False + reflect pad)。"""
    pad = (n_fft - hop) // 2
    return (n_samples + 2 * pad - n_fft) // hop + 1


# ===========================================================================
# 1. preset の第一原理 (分解能の導出)
# ===========================================================================


@pytest.mark.unit
class TestHiresPresetFirstPrinciples:
    def test_presets_have_no_zero_padding(self):
        """win_length == n_fft — zero-pad は実効分解能を上げないため。"""
        for name, (n_fft, _hop, win) in _presets().items():
            assert win == n_fft, (
                f"preset {name}: win={win} != n_fft={n_fft} — zero-pad では "
                "実効分解能 (SR/win) が上がらない"
            )

    def test_flagship_preset_resolves_the_comb_teeth(self):
        """4096 preset は歯の幅 (10.8Hz) 以下の分解能を持つ。"""
        _n_fft, _hop, win = _presets()["4096"]
        delta_f = SR / win
        assert delta_f <= COMB_TOOTH_WIDTH_HZ, (
            f"Δf={delta_f:.2f}Hz > 歯の幅 {COMB_TOOTH_WIDTH_HZ:.2f}Hz — "
            "コムの歯が 1 bin に潰れる"
        )
        # 歯間 (172.27Hz) に十分な bin があること (床とピークが分離できる)
        assert COMB_SPACING_HZ / delta_f >= 16

    def test_existing_resolutions_cannot_resolve_the_comb(self):
        """既存 3 解像度はいずれも歯を分解できない (H-3 が必要な理由の pin)。"""
        best = min(SR / win for (_n, _h, win) in _mrd().resolutions[:3])
        assert best > COMB_TOOTH_WIDTH_HZ, (
            "既存解像度で歯が分解できるなら H-3 の前提が崩れる"
        )

    def test_hires_costs_about_the_same_as_the_existing_2048_branch(self):
        """活性化フットプリント (F × frames) が既存 2048 分岐と同級。

        長窓はフレーム数を減らすため、周波数 bin 増と相殺する。この等価性が
        「resolution を置換せず追加できる」根拠 (VRAM/速度の gate)。
        """
        segment = 8192  # 学習時の segment_size
        n_fft_e, hop_e, _ = (2048, 240, 1200)
        pixels_existing = (n_fft_e // 2 + 1) * _n_frames(n_fft_e, hop_e, segment)
        n_fft_h, hop_h, _ = _presets()["4096"]
        pixels_hires = (n_fft_h // 2 + 1) * _n_frames(n_fft_h, hop_h, segment)
        ratio = pixels_hires / pixels_existing
        assert ratio <= 1.25, (
            f"hires 分岐の活性化が既存 2048 分岐の {ratio:.2f}x — "
            "追加コストが想定を超える"
        )

    def test_hires_frames_survive_the_training_segment(self):
        """segment_size=8192 で 4096 窓のフレームが 1 以上残る (時間軸が潰れない)。"""
        n_fft, hop, _win = _presets()["4096"]
        assert _n_frames(n_fft, hop, 8192) >= 8


# ===========================================================================
# 2. 追加 (置換ではない) + off 互換
# ===========================================================================


@pytest.mark.unit
class TestHiresAppendsResolution:
    def test_default_mrd_unchanged(self):
        mrd = _mrd()
        assert mrd.n_resolutions == 3
        assert mrd.resolutions == (
            (1024, 120, 600),
            (2048, 240, 1200),
            (512, 50, 240),
        )

    def test_hires_is_appended_not_substituted(self):
        base = _mrd().resolutions
        mrd = _mrd(hires_resolution=_presets()["4096"])
        assert mrd.n_resolutions == 4
        assert mrd.resolutions[:3] == base, "既存 resolution が置換されている"
        assert mrd.resolutions[3] == _presets()["4096"]
        assert len(mrd.discriminators) == 4

    def test_state_dict_keys_unchanged_when_off(self):
        keys_off = set(_mrd().state_dict().keys())
        keys_on = set(_mrd(hires_resolution=_presets()["4096"]).state_dict().keys())
        assert keys_off < keys_on
        assert {k for k in keys_on - keys_off if k.startswith("discriminators.3.")} == (
            keys_on - keys_off
        ), "追加分は discriminators.3.* のみ (既存 index を動かしていない)"

    def test_forward_and_gradient_through_hires_branch(self):
        from piper_train.vits.losses import generator_loss

        mrd = _mrd(hires_resolution=_presets()["4096"])
        y = torch.randn(1, 1, 8192)
        y_hat = torch.randn(1, 1, 8192, requires_grad=True)
        y_d_rs, y_d_gs, fmap_rs, _ = mrd(y, y_hat)
        assert len(y_d_rs) == len(y_d_gs) == len(fmap_rs) == 4
        # hires 分岐単独の勾配が y_hat まで届く
        loss, _ = generator_loss([y_d_gs[3]])
        loss.backward()
        assert y_hat.grad is not None and float(y_hat.grad.abs().sum()) > 0

    def test_hires_branch_sees_narrow_spectral_peak(self):
        """hires 分岐のスペクトログラムで隣接 172Hz の 2 トーンが分離される。

        既存 (2048, 240, 1200) では同一 bin 近傍に混ざる = 「コムに鈍感」の実証。
        """
        n_fft, hop, win = _presets()["4096"]
        from piper_train.vits.models import DiscriminatorR

        t = torch.arange(16384, dtype=torch.float32) / SR
        two_tones = (
            torch.sin(2 * torch.pi * 5000 * t)
            + torch.sin(2 * torch.pi * (5000 + COMB_SPACING_HZ) * t)
        ).reshape(1, 1, -1)

        def dip_depth(resolution):
            spec = DiscriminatorR(resolution).spectrogram(two_tones)[0].mean(dim=-1)
            freqs = torch.linspace(0, SR / 2, spec.shape[0])
            lo = int(torch.argmin((freqs - 5000).abs()))
            hi = int(torch.argmin((freqs - (5000 + COMB_SPACING_HZ)).abs()))
            peak = min(float(spec[lo]), float(spec[hi]))
            valley = float(spec[lo + 1 : hi].min())
            return peak / max(valley, 1e-9)

        assert dip_depth((n_fft, hop, win)) > dip_depth((2048, 240, 1200)), (
            "hires 分岐が既存解像度より 2 トーンを分離できていない"
        )


# ===========================================================================
# 3. lightning / CLI 配線
# ===========================================================================


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": 4,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 2,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestHiresWiring:
    def test_lightning_default_has_three_resolutions(self):
        model = _vits_model(use_mrd=True)
        assert model.model_d_mrd.n_resolutions == 3

    def test_lightning_appends_hires_resolution(self):
        model = _vits_model(use_mrd=True, mrd_hires_resolution="4096")
        assert model.model_d_mrd.n_resolutions == 4
        assert model.model_d_mrd.resolutions[3] == _presets()["4096"]

    def test_cli_default_off(self):
        assert _parse_train_args().mrd_hires_resolution == "off"

    def test_cli_choices_are_the_presets(self):
        for name in _presets():
            args = _parse_train_args(("--use-mrd", "--mrd-hires-resolution", name))
            assert args.mrd_hires_resolution == name
        with pytest.raises(SystemExit):
            _parse_train_args(("--mrd-hires-resolution", "8192"))

    def test_cli_dependency_check_requires_mrd(self):
        from piper_train.__main__ import check_discriminator_arg_consistency

        args = _parse_train_args(("--mrd-hires-resolution", "4096"))
        msg = check_discriminator_arg_consistency(args)
        assert msg is not None and "--use-mrd" in msg
