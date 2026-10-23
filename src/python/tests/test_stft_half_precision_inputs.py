"""STFT-based mel helpers must accept bf16 / fp16 waveforms.

Under ``--precision bf16-mixed`` the generator output reaches these helpers in
bf16, and ``torch.stft`` on CUDA raises ``cuFFT doesn't support tensor of type:
BFloat16``. The helpers upcast to fp32 before the STFT; these tests pin that the
result is fp32 and matches the fp32 path on the same samples.
"""

import pytest

torch = pytest.importorskip("torch")

from piper_train.vits.losses import mel_speaker_consistency_loss  # noqa: E402
from piper_train.vits.mel_processing import (  # noqa: E402
    mel_spectrogram_torch,
    spectrogram_torch,
)

pytestmark = pytest.mark.unit

HALF_DTYPES = [torch.bfloat16, torch.float16]


def _wave(dtype: torch.dtype) -> torch.Tensor:
    gen = torch.Generator().manual_seed(0)
    wav = torch.rand(2, 4096, generator=gen) * 1.6 - 0.8
    # Round through the half dtype once so the fp32 reference sees the same samples.
    return wav.to(dtype)


@pytest.mark.parametrize("dtype", HALF_DTYPES)
def test_spectrogram_torch_upcasts_half_input(dtype):
    wav = _wave(dtype)
    spec = spectrogram_torch(wav, 1024, 22050, 256, 1024)
    ref = spectrogram_torch(wav.float(), 1024, 22050, 256, 1024)
    assert spec.dtype == torch.float32
    torch.testing.assert_close(spec, ref)


@pytest.mark.parametrize("dtype", HALF_DTYPES)
def test_mel_spectrogram_torch_upcasts_half_input(dtype):
    wav = _wave(dtype)
    mel = mel_spectrogram_torch(wav, 1024, 80, 22050, 256, 1024, 0.0, None)
    ref = mel_spectrogram_torch(wav.float(), 1024, 80, 22050, 256, 1024, 0.0, None)
    assert mel.dtype == torch.float32
    torch.testing.assert_close(mel, ref)


@pytest.mark.parametrize("dtype", HALF_DTYPES)
def test_mel_speaker_consistency_loss_upcasts_half_input(dtype):
    y_hat = _wave(dtype)
    y = _wave(dtype).flip(-1)
    loss = mel_speaker_consistency_loss(y_hat, y)
    ref = mel_speaker_consistency_loss(y_hat.float(), y.float())
    assert loss.dtype == torch.float32
    torch.testing.assert_close(loss, ref)
