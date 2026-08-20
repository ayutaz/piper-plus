"""v11 P5: SNAC 統計注入の除去 (--no-snac-stats) の TDD。

docs/design/zero-shot-v11-conditioning-design.md §10.5 P5:
Phase 0 D-3 LOO で SNAC 統計は −0.017 (最弱)、D-4 isolation で chance =
死荷重と実測 → 「SNAC 除去 flag」に縮退 (−394k param の無害軽量化)。

固定する契約:

* **default (snac_stats=True) = v10b bit 互換** (sn_linear 構築・挙動不変)。
* **snac_stats=False は SN/SDN 統計のみ恒等化**: sn_linear を構築しない
  (= use_snac + snac_stats=False のパラメータ集合は plain coupling と同一)。
* **flow 構造は不変**: 可逆性 (reverse∘forward ≈ id) と logdet の KL 配線
  (forward が (x, logdet) を返す) は維持される。
* **fail-fast**: --no-snac-stats を --use-snac-flow なしで指定したら即エラー
  (黙って no-op の学習を走らせない)。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits import modules  # noqa: E402
from piper_train.vits.models import ResidualCouplingBlock  # noqa: E402


def _randomize_(module, std: float = 0.2, seed: int = 0):
    rng = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for p in module.parameters():
            p.copy_(torch.randn(p.shape, generator=rng) * std)


# ---------------------------------------------------------------------------
# ResidualCouplingLayer 単体
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCouplingLayerNoStats:
    def test_no_stats_builds_no_sn_linear(self):
        layer = modules.ResidualCouplingLayer(
            4,
            8,
            3,
            1,
            2,
            gin_channels=8,
            mean_only=True,
            use_snac=True,
            snac_stats=False,
        )
        assert not hasattr(layer, "sn_linear")
        assert not any("sn_linear" in k for k in layer.state_dict())

    def test_no_stats_param_set_equals_plain_coupling(self):
        """v9 plain ckpt が strict load 可能 (双方向)。"""
        plain = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True
        )
        _randomize_(plain, seed=1)
        no_stats = modules.ResidualCouplingLayer(
            4,
            8,
            3,
            1,
            2,
            gin_channels=8,
            mean_only=True,
            use_snac=True,
            snac_stats=False,
        )
        no_stats.load_state_dict(plain.state_dict())  # strict=True
        plain.load_state_dict(no_stats.state_dict())  # strict=True

    def test_no_stats_forward_matches_plain_bitwise(self):
        """統計恒等化後の forward (x, logdet) は plain coupling と bit 一致
        (g_spk を渡しても無視される)。"""
        plain = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=False
        )
        _randomize_(plain, seed=2)
        no_stats = modules.ResidualCouplingLayer(
            4,
            8,
            3,
            1,
            2,
            gin_channels=8,
            mean_only=False,
            use_snac=True,
            snac_stats=False,
        )
        no_stats.load_state_dict(plain.state_dict())
        plain.eval()
        no_stats.eval()
        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g = torch.randn(2, 8, 1)
        g_spk = torch.randn(2, 8, 1)
        with torch.no_grad():
            y_ref, logdet_ref = plain(x, mask, g=g)
            y, logdet = no_stats(x, mask, g=g, g_spk=g_spk)
        assert torch.equal(y, y_ref)
        assert torch.equal(logdet, logdet_ref)

    def test_no_stats_matches_snac_with_zeroed_sn_linear(self):
        """sn_linear を全ゼロ化した snac-with-stats と bit 一致
        (「統計注入**のみ**の除去」の直接検証)。"""
        with_stats = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True, use_snac=True
        )
        _randomize_(with_stats, seed=3)
        with torch.no_grad():
            with_stats.sn_linear.weight.zero_()
            with_stats.sn_linear.bias.zero_()
        no_stats = modules.ResidualCouplingLayer(
            4,
            8,
            3,
            1,
            2,
            gin_channels=8,
            mean_only=True,
            use_snac=True,
            snac_stats=False,
        )
        no_stats.load_state_dict(with_stats.state_dict(), strict=False)
        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g = torch.randn(2, 8, 1)
        g_spk = torch.randn(2, 8, 1)
        with torch.no_grad():
            y_ref, logdet_ref = with_stats(x, mask, g=g, g_spk=g_spk)
            y, logdet = no_stats(x, mask, g=g, g_spk=g_spk)
            rev_ref = with_stats(y_ref, mask, g=g, g_spk=g_spk, reverse=True)
            rev = no_stats(y, mask, g=g, g_spk=g_spk, reverse=True)
        assert torch.equal(y, y_ref)
        assert torch.equal(logdet, logdet_ref)
        assert torch.equal(rev, rev_ref)

    def test_default_snac_stats_true_keeps_v10b_behaviour(self):
        """default (snac_stats 未指定) は sn_linear 構築 = v10b 互換。"""
        layer = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True, use_snac=True
        )
        assert hasattr(layer, "sn_linear")
        assert layer.snac_stats is True


# ---------------------------------------------------------------------------
# Block: 可逆性 + logdet 配線の維持
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlockInvertibility:
    def test_block_no_stats_is_invertible_and_returns_logdet(self):
        """可逆性テストが通り続けること (P5 の前提条件)。"""
        torch.manual_seed(4)
        block = ResidualCouplingBlock(
            4,
            8,
            3,
            1,
            1,
            n_flows=2,
            gin_channels=8,
            use_snac=True,
            snac_stats=False,
        )
        _randomize_(block, seed=4)
        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g = torch.randn(2, 8, 1)
        g_spk = torch.randn(2, 8, 1)
        y, logdet = block(x, mask, g=g, g_spk=g_spk)
        assert y.shape == x.shape
        assert logdet.shape == (2,)
        assert torch.isfinite(logdet).all()
        x_rec = block(y, mask, g=g, g_spk=g_spk, reverse=True)
        assert torch.allclose(x_rec, x, atol=1e-4, rtol=1e-4)

    def test_block_logdet_matches_autograd_slogdet(self):
        """logdet が jacobian の slogdet と厳密一致 (KL 配線のガード維持)。"""
        torch.manual_seed(5)
        block = ResidualCouplingBlock(
            4,
            8,
            3,
            1,
            1,
            n_flows=2,
            gin_channels=8,
            use_snac=True,
            snac_stats=False,
        ).double()
        _randomize_(block, seed=5)
        b, c, t = 1, 4, 3
        mask = torch.ones(b, 1, t, dtype=torch.float64)
        g = torch.randn(b, 8, 1, dtype=torch.float64)
        g_spk = torch.randn(b, 8, 1, dtype=torch.float64)
        x = torch.randn(b, c, t, dtype=torch.float64)

        _y, logdet = block(x, mask, g=g, g_spk=g_spk)

        def f(flat):
            out, _ = block(flat.reshape(b, c, t), mask, g=g, g_spk=g_spk)
            return out.flatten()

        jac = torch.autograd.functional.jacobian(f, x.flatten())
        sign, logabsdet = torch.linalg.slogdet(jac)
        assert float(sign) == pytest.approx(1.0)
        assert float(logdet.detach()[0]) == pytest.approx(float(logabsdet), abs=1e-6)


# ---------------------------------------------------------------------------
# SynthesizerTrn / VitsModel / CLI 配線
# ---------------------------------------------------------------------------


def _build_synthesizer(**overrides):
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(1234)
    kwargs: dict = {
        "n_vocab": 60,
        "spec_channels": 513,
        "segment_size": 32,
        "inter_channels": 192,
        "hidden_channels": 96,
        "filter_channels": 128,
        "n_heads": 2,
        "n_layers": 1,
        "kernel_size": 3,
        "p_dropout": 0.0,
        "resblock": "2",
        "resblock_kernel_sizes": (3,),
        "resblock_dilation_sizes": ((1, 2),),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 64,
        "upsample_kernel_sizes": (16, 16),
        "n_speakers": 4,
        "n_languages": 2,
        "gin_channels": 512,
        "use_sdp": False,
        "prosody_dim": 0,
    }
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


@pytest.mark.unit
class TestSynthesizerWiring:
    def test_param_saving_matches_the_design_estimate(self):
        """sn_linear 除去 = Conv1d(512, 2·96, 1) × 4 coupling = 393,984 param
        (doc §10.5 の −394k)。"""
        with_stats = _build_synthesizer(use_snac_flow=True)
        no_stats = _build_synthesizer(use_snac_flow=True, snac_stats=False)
        n_with = sum(p.numel() for p in with_stats.flow.parameters())
        n_without = sum(p.numel() for p in no_stats.flow.parameters())
        assert n_with - n_without == 4 * (512 * 2 * 96 + 2 * 96)
        assert n_with - n_without == 393984

    def test_infer_runs_and_flow_logdet_stays_wired_in_forward(self):
        model = _build_synthesizer(use_snac_flow=True, snac_stats=False)
        model.eval()
        emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
        x = torch.randint(1, 60, (1, 8))
        x_lengths = torch.LongTensor([8])
        with torch.no_grad():
            out = model.infer(
                x, x_lengths, lid=torch.LongTensor([0]), speaker_embeddings=emb
            )
        assert torch.isfinite(out.audio).all()
        # 学習 forward: flow_logdet が返り続ける (KL 配線維持)
        model.train()
        spec = torch.randn(1, 513, 48)
        spec_lengths = torch.LongTensor([48])
        g_out = model(
            x,
            x_lengths,
            spec,
            spec_lengths,
            lid=torch.LongTensor([0]),
            speaker_embeddings=emb,
        )
        assert g_out.flow_logdet is not None
        assert torch.isfinite(g_out.flow_logdet).all()


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": 2,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 4,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


@pytest.mark.unit
class TestCliAndLightningWiring:
    def test_cli_default_is_off(self):
        assert _parse_train_args().no_snac_stats is False

    def test_cli_opt_in_parses(self):
        args = _parse_train_args(("--use-snac-flow", "--no-snac-stats"))
        assert args.no_snac_stats is True

    def test_lightning_fails_fast_without_snac_flow(self):
        with pytest.raises(ValueError, match="use-snac-flow"):
            _vits_model(no_snac_stats=True)

    def test_lightning_flag_reaches_the_flow(self):
        model = _vits_model(use_snac_flow=True, no_snac_stats=True)
        assert model.hparams.no_snac_stats is True
        couplings = [f for f in model.model_g.flow.flows if hasattr(f, "use_snac")]
        assert couplings
        assert all(not hasattr(f, "sn_linear") for f in couplings)
        assert all(f.snac_stats is False for f in couplings)

    def test_lightning_default_keeps_sn_linear(self):
        model = _vits_model(use_snac_flow=True)
        couplings = [f for f in model.model_g.flow.flows if hasattr(f, "use_snac")]
        assert couplings
        assert all(hasattr(f, "sn_linear") for f in couplings)
