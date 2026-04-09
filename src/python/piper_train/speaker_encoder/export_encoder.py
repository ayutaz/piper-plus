"""Speaker Encoder ONNX Export.

Exports the ECAPA-TDNN speaker encoder from a PyTorch checkpoint to ONNX
format with dynamic batch and time axes.

Usage:
    uv run python -m piper_train.speaker_encoder.export_encoder \\
        --checkpoint speaker_encoder.ckpt \\
        --output speaker_encoder.onnx

    # With FP16 conversion (default)
    uv run python -m piper_train.speaker_encoder.export_encoder \\
        --checkpoint speaker_encoder.ckpt \\
        --output speaker_encoder.onnx \\
        --fp16

    # Without FP16 conversion
    uv run python -m piper_train.speaker_encoder.export_encoder \\
        --checkpoint speaker_encoder.ckpt \\
        --output speaker_encoder.onnx \\
        --no-fp16
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import torch


_LOGGER = logging.getLogger("piper_train.speaker_encoder.export_encoder")

OPSET_VERSION = 17


def export_speaker_encoder(
    checkpoint_path: Path,
    output_path: Path,
    *,
    fp16: bool = True,
    opset_version: int = OPSET_VERSION,
) -> None:
    """Export ECAPA-TDNN speaker encoder to ONNX.

    Args:
        checkpoint_path: Path to PyTorch checkpoint.
        output_path: Path for the output ONNX file.
        fp16: Whether to apply FP16 conversion (default: True).
        opset_version: ONNX opset version (default: 17).
    """
    from .ecapa_tdnn import ECAPATDNN  # noqa: PLC0415
    from .encoder import _infer_hparams  # noqa: PLC0415

    _LOGGER.info("Loading checkpoint: %s", checkpoint_path)

    # Load checkpoint
    ckpt = torch.load(str(checkpoint_path), map_location="cpu", weights_only=True)

    if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
        state_dict = ckpt["model_state_dict"]
    elif isinstance(ckpt, dict) and all(isinstance(k, str) for k in ckpt.keys()):
        state_dict = ckpt
    else:
        raise ValueError(
            "Checkpoint format not recognised. Expected a state_dict or a "
            "dict with 'model_state_dict' key."
        )

    hparams = _infer_hparams(state_dict)
    model = ECAPATDNN(**hparams)
    model.load_state_dict(state_dict)
    model.eval()

    _LOGGER.info(
        "Model loaded: input_dim=%d, channels=%d, emb_dim=%d",
        model.input_dim,
        model.channels,
        model.emb_dim,
    )

    # Dummy input: (batch=1, n_mels=80, time=200)
    dummy_mel = torch.randn(1, model.input_dim, 200)

    # Export
    output_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        (dummy_mel,),
        str(output_path),
        verbose=False,
        opset_version=opset_version,
        input_names=["mel"],
        output_names=["embedding"],
        dynamic_axes={
            "mel": {0: "batch_size", 2: "time"},
            "embedding": {0: "batch_size"},
        },
        dynamo=False,
    )

    _LOGGER.info("Exported ONNX model to %s (opset %d)", output_path, opset_version)

    # Verify the ONNX model
    _verify_onnx(output_path, model, dummy_mel)

    # FP16 conversion
    if fp16:
        _apply_fp16(output_path)

    file_size = output_path.stat().st_size
    _LOGGER.info(
        "Final model size: %.2f MB (%s)",
        file_size / (1024 * 1024),
        "FP16" if fp16 else "FP32",
    )


def _verify_onnx(
    onnx_path: Path, torch_model: torch.nn.Module, dummy_mel: torch.Tensor
) -> None:
    """Verify ONNX model produces outputs matching PyTorch.

    Args:
        onnx_path: Path to ONNX model.
        torch_model: Original PyTorch model.
        dummy_mel: Dummy input used during export.
    """
    try:
        import onnxruntime  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning("onnxruntime not available; skipping ONNX verification")
        return

    import numpy as np  # noqa: PLC0415

    session = onnxruntime.InferenceSession(str(onnx_path))
    onnx_result = session.run(
        ["embedding"],
        {"mel": dummy_mel.numpy()},
    )[0]

    with torch.no_grad():
        torch_result = torch_model(dummy_mel).numpy()

    max_diff = np.abs(onnx_result - torch_result).max()
    _LOGGER.info(
        "ONNX verification: max absolute difference = %.2e (shape: %s)",
        max_diff,
        onnx_result.shape,
    )

    if max_diff > 1e-4:
        _LOGGER.warning(
            "ONNX verification: difference (%.2e) exceeds tolerance (1e-4). "
            "The exported model may have numerical issues.",
            max_diff,
        )


def _apply_fp16(onnx_path: Path) -> None:
    """Apply FP16 conversion to the ONNX model.

    Uses the project's convert_fp16 utility for VITS-compatible conversion
    that preserves numerically sensitive operators in FP32.

    Args:
        onnx_path: Path to ONNX model (modified in-place).
    """
    fp32_size = onnx_path.stat().st_size
    tmp_fp16 = onnx_path.with_suffix(".onnx.fp16_tmp")

    try:
        from ..tools.convert_fp16 import convert_fp16  # noqa: PLC0415

        convert_fp16(onnx_path, tmp_fp16)
        tmp_fp16.replace(onnx_path)
    except ImportError:
        _LOGGER.warning(
            "convert_fp16 not available; skipping FP16 conversion. "
            "The model will remain in FP32."
        )
        return
    except Exception:
        tmp_fp16.unlink(missing_ok=True)
        raise

    fp16_size = onnx_path.stat().st_size
    reduction_pct = ((fp32_size - fp16_size) / fp32_size) * 100 if fp32_size > 0 else 0
    _LOGGER.info(
        "FP16 conversion: %.2f MB -> %.2f MB (%.1f%% reduction)",
        fp32_size / (1024 * 1024),
        fp16_size / (1024 * 1024),
        reduction_pct,
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Export ECAPA-TDNN speaker encoder to ONNX",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Path to PyTorch checkpoint (.ckpt or .pt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the output ONNX model (.onnx)",
    )
    parser.add_argument(
        "--fp16",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply FP16 conversion (default: enabled). Use --no-fp16 to disable.",
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=OPSET_VERSION,
        help=f"ONNX opset version (default: {OPSET_VERSION})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    export_speaker_encoder(
        checkpoint_path=args.checkpoint,
        output_path=args.output,
        fp16=args.fp16,
        opset_version=args.opset,
    )


if __name__ == "__main__":
    main()
