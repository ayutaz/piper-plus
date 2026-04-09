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
