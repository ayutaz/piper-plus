"""Tests for the WaveNeXt v1 decoder (Stage 1 of the WaveNeXt ablation).

Covers the ``WaveNeXtGenerator`` contract pinned in
docs/design/wavenext-decoder-ablation/03-ablation-plan.md and
04-pre-stage0-verification.md:

- forward returns ``(fullband, None)`` in training mode and a single tensor
  in ``onnx_export_mode`` (models.py hard unpack / export_onnx.py contract)
- output shape ``[B, 1, T_frames * 256]`` with clip(-1, 1)
- LayerScale gamma init 1/num_blocks = 0.125 (NOT 1e-6 — 04 doc errata)
- parameter count pinned to the PoC measurement (14,124,034)
- zero-init additive speaker conditioning (identity at start)
- state_dict prefixes match ``__main__._WAVENEXT_MARKERS`` (tri-state
  classifier correctness requirement) with no pqmf.* keys
- BSC-LT/wavenext-mel warm-start loader (``--wavenext-init``, 04 doc §7)
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.wavenext import (  # noqa: E402
    WAVENEXT_HOP_LENGTH,
    ConvNeXtBlock,
    WaveNeXtGenerator,
    load_bsc_lt_generator_weights,
)


def _make_generator(seed=42, **overrides):
    torch.manual_seed(seed)
    kwargs = {"in_channels": 192}
    kwargs.update(overrides)
    return WaveNeXtGenerator(**kwargs)


@pytest.mark.unit
class TestForwardContract:
    def test_training_forward_returns_fullband_and_none(self):
        """Training mode returns (fullband, None) — WaveNeXt has no sub-bands.

        models.py の ``o, o_mb = self.dec(...)`` ハード unpack と
        lightning.py の ``if o_mb is not None:`` guard が無変更で成立する契約。
        """
        gen = _make_generator()
        x = torch.randn(1, 192, 32)
        out = gen(x)
        assert isinstance(out, tuple)
        assert len(out) == 2
        fullband, o_mb = out
        assert fullband.shape == (1, 1, 32 * WAVENEXT_HOP_LENGTH)  # (1, 1, 8192)
        assert o_mb is None

    def test_onnx_export_mode_returns_single_tensor(self):
        """onnx_export_mode returns a bare tensor (export_onnx.py dec contract)."""
        gen = _make_generator()
        gen.eval()
        gen.onnx_export_mode = True
        x = torch.randn(1, 192, 32)
        with torch.no_grad():
            out = gen(x)
        assert isinstance(out, torch.Tensor)
        assert out.shape == (1, 1, 8192)

    def test_output_clipped_to_unit_range(self):
        """Head output is clipped to [-1, 1] even for extreme inputs."""
        gen = _make_generator()
        gen.eval()
        # Large-magnitude latent to actually exercise the clip stage
        x = torch.randn(1, 192, 32) * 100.0
        with torch.no_grad():
            fullband, _ = gen(x)
        assert torch.all(fullband >= -1.0)
        assert torch.all(fullband <= 1.0)

    def test_dynamic_frame_length(self):
        """T_frames=200 → 51200 samples (PoC reproduction, 256x in one shot)."""
        gen = _make_generator()
        gen.eval()
        x = torch.randn(1, 192, 200)
        with torch.no_grad():
            fullband, _ = gen(x)
        assert fullband.shape == (1, 1, 200 * WAVENEXT_HOP_LENGTH)  # (1, 1, 51200)

    def test_gradient_flow(self):
        """Gradients reach embed / ConvNeXt backbone / head."""
        gen = _make_generator()
        x = torch.randn(1, 192, 32)
        fullband, _ = gen(x)
        fullband.sum().backward()
        assert gen.embed.weight.grad is not None
        assert gen.convnext[0].dwconv.weight.grad is not None
        assert gen.convnext[7].gamma.grad is not None
        assert gen.head.linear_2.weight.grad is not None


@pytest.mark.unit
class TestArchitecture:
    def test_layer_scale_init_is_inverse_num_blocks(self):
        """LayerScale gamma init = 1/num_blocks = 0.125 (wetdog default).

        04 doc 正誤表: 旧記載の 1e-6 は誤り。
        """
        gen = _make_generator()
        assert len(gen.convnext) == 8
        for block in gen.convnext:
            assert block.gamma is not None
            assert torch.allclose(block.gamma, torch.full((512,), 1.0 / 8))

    def test_parameter_count_pinned(self):
        """Default config (gin_channels=0) parameter count == PoC measurement."""
        gen = _make_generator()
        count = sum(p.numel() for p in gen.parameters())
        assert count == 14_124_034

    def test_head_dimensions(self):
        """Head: Linear(dim, n_fft+2) → Linear(n_fft+2, hop, bias=False)."""
        gen = _make_generator()
        assert gen.head.linear_1.in_features == 512
        assert gen.head.linear_1.out_features == 1026  # n_fft(1024) + 2
        assert gen.head.linear_2.out_features == WAVENEXT_HOP_LENGTH
        assert gen.head.linear_2.bias is None

    def test_remove_weight_norm_is_noop(self):
        """remove_weight_norm() raises nothing and changes no parameters.

        export_onnx.py が無条件に呼ぶための no-op 契約。
        """
        gen = _make_generator()
        before = {k: v.clone() for k, v in gen.state_dict().items()}
        gen.remove_weight_norm()
        after = gen.state_dict()
        assert before.keys() == after.keys()
        for key, tensor in before.items():
            assert torch.equal(tensor, after[key]), key

    def test_adanorm_reserved_for_stage2(self):
        """ConvNeXtBlock(adanorm_num_embeddings=...) is a Stage 2 reservation."""
        with pytest.raises(NotImplementedError, match="Stage 2"):
            ConvNeXtBlock(
                dim=512,
                intermediate_dim=1536,
                layer_scale_init_value=0.125,
                adanorm_num_embeddings=2,
            )


@pytest.mark.unit
class TestSpeakerConditioning:
    def test_zero_init_cond_starts_as_identity(self):
        """gin_channels>0: cond is zero-init, so g and g=None match at start."""
        gen = _make_generator(gin_channels=512)
        gen.eval()
        x = torch.randn(1, 192, 32)
        g = torch.randn(1, 512, 1)
        with torch.no_grad():
            out_with_g, _ = gen(x, g=g)
            out_without_g, _ = gen(x, g=None)
        assert torch.allclose(out_with_g, out_without_g)

    def test_nonzero_cond_changes_output(self):
        """Once cond.weight becomes non-zero the speaker path is live.

        NOTE: 一様な weight は channel 一様オフセットになり post-embed
        LayerNorm に相殺されるため、channel ごとに異なる値を書き込む。
        """
        gen = _make_generator(gin_channels=512)
        gen.eval()
        x = torch.randn(1, 192, 32)
        g = torch.randn(1, 512, 1)
        with torch.no_grad():
            out_before, _ = gen(x, g=g)
            gen.cond.weight.normal_(std=0.1)
            out_after, _ = gen(x, g=g)
        assert not torch.allclose(out_before, out_after)

    def test_gin_zero_has_no_cond_module(self):
        gen = _make_generator(gin_channels=0)
        assert not hasattr(gen, "cond")


@pytest.mark.unit
class TestStateDictContract:
    """Module naming pinned to wetdog/BSC-LT (04 doc §3-8)."""

    _EXPECTED_PREFIXES = (
        "embed.",
        "norm.",
        "convnext.",
        "final_layer_norm.",
        "head.",
    )

    def test_all_keys_use_pinned_prefixes(self):
        gen = _make_generator()
        for key in gen.state_dict():
            assert key.startswith(self._EXPECTED_PREFIXES), key

    def test_gin_channels_adds_only_cond_prefix(self):
        gen = _make_generator(gin_channels=512)
        for key in gen.state_dict():
            assert key.startswith((*self._EXPECTED_PREFIXES, "cond.")), key

    def test_keys_classify_as_wavenext(self):
        """'model_g.dec.' + key must hit __main__._WAVENEXT_MARKERS."""
        from piper_train.__main__ import _detect_decoder_arch_from_state_dict

        gen = _make_generator()
        state_dict = {f"model_g.dec.{k}": None for k in gen.state_dict()}
        assert _detect_decoder_arch_from_state_dict(state_dict) == "wavenext"

    def test_no_pqmf_keys(self):
        """Correctness requirement: WaveNeXt weights contain no pqmf buffers."""
        gen = _make_generator()
        assert not any(k.startswith("pqmf.") for k in gen.state_dict())


# ---------------------------------------------------------------------------
# BSC-LT/wavenext-mel warm-start loader (--wavenext-init)
# ---------------------------------------------------------------------------


def _make_fake_bsc_lt_state_dict():
    """Build an 83-key fake BSC-LT pytorch_model.bin state_dict.

    実 ckpt の構造 (04 doc §7): feature_extractor.* 2 buffer +
    backbone.* 78 (embed 2 / norm 2 / convnext 72 / final_layer_norm 2) +
    head.* 3 (prefix なし) = 83 keys。BSC-LT は 80-mel 入力なので
    embed.weight は (512, 80, 7)。
    """
    torch.manual_seed(7)
    donor = WaveNeXtGenerator(in_channels=80)
    fake_sd = {
        "feature_extractor.mel_spec.spectrogram.window": torch.hann_window(1024),
        "feature_extractor.mel_spec.mel_scale.fb": torch.randn(513, 80),
    }
    for key, tensor in donor.state_dict().items():
        if key.startswith("head."):
            fake_sd[key] = tensor.clone()
        else:
            fake_sd[f"backbone.{key}"] = tensor.clone()
    # embed.bias is zero-init on both sides; make the transfer observable
    fake_sd["backbone.embed.bias"] = torch.randn(512)
    return fake_sd


@pytest.mark.unit
class TestBscLtLoader:
    def test_fake_83_key_checkpoint_loads_80_1_2(self):
        fake_sd = _make_fake_bsc_lt_state_dict()
        assert len(fake_sd) == 83

        gen = _make_generator()
        scratch_embed_weight = gen.embed.weight.detach().clone()

        loaded, skipped, dropped = load_bsc_lt_generator_weights(gen, fake_sd)
        assert (loaded, skipped, dropped) == (80, 1, 2)

        # backbone weights are transferred (rename map backbone.* → *)
        assert torch.allclose(
            gen.convnext[3].pwconv1.weight,
            fake_sd["backbone.convnext.3.pwconv1.weight"],
        )
        # embed.weight (512, 80, 7) is skipped: 192-ch scratch init survives
        assert torch.equal(gen.embed.weight, scratch_embed_weight)
        # embed.bias (512,) is shape-compatible and transferred
        assert torch.allclose(gen.embed.bias, fake_sd["backbone.embed.bias"])
        # head passes through without prefix
        assert torch.allclose(gen.head.linear_1.weight, fake_sd["head.linear_1.weight"])

    def test_cond_stays_zero_init(self):
        """cond.* is absent from BSC-LT; zero-init must survive the load."""
        fake_sd = _make_fake_bsc_lt_state_dict()
        gen = _make_generator(gin_channels=512)
        load_bsc_lt_generator_weights(gen, fake_sd)
        assert torch.equal(gen.cond.weight, torch.zeros_like(gen.cond.weight))
        assert torch.equal(gen.cond.bias, torch.zeros_like(gen.cond.bias))

    def test_unknown_key_raises_key_error(self):
        fake_sd = _make_fake_bsc_lt_state_dict()
        fake_sd["backbone.bogus.weight"] = torch.zeros(1)
        gen = _make_generator()
        with pytest.raises(KeyError, match="bogus"):
            load_bsc_lt_generator_weights(gen, fake_sd)

    def test_shape_mismatch_raises_value_error(self):
        fake_sd = _make_fake_bsc_lt_state_dict()
        fake_sd["backbone.norm.weight"] = torch.randn(256)
        gen = _make_generator()
        with pytest.raises(ValueError, match="Shape mismatch"):
            load_bsc_lt_generator_weights(gen, fake_sd)
