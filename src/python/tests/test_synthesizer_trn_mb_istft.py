"""Tests for SynthesizerTrn with the MB-iSTFT decoder.

Verifies that SynthesizerTrn uses MBiSTFTGenerator (the only decoder),
and that forward/infer/voice_conversion produce the expected output
types and shapes, including decoder_subbands in SynthesizerOutput.
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _make_synthesizer(num_speakers=1, num_languages=2, gin_channels=512):
    from piper_train.vits.models import SynthesizerTrn

    return SynthesizerTrn(
        n_vocab=97,
        spec_channels=513,
        segment_size=32,  # segment_size // hop_length = 8192 // 256
        inter_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        n_speakers=num_speakers,
        n_languages=num_languages,
        gin_channels=gin_channels,
    )


@pytest.mark.unit
def test_uses_mb_istft_generator():
    """SynthesizerTrn uses MBiSTFTGenerator as the decoder."""
    model = _make_synthesizer()
    from piper_train.vits.mb_istft import MBiSTFTGenerator

    assert isinstance(model.dec, MBiSTFTGenerator)


@pytest.mark.unit
def test_forward_returns_synthesizer_output_with_subbands():
    """forward() returns SynthesizerOutput with non-None subbands."""
    from piper_train.vits.models import SynthesizerOutput

    model = _make_synthesizer(num_speakers=2)
    x = torch.randint(0, 97, (1, 10))
    x_lengths = torch.LongTensor([10])
    spec = torch.randn(1, 513, 32)
    spec_lengths = torch.LongTensor([32])
    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])

    output = model(x, x_lengths, spec, spec_lengths, sid=sid, lid=lid)
    assert isinstance(output, SynthesizerOutput)
    assert output.decoder_subbands is not None
    assert output.waveform.shape[1] == 1  # [B, 1, T]


@pytest.mark.unit
def test_infer_returns_fullband_only():
    """infer() returns fullband waveform [B, 1, T]."""
    model = _make_synthesizer(num_speakers=2)
    model.eval()
    x = torch.randint(0, 97, (1, 10))
    x_lengths = torch.LongTensor([10])
    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])

    with torch.no_grad():
        o, attn, y_mask, latents, _durations = model.infer(
            x, x_lengths, sid=sid, lid=lid
        )
    assert o.shape[1] == 1


@pytest.mark.unit
def test_mb_istft_gradient_flow():
    """Gradients flow through the MB-iSTFT decoder to subband_conv_post."""
    model = _make_synthesizer(num_speakers=2)
    x = torch.randint(0, 97, (1, 10))
    x_lengths = torch.LongTensor([10])
    spec = torch.randn(1, 513, 32)
    spec_lengths = torch.LongTensor([32])
    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])

    output = model(x, x_lengths, spec, spec_lengths, sid=sid, lid=lid)
    loss = output.waveform.sum()
    loss.backward()
    assert model.dec.subband_conv_post.weight.grad is not None


@pytest.mark.unit
def test_voice_conversion():
    """voice_conversion() returns fullband output."""
    model = _make_synthesizer(num_speakers=2)
    model.eval()
    spec = torch.randn(1, 513, 32)
    spec_lengths = torch.LongTensor([32])
    sid_src = torch.LongTensor([0])
    sid_tgt = torch.LongTensor([1])
    lid = torch.LongTensor([0])
    with torch.no_grad():
        o_hat, y_mask, (z, z_p, z_hat) = model.voice_conversion(
            spec, spec_lengths, sid_src, sid_tgt, lid=lid
        )
    assert o_hat.shape[1] == 1


@pytest.mark.unit
def test_synthesizer_output_all_fields():
    """All SynthesizerOutput fields have correct types."""
    from piper_train.vits.models import SynthesizerOutput

    model = _make_synthesizer(num_speakers=2)
    x = torch.randint(0, 97, (1, 10))
    x_lengths = torch.LongTensor([10])
    spec = torch.randn(1, 513, 32)
    spec_lengths = torch.LongTensor([32])
    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])

    output = model(x, x_lengths, spec, spec_lengths, sid=sid, lid=lid)

    assert isinstance(output, SynthesizerOutput)
    assert isinstance(output.waveform, torch.Tensor)
    assert isinstance(output.duration_loss, torch.Tensor)
    assert isinstance(output.attention, torch.Tensor)
    assert isinstance(output.ids_slice, torch.Tensor)
    assert isinstance(output.x_mask, torch.Tensor)
    assert isinstance(output.y_mask, torch.Tensor)
    assert isinstance(output.latents, tuple)
    assert len(output.latents) == 6
    assert isinstance(output.decoder_subbands, torch.Tensor)
