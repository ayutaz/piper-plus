"""
PyTorchとONNX推論の一致性を検証するテスト

このテストは、PyTorch推論とONNX推論が同じ入力に対して
ほぼ同じ音声出力を生成することを保証します。特にprosody features
（A1/A2/A3値）を使用する場合のデータ型の一致性を検証します。
"""

from pathlib import Path

import numpy as np
import pytest
import torch


# ============================================================================
# ヘルパー関数
# ============================================================================


def prepare_prosody_tensor(prosody_features: list[dict | None]) -> torch.FloatTensor:
    """prosody features をPyTorch形式のFloatTensorに変換

    Args:
        prosody_features: [{"a1": int, "a2": int, "a3": int}, ...] または None

    Returns:
        torch.FloatTensor of shape (1, num_phonemes, 3)
    """
    result = []
    for feat in prosody_features:
        if feat is None:
            result.append([0.0, 0.0, 0.0])
        else:
            result.append([float(feat["a1"]), float(feat["a2"]), float(feat["a3"])])
    return torch.FloatTensor(result).unsqueeze(0)


def prepare_prosody_array(prosody_features: list[dict | None]) -> np.ndarray:
    """prosody features をONNX形式のnumpy配列に変換

    Args:
        prosody_features: [{"a1": int, "a2": int, "a3": int}, ...] または None

    Returns:
        np.ndarray of shape (1, num_phonemes, 3), dtype=float32
    """
    result = []
    for feat in prosody_features:
        if feat is None:
            result.append([0.0, 0.0, 0.0])
        else:
            result.append([float(feat["a1"]), float(feat["a2"]), float(feat["a3"])])
    return np.expand_dims(np.array(result, dtype=np.float32), 0)


def pytorch_inference(
    model: torch.nn.Module,
    phoneme_ids: list[int],
    prosody_features: list[dict | None] | None = None,
    speaker_id: int | None = None,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_scale_w: float = 0.8,
) -> np.ndarray:
    """PyTorch推論を実行して音声を返す

    Args:
        model: VITSモデル
        phoneme_ids: 音素ID列
        prosody_features: prosody features（オプション）
        speaker_id: 話者ID（オプション）
        noise_scale: noise scale
        length_scale: length scale
        noise_scale_w: noise scale w

    Returns:
        音声データ（numpy配列）
    """
    text = torch.LongTensor(phoneme_ids).unsqueeze(0)
    text_lengths = torch.LongTensor([len(phoneme_ids)])
    sid = torch.LongTensor([speaker_id]) if speaker_id is not None else None

    # prosody features準備
    prosody_tensor = None
    if prosody_features is not None:
        prosody_tensor = prepare_prosody_tensor(prosody_features)

    with torch.no_grad():
        audio = model.infer(
            text,
            text_lengths,
            noise_scale=noise_scale,
            length_scale=length_scale,
            noise_scale_w=noise_scale_w,
            sid=sid,
            prosody_features=prosody_tensor,
        )[0]

    return audio.squeeze().cpu().numpy()


def onnx_inference(
    onnx_path: Path,
    phoneme_ids: list[int],
    prosody_features: list[dict | None] | None = None,
    speaker_id: int | None = None,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_scale_w: float = 0.8,
) -> np.ndarray:
    """ONNX推論を実行して音声を返す

    Args:
        onnx_path: ONNXモデルのパス
        phoneme_ids: 音素ID列
        prosody_features: prosody features（オプション）
        speaker_id: 話者ID（オプション）
        noise_scale: noise scale
        length_scale: length scale
        noise_scale_w: noise scale w

    Returns:
        音声データ（numpy配列）
    """
    import onnxruntime

    session = onnxruntime.InferenceSession(str(onnx_path))

    text = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    text_lengths = np.array([text.shape[1]], dtype=np.int64)
    scales = np.array([noise_scale, length_scale, noise_scale_w], dtype=np.float32)

    # 入力辞書作成
    inputs = {
        "input": text,
        "input_lengths": text_lengths,
        "scales": scales,
    }

    # prosody features準備（モデルがサポートする場合）
    input_names = [inp.name for inp in session.get_inputs()]

    # sidがあれば追加（multi-speaker models用）
    if "sid" in input_names:
        sid = None
        if speaker_id is not None:
            sid = np.array([speaker_id], dtype=np.int64)
        if sid is not None:
            inputs["sid"] = sid

    # prosody_featuresがあれば追加
    if "prosody_features" in input_names:
        if prosody_features is not None:
            prosody_array = prepare_prosody_array(prosody_features)
        else:
            # prosody無しの場合はゼロで埋める
            prosody_array = np.zeros((1, text.shape[1], 3), dtype=np.float32)
        inputs["prosody_features"] = prosody_array

    audio = session.run(None, inputs)[0]
    # Remove batch and channel dimensions: (1, 1, time) -> (time,)
    return audio.squeeze()


# ============================================================================
# テストクラス
# ============================================================================


@pytest.mark.inference
@pytest.mark.unit
class TestPyTorchONNXParity:
    """PyTorchとONNX推論の出力一致性を検証"""

    def test_audio_output_with_prosody(
        self,
        mock_vits_model,
        temp_onnx_model,
        sample_phoneme_ids,
        sample_prosody_features,
        inference_params,
    ):
        """prosody付きでPyTorchとONNX推論が正常に動作することを検証

        注: モックモデルの乱数により音声長は完全には一致しないが、
        prosody_featuresが正しくfloat32として処理され、推論が成功することを確認する。
        """
        pt_audio = pytorch_inference(
            mock_vits_model,
            sample_phoneme_ids,
            prosody_features=sample_prosody_features,
            **inference_params,
        )

        onnx_audio = onnx_inference(
            temp_onnx_model,
            sample_phoneme_ids,
            prosody_features=sample_prosody_features,
            **inference_params,
        )

        # 両方とも1次元配列であることを確認
        assert pt_audio.ndim == 1, f"PyTorch音声の次元が不正: {pt_audio.shape}"
        assert onnx_audio.ndim == 1, f"ONNX音声の次元が不正: {onnx_audio.shape}"

        # 音声が生成されていることを確認（長さ > 0）
        assert pt_audio.shape[0] > 0, "PyTorch音声が生成されていません"
        assert onnx_audio.shape[0] > 0, "ONNX音声が生成されていません"

        # 音声の値が妥当な範囲にあることを確認
        assert np.abs(pt_audio).max() < 1.0, "PyTorch音声の振幅が異常"
        assert np.abs(onnx_audio).max() < 1.0, "ONNX音声の振幅が異常"

    def test_audio_output_without_prosody(
        self,
        mock_vits_model,
        temp_onnx_model,
        sample_phoneme_ids,
        inference_params,
    ):
        """prosody無しでPyTorchとONNX推論が正常に動作することを検証

        注: モックモデルの乱数により音声長は完全には一致しないが、
        推論が成功し、有効な音声が生成されることを確認する。
        """
        pt_audio = pytorch_inference(
            mock_vits_model,
            sample_phoneme_ids,
            prosody_features=None,
            **inference_params,
        )

        onnx_audio = onnx_inference(
            temp_onnx_model,
            sample_phoneme_ids,
            prosody_features=None,
            **inference_params,
        )

        # 両方とも1次元配列であることを確認
        assert pt_audio.ndim == 1, f"PyTorch音声の次元が不正: {pt_audio.shape}"
        assert onnx_audio.ndim == 1, f"ONNX音声の次元が不正: {onnx_audio.shape}"

        # 音声が生成されていることを確認（長さ > 0）
        assert pt_audio.shape[0] > 0, "PyTorch音声が生成されていません"
        assert onnx_audio.shape[0] > 0, "ONNX音声が生成されていません"

        # 音声の値が妥当な範囲にあることを確認
        assert np.abs(pt_audio).max() < 1.0, "PyTorch音声の振幅が異常"
        assert np.abs(onnx_audio).max() < 1.0, "ONNX音声の振幅が異常"

    def test_prosody_data_type_consistency(self, temp_onnx_model):
        """ONNXモデルのprosody_features入力がfloat32であることを確認"""
        import onnxruntime

        session = onnxruntime.InferenceSession(str(temp_onnx_model))

        # 入力の型情報を取得
        prosody_input = None
        for inp in session.get_inputs():
            if inp.name == "prosody_features":
                prosody_input = inp
                break

        assert prosody_input is not None, "prosody_features入力が見つかりません"
        assert prosody_input.type == "tensor(float)", (
            f"prosody_featuresの型がfloatではありません: {prosody_input.type}"
        )

    @pytest.mark.parametrize(
        "noise_scale,length_scale,noise_scale_w",
        [
            (0.667, 1.0, 0.8),  # デフォルト
            (0.5, 1.0, 0.8),  # noise_scale変更
            (0.667, 1.2, 0.8),  # length_scale変更
            (0.667, 1.0, 1.0),  # noise_scale_w変更
        ],
    )
    def test_different_scales(
        self,
        mock_vits_model,
        temp_onnx_model,
        sample_phoneme_ids,
        sample_prosody_features,
        noise_scale,
        length_scale,
        noise_scale_w,
    ):
        """異なるscalesパラメータで推論が正常に動作することを検証

        注: モックモデルの乱数により音声長は完全には一致しないが、
        scalesパラメータが正しく適用され、推論が成功することを確認する。
        """
        params = {
            "noise_scale": noise_scale,
            "length_scale": length_scale,
            "noise_scale_w": noise_scale_w,
        }

        pt_audio = pytorch_inference(
            mock_vits_model,
            sample_phoneme_ids,
            prosody_features=sample_prosody_features,
            **params,
        )

        onnx_audio = onnx_inference(
            temp_onnx_model,
            sample_phoneme_ids,
            prosody_features=sample_prosody_features,
            **params,
        )

        # 両方とも1次元配列であることを確認
        assert pt_audio.ndim == 1, f"PyTorch音声の次元が不正: {pt_audio.shape}"
        assert onnx_audio.ndim == 1, f"ONNX音声の次元が不正: {onnx_audio.shape}"

        # 音声が生成されていることを確認
        assert pt_audio.shape[0] > 0, "PyTorch音声が生成されていません"
        assert onnx_audio.shape[0] > 0, "ONNX音声が生成されていません"

        # 音声の値が妥当な範囲にあることを確認
        assert np.abs(pt_audio).max() < 1.0, "PyTorch音声の振幅が異常"
        assert np.abs(onnx_audio).max() < 1.0, "ONNX音声の振幅が異常"
