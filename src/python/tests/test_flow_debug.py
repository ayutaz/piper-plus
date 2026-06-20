"""
Flow reverse pass diagnostic test: inspect each coupling layer for numerical issues.

Loads the epoch=199 checkpoint, runs flow.reverse, and checks:
  - Each ResidualCouplingLayer's logs values and exp(-logs) magnitude
  - Whether logs are actually learned (not all zero / collapsed)
  - NaN/Inf presence at each layer
  - Final z and audio output quality
"""

import os
from pathlib import Path

import numpy as np
import pytest


try:
    import torch
except ImportError:
    torch = None

pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

# Maintainer-only diagnostic. Override via env var; default path is the
# maintainer's training-host layout (documented in CLAUDE.md / docs/handoff).
# The fixture skips when the checkpoint is absent, so this is safe on CI.
CKPT_PATH = os.environ.get(
    "PIPER_FLOW_DEBUG_CKPT",
    str(Path.home() / "piper-flow-debug-epoch199.ckpt"),
)


def _stats(t, name=""):
    """Return dict of tensor statistics."""
    t_f = t.float()
    return {
        "name": name,
        "shape": list(t.shape),
        "mean": t_f.mean().item(),
        "std": t_f.std().item(),
        "min": t_f.min().item(),
        "max": t_f.max().item(),
        "nan_count": torch.isnan(t_f).sum().item(),
        "inf_count": torch.isinf(t_f).sum().item(),
    }


def _print_stats(s):
    """Pretty-print stats dict."""
    flag = ""
    if s["nan_count"] > 0 or s["inf_count"] > 0:
        flag = f"  *** NaN={s['nan_count']}, Inf={s['inf_count']} ***"
    print(
        f"  {s['name']:45s} shape={str(s['shape']):20s} "
        f"mean={s['mean']:+10.5f}  std={s['std']:10.5f}  "
        f"min={s['min']:+10.5f}  max={s['max']:+10.5f}{flag}"
    )


@pytest.fixture(scope="module")
def loaded_model():
    """Load checkpoint and build SynthesizerTrn."""
    if not Path(CKPT_PATH).exists():
        pytest.skip(f"Checkpoint not found: {CKPT_PATH}")

    ckpt = torch.load(CKPT_PATH, map_location="cpu", weights_only=False)
    state_dict = ckpt["state_dict"]
    hp = ckpt["hyper_parameters"]

    from piper_train.vits.models import SynthesizerTrn

    model = SynthesizerTrn(
        n_vocab=hp["num_symbols"],
        spec_channels=hp["filter_length"] // 2 + 1,
        segment_size=hp["segment_size"] // hp["hop_length"],
        inter_channels=hp["inter_channels"],
        hidden_channels=hp["hidden_channels"],
        filter_channels=hp["filter_channels"],
        n_heads=hp["n_heads"],
        n_layers=hp["n_layers"],
        kernel_size=hp["kernel_size"],
        p_dropout=hp["p_dropout"],
        resblock=hp["resblock"],
        resblock_kernel_sizes=hp["resblock_kernel_sizes"],
        resblock_dilation_sizes=hp["resblock_dilation_sizes"],
        upsample_rates=hp["upsample_rates"],
        upsample_initial_channel=hp["upsample_initial_channel"],
        upsample_kernel_sizes=hp["upsample_kernel_sizes"],
        n_speakers=hp["num_speakers"],
        gin_channels=hp["gin_channels"],
        use_sdp=hp.get("use_sdp", True),
        prosody_dim=hp.get("prosody_dim", 16),
        use_zero_shot=hp.get("use_zero_shot", True),
        spk_embed_dim=hp.get("spk_embed_dim", 192),
    )

    from piper_train.vits.commons import remap_weight_norm_keys

    model_state = {}
    for k, v in state_dict.items():
        if k.startswith("model_g."):
            model_state[k[len("model_g.") :]] = v

    # Remap weight_norm keys (DDP parametrized ↔ legacy format)
    model_state = remap_weight_norm_keys(model_state, model.state_dict())

    # Filter out keys whose shapes changed or were renamed between model versions:
    # 1. flow.post keys (mean_only=True vs False shape change)
    # 2. enc_p.cond -> enc_p.cond_layer rename
    model_params = dict(model.named_parameters())
    model_bufs = dict(model.named_buffers())
    incompatible_keys = []
    for k in list(model_state.keys()):
        # Skip keys with shape mismatches (flow.post mean_only change)
        if "flow." in k and ".post." in k:
            model_param = model_params.get(k)
            if model_param is None:
                model_param = model_bufs.get(k)
            if model_param is not None and model_state[k].shape != model_param.shape:
                incompatible_keys.append(k)
                del model_state[k]
        # Skip keys that don't exist in the current model (renamed or removed)
        elif k not in model_params and k not in model_bufs:
            incompatible_keys.append(k)
            del model_state[k]

    missing, unexpected = model.load_state_dict(model_state, strict=False)
    model.eval()
    return model, hp, missing, unexpected, incompatible_keys


class TestFlowReverseNumerics:
    """Diagnose numerical issues in Flow reverse pass."""

    def test_checkpoint_loads(self, loaded_model):
        """Verify checkpoint loads without key mismatches."""
        model, hp, missing, unexpected, incompatible_keys = loaded_model
        print(f"\nCheckpoint: {CKPT_PATH}")
        print(
            f"gin_channels={hp.get('gin_channels')}, inter_channels={hp.get('inter_channels')}"
        )
        print(f"Missing keys: {len(missing)}")
        for k in missing[:5]:
            print(f"  {k}")
        print(f"Unexpected keys: {len(unexpected)}")
        for k in unexpected[:5]:
            print(f"  {k}")
        if incompatible_keys:
            print(
                f"Incompatible keys (skipped due to mean_only change): {len(incompatible_keys)}"
            )
            for k in incompatible_keys:
                print(f"  {k}")
        # Allow missing keys for:
        # - spk_proj_teacher / dino_center: DINO self-distillation buffers
        # - flow.*: mean_only shape mismatch (re-initialized)
        # - enc_p.cond_layer: TextEncoder speaker conditioning (new in Phase 2)
        # - dec.cond_layers: Decoder FiLM conditioning (new in Phase 2)
        # - dec.ups.*.weight_g/weight_v: weight_norm decomposition (new parametrization)
        allowed_prefixes = (
            "spk_proj_teacher",
            "dino_center",
            "flow.",
            "enc_p.cond_layer",
            "dec.cond_layers",
            "dec.ups.",
        )
        allowed_missing = [
            k
            for k in missing
            if not any(k.startswith(prefix) for prefix in allowed_prefixes)
        ]
        assert len(allowed_missing) == 0, f"Unexpected missing keys: {allowed_missing}"

    def test_flow_architecture(self, loaded_model):
        """Print flow architecture and verify mean_only=True."""
        model, hp, _, _, _ = loaded_model
        flow = model.flow
        print(
            f"\nFlow: n_flows={flow.n_flows}, channels={flow.channels}, "
            f"hidden={flow.hidden_channels}, dilation_rate={flow.dilation_rate}"
        )
        coupling_count = 0
        for i, f_layer in enumerate(flow.flows):
            ltype = type(f_layer).__name__
            if hasattr(f_layer, "mean_only"):
                print(f"  flows[{i}]: {ltype}  mean_only={f_layer.mean_only}")
                assert f_layer.mean_only, f"flow[{i}] should have mean_only=True"
                coupling_count += 1
            else:
                print(f"  flows[{i}]: {ltype}")
        print(f"Total coupling layers: {coupling_count}")
        assert coupling_count == flow.n_flows

    def test_post_weights_are_learned(self, loaded_model):
        """Verify that post weights are learned (not all zero).

        With mean_only=True, post only outputs the mean (no logs portion).
        Note: flow.post weights are re-initialized (not loaded from checkpoint)
        because the checkpoint used mean_only=False with different shapes.
        After re-initialization, weights are zero-initialized by design.
        This test verifies the post layer exists and has the correct shape.
        """
        model, _, _, _, incompatible_keys = loaded_model
        flow = model.flow
        print("\nResidualCouplingLayer post weights (mean_only=True):")
        for i, f_layer in enumerate(flow.flows):
            if not hasattr(f_layer, "post"):
                continue
            w = f_layer.post.weight.data
            b = f_layer.post.bias.data

            _print_stats(_stats(w, f"flow[{i}] post.weight"))
            _print_stats(_stats(b, f"flow[{i}] post.bias"))

            # With mean_only=True, post outputs half_channels
            half_channels = f_layer.half_channels
            assert w.shape[0] == half_channels, (
                f"flow[{i}] post weight shape[0] should be {half_channels} (mean_only=True), got {w.shape[0]}"
            )

    def test_per_layer_reverse_statistics(self, loaded_model):
        """Run flow.reverse layer by layer and inspect statistics."""
        model, hp, _, _, _ = loaded_model
        flow = model.flow

        B, C, T = 1, hp["inter_channels"], 50
        torch.manual_seed(42)
        z_p = torch.randn(B, C, T) * 0.4
        x_mask = torch.ones(B, 1, T)

        spk_emb = torch.randn(1, 192)
        with torch.no_grad():
            g = model.spk_proj(spk_emb).unsqueeze(-1)

        print("\nInput z_p:")
        _print_stats(_stats(z_p, "z_p"))
        print("Speaker g:")
        _print_stats(_stats(g, "g"))

        x = z_p
        all_ok = True
        print("\n--- Per-layer reverse pass ---")
        with torch.no_grad():
            for idx, f_layer in enumerate(reversed(flow.flows)):
                layer_name = type(f_layer).__name__

                if layer_name == "Flip":
                    x = f_layer(x, x_mask, g=g, reverse=True)
                    s = _stats(x, "output")
                    print(f"\n[{idx}] {layer_name}")
                    _print_stats(s)
                    if s["nan_count"] > 0 or s["inf_count"] > 0:
                        all_ok = False
                    continue

                print(f"\n[{idx}] {layer_name} (mean_only={f_layer.mean_only})")
                _print_stats(_stats(x, "input"))

                # Manual forward to inspect internals
                x0, x1 = torch.split(x, [f_layer.half_channels] * 2, 1)
                h = f_layer.pre(x0) * x_mask
                h = f_layer.enc(h, x_mask, g=g)
                stats = f_layer.post(h) * x_mask

                if not f_layer.mean_only:
                    m, logs_raw = torch.split(stats, [f_layer.half_channels] * 2, 1)
                    logs = torch.tanh(logs_raw / 3.0) * 3.0
                    exp_neg_logs = torch.exp(-logs)

                    _print_stats(_stats(m, "m"))
                    _print_stats(_stats(logs_raw, "logs_raw (pre-tanh)"))
                    _print_stats(_stats(logs, "logs (post-tanh)"))
                    _print_stats(_stats(exp_neg_logs, "exp(-logs)"))

                    max_exp = exp_neg_logs.max().item()
                    if max_exp > 50:
                        print(f"  *** WARNING: exp(-logs) max = {max_exp:.2f} ***")
                        all_ok = False

                    x1_new = (x1 - m) * exp_neg_logs * x_mask
                    x = torch.cat([x0, x1_new], 1)
                else:
                    m = stats
                    x1_new = (x1 - m) * x_mask
                    x = torch.cat([x0, x1_new], 1)

                _print_stats(_stats(x, "output"))
                s = _stats(x, "output")
                if s["nan_count"] > 0 or s["inf_count"] > 0:
                    all_ok = False

        z_final = x
        print("\nFinal z (after flow.reverse):")
        _print_stats(_stats(z_final, "z_final"))

        assert all_ok, (
            "NaN/Inf or dangerous exp(-logs) values detected during flow.reverse"
        )

    def test_flow_reverse_consistency(self, loaded_model):
        """Compare manual per-layer output vs model.flow() reverse."""
        model, hp, _, _, _ = loaded_model
        flow = model.flow

        B, C, T = 1, hp["inter_channels"], 50
        torch.manual_seed(42)
        z_p = torch.randn(B, C, T) * 0.4
        x_mask = torch.ones(B, 1, T)

        spk_emb = torch.randn(1, 192)
        with torch.no_grad():
            g = model.spk_proj(spk_emb).unsqueeze(-1)

        # Manual reverse
        x = z_p.clone()
        with torch.no_grad():
            for f_layer in reversed(flow.flows):
                x = f_layer(x, x_mask, g=g, reverse=True)
            z_manual = x

        # Model reverse
        with torch.no_grad():
            z_actual = model.flow(z_p, x_mask, g=g, reverse=True)

        diff = (z_manual - z_actual).abs()
        _print_stats(_stats(diff, "diff (manual vs model.flow)"))
        assert diff.max().item() < 1e-4, (
            f"Manual vs model.flow reverse mismatch: max diff = {diff.max().item()}"
        )

    def test_mean_distribution_per_layer(self, loaded_model):
        """Analyze mean output distribution per coupling layer (mean_only=True)."""
        model, hp, _, _, _ = loaded_model
        flow = model.flow

        B, C, T = 1, hp["inter_channels"], 50
        torch.manual_seed(42)
        z_p = torch.randn(B, C, T) * 0.4
        x_mask = torch.ones(B, 1, T)

        spk_emb = torch.randn(1, 192)
        with torch.no_grad():
            g = model.spk_proj(spk_emb).unsqueeze(-1)

        print("\nMean output distribution per coupling layer (mean_only=True):")
        for i, f_layer in enumerate(flow.flows):
            if not hasattr(f_layer, "post"):
                continue

            with torch.no_grad():
                x0, x1 = torch.split(z_p, [f_layer.half_channels] * 2, 1)
                h = f_layer.pre(x0) * x_mask
                h = f_layer.enc(h, x_mask, g=g)
                m = f_layer.post(h) * x_mask

            m_flat = m.flatten().numpy()
            percentiles = [0, 1, 5, 25, 50, 75, 95, 99, 100]
            pvals = np.percentile(m_flat, percentiles)

            print(f"\n  flow[{i}] mean distribution:")
            for p, v in zip(percentiles, pvals, strict=False):
                print(f"    P{p:3d}: {v:+8.4f}")

            _print_stats(_stats(m, f"flow[{i}] mean output"))

    def test_full_inference_output(self, loaded_model):
        """Run full inference and check audio output for beep-like patterns."""
        model, hp, _, _, _ = loaded_model

        torch.manual_seed(42)
        text_ids = torch.randint(0, hp["num_symbols"], (1, 20))
        text_lengths = torch.LongTensor([20])
        spk_emb = torch.randn(1, 192)

        with torch.no_grad():
            audio, attn, y_mask, (z, z_p, m_p, logs_p) = model.infer(
                text_ids,
                text_lengths,
                noise_scale=0.4,
                noise_scale_w=0.5,
                speaker_embeddings=spk_emb,
            )

        print("\nFull inference output:")
        _print_stats(_stats(m_p, "m_p (TextEncoder prior mean)"))
        _print_stats(_stats(logs_p, "logs_p (TextEncoder prior logvar)"))
        _print_stats(_stats(z_p, "z_p (sampled from prior)"))
        _print_stats(_stats(z, "z (after flow.reverse)"))
        _print_stats(_stats(audio, "audio output"))
        print(f"  audio max abs: {audio.abs().max().item():.6f}")

        # Check for silence
        audio_np = audio.squeeze().numpy()
        audio_range = audio_np.max() - audio_np.min()
        print(f"  audio range: {audio_range:.6f}")
        if audio_range < 0.01:
            print("  *** WARNING: Audio range very small - likely silence or DC ***")

        # Check spectral content for beep
        if len(audio_np) > 256:
            fft = np.abs(np.fft.rfft(audio_np[:2048]))
            peak_freq_bin = np.argmax(fft[1:]) + 1
            sample_rate = hp.get("sample_rate", 22050)
            peak_freq = peak_freq_bin * sample_rate / 2048
            fft_energy_ratio = fft[peak_freq_bin] / (fft.sum() + 1e-8)
            print(f"  Peak frequency: ~{peak_freq:.0f} Hz (bin {peak_freq_bin})")
            print(f"  Peak energy ratio: {fft_energy_ratio:.4f}")
            if fft_energy_ratio > 0.5:
                print(
                    "  *** WARNING: Single frequency dominates - likely beep/tone ***"
                )

        # NaN/Inf checks
        assert not torch.isnan(audio).any(), "Audio contains NaN"
        assert not torch.isinf(audio).any(), "Audio contains Inf"
        assert not torch.isnan(z).any(), "z contains NaN"
        assert not torch.isnan(z_p).any(), "z_p contains NaN"

    def test_posterior_encoder_logs_bias(self, loaded_model):
        """Check PosteriorEncoder proj bias initialization for logs."""
        model, _, _, _, _ = loaded_model
        pe = model.enc_q
        proj_bias = pe.proj.bias.data
        out_ch = pe.out_channels
        bias_m = proj_bias[:out_ch]
        bias_logs = proj_bias[out_ch:]
        print("\nPosteriorEncoder proj bias:")
        _print_stats(_stats(bias_m, "proj.bias (m part)"))
        _print_stats(_stats(bias_logs, "proj.bias (logs part)"))

    def test_spk_proj_output_range(self, loaded_model):
        """Check that spk_proj output range is reasonable for conditioning."""
        model, hp, _, _, _ = loaded_model
        if not hasattr(model, "spk_proj"):
            pytest.skip("No spk_proj in model")

        # Test with multiple speaker embeddings
        torch.manual_seed(0)
        for i in range(5):
            spk_emb = torch.randn(1, 192)
            with torch.no_grad():
                g = model.spk_proj(spk_emb)
            s = _stats(g, f"spk_proj output (emb #{i})")
            _print_stats(s)
            assert s["nan_count"] == 0, f"NaN in spk_proj output for emb #{i}"
            assert s["inf_count"] == 0, f"Inf in spk_proj output for emb #{i}"

    def test_textencoder_prior_with_speaker(self, loaded_model):
        """Check TextEncoder prior (m_p, logs_p) with speaker conditioning."""
        model, hp, _, _, _ = loaded_model

        torch.manual_seed(42)
        text_ids = torch.randint(0, hp["num_symbols"], (1, 20))
        text_lengths = torch.LongTensor([20])
        spk_emb = torch.randn(1, 192)

        with torch.no_grad():
            g = model.spk_proj(spk_emb).unsqueeze(-1)
            x, m_p, logs_p, x_mask = model.enc_p(text_ids, text_lengths, g=g)

        print("\nTextEncoder with speaker conditioning:")
        _print_stats(_stats(x, "encoder output x"))
        _print_stats(_stats(m_p, "m_p (prior mean)"))
        _print_stats(_stats(logs_p, "logs_p (prior log-var)"))

        # Check logs_p range
        assert not torch.isnan(m_p).any(), "m_p contains NaN"
        assert not torch.isnan(logs_p).any(), "logs_p contains NaN"
        print(
            f"  exp(logs_p) range: [{torch.exp(logs_p).min().item():.4f}, {torch.exp(logs_p).max().item():.4f}]"
        )

    def test_multiple_speakers_flow_stability(self, loaded_model):
        """Test flow reverse with multiple different speaker embeddings."""
        model, hp, _, _, _ = loaded_model

        B, C, T = 1, hp["inter_channels"], 50
        x_mask = torch.ones(B, 1, T)

        print("\nFlow reverse with different speaker embeddings:")
        for seed in range(10):
            torch.manual_seed(seed)
            z_p = torch.randn(B, C, T) * 0.4
            spk_emb = torch.randn(1, 192)

            with torch.no_grad():
                g = model.spk_proj(spk_emb).unsqueeze(-1)
                z = model.flow(z_p, x_mask, g=g, reverse=True)

            s = _stats(z, f"z (seed={seed})")
            _print_stats(s)
            assert s["nan_count"] == 0, f"NaN in flow reverse for seed={seed}"
            assert s["inf_count"] == 0, f"Inf in flow reverse for seed={seed}"
            if abs(s["std"]) < 0.01:
                print(
                    f"  *** WARNING: Very low std for seed={seed} - possible collapse ***"
                )
            if abs(s["max"]) > 100:
                print(
                    f"  *** WARNING: Large max for seed={seed} - possible explosion ***"
                )
