"""Teacher-forced reconstruction (posterior z -> decoder) with own or swapped g."""

import json

import numpy as np
import pytest
import torch


pytestmark = pytest.mark.unit

HOP = 256


class _FakeGenerator(torch.nn.Module):
    """Records which g reaches enc_q and dec; g is the embedding's first value."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def _get_global_conditioning(self, sid=None, lid=None, speaker_embeddings=None):
        return speaker_embeddings[:, :1, None].clone()

    def enc_q(self, spec, lengths, g=None):
        self.calls.append(("enc_q", float(g.flatten()[0])))
        z = spec[:, :2]
        mask = torch.ones(1, 1, spec.shape[2])
        return z, z, z, mask

    def dec(self, z, g=None):
        self.calls.append(("dec", float(g.flatten()[0])))
        return torch.full((1, 1, z.shape[2] * HOP), 0.1) * float(g.flatten()[0]), None


def _wav(path, seconds=1.0, rate=48000):
    import soundfile as sf

    t = np.arange(int(rate * seconds)) / rate
    sf.write(path, (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32), rate)
    return path


@pytest.fixture
def inputs(tmp_path):
    sources = {}
    for group in ("ja_a", "ja_b"):
        directory = tmp_path / "src" / group
        directory.mkdir(parents=True)
        sources[group] = [_wav(directory / f"{group}_{i}.wav") for i in range(2)]
    embeddings = {
        "ja_a": np.full(192, 1.0, dtype=np.float32),
        "ja_b": np.full(192, 2.0, dtype=np.float32),
    }
    return sources, embeddings


def test_own_uses_own_g_and_swap_changes_only_the_decoder_g(tmp_path, inputs):
    from piper_train.tools.measure_recon_bound import reconstruct

    sources, embeddings = inputs
    generator = _FakeGenerator()
    out = tmp_path / "out"
    reconstruct(
        generator,
        sources,
        embeddings,
        {"ja_a": "ja_b", "ja_b": "ja_a"},
        out,
        sample_rate=22050,
        filter_length=1024,
        hop_length=HOP,
        win_length=1024,
        seed=0,
        device="cpu",
    )
    calls = generator.calls
    # per source: own (enc_q, dec), swap (enc_q, dec)
    assert calls[:4] == [("enc_q", 1.0), ("dec", 1.0), ("enc_q", 1.0), ("dec", 2.0)]
    assert len(calls) == 4 * 4

    import soundfile as sf

    own = sorted((out / "own" / "ja_a").glob("*.wav"))
    swap = sorted((out / "swap" / "ja_a").glob("*.wav"))
    assert [p.name for p in own] == ["ja_a_0.wav", "ja_a_1.wav"]
    assert [p.name for p in swap] == ["ja_a_0.wav", "ja_a_1.wav"]
    assert sf.info(own[0]).samplerate == 22050
    assert sf.read(swap[0])[0].max() == pytest.approx(0.2, abs=1e-4)

    record = json.loads((out / "recon.json").read_text(encoding="utf-8"))
    assert record["swap"] == {"ja_a": "ja_b", "ja_b": "ja_a"}
    assert len(record["groups"]["ja_a"]) == 2
    assert record["groups"]["ja_a"][0]["source_sha256"]


def test_swap_target_must_be_another_known_group(tmp_path, inputs):
    from piper_train.tools.measure_recon_bound import reconstruct

    sources, embeddings = inputs
    for swap in ({"ja_a": "ja_a", "ja_b": "ja_a"}, {"ja_a": "ja_x", "ja_b": "ja_a"}):
        with pytest.raises(ValueError):
            reconstruct(
                _FakeGenerator(),
                sources,
                embeddings,
                swap,
                tmp_path / "out",
                sample_rate=22050,
                filter_length=1024,
                hop_length=HOP,
                win_length=1024,
                seed=0,
                device="cpu",
            )
