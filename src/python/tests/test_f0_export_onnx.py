"""S-2: F0 経路つきモデルの ONNX export 契約テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §3.2 (export) / §3.4 (位相精度) /
§4.3 判定基準の「ONNX 入力契約 speaker_embedding [1,192] 不変」。

固定する契約:

* **推論は単一 graph で完結**する。F0 は graph 内で予測されるので、外部入力は
  増えない (7 ランタイム無改修という v10b の前提条件そのもの)。
* **torch と ORT の出力が一致**する。ここで使う op は ``CumSum`` / ``Floor`` /
  ``Log`` / ``Clip`` / ``Greater`` など opset 15 の標準のみ。
* **長尺でも parity が保たれる**。fp32 で位相を累積すると torch と ORT で
  cumsum の加算順序が違い、誤差が長さとともに増幅する (設計 doc §3.4【実測】)。
  float64 累積を入れてある前提を、実際に長短 2 通りで確認する。
* **乱数 op を含まない**。位相の初期オフセットは学習時のみ (``eval()`` では 0)
  なので、export された graph に ``RandomUniform`` 系が現れてはいけない。
"""

from __future__ import annotations

import tempfile
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

_KWARGS = dict(
    n_vocab=N_VOCAB,
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
    n_languages=1,
    gin_channels=512,
    use_sdp=True,
    prosody_dim=0,
)


def _build(**overrides):
    torch.manual_seed(1234)
    model = SynthesizerTrn(**_KWARGS, use_f0_path=True, **overrides)
    # 学習済みらしい挙動にするため zero-init を外す (F0 経路が実際に働く graph
    # を export しないと parity テストが無意味になる)
    with torch.no_grad():
        model.dec.head_proj.weight.normal_(0.0, 0.05)
        model.dec.f0_feat.weight.normal_(0.0, 0.05)
        if hasattr(model, "f0_prior_res"):
            model.f0_prior_res.weight.normal_(0.0, 0.05)
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
        args=(text, lengths, scales, emb),
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
    path = tmp_path_factory.mktemp("s2onnx") / "s2.onnx"
    _export(model, path)
    return model, path


def test_export_succeeds_and_passes_the_onnx_checker(exported):
    _model, path = exported
    proto = onnx.load(str(path))
    onnx.checker.check_model(proto, full_check=False)
    onnx.shape_inference.infer_shapes(proto)


def test_input_contract_is_unchanged(exported):
    """F0 は graph 内で予測されるので入力は増えない (7 ランタイム無改修)。"""
    _model, path = exported
    proto = onnx.load(str(path))
    names = [i.name for i in proto.graph.input]
    assert names == ["input", "input_lengths", "scales", "speaker_embedding"]
    spk = next(i for i in proto.graph.input if i.name == "speaker_embedding")
    dims = spk.type.tensor_type.shape.dim
    assert len(dims) == 2
    assert dims[1].dim_value == 192


def test_graph_contains_the_phase_ops_and_no_random_ops(exported):
    """位相テンプレートが graph に出ており、乱数 op は出ていない。

    ``CumSum`` は SDP の flow (transforms) も使うので、op_type だけを見ると
    F0 経路が丸ごと欠けていても pass してしまう。テンプレート module の
    scope 名 (``/dec/phase_template/``) で照合する。
    """
    _model, path = exported
    proto = onnx.load(str(path))
    template_ops = {
        node.op_type
        for node in proto.graph.node
        if "phase_template" in node.name
    }
    assert "CumSum" in template_ops, "phase accumulation is missing"
    assert "Floor" in template_ops, "cycle wrapping is missing"
    # float64 位相累積 (§3.4) — Cast to DOUBLE (elem_type 11) が居ること
    casts_to_double = [
        node
        for node in proto.graph.node
        if node.op_type == "Cast"
        and "phase_template" in node.name
        and any(a.name == "to" and a.i == onnx.TensorProto.DOUBLE
                for a in node.attribute)
    ]
    assert casts_to_double, "phase accumulation must run in float64"

    ops = {node.op_type for node in proto.graph.node}
    assert not {"RandomUniform", "RandomUniformLike"} & ops, (
        "eval-mode export must not contain the training-only phase offset RNG"
    )


def _run_ort(path: Path, n_phonemes: int):
    text, lengths, scales, emb = _inputs(n_phonemes)
    sess = onnxruntime.InferenceSession(
        str(path), providers=["CPUExecutionProvider"]
    )
    out = sess.run(
        None,
        {
            "input": text.numpy(),
            "input_lengths": lengths.numpy(),
            "scales": scales.numpy(),
            "speaker_embedding": emb.numpy(),
        },
    )
    return out[0]


@pytest.mark.parametrize("n_phonemes", [12, 40])
def test_onnx_matches_torch_for_short_and_long_inputs(exported, n_phonemes):
    """dynamic 長で torch と ORT の波形が一致する (位相 float64 累積の効果)。"""
    model, path = exported
    text, lengths, scales, emb = _inputs(n_phonemes)
    with torch.no_grad():
        torch_out, _ = model(text, lengths, scales, emb)
    ort_out = _run_ort(path, n_phonemes)

    assert ort_out.shape == tuple(torch_out.shape)
    np.testing.assert_allclose(
        ort_out, torch_out.numpy(), atol=2e-4, rtol=0
    )


def test_prior_residual_variant_also_exports_and_matches(tmp_path):
    """S-2r (--f0-prior-residual) 込みでも単一 graph で export できる。"""
    model = _build(f0_prior_residual=True)
    path = _export(model, tmp_path / "s2r.onnx")
    onnx.checker.check_model(onnx.load(str(path)), full_check=False)

    text, lengths, scales, emb = _inputs(12)
    with torch.no_grad():
        torch_out, _ = model(text, lengths, scales, emb)
    np.testing.assert_allclose(
        _run_ort(path, 12), torch_out.numpy(), atol=2e-4, rtol=0
    )


def test_production_export_path_uses_build_infer_forward():
    """``export_onnx.main()`` が ``build_infer_forward`` (models.infer の wrapper) を使う。

    かつて main() は ``model.infer`` を呼ばず手書きの infer_forward 複製で
    graph を組んでおり、本テストの旧版はその複製が S-2 (F0 経路) を落とさない
    ことを source 検査で守っていた。しかし v11 P2 (enc_p の g_spk/AdaLN) は
    検査対象外で複製から漏れ、ONNX だけ話者条件が断線して担体の調波が崩壊
    した (2026-08 実測)。個別 marker の検査では「守り漏れ」が構造的に残る
    ため、複製自体を廃止して models.infer へ一本化した。ここではその一本化
    (= 複製の再導入禁止) を pin する。数値 parity は
    ``test_build_infer_forward`` の parity テスト群が担保する。
    """
    import inspect

    from piper_train import export_onnx as ex

    source = inspect.getsource(ex.main)
    assert "build_infer_forward(model_g" in source, (
        "main() が build_infer_forward を使っていない — export graph が "
        "models.infer と乖離する経路は禁止"
    )
    # 複製の再導入を構造的に検出: main() 内での infer 内部ヘルパー直呼びは
    # 「手書き複製が戻ってきた」シグナル
    for forbidden in (
        "model_g._predict_f0(",
        "model_g._apply_f0_prior_residual(",
        "model_g.enc_p(",
        "model_g.flow(",
        "model_g.dec(",
    ):
        assert forbidden not in source, (
            f"main() に infer の手書き複製が再導入されている: {forbidden} — "
            "export 経路は build_infer_forward (models.infer) 一本に固定する"
        )


def _relative_magnitude_spectrum_error(a: np.ndarray, b: np.ndarray) -> float:
    """位相に盲な比較: 振幅スペクトルの最大差 / ピーク振幅。"""
    A = np.abs(np.fft.rfft(a.reshape(-1)))
    B = np.abs(np.fft.rfft(b.reshape(-1)))
    return float(np.abs(A - B).max() / A.max())


def test_fp16_conversion_preserves_the_magnitude_spectrum(exported):
    """FP16 変換後もスペクトルが保たれる (波形の sample 一致は成立しない)。

    **なぜ波形一致で判定しないか (第一原理 + 実測)**: 本モデルの位相参照は
    ``Φ_t = Σ f0_i / fr`` の累積で決まる。FP16 変換は enc_p / predictor の
    initializer を fp16 に丸めるため、予測 log F0 が ~1e-3 変わる。この差は
    cumsum で時間に比例して積み上がり、m 次調波では m 倍される — つまり
    「位相のゆっくりした回転」として出る。実測 (random-init、3072 sample)::

        M=1: 波形 rel 0.051 / 振幅スペクトル rel 0.005
        M=4: 波形 rel 0.135 / 振幅スペクトル rel 0.008
        M=8: 波形 rel 0.209 / 振幅スペクトル rel 0.032

    波形誤差が M に比例し、振幅スペクトル誤差がその 1/10 以下に留まることが、
    「差分の実体は位相であって内容ではない」ことの直接の証拠。位相の絶対値は
    設計上そもそも意味を持たない — 学習時に区間ごとの初期位相を一様乱数で
    振っている (§4.4) のは、モデルを絶対位相に不変にするためである。

    従って判定対象は振幅スペクトルとする。ここを波形 allclose に戻すと、
    「意味のない量で fail するので閾値を緩める」という PQMF 事故と同じ経路に
    入る (docs/design/zero-shot-noise-root-cause-pqmf.md §4)。

    なお fp32 の torch ↔ ORT parity は
    ``test_onnx_matches_torch_for_short_and_long_inputs`` が atol=2e-4 の
    波形一致で厳密に守っている — 緩めているのは precision 変換の比較だけ。
    """
    from piper_train.tools.convert_fp16 import convert_fp16

    _model, path = exported
    with tempfile.TemporaryDirectory() as tmp:
        fp16_path = Path(tmp) / "s2.fp16.onnx"
        convert_fp16(path, fp16_path)
        assert fp16_path.stat().st_size < path.stat().st_size

        fp32_out = _run_ort(path, 12)
        fp16_out = _run_ort(fp16_path, 12)
        assert fp16_out.shape == fp32_out.shape
        assert np.isfinite(fp16_out).all()
        # threshold-relaxed: 判定量を波形 sample 一致から振幅スペクトルへ変更。
        # 根拠は上記 docstring の実測 (誤差が M に比例 = 位相由来、振幅
        # スペクトル誤差は 1/10 以下) と、学習時の一様乱数初期位相により
        # モデルが絶対位相に不変であるという設計上の第一原理。実測 0.032 に
        # 対し 0.10 を上限とする。
        assert _relative_magnitude_spectrum_error(fp32_out, fp16_out) < 0.10


def test_fp16_phase_drift_scales_with_the_harmonic_order(tmp_path):
    """上のテストが依拠する機序 (差分は位相) を独立に固定する。

    m 次調波の位相誤差は基本波の m 倍になるので、M を増やすと波形差は増える
    が、振幅スペクトル差はその 1 桁下に留まる。この関係が崩れたら「位相の
    ずれ」以外の何かが起きている (= 上のテストの前提が壊れている)。
    """
    from piper_train.tools.convert_fp16 import convert_fp16

    results = {}
    for m_harmonics in (1, 8):
        model = _build(f0_harmonics=m_harmonics)
        path = _export(model, tmp_path / f"m{m_harmonics}.onnx")
        fp16_path = tmp_path / f"m{m_harmonics}.fp16.onnx"
        convert_fp16(path, fp16_path)
        fp32_out, fp16_out = _run_ort(path, 12), _run_ort(fp16_path, 12)
        results[m_harmonics] = (
            float(np.abs(fp32_out - fp16_out).max() / np.abs(fp32_out).max()),
            _relative_magnitude_spectrum_error(fp32_out, fp16_out),
        )

    wav_1, mag_1 = results[1]
    wav_8, mag_8 = results[8]
    assert wav_8 > wav_1, "waveform deviation should grow with the harmonic order"
    assert mag_1 < wav_1 / 3, "magnitude error must stay well below waveform error"
    assert mag_8 < wav_8 / 3
