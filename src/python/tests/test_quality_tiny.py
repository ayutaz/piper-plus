"""Tests for the 'tiny' quality tier.

Verifies:
1. CLI argument parsing accepts --quality tiny
2. Configuration values are set correctly by inspecting __main__.py source
3. SynthesizerTrn can be instantiated with tiny parameters
4. Tiny model produces valid audio output via model.infer() public API
5. Parameter count is significantly smaller than medium
"""

import ast
from pathlib import Path

import pytest

# Path to the production __main__.py source
_MAIN_PY = Path(__file__).resolve().parent.parent / "piper_train" / "__main__.py"


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
# Configuration Values (verified against __main__.py source via AST)
# ============================================================================


def _extract_tiny_assignments() -> dict[str, object]:
    """Extract dict_args assignments from the 'args.quality == "tiny"' branch
    in __main__.py by parsing the AST.

    Returns a dict like {"hidden_channels": 64, "inter_channels": 64, ...}.
    """
    source = _MAIN_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        # Look for: if args.quality == "tiny":
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "tiny"
        ):
            continue

        # Found the tiny branch — extract dict_args["key"] = value assignments
        assignments = {}
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Subscript)
                and isinstance(stmt.targets[0].slice, ast.Constant)
                and isinstance(stmt.value, ast.Constant)
            ):
                key = stmt.targets[0].slice.value
                assignments[key] = stmt.value.value
        return assignments

    pytest.fail("Could not find 'args.quality == \"tiny\"' branch in __main__.py")


@pytest.mark.unit
def test_tiny_config_hidden_channels():
    """Tiny quality must set hidden_channels=64 in __main__.py."""
    cfg = _extract_tiny_assignments()
    assert cfg["hidden_channels"] == 64


@pytest.mark.unit
def test_tiny_config_inter_channels():
    """Tiny quality must set inter_channels=64 in __main__.py."""
    cfg = _extract_tiny_assignments()
    assert cfg["inter_channels"] == 64


@pytest.mark.unit
def test_tiny_config_filter_channels():
    """Tiny quality must set filter_channels=256 in __main__.py."""
    cfg = _extract_tiny_assignments()
    assert cfg["filter_channels"] == 256


@pytest.mark.unit
def test_tiny_config_upsample_initial_channel():
    """Tiny quality must set upsample_initial_channel=128 in __main__.py."""
    cfg = _extract_tiny_assignments()
    assert cfg["upsample_initial_channel"] == 128


@pytest.mark.unit
def test_tiny_config_has_exactly_four_overrides():
    """Tiny quality branch must set exactly 4 config overrides."""
    cfg = _extract_tiny_assignments()
    assert len(cfg) == 4, f"Expected 4 overrides, got {len(cfg)}: {cfg}"


# ============================================================================
# Model Instantiation
# ============================================================================


def _create_tiny_model():
    """Create a SynthesizerTrn with tiny quality parameters."""
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:
        if "monotonic_align" in str(e):
            pytest.skip(f"Cython monotonic_align extension not built: {e}")
        raise

    return SynthesizerTrn(
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


@pytest.mark.unit
@pytest.mark.training
def test_tiny_model_instantiation():
    """SynthesizerTrn must be instantiable with tiny quality parameters."""
    pytest.importorskip("torch", reason="torch required")
    model = _create_tiny_model()

    assert model.hidden_channels == 64
    assert model.inter_channels == 64
    assert model.filter_channels == 256


@pytest.mark.unit
@pytest.mark.training
def test_tiny_model_parameter_count():
    """Tiny model must have significantly fewer parameters than medium (~63M)."""
    pytest.importorskip("torch", reason="torch required")
    model = _create_tiny_model()

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
    """Tiny model must produce valid audio output via model.infer() public API."""
    torch = pytest.importorskip("torch", reason="torch required")

    torch.manual_seed(42)

    model = _create_tiny_model()
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()

    # Run inference via public API
    input_length = 10
    x = torch.randint(0, 50, (1, input_length), dtype=torch.long)
    x_lengths = torch.LongTensor([input_length])
    prosody = torch.zeros(1, input_length, 3, dtype=torch.long)

    with torch.no_grad():
        audio, _attn, _y_mask, _latents = model.infer(
            x,
            x_lengths,
            noise_scale=0.0,  # deterministic
            noise_scale_w=0.0,
            prosody_features=prosody,
        )

    # Audio output must be non-empty and finite
    assert audio.shape[0] == 1, "Batch size must be 1"
    assert audio.dim() == 3, f"Expected 3D tensor, got {audio.dim()}D"
    assert audio.shape[2] > 0, "Audio length must be > 0"
    assert torch.isfinite(audio).all(), "Audio must contain only finite values"
