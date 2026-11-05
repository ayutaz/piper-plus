"""推論経路の z (``SynthesizerTrn.prior_path_latent``) の契約。

候補 A (docs/design/zero-shot-next-direction-2026-11-05/impl.md §2.2) は、
decoder を「text → enc_p → MAS の並び → prior → flow⁻¹」で作った z でも
学習・診断する。z の作り方を道具の中に書き写すと、SNAC の引数や clamp の
順番が学習・推論と黙って食い違う (export の手書き複製で AdaLN の g_spk が
切れた ``ca76d6ea`` と同じ型)。そこで本メソッドは ``forward`` (MAS・引き
伸ばし・clamp) と ``infer`` (乱数・flow⁻¹) と同じ部品を通すことを、出力の
一致で固定する。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.models import SynthesizerTrn  # noqa: E402


pytestmark = pytest.mark.unit


BASE = {
    "n_vocab": 40,
    "spec_channels": 513,
    "segment_size": 32,
    "inter_channels": 64,
    "hidden_channels": 64,
    "filter_channels": 128,
    "n_heads": 2,
    "n_layers": 2,
    "kernel_size": 3,
    "p_dropout": 0.0,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 64,
    "upsample_kernel_sizes": (16, 16),
    "n_speakers": 4,
    "gin_channels": 64,
    "prosody_dim": 0,
}


def _model(seed: int = 0, **overrides) -> SynthesizerTrn:
    torch.manual_seed(seed)
    kwargs = dict(BASE)
    kwargs.update(overrides)
    model = SynthesizerTrn(**kwargs).eval()
    # zero-init の層 (flow の post、FiLM 等) も値を持たせ、経路の取り違えが
    # 出力に現れるようにする。
    gen = torch.Generator().manual_seed(seed + 100)
    with torch.no_grad():
        for p in model.parameters():
            p.add_(torch.randn(p.shape, generator=gen) * 0.02)
    return model


def _batch(seed: int = 1):
    g = torch.Generator().manual_seed(seed)
    x = torch.randint(1, 40, (2, 12), generator=g)
    x_lengths = torch.tensor([12, 9])
    spec = torch.randn(2, 513, 48, generator=g).abs()
    spec_lengths = torch.tensor([48, 40])
    emb = torch.nn.functional.normalize(torch.randn(2, 192, generator=g), dim=-1)
    return x, x_lengths, spec, spec_lengths, emb


FLOWS = [
    pytest.param({}, id="plain-flow"),
    pytest.param({"use_snac_flow": True}, id="snac-flow"),
]


@pytest.mark.parametrize("overrides", FLOWS)
def test_alignment_and_expanded_prior_match_training_forward(overrides):
    model = _model(**overrides)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    with torch.no_grad():
        torch.manual_seed(7)
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb)
        z_q, _z_p, m_p, logs_p, _m_q, _logs_q = out.latents
        path = model.prior_path_latent(
            x, x_lengths, z_q, out.y_mask, speaker_embeddings=emb, noise_scale=0.4
        )
    assert torch.equal(path.attention, out.attention)
    torch.testing.assert_close(path.m_p, m_p)
    torch.testing.assert_close(path.logs_p, logs_p)
    assert path.z.shape == z_q.shape


@pytest.mark.parametrize("overrides", FLOWS)
def test_full_residual_returns_the_posterior_latent(overrides):
    """residual_scale=1 は flow⁻¹(flow(z_q)) = z_q (可逆性の誤差の範囲で)。"""
    model = _model(**overrides)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    with torch.no_grad():
        torch.manual_seed(7)
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb)
        z_q = out.latents[0]
        path = model.prior_path_latent(
            x, x_lengths, z_q, out.y_mask, speaker_embeddings=emb, residual_scale=1.0
        )
    torch.testing.assert_close(path.z, z_q * out.y_mask, atol=1e-4, rtol=1e-4)


@pytest.mark.parametrize("overrides", FLOWS)
def test_noise_sampling_matches_inference(overrides):
    """同じ並び・同じ乱数なら、infer と同じ z_p と z を返す。"""
    model = _model(**overrides)
    x, x_lengths, _spec, _spec_lengths, emb = _batch()
    ns = 0.4
    with torch.no_grad():
        torch.manual_seed(3)
        inf = model.infer(
            x, x_lengths, speaker_embeddings=emb, noise_scale=ns, noise_scale_w=0.5
        )
        z, z_p, m_p, logs_p = inf.latents
        eps = (z_p - m_p) / (torch.exp(logs_p) * ns)
        g, g_spk, g_lang = model._get_global_conditioning(
            None, None, speaker_embeddings=emb, return_components=True
        )
        z_again, z_p_again = model._sample_prior_latent(
            m_p, logs_p, inf.y_mask, g, g_spk, g_lang, noise_scale=ns, eps=eps
        )
    torch.testing.assert_close(z_p_again, z_p)
    torch.testing.assert_close(z_again, z)


def test_zero_noise_is_the_prior_mean_through_the_inverse_flow():
    model = _model(use_snac_flow=True)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    with torch.no_grad():
        torch.manual_seed(7)
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb)
        a = model.prior_path_latent(
            x,
            x_lengths,
            out.latents[0],
            out.y_mask,
            speaker_embeddings=emb,
            noise_scale=0.0,
        )
        torch.manual_seed(99)
        b = model.prior_path_latent(
            x,
            x_lengths,
            out.latents[0],
            out.y_mask,
            speaker_embeddings=emb,
            noise_scale=0.0,
        )
    torch.testing.assert_close(a.z, b.z)
    torch.testing.assert_close(a.z_p, a.m_p)


def test_explicit_eps_is_used_and_masked():
    model = _model(use_snac_flow=True)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    with torch.no_grad():
        torch.manual_seed(7)
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb)
        eps = torch.randn_like(out.latents[0])
        a = model.prior_path_latent(
            x,
            x_lengths,
            out.latents[0],
            out.y_mask,
            speaker_embeddings=emb,
            noise_scale=0.4,
            eps=eps,
        )
    torch.testing.assert_close(a.z_p, a.m_p + 0.4 * torch.exp(a.logs_p) * eps)
    pad = out.y_mask[1, 0] == 0
    assert bool(pad.any())
    assert float(a.z[1][:, pad].abs().max()) == 0.0


def test_residual_and_noise_are_exclusive():
    model = _model()
    x, x_lengths, spec, spec_lengths, emb = _batch()
    with torch.no_grad():
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb)
        with pytest.raises(ValueError, match="residual_scale"):
            model.prior_path_latent(
                x,
                x_lengths,
                out.latents[0],
                out.y_mask,
                speaker_embeddings=emb,
                residual_scale=0.5,
                eps=torch.randn_like(out.latents[0]),
            )


def test_no_gradient_reaches_the_text_encoder_or_flow():
    model = _model(use_snac_flow=True)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    with torch.no_grad():
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb)
    path = model.prior_path_latent(
        x, x_lengths, out.latents[0], out.y_mask, speaker_embeddings=emb
    )
    assert not path.z.requires_grad


def test_f0_prior_residual_follows_training_forward():
    model = _model(use_f0_path=True, f0_prior_residual=True)
    with torch.no_grad():
        model.f0_prior_res.weight.normal_(0.0, 0.1)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    f0 = torch.full((2, 1, 48), 210.0)
    with torch.no_grad():
        torch.manual_seed(7)
        out = model(x, x_lengths, spec, spec_lengths, speaker_embeddings=emb, f0=f0)
        path = model.prior_path_latent(
            x, x_lengths, out.latents[0], out.y_mask, speaker_embeddings=emb
        )
    torch.testing.assert_close(path.m_p, out.latents[2])
