#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path

import torch

from .vits import commons
from .vits.lightning import VitsModel


_LOGGER = logging.getLogger("piper_train.export_onnx")

OPSET_VERSION = 15


def simplify_onnx_model(onnx_path: Path, check_n: int = 3) -> bool:
    """
    Simplify ONNX model using onnxsim-prebuilt with validation.

    Args:
        onnx_path: Path to ONNX model file
        check_n: Number of validation checks to perform

    Returns:
        True if simplification succeeded, False otherwise
    """
    try:
        import onnx  # noqa: PLC0415
        from onnxsim import simplify  # noqa: PLC0415

        _LOGGER.info("Loading ONNX model for simplification: %s", onnx_path)
        original_model = onnx.load(str(onnx_path))
        original_size = onnx_path.stat().st_size

        _LOGGER.info("Simplifying ONNX model...")
        simplified_model, check_passed = simplify(
            original_model,
            check_n=check_n,
            perform_optimization=True,
            skip_fuse_bn=False,  # VITSには通常BatchNormがないので安全
        )

        if not check_passed:
            _LOGGER.error("ONNX model simplification failed validation")
            return False

        # Save simplified model
        onnx.save(simplified_model, str(onnx_path))
        new_size = onnx_path.stat().st_size
        reduction_percent = ((original_size - new_size) / original_size) * 100

        _LOGGER.info(
            "Model simplified successfully: %s (%.1f%% size reduction: %d -> %d bytes)",
            onnx_path,
            reduction_percent,
            original_size,
            new_size,
        )
        return True

    except ImportError:
        _LOGGER.warning(
            "onnxsim-prebuilt not installed. Install with: pip install onnxsim-prebuilt"
        )
        return False
    except Exception as e:
        _LOGGER.error("ONNX model simplification failed: %s", e)
        return False


def main() -> None:
    """Main entry point"""
    torch.manual_seed(1234)

    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", help="Path to model checkpoint (.ckpt)")
    parser.add_argument("output", help="Path to output model (.onnx)")

    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )
    parser.add_argument(
        "--simplify",
        action="store_true",
        help="Apply ONNX model simplification after export",
    )
    parser.add_argument(
        "--simplify-only", help="Only simplify existing ONNX model (path to .onnx file)"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    _LOGGER.debug(args)

    # -------------------------------------------------------------------------

    # Handle simplify-only mode
    if args.simplify_only:
        simplify_path = Path(args.simplify_only)
        if not simplify_path.exists():
            _LOGGER.error("ONNX file not found: %s", simplify_path)
            return
        simplify_onnx_model(simplify_path)
        return

    args.checkpoint = Path(args.checkpoint)
    args.output = Path(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    model = VitsModel.load_from_checkpoint(args.checkpoint, dataset=None, strict=False)
    model_g = model.model_g

    num_symbols = model_g.n_vocab
    num_speakers = model_g.n_speakers

    # Enable ONNX export mode for deterministic output
    model_g.onnx_export_mode = True
    # Propagate to Duration Predictor (StochasticDurationPredictor)
    if hasattr(model_g, "dp"):
        model_g.dp.onnx_export_mode = True

    # Inference only
    model_g.eval()

    with torch.no_grad():
        model_g.dec.remove_weight_norm()

    # Check if model uses prosody features
    has_prosody = getattr(model_g, "prosody_dim", 0) > 0

    def infer_forward(text, text_lengths, scales, sid=None, prosody_features=None):
        """
        Efficient forward function that returns both audio and duration information.
        Duration predictor is called only once (not twice as in the previous implementation).
        """
        # noise_scale = scales[0]  # unused in ONNX export (deterministic mode)
        length_scale = scales[1]
        noise_scale_w = scales[2]

        # 1. Encoder
        x, m_p, logs_p, x_mask = model_g.enc_p(text, text_lengths)

        if model_g.n_speakers > 1 and sid is not None:
            g = model_g.emb_g(sid).unsqueeze(-1)
        else:
            g = None

        # 2. Duration Predictor (called only once)
        x_dp = model_g._prepare_prosody_input(x, x_mask, prosody_features)
        if model_g.use_sdp:
            logw = model_g.dp(
                x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w
            )
        else:
            logw = model_g.dp(x_dp, x_mask, g=g)

        w = torch.exp(logw) * x_mask * length_scale
        durations = w.squeeze(1)  # [batch, phoneme_length]

        # 3. Attention/Alignment
        w_ceil = torch.ceil(w)
        y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
        y_mask = torch.unsqueeze(
            commons.sequence_mask(y_lengths, y_lengths.max()), 1
        ).type_as(x_mask)
        attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
        attn = commons.generate_path(w_ceil, attn_mask)

        # 4. Expand prior
        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
        logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)

        # 5. Sample z_p (deterministic in ONNX export mode)
        z_p = m_p  # onnx_export_mode uses mean only

        # 6. Flow + Decoder
        z = model_g.flow(z_p, y_mask, g=g, reverse=True)
        o = model_g.dec((z * y_mask), g=g)
        audio = o.unsqueeze(1)

        return audio, durations

    model_g.forward = infer_forward

    dummy_input_length = 50
    sequences = torch.randint(
        low=0, high=num_symbols, size=(1, dummy_input_length), dtype=torch.long
    )
    sequence_lengths = torch.LongTensor([sequences.size(1)])

    sid: torch.LongTensor | None = None
    if num_speakers > 1:
        sid = torch.LongTensor([0])

    # noise, noise_w, length
    scales = torch.FloatTensor([0.667, 1.0, 0.8])

    # Prosody features [batch, phonemes, 3] - A1/A2/A3 values
    # Use int64 (long) so that .float() in models.py creates explicit Cast node in ONNX graph
    prosody_features: torch.Tensor | None = None
    if has_prosody:
        prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    # Include all inputs for compatibility
    if num_speakers > 1 and has_prosody:
        dummy_input = (sequences, sequence_lengths, scales, sid, prosody_features)
    elif num_speakers > 1:
        dummy_input = (sequences, sequence_lengths, scales, sid)
    elif has_prosody:
        dummy_input = (sequences, sequence_lengths, scales, None, prosody_features)
    else:
        dummy_input = (sequences, sequence_lengths, scales)

    # Export - always include durations output
    output_names = ["output", "durations"]
    dynamic_axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "output": {0: "batch_size", 1: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }

    # Configure input names based on model type
    if num_speakers > 1:
        input_names = ["input", "input_lengths", "scales", "sid"]
        dynamic_axes["sid"] = {0: "batch_size"}
    else:
        input_names = ["input", "input_lengths", "scales"]

    # Add prosody_features if model uses prosody
    if has_prosody:
        input_names.append("prosody_features")
        dynamic_axes["prosody_features"] = {0: "batch_size", 1: "phonemes"}
        _LOGGER.info(
            "Exporting model with prosody features support (prosody_dim=%d)",
            model_g.prosody_dim,
        )

    torch.onnx.export(
        model=model_g,
        args=dummy_input,
        f=str(args.output),
        verbose=False,
        opset_version=OPSET_VERSION,
        input_names=input_names,
        output_names=output_names,
        dynamic_axes=dynamic_axes,
    )

    _LOGGER.info("Exported model to %s", args.output)

    # Apply ONNX simplification if requested
    # Skip simplification for prosody models to avoid numerical precision issues
    if args.simplify:
        if has_prosody:
            _LOGGER.info(
                "Prosody features enabled (prosody_dim=%d) - skipping ONNX simplification to preserve numerical accuracy",
                model_g.prosody_dim,
            )
        else:
            simplify_onnx_model(args.output)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
