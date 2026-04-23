"""Tests for export_onnx stochastic/deterministic export modes, EMA weight application,
and emb_lang unification."""

import numpy as np
import pytest
import torch
from torch import nn


def _onnx_inference(onnx_path, phoneme_ids, prosody_features, noise_scale=0.667):
    """Run ONNX inference and return audio output."""
    import onnxruntime

    session = onnxruntime.InferenceSession(str(onnx_path))
    text = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    text_lengths = np.array([text.shape[1]], dtype=np.int64)
    scales = np.array([noise_scale, 1.0, 0.8], dtype=np.float32)

    inputs = {
        "input": text,
        "input_lengths": text_lengths,
        "scales": scales,
    }

    input_names = [inp.name for inp in session.get_inputs()]
    if "prosody_features" in input_names:
        pf = []
        for feat in prosody_features:
            if feat is None:
                pf.append([0, 0, 0])
            else:
                pf.append([feat["a1"], feat["a2"], feat["a3"]])
        inputs["prosody_features"] = np.expand_dims(np.array(pf, dtype=np.int64), 0)

    outputs = session.run(None, inputs)
    return outputs[0].squeeze()


@pytest.mark.inference
class TestDeterministicExport:
    """Deterministic モード（デフォルト）のテスト"""

    def test_deterministic_ignores_noise_scale(
        self, temp_onnx_model, sample_phoneme_ids, sample_prosody_features
    ):
        """Deterministic モードでは noise_scale を変えても出力が同一"""
        audio_low = _onnx_inference(
            temp_onnx_model,
            sample_phoneme_ids,
            sample_prosody_features,
            noise_scale=0.0,
        )
        audio_high = _onnx_inference(
            temp_onnx_model,
            sample_phoneme_ids,
            sample_prosody_features,
            noise_scale=0.667,
        )

        np.testing.assert_array_equal(
            audio_low,
            audio_high,
            err_msg="Deterministic export should produce identical output regardless of noise_scale",
        )


@pytest.mark.inference
class TestStochasticExport:
    """Stochastic モードのテスト"""

    def test_stochastic_with_zero_noise_scale(
        self,
        temp_onnx_model,
        temp_onnx_model_stochastic,
        sample_phoneme_ids,
        sample_prosody_features,
    ):
        """Stochastic モードで noise_scale=0 なら deterministic と同等の出力"""
        audio_det = _onnx_inference(
            temp_onnx_model,
            sample_phoneme_ids,
            sample_prosody_features,
            noise_scale=0.0,
        )
        audio_stoch = _onnx_inference(
            temp_onnx_model_stochastic,
            sample_phoneme_ids,
            sample_prosody_features,
            noise_scale=0.0,
        )

        np.testing.assert_allclose(
            audio_det,
            audio_stoch,
            atol=1e-4,
            err_msg="Stochastic with noise_scale=0 should match deterministic output",
        )

    def test_stochastic_produces_valid_audio(
        self, temp_onnx_model_stochastic, sample_phoneme_ids, sample_prosody_features
    ):
        """Stochastic モードで有効な音声が生成される"""
        audio = _onnx_inference(
            temp_onnx_model_stochastic,
            sample_phoneme_ids,
            sample_prosody_features,
            noise_scale=0.5,
        )
        assert audio.ndim == 1
        assert audio.shape[0] > 0
        assert np.isfinite(audio).all(), "Audio contains NaN or Inf"


@pytest.mark.unit
class TestEMAWeightApplication:
    """EMA 重み適用のテスト

    Tests use ``apply_ema_shadow_params`` (pure logic, no file I/O) where
    possible.  The convenience wrapper ``apply_ema_weights`` (checkpoint
    loading) is tested separately for the I/O path.
    """

    def test_ema_shadow_params_applied(self):
        """EMA shadow params があればデコーダパラメータに適用される（ファイル不要）"""
        from piper_train.export_onnx import apply_ema_shadow_params

        dec = torch.nn.Sequential(
            torch.nn.Linear(10, 10),
            torch.nn.Linear(10, 5),
        )

        # デコーダの元パラメータを記録
        original_params = {}
        for name, param in dec.named_parameters():
            original_params[name] = param.data.clone()

        # EMA shadow params を作成（元のパラメータ + 0.1）
        shadow_params = {}
        for name, param in dec.named_parameters():
            shadow_params[name] = param.data.clone() + 0.1

        applied, skipped = apply_ema_shadow_params(dec, shadow_params)

        assert applied > 0, "No EMA parameters were applied"
        assert skipped == 0, f"Unexpected skipped parameters: {skipped}"

        # パラメータが変更されたことを確認
        for name, param in dec.named_parameters():
            if name in original_params:
                assert not torch.equal(param.data, original_params[name]), (
                    f"Parameter {name} was not updated by EMA"
                )

    def test_extra_keys_are_skipped(self):
        """shadow_params にデコーダにないキーがあれば skipped としてカウントされる"""
        from piper_train.export_onnx import apply_ema_shadow_params

        dec = torch.nn.Sequential(torch.nn.Linear(10, 10))

        shadow_params = {}
        for name, param in dec.named_parameters():
            shadow_params[name] = param.data.clone() + 0.1
        # デコーダに存在しないキーを追加
        shadow_params["nonexistent.weight"] = torch.randn(5, 5)

        applied, skipped = apply_ema_shadow_params(dec, shadow_params)
        assert applied > 0
        assert skipped == 1, f"Expected 1 skipped, got {skipped}"

    def test_empty_shadow_params(self):
        """shadow_params が空辞書の場合、applied=0 で warning が出る"""
        from piper_train.export_onnx import apply_ema_shadow_params

        dec = torch.nn.Sequential(torch.nn.Linear(10, 10))

        applied, skipped = apply_ema_shadow_params(dec, {})
        assert applied == 0
        assert skipped == 0

    def test_convenience_wrapper_no_ema_state(self, tmp_path):
        """apply_ema_weights: チェックポイントに EMA state がない場合はスキップ"""
        from piper_train.export_onnx import apply_ema_weights

        dec = torch.nn.Sequential(torch.nn.Linear(10, 10))

        ckpt_path = tmp_path / "no_ema.ckpt"
        torch.save({"state_dict": {}}, str(ckpt_path))

        applied, skipped = apply_ema_weights(dec, ckpt_path)
        assert applied == 0
        assert skipped == 0

    def test_convenience_wrapper_loads_and_applies(self, tmp_path):
        """apply_ema_weights: チェックポイントから EMA を読み込んで適用"""
        from piper_train.export_onnx import apply_ema_weights

        dec = torch.nn.Sequential(torch.nn.Linear(10, 10))

        shadow_params = {}
        for name, param in dec.named_parameters():
            shadow_params[name] = param.data.clone() + 0.1

        ckpt_path = tmp_path / "test_ema.ckpt"
        torch.save(
            {"ema_generator_state": {"shadow_params": shadow_params}},
            str(ckpt_path),
        )

        applied, skipped = apply_ema_weights(dec, ckpt_path)
        assert applied > 0
        assert skipped == 0


def _make_mock_model_g(n_speakers, n_languages, gin_channels=512):
    """emb_lang テスト用の簡易モックモデルを作成"""

    class MockModelG:
        def __init__(self, n_speakers, n_languages, gin_channels):
            self.n_speakers = n_speakers
            self.n_languages = n_languages
            if n_languages > 1:
                self.emb_lang = nn.Embedding(n_languages, gin_channels)
                # 各言語に異なる初期値を設定
                with torch.no_grad():
                    for i in range(n_languages):
                        self.emb_lang.weight[i].fill_(float(i + 1))

    return MockModelG(n_speakers, n_languages, gin_channels)


@pytest.mark.unit
class TestUnifyEmbLang:
    """emb_lang 統一のテスト（export_onnx のヘルパー関数を直接テスト）"""

    def test_auto_enabled_single_speaker_multilingual(self):
        """num_speakers=1, num_languages>1 → 自動有効化"""
        from piper_train.export_onnx import should_unify_emb_lang

        assert should_unify_emb_lang(None, num_speakers=1, num_languages=6) is True

    def test_auto_disabled_multi_speaker(self):
        """num_speakers>1, num_languages>1 → 自動無効化"""
        from piper_train.export_onnx import should_unify_emb_lang

        assert should_unify_emb_lang(None, num_speakers=2, num_languages=6) is False

    def test_explicit_enable_overrides_auto(self):
        """--unify-emb-lang でマルチスピーカーでも有効化"""
        from piper_train.export_onnx import should_unify_emb_lang

        assert should_unify_emb_lang(True, num_speakers=2, num_languages=6) is True

    def test_explicit_disable_overrides_auto(self):
        """--no-unify-emb-lang でシングルスピーカー多言語でも無効化"""
        from piper_train.export_onnx import should_unify_emb_lang

        assert should_unify_emb_lang(False, num_speakers=1, num_languages=6) is False

    def test_unify_copies_source_to_all(self):
        """統一後に全言語のembeddingがsourceと同一"""
        from piper_train.export_onnx import unify_emb_lang_weights

        num_languages = 6
        model_g = _make_mock_model_g(n_speakers=1, n_languages=num_languages)

        # 統一前: 各言語は異なる値
        for i in range(num_languages):
            assert model_g.emb_lang.weight[i][0].item() == float(i + 1)

        unify_emb_lang_weights(model_g, source=0)

        # 統一後: 全言語がsource (=1.0) と同一
        for i in range(num_languages):
            assert torch.equal(model_g.emb_lang.weight[i], model_g.emb_lang.weight[0])

    def test_unify_with_custom_source(self):
        """--unify-emb-lang-source 2 で言語2基準のコピー"""
        from piper_train.export_onnx import unify_emb_lang_weights

        num_languages = 6
        model_g = _make_mock_model_g(n_speakers=1, n_languages=num_languages)

        unify_emb_lang_weights(model_g, source=2)

        # 全言語がsource (=3.0) と同一
        for i in range(num_languages):
            assert model_g.emb_lang.weight[i][0].item() == 3.0

    def test_invalid_source_raises_error(self):
        """範囲外のsourceでValueError"""
        from piper_train.export_onnx import unify_emb_lang_weights

        model_g = _make_mock_model_g(n_speakers=1, n_languages=6)

        with pytest.raises(ValueError, match="must be 0..5"):
            unify_emb_lang_weights(model_g, source=10)


@pytest.mark.inference
class TestUnifyEmbLangOnnxExport:
    """emb_lang 統一後の ONNX エクスポート統合テスト"""

    def test_onnx_export_succeeds(self, temp_onnx_model_unified_emb_lang):
        """emb_lang統一後のモデルが正常にONNXエクスポートできる"""
        import os

        assert temp_onnx_model_unified_emb_lang.exists()
        assert os.path.getsize(temp_onnx_model_unified_emb_lang) > 0

    def test_onnx_inference_with_different_lid(
        self,
        temp_onnx_model_unified_emb_lang,
        sample_phoneme_ids,
        sample_prosody_features,
    ):
        """emb_lang統一後は異なるlidでも同一の音声出力"""
        import onnxruntime

        session = onnxruntime.InferenceSession(str(temp_onnx_model_unified_emb_lang))
        input_names = {inp.name for inp in session.get_inputs()}

        text = np.expand_dims(np.array(sample_phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text.shape[1]], dtype=np.int64)
        scales = np.array(
            [0.0, 1.0, 0.8], dtype=np.float32
        )  # noise_scale=0 for determinism

        pf = []
        for feat in sample_prosody_features:
            if feat is None:
                pf.append([0, 0, 0])
            else:
                pf.append([feat["a1"], feat["a2"], feat["a3"]])
        prosody = np.expand_dims(np.array(pf, dtype=np.int64), 0)

        def _build_inputs(lid_val):
            inputs = {"input": text, "input_lengths": text_lengths, "scales": scales}
            if "sid" in input_names:
                inputs["sid"] = np.array([0], dtype=np.int64)
            if "lid" in input_names:
                inputs["lid"] = np.array([lid_val], dtype=np.int64)
            if "prosody_features" in input_names:
                inputs["prosody_features"] = prosody
            return inputs

        audio_lid0 = session.run(None, _build_inputs(0))[0].squeeze()
        audio_lid1 = session.run(None, _build_inputs(1))[0].squeeze()

        # emb_lang統一後は出力が同一であるべき
        np.testing.assert_array_equal(
            audio_lid0,
            audio_lid1,
            err_msg="After emb_lang unification, different lid values should produce identical output",
        )


# =============================================================================
# Style Vector Conditioning (Phase 2 P2-T01) -- ONNX export
# =============================================================================


def _build_style_vector_model(style_vector_dim: int, style_condition_mode: str = "global"):
    """Create a minimal SynthesizerTrn with style_vector_dim set.

    Uses n_languages=2 so the production infer() path has a valid fallback
    conditioning vector (avoids a pre-existing issue where speaker_embedding
    with mask=0 and n_languages=1 tries to fall back to a None emb_g result).
    """
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(42)
    model = SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=8192,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="1",
        resblock_kernel_sizes=[3, 7, 11],
        resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        upsample_rates=[8, 8, 2, 2],
        upsample_initial_channel=512,
        upsample_kernel_sizes=[16, 16, 4, 4],
        n_speakers=1,
        n_languages=2,
        # Need gin_channels > 0 for multilingual models (emb_lang) AND for
        # style_condition_mode="global" (style_proj target).
        gin_channels=256,
        use_sdp=True,
        prosody_dim=0,
        style_vector_dim=style_vector_dim,
        style_condition_mode=style_condition_mode,
    )
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()
    return model


def _export_with_style_vector(
    model, tmp_path, *, no_fp16: bool = True, simplify: bool = False
):
    """Export a SynthesizerTrn model to ONNX with style_vector inputs.

    Mirrors the production export path in ``export_onnx.main`` but trimmed
    to what the tests need (no checkpoint I/O, no emb_lang unification).
    """
    from piper_train.export_onnx import (
        build_infer_forward,
        write_style_vector_metadata,
    )

    style_vector_dim = getattr(model, "style_vector_dim", 0)
    style_condition_mode = getattr(model, "style_condition_mode", "global")

    onnx_path = tmp_path / f"style_dim{style_vector_dim}.onnx"
    dummy_len = 10
    sequences = torch.randint(0, 50, (1, dummy_len), dtype=torch.long)
    seq_lengths = torch.LongTensor([dummy_len])
    scales = torch.FloatTensor([0.667, 1.0, 0.8])

    include_sid = model.n_speakers > 1 or model.n_languages > 1
    include_lid = model.n_languages > 1

    dummy_input_list = [sequences, seq_lengths, scales]
    input_names = ["input", "input_lengths", "scales"]
    dynamic_axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "output": {0: "batch_size", 2: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }
    if include_sid:
        dummy_input_list.append(torch.LongTensor([0]))
        input_names.append("sid")
        dynamic_axes["sid"] = {0: "batch_size"}
    if include_lid:
        dummy_input_list.append(torch.LongTensor([0]))
        input_names.append("lid")
        dynamic_axes["lid"] = {0: "batch_size"}

    # NOTE: We intentionally skip speaker_embedding inputs in these style_vector
    # focused tests. The speaker_embedding path in SynthesizerTrn.infer() has a
    # pre-existing tracing issue with certain model configs that is out of
    # scope for P2-T01; the production export path exercises it separately.

    if style_vector_dim > 0:
        dummy_input_list.append(
            torch.zeros(1, style_vector_dim, dtype=torch.float32)
        )
        input_names.append("style_vector")
        dynamic_axes["style_vector"] = {0: "batch_size"}
        dummy_input_list.append(torch.ones(1, 1, dtype=torch.int64))
        input_names.append("style_vector_mask")
        dynamic_axes["style_vector_mask"] = {0: "batch_size"}

    # Wrap build_infer_forward so positional args map to our minimal input set
    # (no prosody/speaker_embedding). torch.onnx.export passes positional args,
    # and the full infer_forward signature includes prosody_features +
    # speaker_embedding* slots that we skip here.
    _infer = build_infer_forward(model, stochastic=False)
    _orig_forward = model.forward

    if include_sid and include_lid and style_vector_dim > 0:
        def thin_forward(
            text, text_lengths, scales, sid, lid, style_vector, style_vector_mask
        ):
            return _infer(
                text, text_lengths, scales,
                sid=sid, lid=lid,
                style_vector=style_vector,
                style_vector_mask=style_vector_mask,
            )
    elif include_sid and include_lid and style_vector_dim == 0:
        def thin_forward(text, text_lengths, scales, sid, lid):
            return _infer(text, text_lengths, scales, sid=sid, lid=lid)
    elif not include_sid and style_vector_dim > 0:
        def thin_forward(text, text_lengths, scales, style_vector, style_vector_mask):
            return _infer(
                text, text_lengths, scales,
                style_vector=style_vector,
                style_vector_mask=style_vector_mask,
            )
    else:
        def thin_forward(text, text_lengths, scales):
            return _infer(text, text_lengths, scales)

    model.forward = thin_forward
    try:
        torch.onnx.export(
            model,
            tuple(dummy_input_list),
            str(onnx_path),
            opset_version=15,
            input_names=input_names,
            output_names=["output", "durations"],
            dynamic_axes=dynamic_axes,
            verbose=False,
            dynamo=False,
        )
    finally:
        model.forward = _orig_forward

    if style_vector_dim > 0:
        write_style_vector_metadata(
            onnx_path, style_vector_dim, style_condition_mode
        )

    return onnx_path


@pytest.mark.inference
class TestExportStyleVector:
    """style_vector 入力の ONNX エクスポートテスト (Phase 2 P2-T01)."""

    def test_export_with_style_vector_dim_0(self, tmp_path):
        """dim=0 の場合、ONNX 入力に style_vector が含まれないこと (後方互換)."""
        import onnxruntime

        model = _build_style_vector_model(style_vector_dim=0)
        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        input_names = {inp.name for inp in session.get_inputs()}
        assert "style_vector" not in input_names
        assert "style_vector_mask" not in input_names

    def test_export_with_style_vector_dim_256(self, tmp_path):
        """dim=256 の場合、style_vector + style_vector_mask 入力が存在."""
        import onnxruntime

        model = _build_style_vector_model(style_vector_dim=256)
        assert model.style_vector_dim == 256
        assert getattr(model, "style_condition_mode", "global") == "global"

        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        input_names = [inp.name for inp in session.get_inputs()]
        assert "style_vector" in input_names
        assert "style_vector_mask" in input_names

        # style_vector は float32 [batch, 256]
        sv = next(inp for inp in session.get_inputs() if inp.name == "style_vector")
        assert sv.type == "tensor(float)"
        # Verify dynamic batch axis
        assert sv.shape[0] in ("batch_size", -1, None)
        assert sv.shape[1] == 256

        # style_vector_mask は int64 [batch, 1]
        mask = next(
            inp for inp in session.get_inputs() if inp.name == "style_vector_mask"
        )
        assert mask.type == "tensor(int64)"

    def test_export_style_vector_metadata_props(self, tmp_path):
        """metadata_props に style_vector_dim / style_condition_mode が書き込まれる."""
        import onnxruntime

        model = _build_style_vector_model(style_vector_dim=128)
        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        meta = dict(session.get_modelmeta().custom_metadata_map)
        assert meta.get("style_vector_dim") == "128"
        assert meta.get("style_condition_mode") == "global"

    def test_export_style_vector_dynamic_batch(self, tmp_path):
        """onnxruntime InferenceSession の shape[0] が symbolic (batch_size)."""
        import onnxruntime

        model = _build_style_vector_model(style_vector_dim=64)
        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        sv = next(inp for inp in session.get_inputs() if inp.name == "style_vector")
        # Dynamic axis may be represented as a string symbol or -1 / None
        assert sv.shape[0] in ("batch_size", -1, None)

    def test_export_with_style_condition_mode_text(self, tmp_path):
        """style_condition_mode='text' でも metadata が正しく書き込まれる."""
        import onnxruntime

        # "text" モードでは gin_channels なしでも動作する
        model = _build_style_vector_model(
            style_vector_dim=32, style_condition_mode="text"
        )
        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        meta = dict(session.get_modelmeta().custom_metadata_map)
        assert meta.get("style_vector_dim") == "32"
        assert meta.get("style_condition_mode") == "text"

    def test_export_dim_0_has_no_metadata(self, tmp_path):
        """dim=0 では metadata_props に style_vector_dim を書き込まない."""
        import onnxruntime

        model = _build_style_vector_model(style_vector_dim=0)
        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        meta = dict(session.get_modelmeta().custom_metadata_map)
        assert "style_vector_dim" not in meta
        assert "style_condition_mode" not in meta

    def test_export_style_vector_inference_with_mask_zero(self, tmp_path):
        """mask=0 のとき、style_vector の値に関わらず出力が一定."""
        import onnxruntime

        model = _build_style_vector_model(style_vector_dim=64)
        onnx_path = _export_with_style_vector(model, tmp_path)

        session = onnxruntime.InferenceSession(str(onnx_path))
        input_names = {inp.name for inp in session.get_inputs()}

        text = np.random.randint(1, 50, size=(1, 10), dtype=np.int64)
        text_lengths = np.array([10], dtype=np.int64)
        scales = np.array([0.0, 1.0, 0.8], dtype=np.float32)  # noise=0 for determinism

        base_inputs = {
            "input": text,
            "input_lengths": text_lengths,
            "scales": scales,
        }
        if "sid" in input_names:
            base_inputs["sid"] = np.array([0], dtype=np.int64)
        if "lid" in input_names:
            base_inputs["lid"] = np.array([0], dtype=np.int64)
        # With mask=0, two different style vectors must produce identical audio
        sv_a = np.random.randn(1, 64).astype(np.float32)
        sv_b = np.random.randn(1, 64).astype(np.float32)

        inputs_a = {**base_inputs, "style_vector": sv_a, "style_vector_mask": np.array([[0]], dtype=np.int64)}
        inputs_b = {**base_inputs, "style_vector": sv_b, "style_vector_mask": np.array([[0]], dtype=np.int64)}

        audio_a = session.run(None, inputs_a)[0]
        audio_b = session.run(None, inputs_b)[0]

        np.testing.assert_array_equal(
            audio_a,
            audio_b,
            err_msg="style_vector_mask=0 should zero-out style_vector contribution",
        )


@pytest.mark.unit
class TestWriteStyleVectorMetadata:
    """Metadata helper (write_style_vector_metadata) の単体テスト."""

    def test_metadata_helper_uses_string_string_entry_proto(self, tmp_path):
        """StringStringEntryProto が使われていて、正しく load できる."""
        import onnx
        import onnxruntime

        from piper_train.export_onnx import write_style_vector_metadata

        # Build a minimal ONNX model (identity)
        from onnx import TensorProto, helper

        node = helper.make_node("Identity", ["x"], ["y"])
        graph = helper.make_graph(
            [node],
            "test-model",
            [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])],
        )
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 15)])
        onnx_path = tmp_path / "tiny.onnx"
        onnx.save(model, str(onnx_path))

        write_style_vector_metadata(
            onnx_path, style_vector_dim=256, style_condition_mode="global"
        )

        session = onnxruntime.InferenceSession(str(onnx_path))
        meta = dict(session.get_modelmeta().custom_metadata_map)
        assert meta["style_vector_dim"] == "256"
        assert meta["style_condition_mode"] == "global"
