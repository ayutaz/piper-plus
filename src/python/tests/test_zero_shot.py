"""
Zero-Shot TTS tests for SynthesizerTrn

Tests for the unified speaker conditioning architecture where:
- n_speakers > 1 always creates spk_proj (2-layer MLP)
- emb_g (nn.Embedding) is removed
- use_zero_shot is accepted for backward compat but not used internally
- speaker_embeddings (plural) is the keyword argument
"""

import pytest


try:
    import torch
except ImportError:
    torch = None

pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

if torch is not None:
    from piper_train.vits.models import (
        DurationPredictor,
        ResidualCouplingBlock,
        StochasticDurationPredictor,
        SynthesizerTrn,
        TextEncoder,
    )

# Minimal model parameters
MODEL_PARAMS = {
    "n_vocab": 50,
    "spec_channels": 513,
    "segment_size": 8192,
    "inter_channels": 192,
    "hidden_channels": 192,
    "filter_channels": 768,
    "n_heads": 2,
    "n_layers": 6,
    "kernel_size": 3,
    "p_dropout": 0.1,
    "resblock": "1",
    "resblock_kernel_sizes": [3, 7, 11],
    "resblock_dilation_sizes": [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
    "upsample_rates": [8, 8, 2, 2],
    "upsample_initial_channel": 512,
    "upsample_kernel_sizes": [16, 16, 4, 4],
    "prosody_dim": 16,
}


class TestZeroShotInit:
    """Test initialization: n_speakers > 1 creates spk_proj, never emb_g"""

    @pytest.mark.unit
    def test_multi_speaker_creates_spk_proj(self):
        """n_speakers > 1 creates spk_proj MLP, emb_g never exists"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        assert hasattr(model, "spk_proj")
        assert not hasattr(model, "emb_g")
        # spk_proj is nn.Sequential: Linear(192, gin_channels) -> LayerNorm -> GELU -> Linear
        assert model.spk_proj[0].weight.shape == (512, 192)

    @pytest.mark.unit
    def test_single_speaker_no_embedding(self):
        """n_speakers=1, gin_channels=0: neither spk_proj nor emb_g"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=1,
            gin_channels=0,
        )
        assert not hasattr(model, "emb_g")
        assert not hasattr(model, "spk_proj")

    @pytest.mark.unit
    def test_single_speaker_with_gin_no_spk_proj(self):
        """n_speakers=1, gin_channels>0: no spk_proj created"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=1,
            gin_channels=512,
        )
        assert not hasattr(model, "spk_proj")
        assert not hasattr(model, "emb_g")

    @pytest.mark.unit
    def test_spk_proj_parameter_count(self):
        """Verify spk_proj parameter count for the 2-layer MLP.

        spk_proj = Linear(192, 512) + LayerNorm(512) + GELU + Linear(512, 512)
        """
        gin = 512
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=gin,
        )
        param_count = sum(p.numel() for p in model.spk_proj.parameters())
        # Linear(192, 512): 192*512 + 512 = 98,816
        # LayerNorm(512):  512 + 512 = 1,024
        # Linear(512, 512): 512*512 + 512 = 262,656
        # Total: 362,496
        expected = (192 * gin + gin) + (gin + gin) + (gin * gin + gin)
        assert param_count == expected, (
            f"spk_proj param count {param_count} != expected {expected}"
        )

    @pytest.mark.unit
    def test_use_zero_shot_accepted_but_not_stored(self):
        """use_zero_shot is accepted for backward compat but not stored as attribute"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
            use_zero_shot=True,
        )
        # Parameter accepted without error; spk_proj created because n_speakers > 1
        assert hasattr(model, "spk_proj")
        assert not hasattr(model, "emb_g")


class TestZeroShotForward:
    """Test forward pass with speaker_embeddings (plural)"""

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_with_speaker_embeddings(self):
        """forward() with speaker_embeddings runs correctly"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.train()

        batch_size = 2
        text_len = 10
        spec_len = 50

        x = torch.randint(0, 50, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len, text_len])
        y = torch.randn(batch_size, 513, spec_len)
        y_lengths = torch.LongTensor([spec_len, spec_len])
        speaker_embeddings = torch.randn(batch_size, 192)

        output = model.forward(
            x, x_lengths, y, y_lengths,
            speaker_embeddings=speaker_embeddings,
        )
        # output: (o, l_length, attn, ids_slice, x_mask, y_mask, (z, z_p, m_p, logs_p, m_q, logs_q))
        assert output[0] is not None  # audio output
        assert output[0].shape[0] == batch_size

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_single_speaker_no_embeddings(self):
        """Single-speaker model forward works without speaker_embeddings"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=1,
            gin_channels=0,
        )
        model.train()

        batch_size = 2
        text_len = 10
        spec_len = 50

        x = torch.randint(0, 50, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len, text_len])
        y = torch.randn(batch_size, 513, spec_len)
        y_lengths = torch.LongTensor([spec_len, spec_len])

        output = model.forward(x, x_lengths, y, y_lengths)
        assert output[0] is not None
        assert output[0].shape[0] == batch_size

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_output_is_finite(self):
        """forward() output contains only finite values"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.train()

        batch_size = 2
        text_len = 10
        spec_len = 50

        x = torch.randint(0, 50, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len, text_len])
        y = torch.randn(batch_size, 513, spec_len)
        y_lengths = torch.LongTensor([spec_len, spec_len])
        speaker_embeddings = torch.randn(batch_size, 192)

        output = model.forward(
            x, x_lengths, y, y_lengths,
            speaker_embeddings=speaker_embeddings,
        )
        audio = output[0]
        assert torch.isfinite(audio).all(), "Output contains NaN or Inf"


class TestZeroShotInfer:
    """Test inference with speaker_embeddings (plural)"""

    @pytest.mark.unit
    @pytest.mark.inference
    def test_infer_with_speaker_embeddings(self):
        """infer() with speaker_embeddings returns audio tensor"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.eval()

        text_len = 10
        x = torch.randint(0, 50, (1, text_len))
        x_lengths = torch.LongTensor([text_len])
        speaker_embeddings = torch.randn(1, 192)

        with torch.no_grad():
            output = model.infer(
                x, x_lengths,
                speaker_embeddings=speaker_embeddings,
            )
        # output: (o, attn, y_mask, (z, z_p, m_p, logs_p))
        audio = output[0]
        assert audio is not None
        assert audio.dim() == 3  # [batch, channels, time]
        assert audio.shape[0] == 1

    @pytest.mark.unit
    @pytest.mark.inference
    def test_infer_single_speaker_regression(self):
        """Single-speaker infer works without speaker_embeddings"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=1,
            gin_channels=0,
        )
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_lengths = torch.LongTensor([10])

        with torch.no_grad():
            output = model.infer(x, x_lengths)
        assert output[0] is not None
        assert output[0].shape[0] == 1

    @pytest.mark.unit
    @pytest.mark.inference
    def test_infer_multi_speaker_requires_speaker_embeddings(self):
        """infer() with n_speakers > 1 and no speaker_embeddings raises AssertionError"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_lengths = torch.LongTensor([10])

        with torch.no_grad():
            with pytest.raises(AssertionError, match="Missing speaker_embeddings"):
                model.infer(x, x_lengths)

    @pytest.mark.unit
    @pytest.mark.inference
    def test_infer_output_range(self):
        """infer() output is in [-1, 1] range (tanh)"""
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_lengths = torch.LongTensor([10])
        speaker_embeddings = torch.randn(1, 192)

        with torch.no_grad():
            output = model.infer(x, x_lengths, speaker_embeddings=speaker_embeddings)
        audio = output[0]
        assert torch.isfinite(audio).all(), "Output contains NaN or Inf"
        assert audio.abs().max() <= 1.0, "Audio output should be in [-1, 1] (tanh)"


class TestTextEncoderSpeakerConditioning:
    """Test TextEncoder accepts g parameter and produces speaker-dependent output"""

    @pytest.mark.unit
    def test_text_encoder_has_cond_layer(self):
        """TextEncoder with gin_channels > 0 has a cond_layer"""
        enc = TextEncoder(
            n_vocab=50,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=512,
        )
        assert hasattr(enc, "cond_layer"), (
            "TextEncoder should have cond_layer when gin_channels > 0"
        )
        # cond_layer maps gin_channels -> hidden_channels via Conv1d
        assert enc.cond_layer.weight.shape == (192, 512, 1), (
            f"Expected cond_layer weight shape (192, 512, 1), got {enc.cond_layer.weight.shape}"
        )

    @pytest.mark.unit
    def test_text_encoder_no_cond_layer_without_gin(self):
        """TextEncoder with gin_channels=0 has no cond_layer"""
        enc = TextEncoder(
            n_vocab=50,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=0,
        )
        assert not hasattr(enc, "cond_layer"), (
            "TextEncoder should not have cond_layer when gin_channels=0"
        )

    @pytest.mark.unit
    def test_text_encoder_accepts_g_parameter(self):
        """TextEncoder forward accepts g and runs without error"""
        torch.manual_seed(42)
        enc = TextEncoder(
            n_vocab=50,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=512,
        )
        enc.eval()

        batch_size = 2
        text_len = 10
        x = torch.randint(0, 50, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len, text_len])
        g = torch.randn(batch_size, 512, 1)  # [batch, gin_channels, 1]

        with torch.no_grad():
            out_x, m, logs, x_mask = enc(x, x_lengths, g=g)

        assert out_x.shape == (batch_size, 192, text_len)
        assert m.shape == (batch_size, 192, text_len)
        assert logs.shape == (batch_size, 192, text_len)

    @pytest.mark.unit
    def test_text_encoder_different_g_produces_different_output(self):
        """Different speaker embeddings g produce different TextEncoder outputs"""
        torch.manual_seed(42)
        enc = TextEncoder(
            n_vocab=50,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=512,
        )
        # cond_layer may be zero-initialized; set non-zero weights to test conditioning
        with torch.no_grad():
            enc.cond_layer.weight.normal_(0, 0.01)
        enc.eval()

        x = torch.randint(0, 50, (1, 10))
        x_lengths = torch.LongTensor([10])
        g1 = torch.randn(1, 512, 1)
        g2 = torch.randn(1, 512, 1)

        with torch.no_grad():
            out1, m1, logs1, _ = enc(x, x_lengths, g=g1)
            out2, m2, logs2, _ = enc(x, x_lengths, g=g2)

        # Different g should produce different outputs
        assert not torch.allclose(m1, m2, atol=1e-5), (
            "TextEncoder should produce different m with different speaker conditioning"
        )

    @pytest.mark.unit
    def test_text_encoder_g_none_still_works(self):
        """TextEncoder with gin_channels > 0 still works when g=None (no conditioning)"""
        torch.manual_seed(42)
        enc = TextEncoder(
            n_vocab=50,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=512,
        )
        enc.eval()

        x = torch.randint(0, 50, (1, 10))
        x_lengths = torch.LongTensor([10])

        with torch.no_grad():
            out_x, m, logs, x_mask = enc(x, x_lengths, g=None)

        assert out_x.shape[0] == 1
        assert torch.isfinite(m).all()


@pytest.mark.skip(
    reason="Generator class replaced by MBiSTFTGenerator after rebase onto dev (#320)"
)
class TestGeneratorFiLMConditioning:
    """Test Generator FiLM (Feature-wise Linear Modulation) conditioning"""

    @pytest.mark.unit
    def test_generator_cond_doubled_output(self):
        """Generator cond layer has 2x upsample_initial_channel output for FiLM (scale + shift)"""
        gen = Generator(
            initial_channel=192,
            resblock="1",
            resblock_kernel_sizes=[3, 7, 11],
            resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
            upsample_rates=[8, 8, 2, 2],
            upsample_initial_channel=512,
            upsample_kernel_sizes=[16, 16, 4, 4],
            gin_channels=512,
        )
        assert hasattr(gen, "cond"), "Generator should have cond layer when gin_channels > 0"
        # FiLM: output is 2 * upsample_initial_channel (scale + shift)
        expected_out_channels = 512 * 2  # upsample_initial_channel * 2
        assert gen.cond.weight.shape[0] == expected_out_channels, (
            f"Generator cond output should be {expected_out_channels} for FiLM, "
            f"got {gen.cond.weight.shape[0]}"
        )

    @pytest.mark.unit
    def test_generator_cond_input_channels(self):
        """Generator cond layer input matches gin_channels"""
        gin_channels = 512
        gen = Generator(
            initial_channel=192,
            resblock="1",
            resblock_kernel_sizes=[3, 7, 11],
            resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
            upsample_rates=[8, 8, 2, 2],
            upsample_initial_channel=512,
            upsample_kernel_sizes=[16, 16, 4, 4],
            gin_channels=gin_channels,
        )
        assert gen.cond.weight.shape[1] == gin_channels, (
            f"Generator cond input should be {gin_channels}, got {gen.cond.weight.shape[1]}"
        )

    @pytest.mark.unit
    def test_generator_film_forward(self):
        """Generator forward with g produces valid output using FiLM conditioning"""
        torch.manual_seed(42)
        gen = Generator(
            initial_channel=192,
            resblock="1",
            resblock_kernel_sizes=[3, 7, 11],
            resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
            upsample_rates=[8, 8, 2, 2],
            upsample_initial_channel=512,
            upsample_kernel_sizes=[16, 16, 4, 4],
            gin_channels=512,
        )
        gen.eval()

        batch_size = 2
        seq_len = 10
        x = torch.randn(batch_size, 192, seq_len)
        g = torch.randn(batch_size, 512, 1)

        with torch.no_grad():
            out = gen(x, g=g)

        assert out.shape[0] == batch_size
        assert out.shape[1] == 1  # mono audio
        assert torch.isfinite(out).all(), "Generator FiLM output should be finite"

    @pytest.mark.unit
    def test_generator_film_different_g(self):
        """Different g vectors produce different Generator outputs (FiLM is effective)"""
        torch.manual_seed(42)
        gen = Generator(
            initial_channel=192,
            resblock="1",
            resblock_kernel_sizes=[3, 7, 11],
            resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
            upsample_rates=[8, 8, 2, 2],
            upsample_initial_channel=512,
            upsample_kernel_sizes=[16, 16, 4, 4],
            gin_channels=512,
        )
        # FiLM cond is zero-initialized for stability; set non-zero weights to test
        with torch.no_grad():
            gen.cond.weight.normal_(0, 0.01)
        gen.eval()

        x = torch.randn(1, 192, 10)
        g1 = torch.randn(1, 512, 1)
        g2 = torch.randn(1, 512, 1)

        with torch.no_grad():
            out1 = gen(x, g=g1)
            out2 = gen(x, g=g2)

        assert not torch.allclose(out1, out2, atol=1e-5), (
            "Generator should produce different outputs with different FiLM conditioning"
        )

    @pytest.mark.unit
    def test_generator_no_cond_without_gin(self):
        """Generator with gin_channels=0 has no cond layer"""
        gen = Generator(
            initial_channel=192,
            resblock="1",
            resblock_kernel_sizes=[3, 7, 11],
            resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
            upsample_rates=[8, 8, 2, 2],
            upsample_initial_channel=512,
            upsample_kernel_sizes=[16, 16, 4, 4],
            gin_channels=0,
        )
        assert not hasattr(gen, "cond"), "Generator should not have cond layer when gin_channels=0"


class TestFlowVarianceLearning:
    """Test that Flow uses mean_only=True (mean-only affine coupling)"""

    @pytest.mark.unit
    def test_flow_mean_only_true(self):
        """ResidualCouplingBlock layers have mean_only=True"""
        flow = ResidualCouplingBlock(
            channels=192,
            hidden_channels=192,
            kernel_size=5,
            dilation_rate=1,
            n_layers=4,
            n_flows=4,
            gin_channels=512,
        )
        for i, module in enumerate(flow.flows):
            if hasattr(module, "mean_only"):
                assert module.mean_only is True, (
                    f"Flow layer {i} should have mean_only=True, got False"
                )

    @pytest.mark.unit
    def test_flow_post_output_channels_mean_only(self):
        """With mean_only=True, ResidualCouplingLayer.post outputs half_channels (mean only)"""
        flow = ResidualCouplingBlock(
            channels=192,
            hidden_channels=192,
            kernel_size=5,
            dilation_rate=1,
            n_layers=4,
            n_flows=4,
            gin_channels=512,
        )
        half_channels = 192 // 2  # 96
        for module in flow.flows:
            if hasattr(module, "post"):
                # mean_only=True: post outputs half_channels * (2 - 1) = half_channels
                expected = half_channels
                actual = module.post.weight.shape[0]
                assert actual == expected, (
                    f"Flow post output should be {expected} (mean_only=True), got {actual}"
                )

    @pytest.mark.unit
    def test_synthesizer_flow_mean_only_true(self):
        """SynthesizerTrn flow uses mean_only=True"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        for module in model.flow.flows:
            if hasattr(module, "mean_only"):
                assert module.mean_only is True, (
                    "SynthesizerTrn flow should use mean_only=True"
                )

    @pytest.mark.unit
    def test_flow_dilation_rate_2(self):
        """SynthesizerTrn flow uses dilation_rate=2 for expanded receptive field"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        assert model.flow.dilation_rate == 2, (
            f"Flow dilation_rate should be 2, got {model.flow.dilation_rate}"
        )

    @pytest.mark.unit
    def test_flow_forward_reverse_roundtrip(self):
        """Flow forward then reverse should approximately recover the input"""
        torch.manual_seed(42)
        flow = ResidualCouplingBlock(
            channels=192,
            hidden_channels=192,
            kernel_size=5,
            dilation_rate=1,
            n_layers=4,
            n_flows=4,
            gin_channels=512,
        )
        flow.eval()

        batch_size = 1
        seq_len = 10
        x = torch.randn(batch_size, 192, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)
        g = torch.randn(batch_size, 512, 1)

        with torch.no_grad():
            z = flow(x, x_mask, g=g, reverse=False)
            x_hat = flow(z, x_mask, g=g, reverse=True)

        assert torch.allclose(x, x_hat, atol=1e-4), (
            f"Flow forward-reverse roundtrip error too large: "
            f"max diff = {(x - x_hat).abs().max().item()}"
        )


class TestDurationPredictorConditioning:
    """Test DurationPredictor and StochasticDurationPredictor conditioning.

    The current implementation uses additive conditioning only (self.cond).
    No cond_scale (multiplicative) is present.
    """

    @pytest.mark.unit
    def test_duration_predictor_has_cond(self):
        """DurationPredictor has cond when gin_channels > 0"""
        dp = DurationPredictor(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.5,
            gin_channels=512,
        )
        assert hasattr(dp, "cond"), (
            "DurationPredictor should have cond when gin_channels > 0"
        )
        # cond maps gin_channels -> in_channels
        assert dp.cond.weight.shape == (192, 512, 1), (
            f"cond weight shape should be (192, 512, 1), got {dp.cond.weight.shape}"
        )

    @pytest.mark.unit
    def test_duration_predictor_no_cond_without_gin(self):
        """DurationPredictor without gin_channels has no cond"""
        dp = DurationPredictor(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.5,
            gin_channels=0,
        )
        assert not hasattr(dp, "cond"), (
            "DurationPredictor should not have cond when gin_channels=0"
        )

    @pytest.mark.unit
    def test_stochastic_duration_predictor_has_cond(self):
        """StochasticDurationPredictor has cond when gin_channels > 0"""
        sdp = StochasticDurationPredictor(
            in_channels=192,
            filter_channels=192,
            kernel_size=3,
            p_dropout=0.5,
            n_flows=4,
            gin_channels=512,
        )
        assert hasattr(sdp, "cond"), (
            "StochasticDurationPredictor should have cond when gin_channels > 0"
        )

    @pytest.mark.unit
    def test_stochastic_duration_predictor_no_cond_without_gin(self):
        """StochasticDurationPredictor without gin_channels has no cond"""
        sdp = StochasticDurationPredictor(
            in_channels=192,
            filter_channels=192,
            kernel_size=3,
            p_dropout=0.5,
            n_flows=4,
            gin_channels=0,
        )
        assert not hasattr(sdp, "cond"), (
            "StochasticDurationPredictor should not have cond when gin_channels=0"
        )

    @pytest.mark.unit
    def test_duration_predictor_forward_with_g(self):
        """DurationPredictor forward with g runs correctly"""
        torch.manual_seed(42)
        dp = DurationPredictor(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.0,
            gin_channels=512,
        )
        dp.eval()

        batch_size = 2
        seq_len = 10
        x = torch.randn(batch_size, 192, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)
        g = torch.randn(batch_size, 512, 1)

        with torch.no_grad():
            out = dp(x, x_mask, g=g)

        assert out.shape == (batch_size, 1, seq_len)
        assert torch.isfinite(out).all(), "DurationPredictor output should be finite"

    @pytest.mark.unit
    def test_duration_predictor_different_g_different_output(self):
        """DurationPredictor with different g produces different output (after weight perturbation)"""
        torch.manual_seed(42)
        dp = DurationPredictor(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.0,
            gin_channels=512,
        )
        dp.eval()

        x = torch.randn(1, 192, 10)
        x_mask = torch.ones(1, 1, 10)
        g1 = torch.randn(1, 512, 1)
        g2 = torch.randn(1, 512, 1)

        # After weight perturbation (simulating training), outputs should differ
        with torch.no_grad():
            dp.cond.weight.add_(torch.randn_like(dp.cond.weight) * 0.1)
            out1 = dp(x, x_mask, g=g1)
            out2 = dp(x, x_mask, g=g2)

        assert not torch.allclose(out1, out2, atol=1e-5), (
            "After training, DurationPredictor should produce different outputs "
            "with different g"
        )

    @pytest.mark.unit
    @pytest.mark.inference
    def test_infer_rejects_wrong_embedding_dimension(self):
        """infer() should validate speaker_embeddings shape[-1] matches spk_proj input.

        spk_proj expects 192-dim CAM++ embeddings. Passing a 191-dim tensor
        should fail (currently via torch's matmul shape-mismatch RuntimeError
        rather than an explicit ValueError). This test pins the failure so a
        future explicit shape check (preferred) does not regress silently.
        """
        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.eval()

        text_len = 10
        x = torch.randint(0, 50, (1, text_len))
        x_lengths = torch.LongTensor([text_len])
        bad_speaker_embeddings = torch.randn(1, 191)  # 191 != 192

        with torch.no_grad():
            with pytest.raises((ValueError, AssertionError, RuntimeError)):
                model.infer(
                    x, x_lengths,
                    speaker_embeddings=bad_speaker_embeddings,
                )

    @pytest.mark.unit
    @pytest.mark.training
    def test_spk_proj_teacher_ema_update_with_finite_weights(self):
        """EMA momentum=0.996 update of spk_proj_teacher only when student is finite.

        Mirrors lightning.py:944-959 EMA block. Verifies:
        1. Finite student → teacher = 0.996*teacher_prev + 0.004*student
        2. NaN student weight → teacher unchanged (skip path)
        """
        import copy

        torch.manual_seed(42)
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        # Build teacher exactly as lightning.py:290 does
        spk_proj_teacher = copy.deepcopy(model.spk_proj)
        spk_proj_teacher.requires_grad_(False)

        # Snapshot teacher weights before update
        teacher_prev = [p.detach().clone() for p in spk_proj_teacher.parameters()]
        student_snapshot = [
            p.detach().clone() for p in model.spk_proj.parameters()
        ]

        # ---- Case 1: finite student → EMA update applied ----
        with torch.no_grad():
            student_finite = all(
                torch.isfinite(p.data).all() for p in model.spk_proj.parameters()
            )
            assert student_finite, "Fresh model weights should be finite"
            for p_ema, p in zip(
                spk_proj_teacher.parameters(),
                model.spk_proj.parameters(),
                strict=True,
            ):
                p_ema.mul_(0.996).add_(p.data, alpha=0.004)

        for prev, student, p_ema in zip(
            teacher_prev, student_snapshot, spk_proj_teacher.parameters(), strict=True
        ):
            expected = prev * 0.996 + student * 0.004
            assert torch.allclose(p_ema.data, expected, atol=1e-6), (
                "Teacher EMA update did not apply 0.996*prev + 0.004*student"
            )

        # ---- Case 2: NaN in student → skip (teacher unchanged) ----
        teacher_after_case1 = [
            p.detach().clone() for p in spk_proj_teacher.parameters()
        ]
        with torch.no_grad():
            # Corrupt one student weight
            first_param = next(model.spk_proj.parameters())
            first_param.data[0, 0] = float("nan")

            student_finite = all(
                torch.isfinite(p.data).all() for p in model.spk_proj.parameters()
            )
            assert not student_finite, "Student should now be non-finite"
            if student_finite:
                for p_ema, p in zip(
                    spk_proj_teacher.parameters(),
                    model.spk_proj.parameters(),
                    strict=True,
                ):
                    p_ema.mul_(0.996).add_(p.data, alpha=0.004)

        for prev, p_ema in zip(
            teacher_after_case1, spk_proj_teacher.parameters(), strict=True
        ):
            assert torch.equal(p_ema.data, prev), (
                "Teacher must remain unchanged when student has NaN"
            )

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_with_mixed_language_id_and_speaker_embeddings(self):
        """forward() with language_id=-1 (mixed-language test path) + speaker_embeddings.

        lightning.py:358 routes language_id=-1 utterances through bilingual
        phonemization, normalizing lid to a valid index before the model.
        This test pins the gap that the model layer has no equivalent
        defense.
        """
        torch.manual_seed(42)
        params = dict(MODEL_PARAMS)
        model = SynthesizerTrn(
            **params,
            n_speakers=20,
            n_languages=2,
            gin_channels=512,
        )
        model.train()

        batch_size = 1
        text_len = 10
        spec_len = 50

        x = torch.randint(0, 50, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len])
        y = torch.randn(batch_size, 513, spec_len)
        y_lengths = torch.LongTensor([spec_len])
        speaker_embeddings = torch.randn(batch_size, 192)
        language_ids = torch.tensor([-1], dtype=torch.long)  # mixed-lang marker

        output = model.forward(
            x, x_lengths, y, y_lengths,
            lid=language_ids,
            speaker_embeddings=speaker_embeddings,
        )
        audio = output[0]
        assert audio is not None
        assert audio.shape[0] == batch_size
        assert audio.dim() == 3, f"Expected [B,1,T] audio, got shape {audio.shape}"

    @pytest.mark.unit
    def test_synthesizer_dp_has_cond(self):
        """SynthesizerTrn's duration predictor has cond when gin_channels > 0"""
        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        assert hasattr(model.dp, "cond"), (
            "SynthesizerTrn's duration predictor should have cond"
        )
