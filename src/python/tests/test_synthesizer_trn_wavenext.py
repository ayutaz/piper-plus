"""Tests for SynthesizerTrn with the WaveNeXt decoder (Stage 1).

Mirrors test_synthesizer_trn_mb_istft.py for ``decoder_arch='wavenext'``:
forward/infer/voice_conversion work through the hard unpack sites in
models.py with the ``(fullband, None)`` return contract, and the real
state_dict keys classify as ``wavenext`` in the tri-state detector
(03 doc test plan: re-verify the mock-state_dict expectation against a
real model).
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _make_synthesizer(num_speakers=1, num_languages=1, gin_channels=0, **overrides):
    from piper_train.vits.models import SynthesizerTrn

    kwargs = {
        "n_vocab": 97,
        "spec_channels": 513,
        "segment_size": 32,  # frames (= 8192 samples // hop 256)
        "inter_channels": 192,
        "hidden_channels": 192,
        "filter_channels": 768,
        "n_heads": 2,
        "n_layers": 6,
        "kernel_size": 3,
        "p_dropout": 0.1,
        "resblock": "2",
        "resblock_kernel_sizes": (3, 5, 7),
        "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 256,
        "upsample_kernel_sizes": (16, 16),
        "n_speakers": num_speakers,
        "n_languages": num_languages,
        "gin_channels": gin_channels,
        "decoder_arch": "wavenext",
    }
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


@pytest.mark.unit
def test_uses_wavenext_generator():
    """decoder_arch='wavenext' builds a WaveNeXtGenerator decoder."""
    from piper_train.vits.wavenext import WaveNeXtGenerator

    model = _make_synthesizer()
    assert model.decoder_arch == "wavenext"
    assert isinstance(model.dec, WaveNeXtGenerator)
    # n_fft = (spec_channels - 1) * 2 = 1024 → head Linear(512, 1026)
    assert model.dec.head.linear_1.out_features == 1026


@pytest.mark.unit
def test_forward_returns_synthesizer_output_without_subbands():
    """forward() survives the ``o, o_mb = self.dec(...)`` hard unpack.

    WaveNeXt has no sub-band output, so decoder_subbands must be None and
    the waveform is the fullband slice (segment_size frames × hop 256).
    """
    from piper_train.vits.models import SynthesizerOutput

    torch.manual_seed(42)
    model = _make_synthesizer()
    x = torch.randint(0, 97, (2, 10))
    x_lengths = torch.LongTensor([10, 10])
    spec = torch.randn(2, 513, 40)
    spec_lengths = torch.LongTensor([40, 40])

    output = model(x, x_lengths, spec, spec_lengths)
    assert isinstance(output, SynthesizerOutput)
    assert output.decoder_subbands is None
    assert output.waveform.shape == (2, 1, 32 * 256)  # (B, 1, 8192)


@pytest.mark.unit
def test_infer_returns_fullband_and_durations():
    """infer() extracts fullband through the isinstance(dec_out, tuple) path."""
    torch.manual_seed(42)
    model = _make_synthesizer()
    model.eval()
    x = torch.randint(0, 97, (1, 10))
    x_lengths = torch.LongTensor([10])

    with torch.no_grad():
        audio, _attn, _y_mask, _latents, durations = model.infer(x, x_lengths)
    assert audio.dim() == 3
    assert audio.shape[0] == 1
    assert audio.shape[1] == 1
    assert audio.shape[2] % 256 == 0
    assert durations.shape == (1, 10)


@pytest.mark.unit
def test_infer_with_speaker_embeddings():
    """gin_channels=512 / n_speakers=2: spk_proj → cond wiring works."""
    torch.manual_seed(42)
    model = _make_synthesizer(num_speakers=2, num_languages=2, gin_channels=512)
    model.eval()
    x = torch.randint(0, 97, (1, 10))
    x_lengths = torch.LongTensor([10])
    lid = torch.LongTensor([0])
    speaker_embeddings = torch.randn(1, 192)

    with torch.no_grad():
        audio, _attn, _y_mask, _latents, _durations = model.infer(
            x, x_lengths, lid=lid, speaker_embeddings=speaker_embeddings
        )
    assert audio.shape[1] == 1


@pytest.mark.unit
def test_voice_conversion():
    """voice_conversion() survives the ``o_hat, _ = self.dec(...)`` unpack."""
    torch.manual_seed(42)
    model = _make_synthesizer(num_speakers=2, num_languages=2, gin_channels=512)
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
    assert y_mask is not None
    assert z.shape == z_p.shape == z_hat.shape


@pytest.mark.unit
def test_real_state_dict_classifies_as_wavenext():
    """Cross-check the tri-state markers against a real model state_dict.

    Stage 0 のモック state_dict テストを実モデルで再検証する (03 doc)。
    """
    from piper_train.__main__ import _detect_decoder_arch_from_state_dict

    model = _make_synthesizer()
    state_dict = {f"model_g.{k}": None for k in model.state_dict()}
    assert _detect_decoder_arch_from_state_dict(state_dict) == "wavenext"
    assert not any(k.startswith("model_g.dec.pqmf.") for k in state_dict)


@pytest.mark.unit
def test_wavenext2_still_raises_not_implemented():
    """wavenext2 stays a Stage 3 stub."""
    with pytest.raises(NotImplementedError, match="wavenext2"):
        _make_synthesizer(decoder_arch="wavenext2")
