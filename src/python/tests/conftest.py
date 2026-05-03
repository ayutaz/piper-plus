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


try:
    from piper_train.export_onnx import build_infer_forward  # noqa: E402
except ImportError:
    build_infer_forward = None  # torch not installed (e.g., CI python-tests job)


# ---------------------------------------------------------------------------
# Shared Japanese phonemization helpers
# ---------------------------------------------------------------------------
# These centralise the BOS/EOS wrapping logic that was previously duplicated
# across test_phonemize.py, test_prosody_extraction.py, test_performance.py,
# and test_integration.py.
#
# Two EOS behaviours exist:
#   auto_eos=True  -- skip "$" when the G2P output already ends with a
#                     sentence-terminal token (?, ?!, ?., ?~).
#                     Used by test_prosody_extraction.py.
#   auto_eos=False -- always append "$" unconditionally.
#                     Used by test_phonemize.py, test_performance.py,
#                     test_integration.py.

try:
    import pyopenjtalk  # noqa: F401
    from piper_plus_g2p import ProsodyInfo  # noqa: F401
    from piper_plus_g2p.encode.pua import map_token as _map_token
    from piper_plus_g2p.japanese import JapanesePhonemizer as _JaPhonemizer

    _HAS_JAPANESE_G2P = True
except ImportError:
    _HAS_JAPANESE_G2P = False

# EOS tokens that the G2P layer may already append.
_EOS_TOKENS = {"$", "?", "?!", "?.", "?~"}


def phonemize_japanese(text: str, *, auto_eos: bool = False) -> list[str]:
    """Phonemize Japanese *text* and wrap with BOS/EOS markers.

    Parameters
    ----------
    text:
        Japanese text to phonemize.
    auto_eos:
        When ``False`` (default), ``"$"`` is **always** appended after the
        G2P output -- even if the output already ends with a
        sentence-terminal token such as ``"?"``.  This is the simpler
        behaviour used by most test files.

        When ``True``, ``"$"`` is appended **only when** the last G2P token
        is not already in ``_EOS_TOKENS``.  This avoids double-termination
        for question sentences and is used by
        ``test_prosody_extraction.py``.

    Raises
    ------
    ImportError
        If ``piper_plus_g2p`` (or ``pyopenjtalk``) is not installed.
    """
    if not _HAS_JAPANESE_G2P:
        raise ImportError("piper_plus_g2p is not installed")
    p = _JaPhonemizer()
    tokens = p.phonemize(text)
    full_tokens = ["^"] + list(tokens)
    if auto_eos:
        if not tokens or tokens[-1] not in _EOS_TOKENS:
            full_tokens.append("$")
    else:
        full_tokens.append("$")
    return [_map_token(t) for t in full_tokens]


def phonemize_japanese_with_prosody(
    text: str,
) -> tuple[list[str], list]:
    """Phonemize Japanese *text* and return aligned prosody info.

    Uses ``auto_eos=True`` semantics (conditional ``"$"``).  A parallel
    ``[None]`` entry is inserted/appended for each added special token so
    that the prosody list stays aligned with the token list.

    Raises
    ------
    ImportError
        If ``piper_plus_g2p`` (or ``pyopenjtalk``) is not installed.
    """
    if not _HAS_JAPANESE_G2P:
        raise ImportError("piper_plus_g2p is not installed")
    p = _JaPhonemizer()
    tokens, prosody = p.phonemize_with_prosody(text)
    full_tokens = ["^"] + list(tokens)
    full_prosody = [None] + list(prosody)
    if not tokens or tokens[-1] not in _EOS_TOKENS:
        full_tokens.append("$")
        full_prosody.append(None)
    mapped_tokens = [_map_token(t) for t in full_tokens]
    return mapped_tokens, full_prosody


# Expose whether Japanese G2P is available for skip-checks in test files.
HAS_JAPANESE_G2P = _HAS_JAPANESE_G2P


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
    # MB-iSTFT decoder: upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x
    upsample_rates = [4, 4]
    upsample_initial_channel = 512
    upsample_kernel_sizes = [16, 16]
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

    # Build infer_forward using the shared factory (deterministic, single-speaker).
    # Thin wrapper adapts positional args: ONNX export passes 4 positional args
    # (text, text_lengths, scales, prosody_features) without sid/lid.
    _infer = build_infer_forward(mock_vits_model, stochastic=False)

    def infer_forward_single(
        input_tensor, input_lengths, scales_tensor, prosody_features_tensor
    ):
        return _infer(
            input_tensor,
            input_lengths,
            scales_tensor,
            prosody_features=prosody_features_tensor,
        )

    mock_vits_model.forward = infer_forward_single

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
                "output": {0: "batch_size", 2: "time"},
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

    # Build infer_forward using the shared factory (stochastic, single-speaker).
    _infer = build_infer_forward(mock_vits_model, stochastic=True)

    def infer_forward_stochastic(
        input_tensor, input_lengths, scales_tensor, prosody_features_tensor
    ):
        return _infer(
            input_tensor,
            input_lengths,
            scales_tensor,
            prosody_features=prosody_features_tensor,
        )

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
                "output": {0: "batch_size", 2: "time"},
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
        upsample_rates=[4, 4],
        upsample_initial_channel=512,
        upsample_kernel_sizes=[16, 16],
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

    # Build infer_forward using the shared factory (deterministic, multilingual).
    # No thin wrapper needed: the signature matches torch.onnx.export's positional
    # args (text, text_lengths, scales, sid, lid, prosody_features).
    _orig_forward = model.forward
    model.forward = build_infer_forward(model, stochastic=False)

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


@pytest.fixture(scope="session")
def mock_wavlm_discriminator():
    """WavLMDiscriminator with mocked WavLM model (avoids ~300MB download).

    The resampler is real (sinc interpolation); only the transformer weights
    are mocked.  Shared across test_vits.py and test_wavlm_discriminator.py.
    """
    from unittest.mock import MagicMock, patch

    pytest.importorskip("transformers")
    pytest.importorskip("torchaudio")

    from piper_train.vits.models import WavLMDiscriminator

    mock_wavlm = MagicMock()
    mock_wavlm.feature_extractor.parameters.return_value = []
    with patch("transformers.WavLMModel") as mock_wavlm_cls:
        mock_wavlm_cls.from_pretrained.return_value = mock_wavlm
        disc = WavLMDiscriminator(
            source_sample_rate=22050,
            target_sample_rate=16000,
        )
    return disc


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
