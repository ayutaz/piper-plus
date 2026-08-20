"""v11 A′: carrier head つきモデルの ONNX export 契約テスト。

docs/design/zero-shot-v11-harmonic-head-design.md §3.5 / §5.4。

固定する契約:

* **入力契約 [1,192] 不変**: F0 も noise も graph 内で完結する
  (7 ランタイム無改修の前提条件)。
* **noise 枝の乱数は RandomNormalLike** (opset 15 標準、既存 piper graph の
  z サンプリングに前例あり)。学習時のみの位相オフセット RNG
  (``RandomUniform`` 系) は eval export に現れてはいけない。
* **torch ↔ ORT parity は決定的に検証する**: full graph は noise RNG を含む
  ため波形一致では比較できない — decoder 単体で noise を外部入力に固定した
  wrapper を export し、長短 2 通りで波形 parity を取る (float64 位相累積に
  より長さ非依存 ~2e-5、設計 doc §5.4)。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")
onnx = pytest.importorskip("onnx", reason="onnx required")
onnxruntime = pytest.importorskip("onnxruntime", reason="onnxruntime required")
pytest.importorskip("onnxscript", reason="onnxscript required for export")

from piper_train.export_onnx import build_infer_forward, set_export_mode  # noqa: E402
from piper_train.vits.models import SynthesizerTrn  # noqa: E402


OPSET = 15
N_VOCAB = 60
HEAD_UP = 16

_KWARGS = {
    "n_vocab": N_VOCAB,
    "spec_channels": 513,
    "segment_size": 32,
    "inter_channels": 192,
    "hidden_channels": 192,
    "filter_channels": 256,
    "n_heads": 2,
    "n_layers": 2,
    "kernel_size": 3,
    "p_dropout": 0.0,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 256,
    "upsample_kernel_sizes": (16, 16),
    "n_speakers": 4,
    "n_languages": 1,
    "gin_channels": 512,
    "use_sdp": True,
    "prosody_dim": 0,
}


def _build(**overrides):
    torch.manual_seed(1234)
    model = SynthesizerTrn(
        **_KWARGS, use_f0_path=True, use_carrier_head=True, **overrides
    )
    # 学習済みらしい挙動にするため zero/small-init を外す (担体が実際に鳴る
    # graph を export しないと契約テストが無意味になる)
    with torch.no_grad():
        model.dec.f0_feat.weight.normal_(0.0, 0.05)
        model.dec.carrier_head.gain_net.weight.normal_(0.0, 0.05)
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()
    set_export_mode(model, True)
    return model


def _inputs(n_phonemes: int):
    torch.manual_seed(7)
    text = torch.randint(1, N_VOCAB, (1, n_phonemes), dtype=torch.long)
    lengths = torch.LongTensor([n_phonemes])
    scales = torch.FloatTensor([0.4, 1.0, 0.5])
    emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
    return text, lengths, scales, emb


def _export(model, path: Path, n_phonemes: int = 12):
    model.forward = build_infer_forward(model, stochastic=False)
    text, lengths, scales, emb = _inputs(n_phonemes)
    torch.onnx.export(
        model=model,
        args=(text, lengths, scales, None, None, None, emb),
        f=str(path),
        opset_version=OPSET,
        input_names=["input", "input_lengths", "scales", "speaker_embedding"],
        output_names=["output", "durations"],
        dynamic_axes={
            "input": {0: "batch_size", 1: "phonemes"},
            "input_lengths": {0: "batch_size"},
            "speaker_embedding": {0: "batch_size"},
            "output": {0: "batch_size", 2: "time"},
            "durations": {0: "batch_size", 1: "phonemes"},
        },
        dynamo=False,
    )
    return path


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    model = _build()
    path = tmp_path_factory.mktemp("carrier_onnx") / "carrier.onnx"
    _export(model, path)
    return model, path


def test_export_succeeds_and_passes_the_onnx_checker(exported):
    _model, path = exported
    proto = onnx.load(str(path))
    onnx.checker.check_model(proto, full_check=False)
    onnx.shape_inference.infer_shapes(proto)


def test_input_contract_is_unchanged(exported):
    """noise / F0 とも graph 内で完結し、入力は増えない (7 ランタイム無改修)。"""
    _model, path = exported
    proto = onnx.load(str(path))
    names = [i.name for i in proto.graph.input]
    assert names == ["input", "input_lengths", "scales", "speaker_embedding"]
    spk = next(i for i in proto.graph.input if i.name == "speaker_embedding")
    dims = spk.type.tensor_type.shape.dim
    assert len(dims) == 2
    assert dims[1].dim_value == 192


def test_graph_has_the_noise_rng_and_carrier_ops_but_no_phase_rng(exported):
    _model, path = exported
    proto = onnx.load(str(path))
    ops = {node.op_type for node in proto.graph.node}
    # noise 枝: RandomNormalLike (既存 z サンプリングに前例のある標準 op)
    assert "RandomNormalLike" in ops
    # 学習時のみの初期位相 RNG は eval export に出ない
    assert not {"RandomUniform", "RandomUniformLike"} & ops

    carrier_ops = {
        node.op_type for node in proto.graph.node if "carrier_head" in node.name
    }
    assert "CumSum" in carrier_ops, "carrier phase accumulation is missing"
    assert "MatMul" in carrier_ops, "MatMul-fused gain application is missing"
    # float64 位相累積 (parity の長さ非依存性)
    casts_to_double = [
        node
        for node in proto.graph.node
        if node.op_type == "Cast"
        and "carrier_head" in node.name
        and any(
            a.name == "to" and a.i == onnx.TensorProto.DOUBLE for a in node.attribute
        )
    ]
    assert casts_to_double, "carrier phase accumulation must run in float64"


def test_ort_runs_and_matches_torch_shapes(exported):
    """full graph は noise RNG を含むため波形一致は取れない — 実行可能性と
    形状・有限性を固定する (決定的 parity は decoder wrapper 側)。"""
    model, path = exported
    text, lengths, scales, emb = _inputs(12)
    with torch.no_grad():
        torch_out, _ = model(text, lengths, scales, None, None, None, emb)
    sess = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    ort_out = sess.run(
        None,
        {
            "input": text.numpy(),
            "input_lengths": lengths.numpy(),
            "scales": scales.numpy(),
            "speaker_embedding": emb.numpy(),
        },
    )[0]
    assert ort_out.shape == tuple(torch_out.shape)
    assert np.isfinite(ort_out).all()


# ---------------------------------------------------------------------------
# 決定的 parity: decoder 単体、noise を外部入力に固定
# ---------------------------------------------------------------------------


class _DecWrapper(torch.nn.Module):
    def __init__(self, dec):
        super().__init__()
        self.dec = dec

    def forward(self, z, g, f0, noise):
        return self.dec(z, g=g, f0=f0, carrier_noise=noise)


def _dec_inputs(frames: int, seed: int = 5):
    g = torch.Generator().manual_seed(seed)
    z = torch.randn(1, 192, frames, generator=g)
    spk = torch.randn(1, 512, 1, generator=g)
    f0 = torch.full((1, 1, frames), 210.0)
    f0[:, :, ::7] = 0.0
    noise = torch.randn(1, 18, frames * HEAD_UP, generator=g)
    return z, spk, f0, noise


@pytest.fixture(scope="module")
def exported_decoder(tmp_path_factory):
    model = _build()
    wrapper = _DecWrapper(model.dec).eval()
    path = tmp_path_factory.mktemp("carrier_dec") / "carrier_dec.onnx"
    torch.onnx.export(
        model=wrapper,
        args=_dec_inputs(60),
        f=str(path),
        opset_version=OPSET,
        input_names=["z", "g", "f0", "noise"],
        output_names=["wav"],
        dynamic_axes={
            "z": {2: "frames"},
            "f0": {2: "frames"},
            "noise": {2: "head_frames"},
            "wav": {2: "time"},
        },
        dynamo=False,
    )
    return wrapper, path


@pytest.mark.parametrize("frames", [60, 300])
def test_decoder_parity_is_length_independent(exported_decoder, frames):
    """noise を固定した decoder 単体で torch と ORT の波形が一致する。

    位相は float64 で累積されるため誤差は長さ非依存 (~2e-5、設計 doc §5.4)。
    fp32 累積に退行すると長尺側だけが落ちる。
    """
    wrapper, path = exported_decoder
    z, g, f0, noise = _dec_inputs(frames)
    with torch.no_grad():
        torch_out = wrapper(z, g, f0, noise)
    sess = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    ort_out = sess.run(
        None,
        {
            "z": z.numpy(),
            "g": g.numpy(),
            "f0": f0.numpy(),
            "noise": noise.numpy(),
        },
    )[0]
    assert ort_out.shape == tuple(torch_out.shape)
    np.testing.assert_allclose(ort_out, torch_out.numpy(), atol=2e-4, rtol=0)
