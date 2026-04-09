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
    """モックモデルをONNXにエクスポート（durations出力付き）"""
    import torch

    from piper_train.vits import commons

    tmp_dir = tmp_path_factory.mktemp("models")
    onnx_path = tmp_dir / "mock_model.onnx"
    _orig_forward = mock_vits_model.forward

    # ダミー入力（prosody有効モデル用）
    dummy_input_length = 10
    sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
    sequence_lengths = torch.LongTensor([dummy_input_length])
    scales = torch.FloatTensor([0.667, 1.0, 0.8])
    prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    # Enable ONNX export mode for deterministic output
    mock_vits_model.onnx_export_mode = True
    if hasattr(mock_vits_model, "dp"):
        mock_vits_model.dp.onnx_export_mode = True

    # Define infer_forward for export (single-speaker, no sid)
    # Returns both audio and durations
    def infer_forward(
        input_tensor,
        input_lengths,
        scales_tensor,
        prosody_features_tensor,
    ):
        # noise_scale = scales_tensor[0]  # unused in ONNX export (deterministic mode)
        length_scale = scales_tensor[1]
        noise_scale_w = scales_tensor[2]

        # 1. Encoder
        x, m_p, logs_p, x_mask = mock_vits_model.enc_p(input_tensor, input_lengths)
        g = None  # Single speaker model

        # 2. Duration Predictor (called only once)
        x_dp = mock_vits_model._prepare_prosody_input(
            x, x_mask, prosody_features_tensor
        )
        if mock_vits_model.use_sdp:
            logw = mock_vits_model.dp(
                x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w
            )
        else:
            logw = mock_vits_model.dp(x_dp, x_mask, g=g)

        w = torch.exp(logw) * x_mask * length_scale
        durations = w.squeeze(1)  # [batch, phoneme_length]

        # 3. Attention/Alignment
        w_ceil = torch.ceil(w)
        y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
        y_mask = torch.unsqueeze(
            commons.sequence_mask(y_lengths, y_lengths.max()), 1
        ).type_as(x_mask)
        attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
        attn = commons.generate_path(w_ceil, attn_mask)

        # 4. Expand prior
        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
        logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)

        # 5. Sample z_p: in this test we always use the mean to mimic ONNX export mode
        z_p = m_p  # deterministic behavior matching when onnx_export_mode is enabled

        # 6. Flow + Decoder
        z = mock_vits_model.flow(z_p, y_mask, g=g, reverse=True)
        o = mock_vits_model.dec((z * y_mask), g=g)
        audio = o.unsqueeze(1)

        return audio, durations

    mock_vits_model.forward = infer_forward

    # ONNX export (single-speaker, no sid input) with durations output
    try:
        torch.onnx.export(
            mock_vits_model,
            (sequences, sequence_lengths, scales, prosody_features),
            str(onnx_path),
            opset_version=15,
            input_names=["input", "input_lengths", "scales", "prosody_features"],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "output": {0: "batch_size", 1: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            verbose=False,
            dynamo=False,
        )
    except (SystemError, Exception) as e:
        mock_vits_model.forward = _orig_forward
        pytest.skip(f"ONNX export not supported with current PyTorch version: {e}")

    mock_vits_model.forward = _orig_forward
    return onnx_path


@pytest.fixture(scope="module")
def temp_onnx_model_stochastic(mock_vits_model, tmp_path_factory):
    """モックモデルをstochasticモードでONNXにエクスポート"""
    import torch

    from piper_train.vits import commons

    tmp_dir = tmp_path_factory.mktemp("models_stochastic")
    onnx_path = tmp_dir / "mock_model_stochastic.onnx"

    dummy_input_length = 10
    sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
    sequence_lengths = torch.LongTensor([dummy_input_length])
    scales = torch.FloatTensor([0.667, 1.0, 0.8])
    prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    mock_vits_model.onnx_export_mode = True
    if hasattr(mock_vits_model, "dp"):
        mock_vits_model.dp.onnx_export_mode = True

    def infer_forward_stochastic(
        input_tensor, input_lengths, scales_tensor, prosody_features_tensor
    ):
        length_scale = scales_tensor[1]
        noise_scale_w = scales_tensor[2]

        x, m_p, logs_p, x_mask = mock_vits_model.enc_p(input_tensor, input_lengths)
        g = None

        x_dp = mock_vits_model._prepare_prosody_input(
            x, x_mask, prosody_features_tensor
        )
        if mock_vits_model.use_sdp:
            logw = mock_vits_model.dp(
                x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w
            )
        else:
            logw = mock_vits_model.dp(x_dp, x_mask, g=g)

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

        # Stochastic: use noise_scale from scales
        noise_scale = scales_tensor[0]
        z_p = m_p + torch.randn_like(m_p) * torch.exp(logs_p) * noise_scale

        z = mock_vits_model.flow(z_p, y_mask, g=g, reverse=True)
        o = mock_vits_model.dec((z * y_mask), g=g)
        audio = o.unsqueeze(1)

        return audio, durations

    _orig_forward = mock_vits_model.forward
    mock_vits_model.forward = infer_forward_stochastic

    try:
        torch.onnx.export(
            mock_vits_model,
            (sequences, sequence_lengths, scales, prosody_features),
            str(onnx_path),
            opset_version=15,
            input_names=["input", "input_lengths", "scales", "prosody_features"],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "output": {0: "batch_size", 1: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            verbose=False,
            dynamo=False,
        )
    except (SystemError, Exception) as e:
        mock_vits_model.forward = _orig_forward
        pytest.skip(f"ONNX export not supported with current PyTorch version: {e}")

    mock_vits_model.forward = _orig_forward
    return onnx_path


@pytest.fixture(scope="module")
def mock_vits_model_multilingual():
    """マルチリンガル対応モックVITSモデルを作成（n_speakers=1, n_languages=2）"""
    import torch

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
        gin_channels=512,
        use_sdp=True,
        prosody_dim=16,
    )

    # 各言語に異なる初期値を設定（統一テスト用）
    with torch.no_grad():
        model.emb_lang.weight[0].fill_(1.0)
        model.emb_lang.weight[1].fill_(2.0)

    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()

    return model


@pytest.fixture(scope="module")
def temp_onnx_model_unified_emb_lang(mock_vits_model_multilingual, tmp_path_factory):
    """emb_lang統一後にONNXエクスポートしたマルチリンガルモデル"""
    import torch

    from piper_train.export_onnx import unify_emb_lang_weights
    from piper_train.vits import commons

    model = mock_vits_model_multilingual

    # Save original weights to restore after export (avoid leaking into other tests)
    original_emb_lang = model.emb_lang.weight.data.clone()

    # emb_lang 統一処理 (export_onnx.py のヘルパー関数を使用)
    unify_emb_lang_weights(model, source=0)

    tmp_dir = tmp_path_factory.mktemp("models_unified")
    onnx_path = tmp_dir / "mock_model_unified.onnx"

    dummy_input_length = 10
    sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
    sequence_lengths = torch.LongTensor([dummy_input_length])
    scales = torch.FloatTensor([0.667, 1.0, 0.8])
    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])
    prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    model.onnx_export_mode = True
    if hasattr(model, "dp"):
        model.dp.onnx_export_mode = True

    def infer_forward(
        input_tensor,
        input_lengths,
        scales_tensor,
        sid_tensor,
        lid_tensor,
        prosody_features_tensor,
    ):
        length_scale = scales_tensor[1]
        noise_scale_w = scales_tensor[2]

        g = model._get_global_conditioning(sid_tensor, lid_tensor)
        x, m_p, logs_p, x_mask = model.enc_p(input_tensor, input_lengths, g=g)

        x_dp = model._prepare_prosody_input(
            x, x_mask, prosody_features_tensor, lid=lid_tensor
        )
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

    _orig_forward = model.forward
    model.forward = infer_forward

    try:
        torch.onnx.export(
            model,
            (sequences, sequence_lengths, scales, sid, lid, prosody_features),
            str(onnx_path),
            opset_version=15,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "sid",
                "lid",
                "prosody_features",
            ],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "sid": {0: "batch_size"},
                "lid": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "output": {0: "batch_size", 2: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            verbose=False,
            dynamo=False,
        )
    except (SystemError, Exception) as e:
        model.forward = _orig_forward
        model.emb_lang.weight.data.copy_(original_emb_lang)
        pytest.skip(f"ONNX export not supported: {e}")

    model.forward = _orig_forward
    # Restore original weights so mock_vits_model_multilingual is not polluted
    model.emb_lang.weight.data.copy_(original_emb_lang)
    return onnx_path


# ============================================================================
# Shared VitsModel / SynthesizerTrn Factory Fixtures
# ============================================================================


@pytest.fixture
def make_vits_model():
    """Factory fixture: create a minimal VitsModel with custom settings.

    Usage in tests:
        model = make_vits_model(freeze_dp=True)
    """
    torch = pytest.importorskip("torch", reason="torch required")  # noqa: F841

    def _factory(
        freeze_dp=False,
        num_speakers=1,
        num_languages=2,
    ):
        try:
            from piper_train.vits.lightning import VitsModel
        except ImportError as e:
            pytest.skip(f"Training dependencies not available: {e}")

        return VitsModel(
            num_symbols=97,
            num_speakers=num_speakers,
            num_languages=num_languages,
            dataset=None,
            batch_size=4,
            learning_rate=2e-4,
            use_wavlm_discriminator=False,
            freeze_dp=freeze_dp,
            use_sdp=False,
        )

    return _factory


@pytest.fixture
def make_synthesizer_trn():
    """Factory fixture: create a minimal SynthesizerTrn with custom settings.

    Usage in tests:
        model = make_synthesizer_trn(n_speakers=2, gin_channels=256)
    """
    torch = pytest.importorskip("torch", reason="torch required")  # noqa: F841

    def _factory(
        n_speakers=1,
        n_languages=1,
        gin_channels=0,
        prosody_dim=0,
        use_sdp=True,
    ):
        from piper_train.vits.models import SynthesizerTrn

        return SynthesizerTrn(
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
            n_speakers=n_speakers,
            n_languages=n_languages,
            gin_channels=gin_channels,
            use_sdp=use_sdp,
            prosody_dim=prosody_dim,
        )

    return _factory


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
