"""Size/speed prototypes for P1 decoder candidates (weights are random)."""

import pytest
import torch


pytestmark = pytest.mark.unit

HOP = 256


def _mb_istft(gin=16):
    from piper_train.vits.mb_istft import MBiSTFTGenerator

    return MBiSTFTGenerator(
        initial_channel=8,
        resblock="2",
        resblock_kernel_sizes=(3,),
        resblock_dilation_sizes=((1, 2),),
        upsample_initial_channel=32,
        gin_channels=gin,
    )


def test_fullband_istft_decoder_output_length_and_modes():
    from piper_train.tools.measure_variant_cost import FullbandISTFTDecoder

    dec = FullbandISTFTDecoder(
        in_channels=8, dim=16, intermediate_dim=32, num_blocks=2, gin_channels=4
    )
    x = torch.randn(2, 8, 5)
    g = torch.randn(2, 4, 1)
    wav, sub = dec(x, g=g, f0=None)
    assert wav.shape == (2, 1, 5 * HOP)
    assert sub is None
    dec.onnx_export_mode = True
    assert dec(x, g=g).shape == (2, 1, 5 * HOP)
    dec.remove_weight_norm()  # export calls it unconditionally


def test_reference_cross_attention_starts_as_identity():
    from piper_train.tools.measure_variant_cost import add_reference_cross_attention

    torch.manual_seed(0)
    dec = _mb_istft().eval()
    x = torch.randn(1, 8, 6)
    g = torch.randn(1, 16, 1)
    with torch.no_grad():
        before, _ = dec(x, g=g)
    n_before = sum(p.numel() for p in dec.parameters())
    add_reference_cross_attention(dec, n_tokens=4, token_dim=12)
    with torch.no_grad():
        after, _ = dec(x, g=g)
    assert sum(p.numel() for p in dec.parameters()) > n_before
    torch.testing.assert_close(after, before)


def test_reference_cross_attention_changes_output_once_trained():
    from piper_train.tools.measure_variant_cost import add_reference_cross_attention

    torch.manual_seed(0)
    dec = _mb_istft().eval()
    x = torch.randn(1, 8, 6)
    with torch.no_grad():
        before, _ = dec(x)
    sites = add_reference_cross_attention(dec, n_tokens=4, token_dim=12)
    with torch.no_grad():
        for site in sites:
            site.out.weight.normal_()
        after, _ = dec(x)
    assert not torch.allclose(after, before)


def test_shrink_flow_keeps_interface():
    from piper_train.tools.measure_variant_cost import shrink_flow
    from piper_train.vits.models import ResidualCouplingBlock

    flow = ResidualCouplingBlock(
        8, 16, 5, 1, 4, n_flows=4, gin_channels=4, use_snac=True
    )
    small = shrink_flow(flow, n_flows=2, hidden_channels=8, n_layers=2)
    assert sum(p.numel() for p in small.parameters()) < sum(
        p.numel() for p in flow.parameters()
    )
    assert small.use_snac and small.n_flows == 2 and small.hidden_channels == 8
    x = torch.randn(1, 8, 7)
    mask = torch.ones(1, 1, 7)
    g = torch.randn(1, 4, 1)
    assert small(x, mask, g=g, g_spk=g, reverse=True).shape == x.shape


def test_load_matching_state_skips_shape_mismatch():
    from piper_train.tools.measure_variant_cost import load_matching_state

    target = torch.nn.Sequential(torch.nn.Linear(3, 4), torch.nn.Linear(4, 5))
    source = torch.nn.Sequential(torch.nn.Linear(3, 4), torch.nn.Linear(4, 6))
    loaded, skipped = load_matching_state(target, source.state_dict())
    assert loaded == ["0.bias", "0.weight"]
    assert skipped == ["1.bias", "1.weight"]
    torch.testing.assert_close(target[0].weight, source[0].weight)


def test_summarize_latencies():
    from piper_train.tools.measure_variant_cost import summarize_latencies

    s = summarize_latencies([0.010, 0.030, 0.020, 0.040, 0.050])
    assert s["p50_ms"] == pytest.approx(30.0)
    assert s["mean_ms"] == pytest.approx(30.0)
    assert s["runs"] == 5


def test_variants_are_described_and_baseline_is_unchanged():
    from piper_train.tools.measure_variant_cost import VARIANTS

    assert "baseline" in VARIANTS
    assert VARIANTS["baseline"].overrides == {}
    assert VARIANTS["baseline"].transforms == ()
    for name, spec in VARIANTS.items():
        assert spec.description, name
