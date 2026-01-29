"""Tests for export_onnx stochastic/deterministic export modes and EMA weight application."""

import numpy as np
import pytest
import torch


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
    """EMA 重み適用のテスト"""

    def test_ema_weights_applied(self, tmp_path):
        """EMA state があればデコーダパラメータに適用される"""
        # VITSモデルの代わりにシンプルなモジュールを使用（Windows互換性のため）
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

        ema_state = {"shadow_params": shadow_params}

        # モックチェックポイントを保存
        ckpt_path = tmp_path / "test_ema.ckpt"
        torch.save({"ema_generator_state": ema_state}, str(ckpt_path))

        # EMA適用ロジックを直接テスト（export_onnx.pyと同じロジック）
        ckpt = torch.load(str(ckpt_path), map_location="cpu")
        ema = ckpt.get("ema_generator_state")
        assert ema is not None

        applied = 0
        dec_params = dict(dec.named_parameters())
        for name, shadow_param in ema["shadow_params"].items():
            if name in dec_params:
                dec_params[name].data.copy_(shadow_param)
                applied += 1

        assert applied > 0, "No EMA parameters were applied"

        # パラメータが変更されたことを確認
        for name, param in dec.named_parameters():
            if name in original_params:
                assert not torch.equal(param.data, original_params[name]), (
                    f"Parameter {name} was not updated by EMA"
                )

    def test_no_ema_state_is_handled(self, tmp_path):
        """チェックポイントに EMA state がない場合はスキップされる"""
        ckpt_path = tmp_path / "no_ema.ckpt"
        torch.save({"state_dict": {}}, str(ckpt_path))

        ckpt = torch.load(str(ckpt_path), map_location="cpu")
        ema_state = ckpt.get("ema_generator_state")
        assert ema_state is None, "Should not have EMA state"
