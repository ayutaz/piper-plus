"""参照条件付け (reference-fusion plan §8 Task 8R) の ONNX export 契約テスト。

固定する契約 (docs/design/zero-shot-reference-fusion-plan-2026-10-17.md §8):

* ``reference_conditioning="ref_spec"`` のモデルだけが入力
  ``reference_spec`` ``[B, 513, T_ref]`` float32 と ``reference_spec_lengths``
  ``[B]`` int64 を持つ。``"none"`` / ``"capacity"`` は旧入力のまま。
* torch (models.infer) と ORT の出力が一致する (参照長・padding によらない)。
* FP16 変換後も長い参照・1 frame の参照・無音/大振幅の参照で有限な音声を出す。
* EMA shadow (``ema_extended_state["reference_encoder"]``) が export に適用される。
* ``--config`` で書く ``<output>.json`` に参照フロントエンドの契約を記録する
  (``none`` では key を持たない)。
* streaming export は参照条件付きモデルを明示エラーで拒否する。

実際に tiny な ``VitsModel`` の checkpoint を作り、``export_onnx.main()`` を
CLI と同じ引数で通す (export 経路をモックで置き換えない)。
"""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")
onnx = pytest.importorskip("onnx", reason="onnx required")
ort = pytest.importorskip("onnxruntime", reason="onnxruntime required")

pytestmark = [pytest.mark.unit, pytest.mark.inference]

N_SYMBOLS = 40
SPEC_CHANNELS = 513  # filter_length 1024 // 2 + 1
SAMPLE_RATE = 22050
LEGACY_INPUTS = [
    "input",
    "input_lengths",
    "scales",
    "speaker_embedding",
    "lid",
    "prosody_features",
]
REFERENCE_INPUTS = ["reference_spec", "reference_spec_lengths"]

# FP32 graph の torch ↔ ORT 一致の許容誤差。両者は同じ fp32 演算を別 kernel
# (畳み込みの加算順・GEMM の blocking・erf/exp の近似) で実行するため、
# 1 op あたり相対 ~1e-7 (fp32 の ulp) の丸め差が出る。tiny decoder (振幅 O(1)
# 以下) の数百段の演算を通っても誤差は ~1e-6..1e-5 に収まる見込みで、1e-4 は
# その 10 倍以上の余裕 (plan §8 Task 8R が指定する atol)。参照の断線や padding
# の混入をこの許容誤差で検出できることは test_reference_input_changes_output /
# TestEma が別に確かめる (効果量 > 10 × atol)。
PARITY_ATOL = 1e-4


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _tiny_vits(mode: str, **overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    model = VitsModel(
        num_symbols=N_SYMBOLS,
        num_speakers=2,
        num_languages=2,
        dataset=None,
        batch_size=2,
        use_wavlm_discriminator=False,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
        upsample_initial_channel=64,
        inter_channels=32,
        hidden_channels=32,
        filter_channels=64,
        n_layers=2,
        gin_channels=64,
        sample_rate=SAMPLE_RATE,
        reference_conditioning=mode,
        **overrides,
    )
    if mode == "ref_spec":
        # 最終層は zero-init (出力 0) なので、そのままでは参照入力が断線して
        # いても parity が通ってしまう。学習済みらしく値を入れる
        with torch.no_grad():
            torch.manual_seed(1)
            model.model_g.reference_encoder.out.weight.normal_(0.0, 0.1)
            model.model_g.reference_encoder.out.bias.normal_(0.0, 0.1)
    return model


def _save_ckpt(model, path: Path, **extra) -> Path:
    torch.save(
        {
            "state_dict": model.state_dict(),
            "hyper_parameters": dict(model.hparams),
            "pytorch-lightning_version": "2.0.0",
            **extra,
        },
        path,
    )
    return path


def _write_source_config(path: Path, **overrides) -> Path:
    config = {
        "audio": {"sample_rate": SAMPLE_RATE, "quality": "medium"},
        "num_symbols": N_SYMBOLS,
        "num_speakers": 2,
        "num_languages": 2,
        "phoneme_id_map": {"_": [0], "a": [1], "": [2]},
    }
    config.update(overrides)
    path.write_text(json.dumps(config, ensure_ascii=True, indent=4), "utf-8")
    return path


def _run_export(ckpt: Path, onnx_path: Path, *flags: str) -> None:
    from piper_train import export_onnx

    saved = sys.argv
    sys.argv = ["piper_train.export_onnx", str(ckpt), str(onnx_path), *flags]
    try:
        export_onnx.main()
    finally:
        sys.argv = saved


def _cli_error(capsys, ckpt: Path, onnx_path: Path, *flags: str) -> str:
    """export が argparse の error (exit 2) で止まることを確かめ、stderr を返す。

    message まで照合させるために使う (exit 2 だけでは未知 flag など無関係な
    argparse の拒否でも通ってしまう)。
    """
    capsys.readouterr()
    with pytest.raises(SystemExit) as excinfo:
        _run_export(ckpt, onnx_path, *flags)
    assert excinfo.value.code == 2
    return capsys.readouterr().err


def _clone(model):
    """同じ hparams / 重みの別インスタンス (weight_norm 付き module は deepcopy 不可)。"""
    from piper_train.vits.lightning import VitsModel

    clone = VitsModel(**dict(model.hparams))
    clone.load_state_dict(model.state_dict())
    return clone


def _torch_infer_model(model):
    """export と同じ前処理 (eval / export mode / weight norm 除去) の torch model。"""
    from piper_train.export_onnx import build_infer_forward, set_export_mode

    model_g = _clone(model).model_g
    set_export_mode(model_g, True)
    model_g.eval()
    with torch.no_grad():
        model_g.dec.remove_weight_norm()
    return build_infer_forward(model_g, stochastic=False)


def _graph_inputs(path: Path) -> list:
    return list(onnx.load(str(path)).graph.input)


def _input_names(path: Path) -> list[str]:
    return [i.name for i in _graph_inputs(path)]


@functools.cache
def _session(path: Path):
    # graph ~5000 node の session 作成は数秒かかるので path ごとに使い回す
    # (session は推論間で状態を持たない)
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _feeds(
    batch: int = 1,
    n_phonemes: int = 12,
    ref_frames: int = 37,
    ref_lengths=None,
    spec=None,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    if spec is None:
        # 線形振幅 spec は非負。0..2 の一様乱数 (log 圧縮後 -inf にならない値域)
        spec = rng.uniform(0.0, 2.0, size=(batch, SPEC_CHANNELS, ref_frames))
    if ref_lengths is None:
        ref_lengths = [spec.shape[-1]] * batch
    return {
        "input": rng.integers(1, N_SYMBOLS, size=(1, n_phonemes))
        .repeat(batch, 0)
        .astype(np.int64),
        "input_lengths": np.full((batch,), n_phonemes, dtype=np.int64),
        # noise_scale / noise_scale_w = 0 で決定的 (length_scale 1)
        "scales": np.array([0.0, 1.0, 0.0], dtype=np.float32),
        "speaker_embedding": rng.standard_normal((1, 192))
        .repeat(batch, 0)
        .astype(np.float32),
        "lid": np.zeros((batch,), dtype=np.int64),
        "prosody_features": np.zeros((batch, n_phonemes, 3), dtype=np.int64),
        "reference_spec": np.asarray(spec, dtype=np.float32),
        "reference_spec_lengths": np.asarray(ref_lengths, dtype=np.int64),
    }


def _ort_run(path: Path, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
    session = _session(path)
    names = [i.name for i in session.get_inputs()]
    return session.run(None, {name: feeds[name] for name in names})


def _torch_run(
    fn, feeds: dict[str, np.ndarray], *, reference: bool = True, prosody: bool = True
):
    args = [
        torch.from_numpy(feeds["input"]),
        torch.from_numpy(feeds["input_lengths"]),
        torch.from_numpy(feeds["scales"]),
        torch.from_numpy(feeds["speaker_embedding"]),
        torch.from_numpy(feeds["lid"]),
        torch.from_numpy(feeds["prosody_features"]) if prosody else None,
    ]
    if reference:
        args += [
            torch.from_numpy(feeds["reference_spec"]),
            torch.from_numpy(feeds["reference_spec_lengths"]),
        ]
    with torch.no_grad():
        audio, durations = fn(*args)
    return audio.numpy(), durations.numpy()


# ---------------------------------------------------------------------------
# module-scoped exports (1 export ~10 s on CPU)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ref_spec_model():
    return _tiny_vits("ref_spec")


@pytest.fixture(scope="module")
def ref_spec_exports(tmp_path_factory, ref_spec_model):
    root = tmp_path_factory.mktemp("ref_spec_export")
    ckpt = _save_ckpt(ref_spec_model, root / "ref.ckpt")
    config = _write_source_config(root / "config.json")
    fp32 = root / "ref_fp32.onnx"
    _run_export(ckpt, fp32, "--no-stochastic", "--no-fp16", "--config", str(config))
    fp16 = root / "ref_fp16.onnx"
    _run_export(ckpt, fp16, "--no-stochastic", "--config", str(config))
    return {"fp32": fp32, "fp16": fp16, "source_config": config}


@pytest.fixture(scope="module")
def ref_no_prosody_export(tmp_path_factory):
    root = tmp_path_factory.mktemp("ref_no_prosody")
    model = _tiny_vits("ref_spec", prosody_dim=0)
    ckpt = _save_ckpt(model, root / "ref.ckpt")
    config = _write_source_config(root / "config.json")
    path = root / "ref.onnx"
    _run_export(ckpt, path, "--no-stochastic", "--no-fp16", "--config", str(config))
    return {"model": model, "onnx": path}


@pytest.fixture(scope="module")
def none_export(tmp_path_factory):
    root = tmp_path_factory.mktemp("none_export")
    model = _tiny_vits("none")
    ckpt = _save_ckpt(model, root / "none.ckpt")
    path = root / "none.onnx"
    _run_export(ckpt, path, "--no-stochastic", "--no-fp16")
    return {"model": model, "onnx": path, "ckpt": ckpt}


@pytest.fixture(scope="module")
def none_config_export(tmp_path_factory, none_export):
    """参照なしモデルを、古い reference_conditioning key が残った config で export。"""
    root = tmp_path_factory.mktemp("none_config_export")
    source = _write_source_config(
        root / "config.json", reference_conditioning=_expected_ref_spec_config()
    )
    path = root / "none.onnx"
    # 既存の <out>.onnx.json を --overwrite-config で明示的に置き換える経路
    Path(str(path) + ".json").write_text('{"stale": true}', "utf-8")
    _run_export(
        none_export["ckpt"],
        path,
        "--no-stochastic",
        "--no-fp16",
        "--config",
        str(source),
        "--overwrite-config",
    )
    return {"onnx": path, "source": source}


@pytest.fixture(scope="module")
def capacity_export(tmp_path_factory):
    root = tmp_path_factory.mktemp("capacity_export")
    model = _tiny_vits("capacity")
    ckpt = _save_ckpt(model, root / "cap.ckpt")
    config = _write_source_config(root / "config.json")
    path = root / "cap.onnx"
    # FP16 変換は入力契約・config に影響しないので省く (export 時間の節約)
    _run_export(ckpt, path, "--no-stochastic", "--no-fp16", "--config", str(config))
    return {"onnx": path}


# ---------------------------------------------------------------------------
# 入力契約
# ---------------------------------------------------------------------------


class TestInputContract:
    def test_legacy_export_input_names_unchanged(self, none_export):
        assert _input_names(none_export["onnx"]) == LEGACY_INPUTS

    def test_legacy_export_outputs_unchanged(self, none_export):
        outputs = [o.name for o in onnx.load(str(none_export["onnx"])).graph.output]
        assert outputs == ["output", "durations"]

    def test_legacy_export_has_no_reference_nodes(self, none_export):
        graph = onnx.load(str(none_export["onnx"])).graph
        assert not [n.name for n in graph.node if "reference" in n.name]

    def test_legacy_export_writes_no_config_without_flag(self, none_export):
        assert not Path(str(none_export["onnx"]) + ".json").exists()

    def test_legacy_export_matches_torch(self, none_export):
        """旧経路 (参照なし) の graph が models.infer と一致する (退行検出)。"""
        feeds = _feeds()
        ort_audio, _ = _ort_run(none_export["onnx"], feeds)
        torch_audio, _ = _torch_run(
            _torch_infer_model(none_export["model"]), feeds, reference=False
        )
        assert ort_audio.shape == torch_audio.shape
        np.testing.assert_allclose(ort_audio, torch_audio, atol=PARITY_ATOL, rtol=0)

    def test_capacity_export_input_names_unchanged(self, capacity_export):
        assert _input_names(capacity_export["onnx"]) == LEGACY_INPUTS

    def test_ref_spec_export_has_reference_inputs(self, ref_spec_exports):
        assert _input_names(ref_spec_exports["fp32"]) == LEGACY_INPUTS + (
            REFERENCE_INPUTS
        )

    @pytest.mark.parametrize("variant", ["fp32", "fp16"])
    def test_reference_input_dtypes(self, ref_spec_exports, variant):
        """FP16 変換後も入力 dtype は float32 / int64 のまま (runtime 契約)。"""
        types = {
            i.name: i.type.tensor_type.elem_type
            for i in _graph_inputs(ref_spec_exports[variant])
        }
        assert types["reference_spec"] == onnx.TensorProto.FLOAT
        assert types["reference_spec_lengths"] == onnx.TensorProto.INT64

    def test_reference_spec_shape_is_dynamic_batch_and_frames(self, ref_spec_exports):
        spec = next(
            i
            for i in _graph_inputs(ref_spec_exports["fp32"])
            if i.name == REFERENCE_INPUTS[0]
        )
        dims = spec.type.tensor_type.shape.dim
        assert len(dims) == 3
        assert dims[0].dim_param == "batch_size"
        assert dims[1].dim_value == SPEC_CHANNELS
        assert dims[2].dim_param == "reference_frames"

    def test_reference_lengths_shape_is_batch(self, ref_spec_exports):
        lengths = next(
            i
            for i in _graph_inputs(ref_spec_exports["fp32"])
            if i.name == REFERENCE_INPUTS[1]
        )
        dims = lengths.type.tensor_type.shape.dim
        assert [d.dim_param for d in dims] == ["batch_size"]

    def test_ref_spec_without_prosody_input_names(self, ref_no_prosody_export):
        """prosody なしでは位置引数に None の placeholder が入る。参照入力は
        その後ろに正しく並ぶ。"""
        legacy = [n for n in LEGACY_INPUTS if n != "prosody_features"]
        assert _input_names(ref_no_prosody_export["onnx"]) == legacy + REFERENCE_INPUTS

    def test_ref_spec_without_prosody_matches_torch(self, ref_no_prosody_export):
        """placeholder の後ろの参照入力が reference_spec* に束縛されている。"""
        feeds = _feeds(ref_frames=40)
        ort_audio, _ = _ort_run(ref_no_prosody_export["onnx"], feeds)
        torch_audio, _ = _torch_run(
            _torch_infer_model(ref_no_prosody_export["model"]), feeds, prosody=False
        )
        np.testing.assert_allclose(ort_audio, torch_audio, atol=PARITY_ATOL, rtol=0)

    def test_ref_spec_export_requires_config(self, tmp_path, capsys, ref_spec_model):
        """記録先なしで参照入力付き ONNX を出すと、runtime がフロントエンド契約を
        知る手段がない。export 前に明示エラーにする。"""
        ckpt = _save_ckpt(ref_spec_model, tmp_path / "ref.ckpt")
        err = _cli_error(capsys, ckpt, tmp_path / "ref.onnx", "--no-stochastic")
        assert "reference_conditioning='ref_spec' models require --config" in err

    def test_ref_spec_export_without_config_writes_nothing(
        self, tmp_path, capsys, ref_spec_model
    ):
        ckpt = _save_ckpt(ref_spec_model, tmp_path / "ref.ckpt")
        _cli_error(capsys, ckpt, tmp_path / "ref.onnx", "--no-stochastic")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["ref.ckpt"]


# ---------------------------------------------------------------------------
# 数値 (FP32)
# ---------------------------------------------------------------------------


class TestTorchOrtParity:
    @pytest.mark.parametrize("ref_frames", [1, 37, 400])
    def test_torch_ort_parity_with_reference_spec(
        self, ref_spec_exports, ref_spec_model, ref_frames
    ):
        feeds = _feeds(ref_frames=ref_frames)
        ort_audio, ort_dur = _ort_run(ref_spec_exports["fp32"], feeds)
        torch_audio, torch_dur = _torch_run(_torch_infer_model(ref_spec_model), feeds)
        np.testing.assert_array_equal(ort_dur, torch_dur)
        np.testing.assert_allclose(ort_audio, torch_audio, atol=PARITY_ATOL, rtol=0)

    def test_torch_ort_parity_padded_batch(self, ref_spec_exports, ref_spec_model):
        """batch 2・長さの違う参照 (padding あり) でも行ごとに torch と一致。"""
        feeds = _feeds(batch=2, ref_frames=120, ref_lengths=[120, 45])
        ort_audio, _ = _ort_run(ref_spec_exports["fp32"], feeds)
        torch_audio, _ = _torch_run(_torch_infer_model(ref_spec_model), feeds)
        np.testing.assert_allclose(ort_audio, torch_audio, atol=PARITY_ATOL, rtol=0)

    def test_padding_content_does_not_change_output(self, ref_spec_exports):
        """有効長より後ろの frame の中身は ONNX の出力に影響しない。"""
        base = _feeds(batch=1, ref_frames=90, ref_lengths=[50])
        other = {k: v.copy() for k, v in base.items()}
        other["reference_spec"][..., 50:] = 7.5
        a, _ = _ort_run(ref_spec_exports["fp32"], base)
        b, _ = _ort_run(ref_spec_exports["fp32"], other)
        np.testing.assert_array_equal(a, b)

    def test_padded_reference_matches_unpadded(self, ref_spec_exports):
        """padding 付き (長さ 50 / 全 90 frame) と 50 frame ちょうどの入力が一致。

        mask の外は時間平均・attention・畳み込みのいずれにも入らないので理論上は
        同一。畳み込みの境界は mask 済み 0 と zero padding で等価だが、attention
        の softmax は key 数が違うため加算順が変わりうる — fp32 丸め差の範囲
        (PARITY_ATOL) で比較する。
        """
        padded = _feeds(batch=1, ref_frames=90, ref_lengths=[50])
        exact = {k: v.copy() for k, v in padded.items()}
        exact["reference_spec"] = padded["reference_spec"][..., :50].copy()
        a, _ = _ort_run(ref_spec_exports["fp32"], padded)
        b, _ = _ort_run(ref_spec_exports["fp32"], exact)
        np.testing.assert_allclose(a, b, atol=PARITY_ATOL, rtol=0)

    def test_reference_input_changes_output(self, ref_spec_exports):
        """参照入力が graph に配線されている (定数に畳まれていない)。

        差が PARITY_ATOL の 10 倍を超えることまで求める: 参照の効き方が許容
        誤差に埋もれる大きさだと、上の parity テストは参照経路の断線を
        検出できない (このテスト群の検出力の前提)。
        """
        a, _ = _ort_run(ref_spec_exports["fp32"], _feeds(seed=0))
        other = _feeds(seed=0)
        other["reference_spec"] = _feeds(seed=1)["reference_spec"]
        b, _ = _ort_run(ref_spec_exports["fp32"], other)
        assert a.shape != b.shape or np.max(np.abs(a - b)) > 10 * PARITY_ATOL


# ---------------------------------------------------------------------------
# FP16
# ---------------------------------------------------------------------------


class TestFp16:
    @pytest.mark.parametrize("ref_frames", [1, 3200])
    def test_fp16_export_long_reference_finite(self, ref_spec_exports, ref_frames):
        """FP16 graph が 3200 frame (~37 s) と 1 frame の参照で有限・非空。"""
        audio, durations = _ort_run(
            ref_spec_exports["fp16"], _feeds(ref_frames=ref_frames)
        )
        assert audio.size > 0
        assert np.isfinite(audio).all()
        assert np.isfinite(durations).all()

    @pytest.mark.parametrize("ref_frames", [1, 3200])
    def test_fp16_matches_fp32_within_export_contract(
        self, ref_spec_exports, ref_frames
    ):
        """FP16 と FP32 の出力差が export 契約の許容 (check_fp16_parity の既定
        1e-2、docs/spec/onnx-export-contract.toml) に収まる。参照の長さで
        fp16 の重み丸め誤差が増幅されない (時間平均は fp32 で行う) ことの確認。"""
        from piper_train.onnx_validation import check_fp16_parity

        feeds = _feeds(ref_frames=ref_frames)
        fp32 = _ort_run(ref_spec_exports["fp32"], feeds)
        fp16 = _ort_run(ref_spec_exports["fp16"], feeds)
        assert check_fp16_parity(fp32, fp16)

    @pytest.mark.parametrize("fill", [0.0, 1e4], ids=["digital_silence", "loud"])
    def test_fp16_export_extreme_magnitude_finite(self, ref_spec_exports, fill):
        """無音 (全 bin 0 = log の下限に張り付く) と大振幅で有限。"""
        spec = np.full((1, SPEC_CHANNELS, 200), fill, dtype=np.float32)
        audio, _ = _ort_run(ref_spec_exports["fp16"], _feeds(spec=spec))
        assert np.isfinite(audio).all()

    @staticmethod
    def _constant_spec_output(path: Path, value: float) -> np.ndarray:
        spec = np.full((1, SPEC_CHANNELS, 50), value, dtype=np.float32)
        return _ort_run(path, _feeds(spec=spec))[0]

    def test_fp16_log_floor_clamps_values_below_floor(self, ref_spec_exports):
        """下限 1e-5 未満 (0 と 5e-6) はどちらも下限に張り付き、出力が一致する。"""
        np.testing.assert_array_equal(
            self._constant_spec_output(ref_spec_exports["fp16"], 0.0),
            self._constant_spec_output(ref_spec_exports["fp16"], 5e-6),
        )

    def test_fp16_log_floor_value_stays_float32(self, ref_spec_exports):
        """FP16 変換後も log の下限は float32 の 1e-5 のまま (graph 構造 (node の
        種類・数) には依らず出力で確かめる)。

        1e-5 を fp16 に丸めると subnormal の 1.00136e-5 (= 168 × 2^-24) になる。
        その間の 1.0007e-5 は、下限が float32 の 1e-5 なら clamp されず無音 (0)
        と異なる出力になり、fp16 に丸められた下限なら clamp されて無音と一致する。
        """
        between = np.float32(1.0007e-5)
        assert np.float32(1e-5) < between < np.float32(np.float16(1e-5))
        silent = self._constant_spec_output(ref_spec_exports["fp16"], 0.0)
        above = self._constant_spec_output(ref_spec_exports["fp16"], float(between))
        assert not np.array_equal(silent, above)

    def test_fp16_converts_reference_encoder_weights(self, ref_spec_exports):
        """下限以外の reference_encoder の重みは FP16 に落ちる (サイズ予算)。"""
        model = onnx.load(str(ref_spec_exports["fp16"]))
        weights = [
            i
            for i in model.graph.initializer
            if i.name.startswith("reference_encoder.") and len(i.dims) >= 1
        ]
        assert weights
        assert all(i.data_type == onnx.TensorProto.FLOAT16 for i in weights)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


class TestEma:
    @pytest.fixture(scope="class")
    def ema_export(self, tmp_path_factory):
        """reference_encoder の shadow を raw と別の値にした ckpt を export。"""
        from piper_train.vits.ema import ExponentialMovingAverage

        root = tmp_path_factory.mktemp("ema_export")
        raw = _tiny_vits("ref_spec")
        ema = ExponentialMovingAverage(raw.model_g.reference_encoder, decay=0.999)
        torch.manual_seed(2)
        # 学習中の shadow と raw の差程度 (重みの ~1 割) にずらす。大きく
        # ずらすと g が発散し export の有限性検証で止まる
        for name in ema.shadow_params:
            p = ema.shadow_params[name]
            ema.shadow_params[name] = p + 0.1 * p.abs().mean() * torch.randn_like(p)
        shadowed = _clone(raw)
        with torch.no_grad():
            for name, p in shadowed.model_g.reference_encoder.named_parameters():
                p.copy_(ema.shadow_params[name])
        ckpt = _save_ckpt(
            raw,
            root / "ema.ckpt",
            ema_scope="legacy",
            ema_extended_state={"reference_encoder": ema.state_dict()},
        )
        config = _write_source_config(root / "config.json")
        path = root / "ema.onnx"
        _run_export(ckpt, path, "--no-stochastic", "--no-fp16", "--config", str(config))
        return {"onnx": path, "raw": raw, "shadowed": shadowed}

    def test_export_uses_reference_encoder_shadow(self, ema_export):
        feeds = _feeds(ref_frames=60)
        ort_audio, _ = _ort_run(ema_export["onnx"], feeds)
        torch_audio, _ = _torch_run(_torch_infer_model(ema_export["shadowed"]), feeds)
        np.testing.assert_allclose(ort_audio, torch_audio, atol=PARITY_ATOL, rtol=0)

    def test_export_does_not_use_raw_reference_encoder(self, ema_export):
        """raw との差が parity 許容誤差の 10 倍を超える (= 上の一致は shadow を
        使ったことの証拠になる。差が許容誤差内なら区別できない)。"""
        feeds = _feeds(ref_frames=60)
        ort_audio, _ = _ort_run(ema_export["onnx"], feeds)
        raw_audio, _ = _torch_run(_torch_infer_model(ema_export["raw"]), feeds)
        assert (
            ort_audio.shape != raw_audio.shape
            or np.max(np.abs(ort_audio - raw_audio)) > 10 * PARITY_ATOL
        )


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def _expected_ref_spec_config() -> dict:
    return {
        "schema": "ref_spec_v1",
        "spec_channels": SPEC_CHANNELS,
        "filter_length": 1024,
        "hop_length": 256,
        "win_length": 1024,
        "sample_rate": SAMPLE_RATE,
        "center": False,
        "frontend": "energy-vad@16k;soxr-hq",
    }


def _exported_config(onnx_path: Path) -> dict:
    return json.loads(Path(str(onnx_path) + ".json").read_text("utf-8"))


class TestConfig:
    def test_config_records_reference_conditioning(self, ref_spec_exports):
        config = _exported_config(ref_spec_exports["fp32"])
        assert config["reference_conditioning"] == _expected_ref_spec_config()

    def test_config_keeps_source_fields(self, ref_spec_exports):
        source = json.loads(ref_spec_exports["source_config"].read_text("utf-8"))
        config = _exported_config(ref_spec_exports["fp32"])
        config.pop("reference_conditioning")
        assert config == source

    def test_capacity_config_records_schema_only(self, capacity_export):
        config = _exported_config(capacity_export["onnx"])
        assert config["reference_conditioning"] == {"schema": "capacity_v1"}

    def test_none_config_copies_source_fields(self, none_config_export):
        source = json.loads(none_config_export["source"].read_text("utf-8"))
        source.pop("reference_conditioning")
        assert _exported_config(none_config_export["onnx"]) == source

    def test_none_config_drops_stale_reference_key(self, none_config_export):
        """参照なしモデルに古い key が残った config を渡しても、出力には書かない
        (runtime が参照入力のない graph に spec を渡そうとする事故の防止)。"""
        assert "reference_conditioning" not in _exported_config(
            none_config_export["onnx"]
        )

    def test_config_sample_rate_mismatch_rejected(
        self, tmp_path, capsys, ref_spec_model
    ):
        ckpt = _save_ckpt(ref_spec_model, tmp_path / "ref.ckpt")
        source = _write_source_config(
            tmp_path / "config.json", audio={"sample_rate": 16000}
        )
        err = _cli_error(
            capsys,
            ckpt,
            tmp_path / "ref.onnx",
            "--no-stochastic",
            "--config",
            str(source),
        )
        assert (
            "config audio.sample_rate (16000) does not match the checkpoint "
            "sample_rate (22050)" in err
        )

    def test_config_sample_rate_mismatch_writes_nothing(
        self, tmp_path, capsys, ref_spec_model
    ):
        ckpt = _save_ckpt(ref_spec_model, tmp_path / "ref.ckpt")
        source = _write_source_config(
            tmp_path / "config.json", audio={"sample_rate": 16000}
        )
        _cli_error(
            capsys,
            ckpt,
            tmp_path / "ref.onnx",
            "--no-stochastic",
            "--config",
            str(source),
        )
        assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "ref.ckpt"]

    def test_missing_config_file_rejected(self, tmp_path, capsys, ref_spec_model):
        ckpt = _save_ckpt(ref_spec_model, tmp_path / "ref.ckpt")
        missing = tmp_path / "missing.json"
        err = _cli_error(
            capsys,
            ckpt,
            tmp_path / "ref.onnx",
            "--no-stochastic",
            "--config",
            str(missing),
        )
        assert "--config:" in err
        assert "missing.json" in err

    def test_missing_config_file_writes_nothing(self, tmp_path, capsys, ref_spec_model):
        ckpt = _save_ckpt(ref_spec_model, tmp_path / "ref.ckpt")
        missing = tmp_path / "missing.json"
        _cli_error(
            capsys,
            ckpt,
            tmp_path / "ref.onnx",
            "--no-stochastic",
            "--config",
            str(missing),
        )
        assert sorted(p.name for p in tmp_path.iterdir()) == ["ref.ckpt"]

    def test_existing_config_refused_without_overwrite(
        self, tmp_path, capsys, none_export
    ):
        """既存の <out>.onnx.json (手で直した config 等) を黙って上書きしない。"""
        source = _write_source_config(tmp_path / "config.json")
        out = tmp_path / "none.onnx"
        Path(str(out) + ".json").write_text('{"hand_fixed": true}', "utf-8")
        err = _cli_error(
            capsys, none_export["ckpt"], out, "--no-stochastic", "--config", str(source)
        )
        assert "already exists" in err
        assert "--overwrite-config" in err

    def test_existing_config_kept_when_refused(self, tmp_path, capsys, none_export):
        source = _write_source_config(tmp_path / "config.json")
        out = tmp_path / "none.onnx"
        existing = Path(str(out) + ".json")
        existing.write_text('{"hand_fixed": true}', "utf-8")
        _cli_error(
            capsys, none_export["ckpt"], out, "--no-stochastic", "--config", str(source)
        )
        assert existing.read_text("utf-8") == '{"hand_fixed": true}'
        assert not out.exists()

    def test_overwrite_config_replaces_existing(self, none_config_export):
        """--overwrite-config 付きなら既存の <out>.onnx.json を置き換える。"""
        assert "stale" not in _exported_config(none_config_export["onnx"])

    def test_overwrite_config_requires_config(self, tmp_path, capsys, none_export):
        err = _cli_error(
            capsys,
            none_export["ckpt"],
            tmp_path / "none.onnx",
            "--no-stochastic",
            "--overwrite-config",
        )
        assert "--overwrite-config requires --config" in err


class TestReferenceConditioningConfig:
    """``reference_conditioning_config`` の純関数部分 (export なし)。"""

    def test_none_returns_none(self):
        from piper_train.export_onnx import reference_conditioning_config

        model = _tiny_vits("none")
        assert reference_conditioning_config(model.model_g, model.hparams) is None

    def test_ref_spec_uses_model_hparams(self):
        from piper_train.export_onnx import reference_conditioning_config

        model = _tiny_vits("ref_spec")
        assert (
            reference_conditioning_config(model.model_g, model.hparams)
            == _expected_ref_spec_config()
        )

    def test_spec_channel_mismatch_raises(self):
        """encoder の入力 bin 数と filter_length が食い違う ckpt は記録しない。"""
        from piper_train.export_onnx import reference_conditioning_config

        model = _tiny_vits("ref_spec")
        hparams = dict(model.hparams)
        hparams["filter_length"] = 2048
        with pytest.raises(ValueError, match="spec_channels"):
            reference_conditioning_config(model.model_g, hparams)


# ---------------------------------------------------------------------------
# build_infer_forward の位置引数
# ---------------------------------------------------------------------------


class TestInferForwardPositional:
    def test_positional_reference_args_match_infer(self, ref_spec_model):
        """位置引数 7・8 番目が reference_spec / reference_spec_lengths に束縛される
        (torch.onnx.export の args tuple の並びと input_names の対応の pin)。"""
        model_g = _clone(ref_spec_model).model_g
        model_g.eval()
        fn = _torch_infer_model(ref_spec_model)
        feeds = _feeds(ref_frames=30)
        audio, _ = _torch_run(fn, feeds)
        from piper_train.export_onnx import set_export_mode

        set_export_mode(model_g, True)
        with torch.no_grad():
            model_g.dec.remove_weight_norm()
            expected = model_g.infer(
                torch.from_numpy(feeds["input"]),
                torch.from_numpy(feeds["input_lengths"]),
                lid=torch.from_numpy(feeds["lid"]),
                noise_scale=0.0,
                length_scale=1.0,
                noise_scale_w=0.0,
                prosody_features=torch.from_numpy(feeds["prosody_features"]),
                speaker_embeddings=torch.from_numpy(feeds["speaker_embedding"]),
                reference_spec=torch.from_numpy(feeds["reference_spec"]),
                reference_spec_lengths=torch.from_numpy(
                    feeds["reference_spec_lengths"]
                ),
            )[0]
        np.testing.assert_array_equal(audio, expected.numpy())


# ---------------------------------------------------------------------------
# ABI 契約 (docs/spec/onnx-export-contract.toml / scripts/check_onnx_inputs.py)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _export_contract() -> dict:
    import tomllib

    path = _REPO_ROOT / "docs" / "spec" / "onnx-export-contract.toml"
    return tomllib.loads(path.read_text("utf-8"))


def _check_onnx_inputs_module():
    import importlib.util

    path = _REPO_ROOT / "scripts" / "check_onnx_inputs.py"
    spec = importlib.util.spec_from_file_location("_check_onnx_inputs_8r", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAbiContract:
    def test_contract_declares_every_ref_spec_input(self, ref_spec_exports):
        """export された全入力名が契約の [tensor_names.inputs] に載っている。"""
        declared = set(_export_contract()["tensor_names"]["inputs"])
        assert set(_input_names(ref_spec_exports["fp32"])) <= declared

    def test_contract_records_runtime_preconditions(self):
        """graph は参照入力を検査しない (trace 中は検査を省く) ので、runtime が
        session の前に検査すべき前提を契約に明記する。"""
        pre = _export_contract()["tensor_names"]["reference_spec_preconditions"]
        assert pre == {
            "validated_in_graph": False,
            "lengths_min": 1,
            "lengths_max": "reference_spec.shape[2]",
            "spec_finite": True,
            "spec_non_negative": True,
            "spec_channels": "config.json reference_conditioning.spec_channels",
        }

    def test_check_onnx_inputs_accepts_ref_spec_export(self, ref_spec_exports):
        """配布前の入力 gate (scripts/check_onnx_inputs.py) が参照入力を知っている。"""
        ok, message = _check_onnx_inputs_module().check(
            ref_spec_exports["fp32"], allow_voice_cloning=False, strict_expected=None
        )
        assert ok, message


# ---------------------------------------------------------------------------
# streaming export
# ---------------------------------------------------------------------------


class TestStreamingExport:
    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_streaming_export_rejects_reference_conditioning(self, mode):
        from piper_train.export_onnx_streaming import check_streaming_export_supported

        model = _tiny_vits(mode)
        with pytest.raises(NotImplementedError, match="reference_conditioning"):
            check_streaming_export_supported(model.model_g)

    def test_streaming_rejection_points_to_export_onnx(self):
        from piper_train.export_onnx_streaming import check_streaming_export_supported

        model = _tiny_vits("ref_spec")
        with pytest.raises(
            NotImplementedError, match=r"Use piper_train\.export_onnx instead"
        ):
            check_streaming_export_supported(model.model_g)

    def test_streaming_export_accepts_none(self):
        from piper_train.export_onnx_streaming import check_streaming_export_supported

        check_streaming_export_supported(_tiny_vits("none").model_g)
