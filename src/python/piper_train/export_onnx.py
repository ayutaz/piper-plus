#!/usr/bin/env python3
import argparse
import logging
import pathlib
import platform
from pathlib import Path

import torch


torch.serialization.add_safe_globals([pathlib.PosixPath])

from .vits import commons
from .vits.lightning import VitsModel


# Allow Path objects in checkpoints (PyTorch 2.6+ weights_only=True)
torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])

# Fix PosixPath instantiation error when loading Linux checkpoints on Windows
if platform.system() == "Windows":
    pathlib.PosixPath = pathlib.WindowsPath


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
    parser.add_argument(
        "--stochastic",
        action="store_true",
        help="Enable stochastic sampling (z_p = m_p + noise * noise_scale). "
        "Recommended for WavLM-trained models to avoid mechanical artifacts.",
    )
    parser.add_argument(
        "--use-ema",
        action="store_true",
        default=True,
        help="Apply EMA weights to decoder if available in checkpoint (default: enabled)",
    )
    parser.add_argument(
        "--no-ema",
        action="store_true",
        help="Disable EMA weight application",
    )
    args = parser.parse_args()

    if args.no_ema:
        args.use_ema = False

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
    num_languages = getattr(model_g, "n_languages", 1)

    # Enable ONNX export mode for deterministic output
    model_g.onnx_export_mode = True
    # Propagate to Duration Predictor (StochasticDurationPredictor)
    if hasattr(model_g, "dp"):
        model_g.dp.onnx_export_mode = True

    # Inference only
    model_g.eval()

    with torch.no_grad():
        model_g.dec.remove_weight_norm()

    # Apply EMA weights to decoder if available
    if args.use_ema:
        ckpt = torch.load(args.checkpoint, map_location="cpu")
        ema_state = ckpt.get("ema_generator_state")
        if ema_state and "shadow_params" in ema_state:
            applied = 0
            dec_params = dict(model_g.dec.named_parameters())
            for name, shadow_param in ema_state["shadow_params"].items():
                if name in dec_params:
                    dec_params[name].data.copy_(shadow_param)
                    applied += 1
            if applied > 0:
                _LOGGER.info("Applied EMA weights to decoder: %d parameters", applied)
            else:
                _LOGGER.warning("EMA state found but no matching decoder parameters")
        else:
            _LOGGER.info("No EMA state found in checkpoint, skipping EMA")
        del ckpt

    # Check if model uses prosody features
    has_prosody = getattr(model_g, "prosody_dim", 0) > 0

    stochastic = args.stochastic

    def infer_forward(
        text, text_lengths, scales, sid=None, lid=None, prosody_features=None
    ):
        """
        Efficient forward function that returns both audio and duration information.
        The duration predictor is called once to compute both durations and audio output.
        """
        # noise_scale = scales[0]  # unused in ONNX export (deterministic mode)
        length_scale = scales[1]
        noise_scale_w = scales[2]

        # 1. Encoder
        x, m_p, logs_p, x_mask = model_g.enc_p(text, text_lengths)

        g = model_g._get_global_conditioning(sid, lid)

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

        # 5. Sample z_p
        if stochastic:
            noise_scale = scales[0]
            z_p = m_p + torch.randn_like(m_p) * torch.exp(logs_p) * noise_scale
        else:
            z_p = m_p

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

    lid: torch.LongTensor | None = None
    if num_languages > 1:
        lid = torch.LongTensor([0])

    # noise, noise_w, length
    scales = torch.FloatTensor([0.667, 1.0, 0.8])

    # Prosody features [batch, phonemes, 3] - A1/A2/A3 values
    # Use int64 (long) so that .float() in models.py creates explicit Cast node in ONNX graph
    prosody_features: torch.Tensor | None = None
    if has_prosody:
        prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    # Build dummy input tuple dynamically
    dummy_input_list: list = [sequences, sequence_lengths, scales]
    if num_speakers > 1:
        dummy_input_list.append(sid)
    if num_languages > 1:
        dummy_input_list.append(lid)
    if has_prosody:
        dummy_input_list.append(prosody_features)
    dummy_input = tuple(dummy_input_list)

    # Export - always include durations output
    output_names = ["output", "durations"]
    dynamic_axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "output": {0: "batch_size", 1: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }

    # Configure input names based on model type
    input_names = ["input", "input_lengths", "scales"]
    if num_speakers > 1:
        input_names.append("sid")
        dynamic_axes["sid"] = {0: "batch_size"}
    if num_languages > 1:
        input_names.append("lid")
        dynamic_axes["lid"] = {0: "batch_size"}

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
        dynamo=False,
    )

    mode = "stochastic" if args.stochastic else "deterministic"
    _LOGGER.info(
        "Exported model to %s (mode: %s, ema: %s)", args.output, mode, args.use_ema
    )

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
