"""Unit tests for build_infer_forward() extracted from export_onnx.py.

Tests verify:
- The factory returns a callable
- Deterministic mode produces stable output
- Stochastic mode produces varying output
- Output shapes are correct
- Single-speaker (sid=None, lid=None) works
- Multi-speaker with sid/lid works
"""

import pytest

torch = pytest.importorskip(
    "torch", reason="torch required for build_infer_forward tests"
)


@pytest.mark.unit
class TestBuildInferForward:
    """Tests for the build_infer_forward factory function."""

    def test_returns_callable(self, mock_vits_model):
        """build_infer_forward returns a callable."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)
        assert callable(fn)

    def test_deterministic_output_stable(self, mock_vits_model):
        """Deterministic mode: same input produces identical output twice.

        Note: onnx_export_mode must be set to ensure the StochasticDurationPredictor
        produces deterministic durations (it uses internal randomness otherwise).
        """
        from piper_train.export_onnx import build_infer_forward

        # Enable ONNX export mode so SDP is fully deterministic
        mock_vits_model.onnx_export_mode = True
        if hasattr(mock_vits_model, "dp"):
            mock_vits_model.dp.onnx_export_mode = True

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.4, 1.0, 0.5])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio1, dur1 = fn(text, text_lengths, scales, prosody_features=prosody)
            audio2, dur2 = fn(text, text_lengths, scales, prosody_features=prosody)

        torch.testing.assert_close(audio1, audio2)
        torch.testing.assert_close(dur1, dur2)

    def test_stochastic_output_varies(self, mock_vits_model):
        """Stochastic mode: same input produces different output across runs."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=True)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.4, 1.0, 0.5])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio1, _ = fn(text, text_lengths, scales, prosody_features=prosody)
            audio2, _ = fn(text, text_lengths, scales, prosody_features=prosody)

        # With noise_scale=0.4, outputs should differ
        assert not torch.equal(audio1, audio2), (
            "Stochastic mode should produce different outputs across runs"
        )

    def test_output_shape_audio(self, mock_vits_model):
        """Audio output has 3 dimensions: (batch, channels, time)."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.4, 1.0, 0.5])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio, _ = fn(text, text_lengths, scales, prosody_features=prosody)

        assert audio.ndim == 3, f"Expected audio.ndim == 3, got {audio.ndim}"
        assert audio.shape[0] == 1, "Batch dimension should be 1"

    def test_output_shape_durations(self, mock_vits_model):
        """Durations shape is (batch, phoneme_length)."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        phoneme_length = 10
        text = torch.randint(0, 50, (1, phoneme_length), dtype=torch.long)
        text_lengths = torch.LongTensor([phoneme_length])
        scales = torch.FloatTensor([0.4, 1.0, 0.5])
        prosody = torch.zeros(1, phoneme_length, 3, dtype=torch.long)

        with torch.no_grad():
            _, durations = fn(text, text_lengths, scales, prosody_features=prosody)

        assert durations.shape == (1, phoneme_length), (
            f"Expected durations shape (1, {phoneme_length}), got {durations.shape}"
        )

    def test_single_speaker_no_embedding(self, mock_vits_model):
        """Single-speaker model works with speaker_embedding=None, lid=None."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.4, 1.0, 0.5])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio, durations = fn(
                text,
                text_lengths,
                scales,
                speaker_embedding=None,
                lid=None,
                prosody_features=prosody,
            )

        assert audio.shape[0] == 1
        assert durations.shape[0] == 1

    def test_multilingual_with_lid(self, mock_vits_model_multilingual):
        """Multilingual model works with explicit lid (sid は v1.12 契約で廃止)。"""
        from piper_train.export_onnx import build_infer_forward

        model = mock_vits_model_multilingual
        fn = build_infer_forward(model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.4, 1.0, 0.5])
        lid = torch.LongTensor([0])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio, durations = fn(
                text,
                text_lengths,
                scales,
                lid=lid,
                prosody_features=prosody,
            )

        assert audio.ndim == 3, f"Expected audio.ndim == 3, got {audio.ndim}"
        assert durations.shape == (1, 10)


@pytest.mark.unit
@pytest.mark.training
def test_parity_with_model_infer():
    """build_infer_forward output must match model.infer() output (deterministic mode).

    This ensures the two inference code paths — build_infer_forward() used for
    ONNX export and SynthesizerTrn.infer() used at training-time — stay in sync.
    Divergence would mean the exported ONNX model behaves differently from the
    PyTorch model's own inference method.
    """
    from piper_train.vits.models import SynthesizerTrn
    from piper_train.export_onnx import build_infer_forward

    torch.manual_seed(42)

    # Create a tiny model (small enough to run fast in CI)
    model = SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=8192,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.0,
        resblock="1",
        resblock_kernel_sizes=[3, 7, 11],
        resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        upsample_rates=[8, 8, 2, 2],
        upsample_initial_channel=128,
        upsample_kernel_sizes=[16, 16, 4, 4],
        n_speakers=1,
        gin_channels=0,
        use_sdp=True,
        prosody_dim=16,
    )
    model.eval()

    with torch.no_grad():
        model.dec.remove_weight_norm()

    # Enable ONNX export mode for deterministic SDP behaviour
    model.onnx_export_mode = True
    if hasattr(model, "dp"):
        model.dp.onnx_export_mode = True

    # Shared inputs
    text = torch.randint(0, 50, (1, 10), dtype=torch.long)
    text_lengths = torch.LongTensor([10])
    prosody = torch.zeros(1, 10, 3, dtype=torch.long)

    # --- Path 1: model.infer() (deterministic via onnx_export_mode + noise_scale=0) ---
    with torch.no_grad():
        audio_infer, _attn, _y_mask, (_z, _z_p, _m_p, _logs_p), _durations = (
            model.infer(
                text,
                text_lengths,
                noise_scale=0.0,
                noise_scale_w=0.0,
                length_scale=1.0,
                prosody_features=prosody,
            )
        )

    # --- Path 2: build_infer_forward (deterministic, stochastic=False) ---
    infer_fn = build_infer_forward(model, stochastic=False)
    scales = torch.FloatTensor(
        [0.0, 1.0, 0.0]
    )  # noise_scale, length_scale, noise_scale_w

    with torch.no_grad():
        audio_export, _durations = infer_fn(
            text,
            text_lengths,
            scales,
            prosody_features=prosody,
        )

    # Both paths should produce identical audio
    assert audio_infer.shape == audio_export.shape, (
        f"Shape mismatch: model.infer()={audio_infer.shape} vs "
        f"build_infer_forward()={audio_export.shape}"
    )
    assert torch.allclose(audio_infer, audio_export, atol=1e-5), (
        "Audio output diverged between model.infer() and build_infer_forward(). "
        f"Max diff: {(audio_infer - audio_export).abs().max().item():.6e}"
    )


@pytest.mark.unit
@pytest.mark.training
def test_export_positional_order_zero_shot_adaln_carrier():
    """export の位置引数順で build_infer_forward が models.infer と一致する。

    ONNX export の入力順は (text, lengths, scales, speaker_embedding, lid,
    prosody_features) — speaker_embedding が第 4 位置。v11 実測バグ (2026-08):
    main() 内の手書き infer_forward 複製が enc_p の g_spk (P2 AdaLN) を
    落とし、ONNX だけ話者条件が断線して担体の調波が崩壊した。export 経路を
    build_infer_forward 一本に固定し、export と同じ位置順 + v11 構成
    (use_adaln_encp + use_f0_path + use_carrier_head) の parity をここで pin する。
    """
    from piper_train.export_onnx import build_infer_forward, set_export_mode
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(1234)
    model = SynthesizerTrn(
        n_vocab=60,
        spec_channels=513,
        segment_size=32,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=256,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.0,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        n_speakers=4,
        n_languages=2,
        gin_channels=512,
        use_sdp=True,
        prosody_dim=0,
        use_f0_path=True,
        use_carrier_head=True,
        use_adaln_encp=True,
    )
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()
    set_export_mode(model, True)
    # SDP は onnx_export_mode 属性を宣言していないため set_export_mode の
    # hasattr ガードを素通りする — 参照経路の決定論化はここで明示する
    # (build_infer_forward(stochastic=False) は fn 側で同じ値を設定する)
    model.onnx_export_mode = True
    model.dp.onnx_export_mode = True

    text = torch.randint(1, 60, (1, 12), dtype=torch.long)
    lengths = torch.LongTensor([12])
    scales = torch.FloatTensor([0.4, 1.0, 0.5])
    emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
    lid = torch.LongTensor([0])

    # carrier のノイズ枝 (randn_like) が RNG を消費するため、両経路の直前で
    # 同一 seed を張る (z_p/SDP は export mode で決定論)
    torch.manual_seed(7)
    with torch.no_grad():
        ref_audio, _attn, _y_mask, _latents, ref_dur = model.infer(
            text,
            lengths,
            lid=lid,
            noise_scale=0.4,
            length_scale=1.0,
            noise_scale_w=0.5,
            speaker_embeddings=emb,
        )

    fn = build_infer_forward(model, stochastic=False)
    torch.manual_seed(7)
    with torch.no_grad():
        audio, dur = fn(text, lengths, scales, emb, lid)

    torch.testing.assert_close(audio, ref_audio)
    torch.testing.assert_close(dur, ref_dur)
