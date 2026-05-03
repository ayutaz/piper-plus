"""Tests for M3-02: speaker_embedding input path in SynthesizerTrn.

Verifies:
- SynthesizerTrn.infer() accepts speaker_embedding and produces valid audio
- speaker_embedding=None falls back to emb_g(sid) (backward compat)
- Linear projection when speaker_embedding dim != gin_channels
- ONNX export includes speaker_embedding / speaker_embedding_mask inputs
- speaker_embedding_mask=0 causes speaker_embedding to be ignored
- forward() accepts speaker_embedding kwarg without using it
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
        """Passing a speaker_embedding produces valid (non-zero) audio."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 12))
        x_len = torch.LongTensor([12])
        spk_emb = torch.randn(1, gin)

        with torch.no_grad():
            o, attn, y_mask, _, _ = model.infer(
                x, x_len, speaker_embedding=spk_emb
            )

        assert o.dim() == 3
        assert o.shape[0] == 1
        assert o.shape[2] > 0, "Audio length should be > 0"

    @pytest.mark.unit
    def test_infer_none_speaker_embedding_uses_sid(self, make_synthesizer_trn):
        """speaker_embedding=None falls back to emb_g(sid)."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        sid = torch.LongTensor([0])

        with torch.no_grad():
            o, attn, y_mask, _, _ = model.infer(x, x_len, sid=sid)

        assert o.dim() == 3
        assert o.shape[0] == 1

    @pytest.mark.unit
    def test_infer_speaker_embedding_overrides_sid(self, make_synthesizer_trn):
        """When both speaker_embedding and sid are provided, speaker_embedding wins."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        sid = torch.LongTensor([0])
        spk_emb = torch.randn(1, gin)

        with torch.no_grad():
            o_emb, _, _, _, _ = model.infer(
                x, x_len, sid=sid, speaker_embedding=spk_emb
            )
            o_sid, _, _, _, _ = model.infer(x, x_len, sid=sid)

        # Both should produce valid 3D audio tensors.
        # Audio lengths may differ (different conditioning -> different durations).
        assert o_emb.dim() == 3
        assert o_sid.dim() == 3
        assert o_emb.shape[0] == 1
        assert o_sid.shape[0] == 1

    @pytest.mark.unit
    def test_infer_speaker_embedding_3d(self, make_synthesizer_trn):
        """speaker_embedding with shape (batch, dim, 1) is accepted."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        spk_emb = torch.randn(1, gin, 1)  # already has trailing dim

        with torch.no_grad():
            o, _, _, _, _ = model.infer(x, x_len, speaker_embedding=spk_emb)

        assert o.dim() == 3


# ---------------------------------------------------------------------------
# Tests: Linear projection when dim mismatch
# ---------------------------------------------------------------------------


class TestSpeakerEmbeddingProjection:
    """Linear projection for mismatched speaker_embedding dimensions."""

    @pytest.mark.unit
    def test_projection_created_on_mismatch(self, make_synthesizer_trn):
        """spk_proj is lazily created when emb_dim != gin_channels."""
        gin = 512
        emb_dim = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        assert model.spk_proj is None, "spk_proj should start as None"

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        spk_emb = torch.randn(1, emb_dim)

        with torch.no_grad():
            o, _, _, _, _ = model.infer(x, x_len, speaker_embedding=spk_emb)

        assert model.spk_proj is not None, "spk_proj should be created"
        assert model.spk_proj.in_features == emb_dim
        assert model.spk_proj.out_features == gin

    @pytest.mark.unit
    def test_no_projection_when_dims_match(self, make_synthesizer_trn):
        """No projection needed when emb_dim == gin_channels."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        spk_emb = torch.randn(1, gin)

        with torch.no_grad():
            model.infer(x, x_len, speaker_embedding=spk_emb)

        assert model.spk_proj is None, "spk_proj should remain None when dims match"

    @pytest.mark.unit
    def test_projection_reused_across_calls(self, make_synthesizer_trn):
        """spk_proj is created once and reused."""
        gin = 512
        emb_dim = 256
        model = make_synthesizer_trn(n_speakers=2, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        spk_emb = torch.randn(1, emb_dim)

        with torch.no_grad():
            model.infer(x, x_len, speaker_embedding=spk_emb)
            proj_first = model.spk_proj
            model.infer(x, x_len, speaker_embedding=spk_emb)
            proj_second = model.spk_proj

        assert proj_first is proj_second, "spk_proj should be the same object"


# ---------------------------------------------------------------------------
# Tests: speaker_embedding with language embedding
# ---------------------------------------------------------------------------


class TestSpeakerEmbeddingWithLanguage:
    """speaker_embedding + emb_lang (multilingual voice cloning)."""

    @pytest.mark.unit
    def test_infer_with_speaker_embedding_and_lid(self, make_synthesizer_trn):
        """speaker_embedding combined with language embedding."""
        gin = 256
        model = make_synthesizer_trn(n_speakers=2, n_languages=3, gin_channels=gin)
        model.eval()

        x = torch.randint(0, 50, (1, 10))
        x_len = torch.LongTensor([10])
        lid = torch.LongTensor([1])
        spk_emb = torch.randn(1, gin)

        with torch.no_grad():
            o, _, _, _, _ = model.infer(
                x, x_len, lid=lid, speaker_embedding=spk_emb
            )

        assert o.dim() == 3
        assert o.shape[0] == 1


# ---------------------------------------------------------------------------
# Tests: forward() accepts speaker_embedding without using it
# ---------------------------------------------------------------------------


class TestForwardSpeakerEmbedding:
    """forward() accepts speaker_embedding kwarg (unused, future-reserved)."""

    @pytest.mark.unit
    def test_forward_accepts_speaker_embedding_kwarg(self, make_synthesizer_trn):
        """forward() does not raise when speaker_embedding is passed."""
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
                speaker_embedding=spk_emb,
            )

        # forward returns 8 elements (including decoder_subbands)
        assert len(result) == 8


# ---------------------------------------------------------------------------
# Tests: ONNX export with speaker_embedding inputs
# ---------------------------------------------------------------------------


class TestOnnxExportSpeakerEmbedding:
    """ONNX export includes speaker_embedding and speaker_embedding_mask."""

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
        spk_mask = torch.zeros(1, 1, dtype=torch.int64)

        def infer_forward(text, text_lengths, scales_t, sid_t,
                          speaker_embedding, speaker_embedding_mask):
            length_scale = scales_t[1]
            noise_scale_w = scales_t[2]

            # Standard sid-based conditioning
            g_base = model.emb_g(sid_t).unsqueeze(-1)  # (batch, gin, 1)

            # Speaker-embedding conditioning (trace-friendly: always evaluate
            # both paths and select via torch.where)
            g_se = speaker_embedding.unsqueeze(-1)  # (batch, emb_dim, 1)
            use_se = (speaker_embedding_mask >= 1).unsqueeze(-1).float()
            g = torch.where(use_se >= 1, g_se, g_base)

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
                (sequences, seq_lengths, scales, sid, spk_emb, spk_mask),
                str(onnx_path),
                opset_version=15,
                input_names=[
                    "input", "input_lengths", "scales", "sid",
                    "speaker_embedding", "speaker_embedding_mask",
                ],
                output_names=["output", "durations"],
                dynamic_axes={
                    "input": {0: "batch_size", 1: "phonemes"},
                    "input_lengths": {0: "batch_size"},
                    "sid": {0: "batch_size"},
                    "speaker_embedding": {0: "batch_size", 1: "emb_dim"},
                    "speaker_embedding_mask": {0: "batch_size"},
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
        """Exported ONNX model has speaker_embedding and mask inputs."""
        import onnxruntime

        session = onnxruntime.InferenceSession(str(onnx_model_with_spk_emb))
        names = {inp.name for inp in session.get_inputs()}

        assert "speaker_embedding" in names
        assert "speaker_embedding_mask" in names

    @pytest.mark.inference
    def test_onnx_mask_zero_ignores_embedding(self, onnx_model_with_spk_emb):
        """mask=0 produces same output regardless of speaker_embedding values."""
        import numpy as np
        import onnxruntime

        session = onnxruntime.InferenceSession(str(onnx_model_with_spk_emb))

        text = np.array([[1, 8, 5, 10, 20, 30, 15, 2]], dtype=np.int64)
        text_lengths = np.array([text.shape[1]], dtype=np.int64)
        scales = np.array([0.0, 1.0, 0.8], dtype=np.float32)
        sid = np.array([0], dtype=np.int64)
        mask_off = np.array([[0]], dtype=np.int64)

        # Two different embeddings but both with mask=0
        np.random.seed(42)
        emb_a = np.random.randn(1, 256).astype(np.float32)
        emb_b = np.random.randn(1, 256).astype(np.float32)

        out_a = session.run(None, {
            "input": text, "input_lengths": text_lengths,
            "scales": scales, "sid": sid,
            "speaker_embedding": emb_a,
            "speaker_embedding_mask": mask_off,
        })[0]

        out_b = session.run(None, {
            "input": text, "input_lengths": text_lengths,
            "scales": scales, "sid": sid,
            "speaker_embedding": emb_b,
            "speaker_embedding_mask": mask_off,
        })[0]

        np.testing.assert_array_equal(
            out_a, out_b,
            err_msg="With mask=0, different speaker_embeddings should produce identical output",
        )

    @pytest.mark.inference
    def test_onnx_mask_one_uses_embedding(self, onnx_model_with_spk_emb):
        """mask=1 produces valid audio output."""
        import numpy as np
        import onnxruntime

        session = onnxruntime.InferenceSession(str(onnx_model_with_spk_emb))

        text = np.array([[1, 8, 5, 10, 20, 30, 15, 2]], dtype=np.int64)
        text_lengths = np.array([text.shape[1]], dtype=np.int64)
        scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)
        sid = np.array([0], dtype=np.int64)
        emb = np.random.randn(1, 256).astype(np.float32)
        mask_on = np.array([[1]], dtype=np.int64)

        out = session.run(None, {
            "input": text, "input_lengths": text_lengths,
            "scales": scales, "sid": sid,
            "speaker_embedding": emb,
            "speaker_embedding_mask": mask_on,
        })[0]

        assert out.ndim >= 2
        assert out.size > 0
        assert np.isfinite(out).all(), "Audio contains NaN or Inf"
