"""Tests for Multi-scale FiLM in MBiSTFTGenerator.

Multi-scale FiLM is a re-introduction of speaker conditioning at every
upsample stage of the MB-iSTFT generator. Originally the branch had this
in the legacy ``Generator + Multi-scale FiLM`` class which was removed
during dev rebase. The single ``conv_pre`` + add conditioning that
remained was insufficient for stable zero-shot training under 32-true
precision (NaN/CUDA illegal access at step ~149 in multi-6lang scratch).

The new implementation:
- Input-stage FiLM right after ``conv_pre`` (scale + shift)
- ``cond_layers`` (one per upsample stage), zero-initialised so FiLM is
  identity at start
- ``_apply_film`` uses ``scale = sigmoid(x) + 0.5`` so scale ∈ [0.5, 1.5]
  (stable, no channel collapse)
"""

from __future__ import annotations

import pytest


pytest.importorskip("torch", reason="torch required for MBiSTFTGenerator")

import torch  # noqa: E402

from piper_train.vits.mb_istft import MBiSTFTGenerator  # noqa: E402


# ---------------------------------------------------------------------------
# 共通フィクスチャ
# ---------------------------------------------------------------------------


def _make_generator(gin_channels: int = 512) -> MBiSTFTGenerator:
    """テスト用の小さい MBiSTFTGenerator を構築する"""
    return MBiSTFTGenerator(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        gin_channels=gin_channels,
    )


# ---------------------------------------------------------------------------
# _apply_film: 単体ロジック
# ---------------------------------------------------------------------------


class TestApplyFilm:
    """``_apply_film`` の数値挙動を検証する"""

    def test_zero_scale_shift_returns_x_times_one(self):
        """scale_raw=0 → sigmoid(0)+0.5 = 1.0、shift=0 → 出力は x のまま"""
        x = torch.randn(2, 4, 8)
        zero = torch.zeros(2, 8, 8)  # 4 scale + 4 shift = 8 channels
        y = MBiSTFTGenerator._apply_film(x, zero)
        torch.testing.assert_close(y, x)

    def test_scale_range_is_half_to_one_point_five(self):
        """scale = sigmoid(scale_raw) + 0.5 → [0.5, 1.5] にクリップされる"""
        x = torch.ones(1, 4, 8)
        # scale_raw = +inf → sigmoid → 1.0 → +0.5 = 1.5
        big_pos = torch.full((1, 8, 8), 100.0)
        y_pos = MBiSTFTGenerator._apply_film(x, big_pos)
        # shift=100 が上乗せされるので、scale 部分だけ確認するため shift をゼロにする
        scale_only = torch.cat([torch.full((1, 4, 8), 100.0), torch.zeros(1, 4, 8)], dim=1)
        y_scale = MBiSTFTGenerator._apply_film(x, scale_only)
        assert torch.allclose(y_scale, torch.full_like(x, 1.5), atol=1e-5)

        # scale_raw = -inf → sigmoid → 0 → +0.5 = 0.5
        scale_only_neg = torch.cat([torch.full((1, 4, 8), -100.0), torch.zeros(1, 4, 8)], dim=1)
        y_neg = MBiSTFTGenerator._apply_film(x, scale_only_neg)
        assert torch.allclose(y_neg, torch.full_like(x, 0.5), atol=1e-5)

    def test_shift_is_added(self):
        """shift がそのまま加算される"""
        x = torch.zeros(1, 4, 8)
        # scale_raw=0 (=> scale=1), shift=3.0
        scale_shift = torch.cat(
            [torch.zeros(1, 4, 8), torch.full((1, 4, 8), 3.0)], dim=1
        )
        y = MBiSTFTGenerator._apply_film(x, scale_shift)
        assert torch.allclose(y, torch.full_like(x, 3.0))


# ---------------------------------------------------------------------------
# 構造的検証: __init__
# ---------------------------------------------------------------------------


class TestGeneratorStructure:
    def test_cond_output_channel_doubled_for_film(self):
        """Input-stage FiLM: cond の output channel = upsample_initial_channel * 2"""
        m = _make_generator(gin_channels=512)
        # cond input = gin_channels = 512, output = 256 * 2 = 512
        assert m.cond.in_channels == 512
        assert m.cond.out_channels == 512

    def test_cond_layers_count_matches_upsample_stages(self):
        """Multi-scale FiLM 層数 = upsample 段数"""
        m = _make_generator(gin_channels=512)
        assert len(m.cond_layers) == m.num_upsamples

    def test_cond_layers_output_channel_matches_stage(self):
        """各 cond_layers の output channel = stage_ch * 2 (scale + shift)"""
        m = _make_generator(gin_channels=512)
        # upsample_initial_channel = 256, upsample_rates = (4, 4)
        # stage 0 ch = 256 // 2 = 128 → cond output = 128*2 = 256
        # stage 1 ch = 256 // 4 = 64 → cond output = 64*2 = 128
        assert m.cond_layers[0].out_channels == 256
        assert m.cond_layers[1].out_channels == 128

    def test_cond_layers_zero_initialized(self):
        """cond_layers は zero-init (FiLM が学習開始時 identity)"""
        m = _make_generator(gin_channels=512)
        for layer in m.cond_layers:
            assert (layer.weight == 0).all()
            assert (layer.bias == 0).all()

    def test_no_cond_when_gin_channels_zero(self):
        """gin_channels=0 では cond / cond_layers 属性なし"""
        m = _make_generator(gin_channels=0)
        assert not hasattr(m, "cond")
        assert not hasattr(m, "cond_layers")
        assert m.gin_channels == 0


# ---------------------------------------------------------------------------
# Forward 動作テスト
# ---------------------------------------------------------------------------


class TestGeneratorForward:
    def test_forward_with_speaker_embedding(self):
        """g 付き forward が動作 + 出力 shape 維持"""
        m = _make_generator(gin_channels=512)
        x = torch.randn(2, 192, 32)
        g = torch.randn(2, 512, 1)
        fb, sb = m(x, g)
        assert fb.shape == (2, 1, 32 * 16 * 16)  # T_frames * upsample(16x) * pqmf(16x)
        assert sb.shape == (2, 4, 32 * 16 * 4)
        assert not torch.isnan(fb).any()
        assert not torch.isnan(sb).any()

    def test_forward_without_g_with_film_capable_model(self):
        """gin_channels>0 でも g=None なら conditioning 経路は skip される"""
        m = _make_generator(gin_channels=512)
        x = torch.randn(2, 192, 32)
        fb, sb = m(x, g=None)
        assert fb.shape == (2, 1, 32 * 16 * 16)
        assert not torch.isnan(fb).any()

    def test_forward_with_gin_channels_zero(self):
        """gin_channels=0: g なしで通常動作"""
        m = _make_generator(gin_channels=0)
        x = torch.randn(2, 192, 32)
        fb, sb = m(x, g=None)
        assert fb.shape == (2, 1, 32 * 16 * 16)
        assert not torch.isnan(fb).any()

    def test_zero_init_film_is_identity_at_start(self):
        """zero-init 直後は FiLM が identity (Multi-scale 段で出力変化なし)"""
        torch.manual_seed(0)
        m = _make_generator(gin_channels=512)
        m.eval()  # dropout 等を切る
        x = torch.randn(1, 192, 16)
        # 注意: cond (Input-stage FiLM) は normal-init なので非 zero、Multi-scale のみ zero-init
        # この test では Multi-scale FiLM の効果が初期で identity であることを確認するため
        # cond も zero-init 状態で比較する
        with torch.no_grad():
            torch.nn.init.zeros_(m.cond.weight)
            torch.nn.init.zeros_(m.cond.bias)
        # g_a と g_b (異なる) で同じ結果になるはず (全 FiLM が identity)
        g_a = torch.randn(1, 512, 1)
        g_b = torch.randn(1, 512, 1)
        with torch.no_grad():
            fb_a, _ = m(x, g_a)
            fb_b, _ = m(x, g_b)
        torch.testing.assert_close(fb_a, fb_b, atol=1e-5, rtol=1e-5)

    def test_different_speakers_yield_different_outputs_after_random_init(self):
        """cond_layers をランダム初期化すれば、異なる g で異なる出力が出る"""
        torch.manual_seed(42)
        m = _make_generator(gin_channels=512)
        # cond_layers は zero-init なので、わざとランダム化する
        for layer in m.cond_layers:
            torch.nn.init.normal_(layer.weight, std=0.1)
            torch.nn.init.normal_(layer.bias, std=0.1)
        m.eval()
        x = torch.randn(1, 192, 16)
        g_a = torch.full((1, 512, 1), 1.0)
        g_b = torch.full((1, 512, 1), -1.0)
        with torch.no_grad():
            fb_a, _ = m(x, g_a)
            fb_b, _ = m(x, g_b)
        # 出力が同一でないこと (FiLM が effective)
        diff = (fb_a - fb_b).abs().mean().item()
        assert diff > 1e-4, f"Outputs too similar (diff={diff})"


# ---------------------------------------------------------------------------
# Gradient flow テスト
# ---------------------------------------------------------------------------


class TestGradientFlow:
    def test_cond_layers_receive_gradient(self):
        """backward 後、cond_layers の重みに勾配が流れている"""
        m = _make_generator(gin_channels=512)
        x = torch.randn(1, 192, 16)
        g = torch.randn(1, 512, 1)
        fb, _ = m(x, g)
        loss = fb.mean()
        loss.backward()

        # Input-stage FiLM (cond) の勾配チェック
        assert m.cond.weight.grad is not None
        assert m.cond.weight.grad.abs().sum().item() > 0, (
            "cond.weight.grad は zero-only ではいけない"
        )

        # Multi-scale FiLM (cond_layers) の勾配チェック
        for i, layer in enumerate(m.cond_layers):
            assert layer.weight.grad is not None, f"cond_layers[{i}].weight.grad is None"
            # zero-init で開始するので grad は出るはず (ただし shift ↔ scale で計算)
            assert layer.weight.grad.shape == layer.weight.shape

    def test_speaker_embedding_receives_gradient_path(self):
        """g に対する勾配が cond / cond_layers 経由で流れる"""
        m = _make_generator(gin_channels=512)
        x = torch.randn(1, 192, 16, requires_grad=False)
        g = torch.randn(1, 512, 1, requires_grad=True)
        fb, _ = m(x, g)
        loss = fb.mean()
        loss.backward()
        assert g.grad is not None
        # cond_layers が zero-init なので Multi-scale 経由の勾配は 0、
        # ただし Input-stage FiLM (cond, normal-init) 経由で勾配が流れるはず
        assert g.grad.abs().sum().item() > 0, (
            "g にまったく勾配が流れていない (FiLM 経路が機能していない)"
        )
