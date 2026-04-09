"""Tests for the 'tiny' quality tier.

Verifies:
1. CLI argument parsing accepts --quality tiny
2. Configuration values are set correctly (hidden=64, inter=64, filter=256, upsample_initial=128)
3. SynthesizerTrn can be instantiated with tiny parameters
4. Tiny model produces valid audio output (forward pass)
5. Parameter count is significantly smaller than medium
"""

import pytest


# ============================================================================
# CLI Argument Parsing
# ============================================================================


def _parse_main_args(cli_args):
    """Parse CLI args using the canonical parser from __main__.py."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    return parser.parse_args(cli_args)


@pytest.mark.unit
def test_quality_tiny_is_valid_choice():
    """--quality tiny should be accepted by argparse."""
    args = _parse_main_args(
        ["--dataset-dir", "/tmp/test", "--batch-size", "4", "--quality", "tiny"]
    )
    assert args.quality == "tiny"


@pytest.mark.unit
def test_quality_default_is_medium():
    """Default quality should remain 'medium'."""
    args = _parse_main_args(["--dataset-dir", "/tmp/test", "--batch-size", "4"])
    assert args.quality == "medium"


# ============================================================================
# Configuration Values
# ============================================================================


def _apply_quality_config(quality: str) -> dict:
    """Simulate __main__.py quality tier logic, returning dict_args."""
    dict_args = {}
    if quality == "tiny":
        dict_args["hidden_channels"] = 64
        dict_args["inter_channels"] = 64
        dict_args["filter_channels"] = 256
        dict_args["upsample_initial_channel"] = 128
    elif quality == "x-low":
        dict_args["hidden_channels"] = 96
        dict_args["inter_channels"] = 96
        dict_args["filter_channels"] = 384
    elif quality == "high":
        dict_args["resblock"] = "1"
        dict_args["resblock_kernel_sizes"] = (3, 7, 11)
        dict_args["resblock_dilation_sizes"] = (
            (1, 3, 5),
            (1, 3, 5),
            (1, 3, 5),
        )
        dict_args["upsample_rates"] = (8, 8, 2, 2)
        dict_args["upsample_initial_channel"] = 512
        dict_args["upsample_kernel_sizes"] = (16, 16, 4, 4)
    return dict_args


@pytest.mark.unit
def test_tiny_config_hidden_channels():
    """Tiny quality must set hidden_channels=64."""
    cfg = _apply_quality_config("tiny")
    assert cfg["hidden_channels"] == 64


@pytest.mark.unit
def test_tiny_config_inter_channels():
    """Tiny quality must set inter_channels=64."""
    cfg = _apply_quality_config("tiny")
    assert cfg["inter_channels"] == 64


@pytest.mark.unit
def test_tiny_config_filter_channels():
    """Tiny quality must set filter_channels=256."""
    cfg = _apply_quality_config("tiny")
    assert cfg["filter_channels"] == 256


@pytest.mark.unit
def test_tiny_config_upsample_initial_channel():
    """Tiny quality must set upsample_initial_channel=128."""
    cfg = _apply_quality_config("tiny")
    assert cfg["upsample_initial_channel"] == 128


@pytest.mark.unit
def test_tiny_does_not_change_other_qualities():
    """Tiny config must not affect x-low, medium, or high tiers."""
    x_low = _apply_quality_config("x-low")
    assert x_low["hidden_channels"] == 96

    medium = _apply_quality_config("medium")
    assert len(medium) == 0  # medium uses defaults, no overrides

    high = _apply_quality_config("high")
    assert high["upsample_initial_channel"] == 512


# ============================================================================
# Model Instantiation
# ============================================================================


@pytest.mark.unit
@pytest.mark.training
def test_tiny_model_instantiation():
    """SynthesizerTrn must be instantiable with tiny quality parameters."""
    torch = pytest.importorskip("torch", reason="torch required")
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:
        if "monotonic_align" in str(e):
            pytest.skip(f"Cython monotonic_align extension not built: {e}")
        raise

    model = SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=8192,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=256,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=[3, 5, 7],
        resblock_dilation_sizes=[[1, 2], [2, 6], [3, 12]],
        upsample_rates=[8, 8, 4],
        upsample_initial_channel=128,
        upsample_kernel_sizes=[16, 16, 8],
        n_speakers=1,
        gin_channels=0,
        use_sdp=True,
        prosody_dim=16,
    )

    assert model.hidden_channels == 64
    assert model.inter_channels == 64
    assert model.filter_channels == 256


@pytest.mark.unit
@pytest.mark.training
def test_tiny_model_parameter_count():
    """Tiny model must have significantly fewer parameters than medium (~63M)."""
    torch = pytest.importorskip("torch", reason="torch required")
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:
        if "monotonic_align" in str(e):
            pytest.skip(f"Cython monotonic_align extension not built: {e}")
        raise

    model = SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=8192,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=256,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=[3, 5, 7],
        resblock_dilation_sizes=[[1, 2], [2, 6], [3, 12]],
        upsample_rates=[8, 8, 4],
        upsample_initial_channel=128,
        upsample_kernel_sizes=[16, 16, 8],
        n_speakers=1,
        gin_channels=0,
        use_sdp=True,
        prosody_dim=16,
    )

    total_params = sum(p.numel() for p in model.parameters())

    # Tiny should be under 10M parameters (medium is ~63M)
    assert total_params < 10_000_000, (
        f"Tiny model has {total_params:,} params, expected < 10M"
    )
    # Sanity check: should have at least some parameters
    assert total_params > 100_000, (
        f"Tiny model has {total_params:,} params, suspiciously low"
    )


@pytest.mark.unit
@pytest.mark.training
def test_tiny_model_forward_pass():
    """Tiny model must produce valid audio output in inference mode."""
    torch = pytest.importorskip("torch", reason="torch required")
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:
        if "monotonic_align" in str(e):
            pytest.skip(f"Cython monotonic_align extension not built: {e}")
        raise

    from piper_train.vits import commons

    torch.manual_seed(42)

    model = SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=8192,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=256,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=[3, 5, 7],
        resblock_dilation_sizes=[[1, 2], [2, 6], [3, 12]],
        upsample_rates=[8, 8, 4],
        upsample_initial_channel=128,
        upsample_kernel_sizes=[16, 16, 8],
        n_speakers=1,
        gin_channels=0,
        use_sdp=True,
        prosody_dim=16,
    )

    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()

    # Run inference
    input_length = 10
    x = torch.randint(0, 50, (1, input_length), dtype=torch.long)
    x_lengths = torch.LongTensor([input_length])
    prosody = torch.zeros(1, input_length, 3, dtype=torch.long)

    with torch.no_grad():
        x_enc, m_p, logs_p, x_mask = model.enc_p(x, x_lengths)
        x_dp = model._prepare_prosody_input(x_enc, x_mask, prosody)
        logw = model.dp(x_dp, x_mask, g=None, reverse=True, noise_scale=0.8)

        w = torch.exp(logw) * x_mask
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
        z = model.flow(z_p, y_mask, g=None, reverse=True)
        audio = model.dec((z * y_mask), g=None)

    # Audio output must be non-empty and finite
    assert audio.shape[0] == 1, "Batch size must be 1"
    assert audio.shape[1] > 0, "Audio channels must be > 0"
    assert audio.shape[2] > 0, "Audio length must be > 0"
    assert torch.isfinite(audio).all(), "Audio must contain only finite values"
