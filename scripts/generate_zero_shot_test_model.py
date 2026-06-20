#!/usr/bin/env python3
"""Generate a small zero-shot ONNX test model for E2E CI testing.

Creates a minimal SynthesizerTrn model with speaker_embedding input and exports
it to ONNX. Suitable for cross-language CI tests (C++, C#, Rust, Python).

Output files:
  test/models/zero-shot-test.onnx      - ONNX model with speaker_embedding input
  test/models/zero-shot-test.onnx.json - config.json for the model
  test/models/test_speaker.npy         - 192-dim L2-normalised speaker embedding
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch


# Ensure the piper_train package is importable from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "python"))

from piper_train.vits import commons  # noqa: E402
from piper_train.vits.models import SynthesizerTrn  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal model parameters for CI (kept well under 5 MB ONNX file size)
# ---------------------------------------------------------------------------
# Key size drivers and reductions applied:
#   - inter/hidden_channels=32: encoder/flow tensors shrink quadratically
#   - filter_channels=64: attention feed-forward is much smaller
#   - n_layers=1: single transformer layer in TextEncoder
#   - upsample_initial_channel=64: decoder Conv stack starts thin
#   - resblock="2" + narrow kernel list: smallest resblock variant
#   - gin_channels=128: spk_proj MLP is Linear(192,128)->Linear(128,128)
#     still tests the zero-shot conditioning path end-to-end
#   - n_vocab=128: smaller embedding table
MODEL_PARAMS: dict = {
    "n_vocab": 128,
    "spec_channels": 513,
    "segment_size": 8192,
    "inter_channels": 32,
    "hidden_channels": 32,
    "filter_channels": 64,
    "n_heads": 2,
    "n_layers": 1,
    "kernel_size": 3,
    "p_dropout": 0.1,
    "resblock": "2",
    "resblock_kernel_sizes": [3, 5],
    "resblock_dilation_sizes": [[1, 2], [2, 6]],
    "upsample_rates": [8, 8, 2, 2],
    "upsample_initial_channel": 64,
    "upsample_kernel_sizes": [16, 16, 4, 4],
    "n_speakers": 2,
    "gin_channels": 128,
    "n_languages": 1,
    "prosody_dim": 16,
}

# Output paths
OUTPUT_DIR = _REPO_ROOT / "test" / "models"
ONNX_PATH = OUTPUT_DIR / "zero-shot-test.onnx"
CONFIG_PATH = OUTPUT_DIR / "zero-shot-test.onnx.json"
SPEAKER_EMB_PATH = OUTPUT_DIR / "test_speaker.npy"

OPSET_VERSION = 15


def build_infer_forward(model: SynthesizerTrn, *, stochastic: bool = False):
    """Return an ONNX-compatible forward function for zero-shot inference.

    Mirrors the logic in export_onnx.py's inline infer_forward, using
    model._get_global_conditioning (which calls _get_speaker_condition via
    spk_proj) so the exported graph accepts a speaker_embedding input.
    """

    def infer_forward(
        text,
        text_lengths,
        scales,
        speaker_embedding=None,
        prosody_features=None,
    ):
        length_scale = scales[1]
        noise_scale_w = scales[2]

        # Global conditioning via spk_proj MLP
        g = model._get_global_conditioning(
            sid=None, lid=None, speaker_embeddings=speaker_embedding
        )

        # Encoder
        x, m_p, logs_p, x_mask = model.enc_p(text, text_lengths, g=g)

        # Duration predictor
        x_dp = model._prepare_prosody_input(x, x_mask, prosody_features, lid=None)
        if model.use_sdp:
            logw = model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w)
        else:
            logw = model.dp(x_dp, x_mask, g=g)

        w = torch.exp(logw) * x_mask * length_scale
        durations = w.squeeze(1)

        # Alignment
        w_ceil = torch.ceil(w)
        y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
        y_mask = torch.unsqueeze(
            commons.sequence_mask(y_lengths, y_lengths.max()), 1
        ).type_as(x_mask)
        attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
        attn = commons.generate_path(w_ceil, attn_mask)

        # Expand prior
        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
        logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)

        # Sample / decode
        if stochastic:
            noise_scale = scales[0]
            z_p = m_p + torch.randn_like(m_p) * torch.exp(logs_p) * noise_scale
        else:
            z_p = m_p

        z = model.flow(z_p, y_mask, g=g, reverse=True)
        o = model.dec((z * y_mask), g=g)

        return o, durations

    return infer_forward


def create_model() -> SynthesizerTrn:
    torch.manual_seed(42)
    model = SynthesizerTrn(**MODEL_PARAMS)
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()

    # Set ONNX export mode (deterministic: no stochastic sampling)
    model.onnx_export_mode = True
    if hasattr(model, "dp"):
        model.dp.onnx_export_mode = True

    return model


def export_onnx(model: SynthesizerTrn, output_path: Path) -> None:
    model.forward = build_infer_forward(model, stochastic=False)

    dummy_input_length = 20
    sequences = torch.randint(
        0, MODEL_PARAMS["n_vocab"], (1, dummy_input_length), dtype=torch.long
    )
    sequence_lengths = torch.LongTensor([dummy_input_length])
    scales = torch.FloatTensor(
        [0.4, 1.0, 0.5]
    )  # noise_scale, length_scale, noise_scale_w
    speaker_embedding = torch.zeros(1, 192, dtype=torch.float32)
    prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    dummy_input = (
        sequences,
        sequence_lengths,
        scales,
        speaker_embedding,
        prosody_features,
    )
    input_names = [
        "input",
        "input_lengths",
        "scales",
        "speaker_embedding",
        "prosody_features",
    ]
    output_names = ["output", "durations"]
    dynamic_axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "scales": {},
        "speaker_embedding": {0: "batch_size"},
        "prosody_features": {0: "batch_size", 1: "phonemes"},
        "output": {0: "batch_size", 2: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }

    print(f"Exporting ONNX model to {output_path} ...")
    torch.onnx.export(
        model=model,
        args=dummy_input,
        f=str(output_path),
        verbose=False,
        opset_version=OPSET_VERSION,
        input_names=input_names,
        output_names=output_names,
        dynamic_axes=dynamic_axes,
        dynamo=False,
    )
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Done. Size: {size_mb:.2f} MB")


def write_config(output_path: Path) -> None:
    """Write a config.json compatible with infer_onnx.py."""
    config = {
        "audio": {
            "sample_rate": 22050,
            "quality": "x_low",
        },
        "espeak": {
            "voice": "en-us",
        },
        "inference": {
            "noise_scale": 0.4,
            "length_scale": 1.0,
            "noise_scale_w": 0.5,
        },
        "phoneme_type": "espeak",
        "phoneme_map": {},
        "phoneme_id_map": {
            "^": [1],
            "a": [10],
            "n": [57],
            "o": [14],
            "$": [2],
            "_": [0],
            " ": [3],
        },
        "num_symbols": MODEL_PARAMS["n_vocab"],
        "num_speakers": MODEL_PARAMS["n_speakers"],
        "gin_channels": MODEL_PARAMS["gin_channels"],
        "speaker_id_map": {
            "speaker_0": 0,
            "speaker_1": 1,
        },
        "language": {
            "code": "en_US",
            "family": "en",
            "region": "US",
            "name_native": "English",
            "name_english": "English",
            "country_english": "United States",
        },
        "dataset": "zero-shot-test",
        "piper_version": "1.0.0",
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"  Config written to {output_path}")


def write_speaker_embedding(output_path: Path) -> None:
    """Generate a random L2-normalised 192-dim speaker embedding."""
    rng = np.random.default_rng(seed=42)
    emb = rng.standard_normal(192).astype(np.float32)
    emb /= np.linalg.norm(emb)  # L2 normalise
    np.save(str(output_path), emb)
    print(
        f"  Speaker embedding written to {output_path} (shape={emb.shape}, norm={np.linalg.norm(emb):.4f})"
    )


def verify_model(onnx_path: Path) -> None:
    """Load with onnxruntime and run a quick inference to verify correctness."""
    try:
        import onnxruntime as ort
    except ImportError:
        print("WARNING: onnxruntime not installed, skipping verification.")
        return

    print("\nVerifying ONNX model ...")
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])

    print("  Inputs:")
    for inp in sess.get_inputs():
        print(f"    {inp.name}: {inp.shape}  {inp.type}")
    print("  Outputs:")
    for out in sess.get_outputs():
        print(f"    {out.name}: {out.shape}  {out.type}")

    # Check expected input names
    input_names = {inp.name for inp in sess.get_inputs()}
    assert "input" in input_names, "Missing 'input'"
    assert "input_lengths" in input_names, "Missing 'input_lengths'"
    assert "scales" in input_names, "Missing 'scales'"
    assert "speaker_embedding" in input_names, "Missing 'speaker_embedding'"
    assert "sid" not in input_names, "Unexpected 'sid' (should be zero-shot only)"

    # Run quick inference
    text_np = np.array([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]], dtype=np.int64)
    text_lengths_np = np.array([text_np.shape[1]], dtype=np.int64)
    scales_np = np.array([0.4, 1.0, 0.5], dtype=np.float32)
    spk_emb_np = np.load(str(SPEAKER_EMB_PATH)).reshape(1, 192).astype(np.float32)
    prosody_np = np.zeros((1, text_np.shape[1], 3), dtype=np.int64)

    feed = {
        "input": text_np,
        "input_lengths": text_lengths_np,
        "scales": scales_np,
        "speaker_embedding": spk_emb_np,
        "prosody_features": prosody_np,
    }
    outputs = sess.run(None, feed)
    audio = outputs[0]

    print(
        f"\n  Inference OK: audio shape={audio.shape}, "
        f"finite={np.isfinite(audio).all()}, "
        f"max={np.abs(audio).max():.4f}"
    )
    assert np.isfinite(audio).all(), "Output contains NaN or Inf!"
    print("  All checks passed.")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Generating zero-shot test model ===")
    print(f"Output directory: {OUTPUT_DIR}\n")

    # 1. Build and export ONNX model
    model = create_model()
    export_onnx(model, ONNX_PATH)

    # 2. Write config.json
    write_config(CONFIG_PATH)

    # 3. Write test speaker embedding
    write_speaker_embedding(SPEAKER_EMB_PATH)

    # 4. Verify
    verify_model(ONNX_PATH)

    # Final size report
    size_mb = ONNX_PATH.stat().st_size / (1024 * 1024)
    print("\n=== Summary ===")
    print(f"  ONNX model : {ONNX_PATH}  ({size_mb:.2f} MB)")
    print(f"  Config     : {CONFIG_PATH}")
    print(f"  Speaker emb: {SPEAKER_EMB_PATH}")
    if size_mb > 5.0:
        print(f"  WARNING: model size {size_mb:.2f} MB exceeds 5 MB target")
    else:
        print("  Size OK (< 5 MB target)")


if __name__ == "__main__":
    main()
