"""Tests for MBiSTFTGenerator (Multi-Band iSTFT decoder).

This module tests:
1. Output shapes in training and ONNX export modes
2. Speaker conditioning (gin_channels)
3. Weight norm removal
4. Internal layer channel dimensions
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_generator(**overrides):
    """Helper to build MBiSTFTGenerator with sensible defaults."""
    from piper_train.vits.mb_istft import MBiSTFTGenerator

    defaults = dict(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
    )
    defaults.update(overrides)
    return MBiSTFTGenerator(**defaults)


@pytest.mark.unit
def test_generator_output_shape_training():
    """Training mode returns (fullband, subbands) with correct shapes.

    Output length exceeds simple hop*frames because iSTFT + PQMF synthesis
    adds filter-bank padding.  The exact value is deterministic for a given
    set of hyperparameters.
    """
    gen = _make_generator()
    x = torch.randn(2, 192, 32)
    fullband, subbands = gen(x)
    assert fullband.shape == (2, 1, 8192)
    assert subbands.shape == (2, 4, 2048)


@pytest.mark.unit
def test_generator_output_shape_onnx_mode():
    """ONNX export mode returns a single fullband tensor."""
    gen = _make_generator()
    gen.onnx_export_mode = True
    x = torch.randn(2, 192, 32)
    out = gen(x)
    assert isinstance(out, torch.Tensor)  # not a tuple
    assert out.shape == (2, 1, 8192)


@pytest.mark.unit
def test_generator_speaker_conditioning():
    """Speaker conditioning via gin_channels produces valid output."""
    gen = _make_generator(gin_channels=512)
    assert hasattr(gen, "cond")
    x = torch.randn(2, 192, 32)
    g = torch.randn(2, 512, 1)
    fullband, subbands = gen(x, g=g)
    assert fullband.shape == (2, 1, 8192)


@pytest.mark.unit
def test_generator_no_speaker_conditioning():
    """gin_channels=0 means no cond layer is created."""
    gen = _make_generator(gin_channels=0)
    assert not hasattr(gen, "cond")
    x = torch.randn(1, 192, 32)
    fullband, subbands = gen(x)
    assert fullband.shape[0] == 1


@pytest.mark.unit
def test_generator_remove_weight_norm():
    """remove_weight_norm completes without error and inference still works."""
    gen = _make_generator()
    gen.remove_weight_norm()
    x = torch.randn(1, 192, 32)
    fullband, _ = gen(x)
    assert fullband.shape == (1, 1, 8192)


@pytest.mark.unit
def test_subband_conv_post_channels():
    """subband_conv_post has expected in/out channels."""
    gen = _make_generator()
    expected_in = 256 // (2**2)  # = 64
    assert gen.subband_conv_post.in_channels == expected_in
    assert gen.subband_conv_post.out_channels == 4 * (16 + 2)  # = 72


@pytest.mark.unit
def test_generator_pqmf_injection():
    """MBiSTFTGenerator accepts external PQMF instance."""
    from piper_train.vits.mb_istft import PQMF, MBiSTFTGenerator

    pqmf = PQMF(subbands=4)
    gen = _make_generator(pqmf=pqmf)
    assert gen.pqmf is pqmf
    x = torch.randn(1, 192, 32)
    fullband, subbands = gen(x)
    assert fullband.shape == (1, 1, 8192)


@pytest.mark.unit
def test_generator_resblock1():
    """MBiSTFTGenerator works with ResBlock1."""
    gen = _make_generator(
        resblock="1",
        resblock_dilation_sizes=((1, 3, 5), (1, 3, 5), (1, 3, 5)),
    )
    x = torch.randn(1, 192, 32)
    fullband, _ = gen(x)
    assert fullband.shape == (1, 1, 8192)


@pytest.mark.unit
def test_generator_speaker_cond_batch1():
    """MB-iSTFT with speaker conditioning and batch_size=1."""
    gen = _make_generator(gin_channels=512)
    x = torch.randn(1, 192, 32)
    g = torch.randn(1, 512, 1)
    fullband, subbands = gen(x, g=g)
    assert fullband.shape == (1, 1, 8192)
    assert subbands.shape == (1, 4, 2048)
