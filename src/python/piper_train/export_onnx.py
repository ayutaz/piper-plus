#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path

import torch

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

    model = VitsModel.load_from_checkpoint(args.checkpoint, dataset=None)
    model_g = model.model_g

    num_symbols = model_g.n_vocab
    num_speakers = model_g.n_speakers

    # Inference only
    model_g.eval()

    with torch.no_grad():
        model_g.dec.remove_weight_norm()

    # old_forward = model_g.infer

    def infer_forward(text, text_lengths, scales, sid=None):
        noise_scale = scales[0]
        length_scale = scales[1]
        noise_scale_w = scales[2]
        audio = model_g.infer(
            text,
            text_lengths,
            noise_scale=noise_scale,
            length_scale=length_scale,
            noise_scale_w=noise_scale_w,
            sid=sid,
        )[0].unsqueeze(1)

        return audio

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
    dummy_input = (sequences, sequence_lengths, scales, sid)

    # Export
    torch.onnx.export(
        model=model_g,
        args=dummy_input,
        f=str(args.output),
        verbose=False,
        opset_version=OPSET_VERSION,
        input_names=["input", "input_lengths", "scales", "sid"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size", 1: "phonemes"},
            "input_lengths": {0: "batch_size"},
            "output": {0: "batch_size", 1: "time"},
        },
    )

    _LOGGER.info("Exported model to %s", args.output)

    # Apply ONNX simplification if requested
    if args.simplify:
        simplify_onnx_model(args.output)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
