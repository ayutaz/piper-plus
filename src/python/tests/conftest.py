import sys
from pathlib import Path

import pytest


# Add <repo>/src/python to PYTHONPATH during tests so that
# `import piper_train ...` works when tests are executed from project root.
_current = Path(__file__).resolve()
# Walk up until we find a directory that contains "src/python"
python_src = None
for parent in _current.parents:
    candidate = parent / "src" / "python"
    if candidate.is_dir():
        python_src = candidate
        break

if python_src and (str(python_src) not in sys.path):
    sys.path.insert(0, str(python_src))


# ============================================================================
# PyTorch/ONNX Parity Test Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def mock_vits_model():
    """モックVITSモデルを作成（prosody対応）"""
    import torch

    from piper_train.vits.models import SynthesizerTrn

    # 乱数シードを固定（再現性のため）
    torch.manual_seed(42)

    # 最小限の設定
    n_vocab = 50  # 音素数
    spec_channels = 513
    segment_size = 8192
    inter_channels = 192
    hidden_channels = 192
    filter_channels = 768
    n_heads = 2
    n_layers = 6
    kernel_size = 3
    p_dropout = 0.1
    resblock = "1"
    resblock_kernel_sizes = [3, 7, 11]
    resblock_dilation_sizes = [[1, 3, 5], [1, 3, 5], [1, 3, 5]]
    upsample_rates = [8, 8, 2, 2]
    upsample_initial_channel = 512
    upsample_kernel_sizes = [16, 16, 4, 4]
    n_speakers = 1
    gin_channels = 0
    use_sdp = True
    prosody_dim = 16  # prosody有効

    model = SynthesizerTrn(
        n_vocab=n_vocab,
        spec_channels=spec_channels,
        segment_size=segment_size,
        inter_channels=inter_channels,
        hidden_channels=hidden_channels,
        filter_channels=filter_channels,
        n_heads=n_heads,
        n_layers=n_layers,
        kernel_size=kernel_size,
        p_dropout=p_dropout,
        resblock=resblock,
        resblock_kernel_sizes=resblock_kernel_sizes,
        resblock_dilation_sizes=resblock_dilation_sizes,
        upsample_rates=upsample_rates,
        upsample_initial_channel=upsample_initial_channel,
        upsample_kernel_sizes=upsample_kernel_sizes,
        n_speakers=n_speakers,
        gin_channels=gin_channels,
        use_sdp=use_sdp,
        prosody_dim=prosody_dim,
    )

    # モデルを評価モードに
    model.eval()

    # weight_normを削除
    with torch.no_grad():
        model.dec.remove_weight_norm()

    return model


@pytest.fixture(scope="module")
def temp_onnx_model(mock_vits_model, tmp_path_factory):
    """モックモデルをONNXにエクスポート"""
    import torch

    tmp_dir = tmp_path_factory.mktemp("models")
    onnx_path = tmp_dir / "mock_model.onnx"

    # ダミー入力（prosody有効モデル用）
    dummy_input_length = 10
    sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
    sequence_lengths = torch.LongTensor([dummy_input_length])
    scales = torch.FloatTensor([0.667, 1.0, 0.8])
    prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    # Define infer_forward for export (single-speaker, no sid)
    def infer_forward(
        input_tensor,
        input_lengths,
        scales_tensor,
        prosody_features_tensor,
    ):
        noise_scale = scales_tensor[0]
        length_scale = scales_tensor[1]
        noise_scale_w = scales_tensor[2]

        audio = mock_vits_model.infer(
            input_tensor,
            input_lengths,
            noise_scale=noise_scale,
            length_scale=length_scale,
            noise_scale_w=noise_scale_w,
            sid=None,  # Single speaker model
            prosody_features=prosody_features_tensor,
        )[0].unsqueeze(1)

        return audio

    mock_vits_model.forward = infer_forward

    # ONNX export (single-speaker, no sid input)
    torch.onnx.export(
        mock_vits_model,
        (sequences, sequence_lengths, scales, prosody_features),
        str(onnx_path),
        opset_version=15,
        input_names=["input", "input_lengths", "scales", "prosody_features"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size", 1: "phonemes"},
            "input_lengths": {0: "batch_size"},
            "prosody_features": {0: "batch_size", 1: "phonemes"},
            "output": {0: "batch_size", 1: "time"},
        },
        verbose=False,
    )

    return onnx_path


@pytest.fixture
def sample_phoneme_ids():
    """標準的なテスト用音素ID列"""
    return [1, 8, 5, 39, 25, 11, 0, 15, 22, 40]


@pytest.fixture
def sample_prosody_features():
    """標準的なテスト用prosody features"""
    return [
        {"a1": -2, "a2": 1, "a3": 5},
        {"a1": -1, "a2": 2, "a3": 5},
        {"a1": 0, "a2": 3, "a3": 5},
        {"a1": 1, "a2": 4, "a3": 5},
        {"a1": 2, "a2": 5, "a3": 5},
        None,  # 特殊トークン
        {"a1": -3, "a2": 1, "a3": 4},
        {"a1": -2, "a2": 2, "a3": 4},
        {"a1": -1, "a2": 3, "a3": 4},
        {"a1": 0, "a2": 4, "a3": 4},
    ]


@pytest.fixture
def inference_params():
    """推論パラメータのデフォルト値"""
    return {
        "noise_scale": 0.667,
        "length_scale": 1.0,
        "noise_scale_w": 0.8,
    }
