"""v11 P0: decoder FiLM scale の開放 (--film-free-scale) の TDD。

docs/design/zero-shot-v11-conditioning-design.md §5.2 (b-1) P0:
現行の ``scale = sigmoid(raw) + 0.5`` は scale を [0.5, 1.5] に制限しており、
FiLM 原典が「γ の sigmoid/tanh 制限は劣化」と実証済みの形。開放形は
``scale = 1 + γ̂`` (無界、γ̂ zero-init) — zero-init 層 (cond_layers) では
raw=0 → scale=1.0 で両形式が一致するため、on 直後の挙動は off と一致する。

default off = v10b (ep79) bit 互換。既存 ckpt とは学習継続で非互換
(scale の意味が変わる) なので from-scratch / 明示 flag のみ。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import MBiSTFTGenerator  # noqa: E402


def _make_generator(**overrides) -> MBiSTFTGenerator:
    kwargs = dict(
        initial_channel=32,
        resblock="2",
        resblock_kernel_sizes=(3,),
        resblock_dilation_sizes=((1, 2),),
        upsample_rates=(4, 4),
        upsample_initial_channel=32,
        upsample_kernel_sizes=(16, 16),
        gin_channels=64,
    )
    kwargs.update(overrides)
    return MBiSTFTGenerator(**kwargs)


# ---------------------------------------------------------------------------
# _apply_film: 開放形の数値挙動
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyFilmFreeScale:
    def test_free_scale_is_one_plus_raw(self):
        """開放形: scale = 1 + raw (conditioning doc §5.2 b-1 の 1+γ̂)。"""
        x = torch.ones(1, 4, 8)
        raw = torch.cat([torch.full((1, 4, 8), 2.0), torch.zeros(1, 4, 8)], dim=1)
        y = MBiSTFTGenerator._apply_film(x, raw, free_scale=True)
        assert torch.allclose(y, torch.full_like(x, 3.0))

    def test_free_scale_is_unbounded_and_can_flip_sign(self):
        """sigmoid 形の [0.5, 1.5] 制限がない (負 scale も表現可能 = 無界)。"""
        x = torch.ones(1, 4, 8)
        big = torch.cat([torch.full((1, 4, 8), 9.0), torch.zeros(1, 4, 8)], dim=1)
        assert torch.allclose(
            MBiSTFTGenerator._apply_film(x, big, free_scale=True),
            torch.full_like(x, 10.0),
        ), "scale が 1.5 で飽和している (開放されていない)"
        neg = torch.cat([torch.full((1, 4, 8), -3.0), torch.zeros(1, 4, 8)], dim=1)
        assert torch.allclose(
            MBiSTFTGenerator._apply_film(x, neg, free_scale=True),
            torch.full_like(x, -2.0),
        )

    def test_zero_raw_matches_the_clamped_form(self):
        """γ̂=0 では両形式とも scale=1.0, shift=0 → 出力一致 (zero-init の要)。"""
        x = torch.randn(2, 4, 8)
        zero = torch.zeros(2, 8, 8)
        y_free = MBiSTFTGenerator._apply_film(x, zero, free_scale=True)
        y_clamped = MBiSTFTGenerator._apply_film(x, zero, free_scale=False)
        torch.testing.assert_close(y_free, x)
        torch.testing.assert_close(y_free, y_clamped)

    def test_default_call_signature_stays_clamped(self):
        """2 引数の既存呼び出し (free_scale 省略) は sigmoid+0.5 のまま。"""
        x = torch.ones(1, 4, 8)
        big = torch.cat([torch.full((1, 4, 8), 100.0), torch.zeros(1, 4, 8)], dim=1)
        y = MBiSTFTGenerator._apply_film(x, big)
        assert torch.allclose(y, torch.full_like(x, 1.5), atol=1e-5)


# ---------------------------------------------------------------------------
# Generator 配線: on/off の互換性
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGeneratorFreeScale:
    def test_default_is_off(self):
        assert _make_generator().film_free_scale is False

    def test_flag_is_stored(self):
        assert _make_generator(film_free_scale=True).film_free_scale is True

    def test_zero_init_layers_make_on_identical_to_off(self):
        """zero-init FiLM (cond_layers) では on 直後の出力が off と bit 一致する。

        Input-stage FiLM (``cond``) は normal-init のため、その scale 半分を
        両モデルで 0 にして「zero-init された FiLM 層」の条件を揃える
        (from-scratch 学習開始時の cond_layers がまさにこの状態)。
        """
        torch.manual_seed(0)
        gen_off = _make_generator(film_free_scale=False)
        gen_on = _make_generator(film_free_scale=True)
        gen_on.load_state_dict(gen_off.state_dict())
        for m in (gen_off, gen_on):
            with torch.no_grad():
                m.cond.weight.zero_()
                m.cond.bias.zero_()
            m.eval()
        x = torch.randn(1, 32, 16)
        g = torch.randn(1, 64, 1)
        with torch.no_grad():
            fb_off, _ = gen_off(x, g)
            fb_on, _ = gen_on(x, g)
        torch.testing.assert_close(fb_on, fb_off)

    def test_on_differs_from_off_once_film_weights_are_nonzero(self):
        """FiLM 重みが動いた後は on/off で出力が変わる (flag が実際に効く)。"""
        torch.manual_seed(1)
        gen_off = _make_generator(film_free_scale=False)
        gen_on = _make_generator(film_free_scale=True)
        gen_on.load_state_dict(gen_off.state_dict())
        for m in (gen_off, gen_on):
            with torch.no_grad():
                for layer in m.cond_layers:
                    torch.manual_seed(7)
                    torch.nn.init.normal_(layer.weight, std=0.5)
                    torch.nn.init.normal_(layer.bias, std=0.5)
            m.eval()
        x = torch.randn(1, 32, 16)
        g = torch.randn(1, 64, 1)
        with torch.no_grad():
            fb_off, _ = gen_off(x, g)
            fb_on, _ = gen_on(x, g)
        assert float((fb_on - fb_off).abs().mean()) > 1e-6, (
            "film_free_scale=True でも出力が変わらない (flag が forward に"
            "配線されていない)"
        )

    def test_gradient_flows_through_free_scale_film(self):
        gen = _make_generator(film_free_scale=True)
        x = torch.randn(1, 32, 16)
        g = torch.randn(1, 64, 1, requires_grad=True)
        fb, _ = gen(x, g)
        fb.mean().backward()
        assert g.grad is not None
        assert float(g.grad.abs().sum()) > 0.0
        for i, layer in enumerate(gen.cond_layers):
            assert layer.weight.grad is not None, f"cond_layers[{i}] に勾配なし"


# ---------------------------------------------------------------------------
# CLI / lightning 配線
# ---------------------------------------------------------------------------


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


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


@pytest.mark.unit
class TestCliAndLightningWiring:
    def test_cli_default_is_off(self):
        assert _parse_train_args().film_free_scale is False

    def test_cli_opt_in_parses(self):
        assert _parse_train_args(("--film-free-scale",)).film_free_scale is True

    def test_lightning_default_keeps_decoder_clamped(self):
        model = _vits_model()
        assert model.hparams.film_free_scale is False
        assert model.model_g.dec.film_free_scale is False

    def test_lightning_flag_reaches_the_decoder(self):
        """hparam → decoder 属性の統合点 pin (ckpt resume / ONNX export は
        hparams 経由で VitsModel を再構築するため、hparams に保存されて
        decoder に届くことが再現性の要)。"""
        model = _vits_model(film_free_scale=True)
        assert model.hparams.film_free_scale is True
        assert model.model_g.dec.film_free_scale is True
