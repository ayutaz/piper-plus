"""``DifferentiableCamPPEncoder`` の Kaldi fbank を batch 一括で計算する。

旧実装は ``torchaudio.compliance.kaldi.fbank`` を行ごとに呼んでいた。torchaudio は
行ごとに定数 (epsilon) を GPU へコピーするため、SCL の 1 回で batch 行数ぶん
host と同期していた。新実装は同じ既定値 (povey 窓 / preemphasis 0.97 / DC 除去 /
512 点 FFT の power / mel 80 / dither 0) で全行を一度に計算する。

固定する性質: 旧実装 (下の ``_reference``) と fbank・勾配が一致する。CUDA では
forward・backward とも host 同期しない (mel 行列は device ごとに 1 度だけ作る)。
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="needs torch")
torchaudio = pytest.importorskip("torchaudio", reason="needs torchaudio")

from piper_train.speaker_encoder.campplus_torch import (  # noqa: E402
    CAMPPlus,
    DifferentiableCamPPEncoder,
)

pytestmark = pytest.mark.unit


def _reference(audio, sample_frequency=16000):
    """旧実装 (行ごとの torchaudio fbank + CMN) をそのまま残した参照。"""
    fbanks = []
    for i in range(audio.size(0)):
        fb = torchaudio.compliance.kaldi.fbank(
            audio[i : i + 1], num_mel_bins=80, sample_frequency=sample_frequency, dither=0.0
        )
        fbanks.append(fb - fb.mean(dim=0, keepdim=True))
    return torch.stack(fbanks)


@pytest.fixture(scope="module")
def encoder(tmp_path_factory):
    path = tmp_path_factory.mktemp("campplus") / "campplus_random.bin"
    torch.save(CAMPPlus(embedding_size=192).state_dict(), path)
    return DifferentiableCamPPEncoder(str(path), source_sr=22050)


def _audio(dtype, device="cpu", rows=3, samples=11889):
    g = torch.Generator().manual_seed(0)
    audio = torch.randn(rows, samples, generator=g) * 0.1
    audio[1, :2000] = 0.0  # 無音区間 (mel が epsilon で下限に張り付く)
    return audio.to(device=device, dtype=dtype)


@pytest.mark.parametrize("dtype", [torch.float64, torch.float32])
def test_fbank_matches_the_row_loop(encoder, dtype):
    base = _audio(dtype)
    x_new = base.clone().requires_grad_(True)
    x_ref = base.clone().requires_grad_(True)
    new = encoder._fbank(x_new)
    ref = _reference(x_ref)
    assert new.dtype == ref.dtype and new.shape == ref.shape
    # 同じ式を行ごとに計算する。mel の行列積だけ batch と行で加算順が変わりうる。
    torch.testing.assert_close(new, ref)
    weight = torch.randn(ref.shape, generator=torch.Generator().manual_seed(1)).to(dtype)
    (new * weight).sum().backward()
    (ref * weight).sum().backward()
    torch.testing.assert_close(x_new.grad, x_ref.grad)


def test_forward_matches_the_row_loop_embedding(encoder):
    audio = _audio(torch.float32, samples=16384)
    resampled = torchaudio.functional.resample(audio, 22050, 16000)
    expected = torch.nn.functional.normalize(encoder.model(_reference(resampled)), dim=-1)
    torch.testing.assert_close(encoder(audio), expected)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_cuda_fbank_does_not_synchronize(encoder):
    encoder.cuda()
    try:
        audio = _audio(torch.float32, "cuda", rows=24).requires_grad_(True)
        encoder._fbank(audio)  # mel 行列を device に置く (初回のみのコピー)
        torch.cuda.synchronize()
        torch.cuda.set_sync_debug_mode("error")
        try:
            out = encoder._fbank(audio)
            out.sum().backward()
        finally:
            torch.cuda.set_sync_debug_mode(0)
        torch.cuda.synchronize()
        torch.testing.assert_close(
            out.detach().cpu(), _reference(audio.detach().cpu()), rtol=1e-4, atol=1e-4
        )
    finally:
        encoder.cpu()
