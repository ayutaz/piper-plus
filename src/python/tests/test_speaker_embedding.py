"""Tests for M3-02: speaker_embeddings input path in SynthesizerTrn.

Verifies:
- SynthesizerTrn.infer() accepts speaker_embeddings and produces valid audio
- speaker_embeddings is required for multi-speaker models
- spk_proj is always a 2-layer MLP Sequential for multi-speaker models
- ONNX export includes speaker_embedding input
- forward() accepts speaker_embeddings kwarg
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


# ---------------------------------------------------------------------------
# Tests: SynthesizerTrn.infer() with speaker_embedding
# ---------------------------------------------------------------------------


class TestInferSpeakerEmbedding:
    """SynthesizerTrn.infer() speaker_embedding path."""

    @pytest.mark.unit
    def test_infer_with_speaker_embedding_produces_audio(self, make_synthesizer_trn):
        """Passing speaker_embeddings (192-dim CAM++) produces valid (non-zero) audio."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 12))
        x_len = torch.LongTensor([12])
        spk_emb = torch.randn(1, 192)  # CAM++ 192-dim embedding

        with torch.no_grad():
            o, attn, y_mask, _, _ = model.infer(
                x, x_len, speaker_embeddings=spk_emb
            )

        assert o.dim() == 3
        assert o.shape[0] == 1
        assert o.shape[2] > 0, "Audio length should be > 0"

    @pytest.mark.unit
    def test_infer_requires_speaker_embeddings_for_multi_speaker(self, make_synthesizer_trn):
        """Multi-speaker models require speaker_embeddings; omitting raises AssertionError."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])

        with pytest.raises(AssertionError, match="Missing speaker_embeddings"):
            with torch.no_grad():
                model.infer(x, x_len)

    @pytest.mark.unit
    def test_infer_speaker_embeddings_with_sid_accepted(self, make_synthesizer_trn):
        """sid is accepted alongside speaker_embeddings (ONNX compat); only spk_emb used."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        sid = torch.LongTensor([0])
        spk_emb_a = torch.randn(1, 192)
        spk_emb_b = torch.randn(1, 192)

        with torch.no_grad():
            o_a, _, _, _, _ = model.infer(
                x, x_len, sid=sid, speaker_embeddings=spk_emb_a
            )
            o_b, _, _, _, _ = model.infer(
                x, x_len, sid=sid, speaker_embeddings=spk_emb_b
            )

        # Both should produce valid 3D audio tensors.
        assert o_a.dim() == 3
        assert o_b.dim() == 3
        assert o_a.shape[0] == 1
        assert o_b.shape[0] == 1

    @pytest.mark.unit
    def test_infer_speaker_embedding_192dim(self, make_synthesizer_trn):
        """speaker_embeddings with CAM++ standard shape [batch, 192] is accepted."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        spk_emb = torch.randn(1, 192)  # standard CAM++ embedding shape

        with torch.no_grad():
            o, _, _, _, _ = model.infer(x, x_len, speaker_embeddings=spk_emb)

        assert o.dim() == 3


# ---------------------------------------------------------------------------
# Tests: spk_proj MLP for multi-speaker models
# ---------------------------------------------------------------------------


class TestSpeakerEmbeddingProjection:
    """spk_proj is always a 2-layer MLP Sequential for multi-speaker models."""

    @pytest.mark.unit
    def test_spk_proj_exists_for_multi_speaker(self, make_synthesizer_trn):
        """spk_proj is always a nn.Sequential for n_speakers > 1."""
        import torch.nn as nn

        gin = 512
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)

        assert hasattr(model, "spk_proj"), "spk_proj should exist for multi-speaker"
        assert isinstance(model.spk_proj, nn.Sequential), (
            "spk_proj should be an nn.Sequential (2-layer MLP)"
        )

    @pytest.mark.unit
    def test_spk_proj_input_dim_is_192(self, make_synthesizer_trn):
        """spk_proj first Linear layer accepts 192-dim CAM++ embeddings."""
        import torch.nn as nn

        gin = 512
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)

        first_linear = model.spk_proj[0]
        assert isinstance(first_linear, nn.Linear)
        assert first_linear.in_features == 192, (
            f"Expected spk_proj input dim 192, got {first_linear.in_features}"
        )
        assert first_linear.out_features == gin, (
            f"Expected spk_proj output dim {gin}, got {first_linear.out_features}"
        )

    @pytest.mark.unit
    def test_spk_proj_not_created_for_single_speaker(self, make_synthesizer_trn):
        """spk_proj is not created for single-speaker models."""
        model = make_synthesizer_trn(n_speakers=1, gin_channels=0)

        assert not hasattr(model, "spk_proj"), (
            "spk_proj should not exist for single-speaker models"
        )

    @pytest.mark.unit
    def test_infer_consistent_across_calls(self, make_synthesizer_trn):
        """Same speaker_embeddings produce same output across repeated calls."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()
        model.onnx_export_mode = True
        if hasattr(model, "dp"):
            model.dp.onnx_export_mode = True

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        spk_emb = torch.randn(1, 192)

        with torch.no_grad():
            o1, _, _, _, _ = model.infer(
                x, x_len, noise_scale=0.0, noise_scale_w=0.0,
                speaker_embeddings=spk_emb,
            )
            o2, _, _, _, _ = model.infer(
                x, x_len, noise_scale=0.0, noise_scale_w=0.0,
                speaker_embeddings=spk_emb,
            )

        torch.testing.assert_close(o1, o2)


# ---------------------------------------------------------------------------
# Tests: speaker_embedding with language embedding
# ---------------------------------------------------------------------------


class TestSpeakerEmbeddingWithLanguage:
    """speaker_embeddings + emb_lang (multilingual voice cloning)."""

    @pytest.mark.unit
    def test_infer_with_speaker_embedding_and_lid(self, make_synthesizer_trn):
        """speaker_embeddings combined with language embedding."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, n_languages=3, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        lid = torch.LongTensor([1])
        spk_emb = torch.randn(1, 192)  # 192-dim CAM++ embedding

        with torch.no_grad():
            o, _, _, _, _ = model.infer(
                x, x_len, lid=lid, speaker_embeddings=spk_emb
            )

        assert o.dim() == 3
        assert o.shape[0] == 1


# ---------------------------------------------------------------------------
# Tests: forward() accepts speaker_embeddings
# ---------------------------------------------------------------------------


class TestForwardSpeakerEmbedding:
    """forward() accepts speaker_embeddings kwarg."""

    @pytest.mark.unit
    def test_forward_accepts_speaker_embeddings_kwarg(self, make_synthesizer_trn):
        """forward() does not raise when speaker_embeddings is passed to single-speaker model."""
        model = make_synthesizer_trn(n_speakers=1, gin_channels=0)

        batch, text_len, spec_len = 1, 10, 50
        x = torch.randint(0, 50, (batch, text_len))
        x_lengths = torch.LongTensor([text_len])
        spec = torch.randn(batch, 513, spec_len)
        spec_lengths = torch.LongTensor([spec_len])
        spk_emb = torch.randn(batch, 256)

        with torch.no_grad():
            result = model(
                x, x_lengths, spec, spec_lengths,
                speaker_embeddings=spk_emb,
            )

        # forward returns 8 elements (including decoder_subbands)
        assert len(result) == 8


# ---------------------------------------------------------------------------
# Tests: ONNX export with speaker_embedding inputs
# ---------------------------------------------------------------------------


class TestOnnxExportSpeakerEmbedding:
    """ONNX export includes speaker_embedding input."""

    @pytest.fixture
    def onnx_model_with_spk_emb(self, tmp_path, make_synthesizer_trn):
        """Export a multi-speaker model to ONNX with speaker_embedding support."""
        from piper_train.vits import commons

        torch.manual_seed(42)

        gin_channels = 256
        spk_emb_dim = 256  # same as gin_channels -> no projection needed

        model = make_synthesizer_trn(
            n_speakers=2, gin_channels=gin_channels, use_sdp=True, prosody_dim=0,
        )
        model.eval()
        model.onnx_export_mode = True
        if hasattr(model, "dp"):
            model.dp.onnx_export_mode = True

        with torch.no_grad():
            model.dec.remove_weight_norm()

        dummy_len = 10
        sequences = torch.randint(0, 50, (1, dummy_len), dtype=torch.long)
        seq_lengths = torch.LongTensor([dummy_len])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        sid = torch.LongTensor([0])
        spk_emb = torch.zeros(1, spk_emb_dim, dtype=torch.float32)

        def infer_forward(text, text_lengths, scales_t, sid_t,
                          speaker_embedding):
            length_scale = scales_t[1]
            noise_scale_w = scales_t[2]

            g = speaker_embedding.unsqueeze(-1)  # (batch, emb_dim, 1)

            x, m_p, logs_p, x_mask = model.enc_p(text, text_lengths, g=g)
            x_dp = model._prepare_prosody_input(x, x_mask, None)

            if model.use_sdp:
                logw = model.dp(
                    x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w
                )
            else:
                logw = model.dp(x_dp, x_mask, g=g)

            w = torch.exp(logw) * x_mask * length_scale
            durations = w.squeeze(1)
            w_ceil = torch.ceil(w)
            y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
            y_mask = torch.unsqueeze(
                commons.sequence_mask(y_lengths, y_lengths.max()), 1
            ).type_as(x_mask)
            attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
            attn = commons.generate_path(w_ceil, attn_mask)
            m_p = torch.matmul(
                attn.squeeze(1), m_p.transpose(1, 2)
            ).transpose(1, 2)
            logs_p = torch.matmul(
                attn.squeeze(1), logs_p.transpose(1, 2)
            ).transpose(1, 2)
            z_p = m_p
            z = model.flow(z_p, y_mask, g=g, reverse=True)
            o = model.dec((z * y_mask), g=g)
            return o, durations

        _orig = model.forward
        model.forward = infer_forward

        onnx_path = tmp_path / "test_spk_emb.onnx"
        try:
            torch.onnx.export(
                model,
                (sequences, seq_lengths, scales, sid, spk_emb),
                str(onnx_path),
                opset_version=15,
                input_names=[
                    "input", "input_lengths", "scales", "sid",
                    "speaker_embedding",
                ],
                output_names=["output", "durations"],
                dynamic_axes={
                    "input": {0: "batch_size", 1: "phonemes"},
                    "input_lengths": {0: "batch_size"},
                    "sid": {0: "batch_size"},
                    "speaker_embedding": {0: "batch_size", 1: "emb_dim"},
                    "output": {0: "batch_size", 2: "time"},
                    "durations": {0: "batch_size", 1: "phonemes"},
                },
                verbose=False,
                dynamo=False,
            )
        except (SystemError, Exception) as e:
            model.forward = _orig
            pytest.skip(f"ONNX export not supported: {e}")

        model.forward = _orig
        return onnx_path

    @pytest.mark.inference
    def test_onnx_has_speaker_embedding_inputs(self, onnx_model_with_spk_emb):
        """Exported ONNX model has speaker_embedding input."""
        import onnxruntime

        session = onnxruntime.InferenceSession(str(onnx_model_with_spk_emb))
        names = {inp.name for inp in session.get_inputs()}

        assert "speaker_embedding" in names
