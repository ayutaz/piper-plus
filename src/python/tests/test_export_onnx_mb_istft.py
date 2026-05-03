"""Tests for MB-iSTFT model ONNX export path.

Covers the full export pipeline for MBiSTFTGenerator-based models:
  1. torch.onnx.export succeeds for a SynthesizerTrn (MB-iSTFT decoder) model
  2. remove_weight_norm + onnx_export_mode forward produces correct output
  3. Exported ONNX model produces [B, 1, T] output (onnxruntime validation)
"""

import tempfile
from pathlib import Path

import pytest
import torch

from piper_train.export_onnx import set_export_mode
from piper_train.vits import commons
from piper_train.vits.mb_istft import MBiSTFTGenerator
from piper_train.vits.models import SynthesizerTrn


# ---------------------------------------------------------------------------
# Shared constants for MB-iSTFT model configuration
# ---------------------------------------------------------------------------

_MB_ISTFT_KWARGS = dict(
    n_vocab=97,
    spec_channels=513,
    segment_size=32,
    inter_channels=192,
    hidden_channels=192,
    filter_channels=768,
    n_heads=2,
    n_layers=6,
    kernel_size=3,
    p_dropout=0.1,
    resblock="2",
    resblock_kernel_sizes=(3, 5, 7),
    resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
    upsample_rates=(4, 4),
    upsample_initial_channel=256,
    upsample_kernel_sizes=(16, 16),
    n_speakers=1,
    n_languages=2,
    gin_channels=512,
    use_sdp=True,
    prosody_dim=0,
)

_DUMMY_INPUT_LENGTH = 10


def _build_mb_istft_model():
    """Create, eval, and prepare a SynthesizerTrn (MB-iSTFT decoder) for export."""
    torch.manual_seed(42)
    model = SynthesizerTrn(**_MB_ISTFT_KWARGS)
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()
    set_export_mode(model, True)
    return model


def _make_infer_forward(model):
    """Return a deterministic infer_forward closure suitable for ONNX export."""

    def infer_forward(text, text_lengths, scales, sid=None, lid=None):
        length_scale = scales[1]
        noise_scale_w = scales[2]

        g = model._get_global_conditioning(sid, lid)
        x, m_p, logs_p, x_mask = model.enc_p(text, text_lengths, g=g)

        x_dp = model._prepare_prosody_input(x, x_mask, None, lid=lid)
        if model.use_sdp:
            logw = model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w)
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

        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
        logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)

        z_p = m_p  # deterministic
        z = model.flow(z_p, y_mask, g=g, reverse=True)
        o = model.dec((z * y_mask), g=g)

        return o, durations

    return infer_forward


def _build_dummy_inputs():
    """Return (tuple_of_tensors, input_names, dynamic_axes) for ONNX export."""
    sequences = torch.randint(0, 97, (1, _DUMMY_INPUT_LENGTH), dtype=torch.long)
    sequence_lengths = torch.LongTensor([_DUMMY_INPUT_LENGTH])
    scales = torch.FloatTensor([0.667, 1.0, 0.8])
    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])

    dummy_input = (sequences, sequence_lengths, scales, sid, lid)
    input_names = ["input", "input_lengths", "scales", "sid", "lid"]
    dynamic_axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "sid": {0: "batch_size"},
        "lid": {0: "batch_size"},
        "output": {0: "batch_size", 2: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }
    return dummy_input, input_names, dynamic_axes


# ===========================================================================
# Test 1: torch.onnx.export succeeds for MB-iSTFT SynthesizerTrn
# ===========================================================================


@pytest.mark.unit
def test_mb_istft_onnx_export_succeeds():
    """MB-iSTFT model can be exported to ONNX via torch.onnx.export."""
    model = _build_mb_istft_model()
    model.forward = _make_infer_forward(model)

    dummy_input, input_names, dynamic_axes = _build_dummy_inputs()

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
        onnx_path = Path(f.name)

    try:
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            opset_version=15,
            input_names=input_names,
            output_names=["output", "durations"],
            dynamic_axes=dynamic_axes,
            verbose=False,
            dynamo=False,
        )
        assert onnx_path.stat().st_size > 0, "Exported ONNX file is empty"
    finally:
        onnx_path.unlink(missing_ok=True)


# ===========================================================================
# Test 2: remove_weight_norm + onnx_export_mode forward works correctly
# ===========================================================================


@pytest.mark.unit
def test_remove_weight_norm_then_onnx_forward():
    """MBiSTFTGenerator produces [B, 1, T] after remove_weight_norm + onnx_export_mode."""
    torch.manual_seed(42)
    gen = MBiSTFTGenerator(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
    )
    gen.eval()
    gen.remove_weight_norm()
    gen.onnx_export_mode = True

    x = torch.randn(1, 192, 32)
    with torch.no_grad():
        out = gen(x)

    assert isinstance(out, torch.Tensor), "Expected a single Tensor in onnx_export_mode"
    # Upsampling: 32 * 4 * 4 = 512 frames
    # iSTFT:      512 * hop_length(4) = 2048 per sub-band
    # PQMF:       2048 * subbands(4) = 8192 fullband samples
    assert out.shape == (1, 1, 8192), f"Expected (1, 1, 8192), got {out.shape}"


# ===========================================================================
# Test 3: ONNX model output shape [B, 1, T] via onnxruntime
# ===========================================================================


@pytest.mark.unit
def test_onnx_export_output_shape_b1t():
    """Exported MB-iSTFT ONNX model produces output with shape [B, 1, T]."""
    ort = pytest.importorskip("onnxruntime")
    import numpy as np

    model = _build_mb_istft_model()
    model.forward = _make_infer_forward(model)

    dummy_input, input_names, dynamic_axes = _build_dummy_inputs()

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
        onnx_path = Path(f.name)

    try:
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            opset_version=15,
            input_names=input_names,
            output_names=["output", "durations"],
            dynamic_axes=dynamic_axes,
            verbose=False,
            dynamo=False,
        )

        # Run inference with onnxruntime
        session = ort.InferenceSession(
            str(onnx_path), providers=["CPUExecutionProvider"]
        )

        # Build feeds from the actual ONNX graph inputs.
        # ONNX may drop unused inputs (e.g. sid when n_speakers=1),
        # so we query the session to stay in sync.
        onnx_input_names = {inp.name for inp in session.get_inputs()}

        phoneme_ids = np.random.randint(0, 97, (_DUMMY_INPUT_LENGTH,))
        all_feeds = {
            "input": np.expand_dims(phoneme_ids.astype(np.int64), 0),
            "input_lengths": np.array([_DUMMY_INPUT_LENGTH], dtype=np.int64),
            "scales": np.array([0.667, 1.0, 0.8], dtype=np.float32),
            "sid": np.array([0], dtype=np.int64),
            "lid": np.array([0], dtype=np.int64),
        }
        feeds = {k: v for k, v in all_feeds.items() if k in onnx_input_names}

        outputs = session.run(None, feeds)
        audio = outputs[0]
        durations = outputs[1]

        # audio: [B, 1, T]
        assert audio.ndim == 3, f"Expected 3D output, got {audio.ndim}D"
        assert audio.shape[0] == 1, f"Expected batch=1, got {audio.shape[0]}"
        assert audio.shape[1] == 1, f"Expected channels=1, got {audio.shape[1]}"
        assert audio.shape[2] > 0, "Audio time dimension must be positive"

        # durations: [B, phonemes]
        assert durations.ndim == 2, f"Expected 2D durations, got {durations.ndim}D"
        assert durations.shape[0] == 1
        assert durations.shape[1] == _DUMMY_INPUT_LENGTH
    finally:
        onnx_path.unlink(missing_ok=True)
