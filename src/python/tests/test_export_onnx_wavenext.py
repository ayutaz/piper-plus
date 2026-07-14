"""Tests for the WaveNeXt model ONNX export path (Stage 1).

Mirrors test_export_onnx_mb_istft.py for ``decoder_arch='wavenext'`` and
pins the opset-17 branch decided in
docs/design/wavenext-decoder-ablation/04-pre-stage0-verification.md §4:

  1. full-model export succeeds with OPSET_VERSION_WAVENEXT (17)
  2. ai.onnx opset_import version == 17
  3. decoder-only graph has exactly 10 native LayerNormalization nodes
     (post-embed 1 + ConvNeXtBlock 8 + final 1 — 03 doc test plan)
  4. onnxruntime inference produces [1, 1, T] with T % 256 == 0
  5. decoder torch↔ORT parity (PoC measured 1.13e-06; CI margin 1e-4)
  6. OPSET_VERSION=15 contract pin (check_onnx_export_contract.py regex
     must not match OPSET_VERSION_WAVENEXT)
  7. convert_fp16 LayerNormalization keep-list fires on the opset-17 graph
"""

import re
from collections import Counter
from pathlib import Path

import pytest
import torch

from piper_train import export_onnx
from piper_train.export_onnx import (
    OPSET_VERSION,
    OPSET_VERSION_WAVENEXT,
    set_export_mode,
)
from piper_train.vits import commons
from piper_train.vits.models import SynthesizerTrn
from piper_train.vits.wavenext import WaveNeXtGenerator


# ---------------------------------------------------------------------------
# Shared constants for WaveNeXt model configuration
# (same layout as test_export_onnx_mb_istft.py, decoder swapped)
# ---------------------------------------------------------------------------

_WAVENEXT_KWARGS = {
    "n_vocab": 97,
    "spec_channels": 513,
    "segment_size": 32,
    "inter_channels": 192,
    "hidden_channels": 192,
    "filter_channels": 768,
    "n_heads": 2,
    "n_layers": 6,
    "kernel_size": 3,
    "p_dropout": 0.1,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 256,
    "upsample_kernel_sizes": (16, 16),
    "n_speakers": 1,
    "n_languages": 2,
    "gin_channels": 512,
    "use_sdp": True,
    "prosody_dim": 0,
    "decoder_arch": "wavenext",
}

_DUMMY_INPUT_LENGTH = 10


def _build_wavenext_model():
    """Create, eval, and prepare a SynthesizerTrn (WaveNeXt decoder) for export."""
    torch.manual_seed(42)
    model = SynthesizerTrn(**_WAVENEXT_KWARGS)
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


@pytest.fixture(scope="module")
def full_model_onnx(tmp_path_factory):
    """Export the full WaveNeXt SynthesizerTrn once with the opset-17 branch."""
    model = _build_wavenext_model()
    model.forward = _make_infer_forward(model)

    dummy_input, input_names, dynamic_axes = _build_dummy_inputs()
    onnx_path = tmp_path_factory.mktemp("wavenext_onnx") / "wavenext_full.onnx"

    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        opset_version=OPSET_VERSION_WAVENEXT,
        input_names=input_names,
        output_names=["output", "durations"],
        dynamic_axes=dynamic_axes,
        verbose=False,
        dynamo=False,
    )
    return onnx_path


@pytest.fixture(scope="module")
def decoder_onnx(tmp_path_factory):
    """Export a standalone WaveNeXtGenerator once (opset 17, dynamic frames).

    Returns (generator, onnx_path) so parity tests compare against the same
    weights that were exported.
    """
    torch.manual_seed(1234)
    gen = WaveNeXtGenerator(in_channels=192)
    gen.eval()
    gen.remove_weight_norm()
    gen.onnx_export_mode = True

    onnx_path = tmp_path_factory.mktemp("wavenext_dec_onnx") / "wavenext_dec.onnx"
    dummy = torch.randn(1, 192, 32)
    torch.onnx.export(
        gen,
        (dummy,),
        str(onnx_path),
        opset_version=OPSET_VERSION_WAVENEXT,
        input_names=["z"],
        output_names=["audio"],
        dynamic_axes={
            "z": {0: "batch_size", 2: "frames"},
            "audio": {0: "batch_size", 2: "time"},
        },
        verbose=False,
        dynamo=False,
    )
    return gen, onnx_path


# ===========================================================================
# Test 1-2: full-model export with the wavenext opset branch
# ===========================================================================


@pytest.mark.unit
def test_wavenext_onnx_export_succeeds(full_model_onnx):
    """WaveNeXt model exports via torch.onnx.export at OPSET_VERSION_WAVENEXT."""
    assert full_model_onnx.stat().st_size > 0, "Exported ONNX file is empty"


@pytest.mark.unit
def test_wavenext_opset_import_is_17(full_model_onnx):
    """The exported graph declares ai.onnx opset 17."""
    onnx = pytest.importorskip("onnx")

    model = onnx.load(str(full_model_onnx))
    ai_onnx_versions = [
        opset.version for opset in model.opset_import if opset.domain in ("", "ai.onnx")
    ]
    assert ai_onnx_versions == [OPSET_VERSION_WAVENEXT]


# ===========================================================================
# Test 3: native LayerNormalization nodes in the decoder graph
# ===========================================================================


@pytest.mark.unit
def test_decoder_graph_has_10_layer_normalization_nodes(decoder_onnx):
    """opset 17 keeps 10 native LN nodes: post-embed 1 + block 8 + final 1."""
    onnx = pytest.importorskip("onnx")

    _gen, onnx_path = decoder_onnx
    model = onnx.load(str(onnx_path))
    op_counts = Counter(node.op_type for node in model.graph.node)
    assert op_counts["LayerNormalization"] == 10


# ===========================================================================
# Test 4: ONNX model output shape [1, 1, T] via onnxruntime
# ===========================================================================


@pytest.mark.unit
def test_onnx_inference_output_is_hop_aligned(full_model_onnx):
    """ORT output is [1, 1, T] with T a multiple of hop 256, durations [1, P]."""
    ort = pytest.importorskip("onnxruntime")
    import numpy as np

    session = ort.InferenceSession(
        str(full_model_onnx), providers=["CPUExecutionProvider"]
    )

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

    assert audio.ndim == 3, f"Expected 3D output, got {audio.ndim}D"
    assert audio.shape[0] == 1
    assert audio.shape[1] == 1
    assert audio.shape[2] > 0
    assert audio.shape[2] % 256 == 0, (
        f"WaveNeXt output must be frame-aligned to hop 256, got {audio.shape[2]}"
    )

    assert durations.ndim == 2
    assert durations.shape[0] == 1
    assert durations.shape[1] == _DUMMY_INPUT_LENGTH


# ===========================================================================
# Test 5: decoder torch↔ORT parity
# ===========================================================================


@pytest.mark.unit
def test_decoder_torch_ort_parity(decoder_onnx):
    """Decoder torch vs ORT max abs diff < 1e-4 (PoC measured 1.13e-06)."""
    ort = pytest.importorskip("onnxruntime")
    import numpy as np

    gen, onnx_path = decoder_onnx
    torch.manual_seed(1234)
    z = torch.randn(1, 192, 200)

    with torch.no_grad():
        torch_out = gen(z).numpy()

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    (ort_out,) = session.run(None, {"z": z.numpy()})

    assert ort_out.shape == torch_out.shape == (1, 1, 200 * 256)
    max_abs_diff = float(np.max(np.abs(torch_out - ort_out)))
    assert max_abs_diff < 1e-4, f"torch↔ORT parity too loose: {max_abs_diff}"


# ===========================================================================
# Test 6: OPSET_VERSION=15 contract stays unbroken
# ===========================================================================


@pytest.mark.unit
def test_opset_contract_regex_still_pins_15():
    """OPSET_VERSION_WAVENEXT must not shadow the blocking contract gate.

    scripts/check_onnx_export_contract.py:36 の regex (re.search 先頭一致) が
    従来どおり main opset=15 を見つけることを恒久 pin する。prefix 命名
    (WAVENEXT_OPSET_VERSION) だと部分文字列マッチで gate が壊れる (04 doc §4)。
    """
    source = Path(export_onnx.__file__).read_text(encoding="utf-8")
    # Same regex as scripts/check_onnx_export_contract.py
    match = re.search(r"OPSET_VERSION\s*=\s*(\d+)", source)
    assert match is not None
    assert match.group(1) == "15"
    assert OPSET_VERSION == 15
    assert OPSET_VERSION_WAVENEXT == 17


# ===========================================================================
# Test 7: convert_fp16 LayerNormalization keep-list fires
# ===========================================================================


@pytest.mark.unit
def test_convert_fp16_keeps_layer_norm_params_fp32(decoder_onnx, tmp_path):
    """FP16 conversion keeps LN scale/bias FP32 and converts large weights.

    opset 17 の native LayerNormalization node があることで convert_fp16 の
    DEFAULT_KEEP_FP32_OPS keep-list が発火する (wavenext を opset 17 で
    export する rationale そのもの — 04 doc §4)。
    """
    onnx = pytest.importorskip("onnx")

    from piper_train.tools.convert_fp16 import convert_fp16

    _gen, onnx_path = decoder_onnx
    fp16_path = tmp_path / "wavenext_dec_fp16.onnx"
    converted = convert_fp16(onnx_path, fp16_path)

    init_by_name = {init.name: init for init in converted.graph.initializer}
    ln_inits = [
        init_by_name[inp]
        for node in converted.graph.node
        if node.op_type == "LayerNormalization"
        for inp in node.input
        if inp in init_by_name
    ]
    assert ln_inits, "No initializer-fed LayerNormalization nodes found"
    assert all(init.data_type == onnx.TensorProto.FLOAT for init in ln_inits), (
        "LayerNormalization scale/bias must stay FP32 (keep-list)"
    )

    def _numel(init):
        n = 1
        for d in init.dims:
            n *= d
        return n

    large_fp16 = [
        init
        for init in converted.graph.initializer
        if init.data_type == onnx.TensorProto.FLOAT16 and _numel(init) > 100_000
    ]
    assert large_fp16, "Large weight initializers should have been converted to FP16"

    onnx.checker.check_model(onnx.load(str(fp16_path)), full_check=False)
