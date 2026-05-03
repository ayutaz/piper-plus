#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import pathlib
import platform
from pathlib import Path
from typing import TYPE_CHECKING

import torch

from .tools.convert_fp16 import convert_fp16
from .vits.lightning import VitsModel


if TYPE_CHECKING:
    from .vits.models import SynthesizerTrn


# Allow Path objects in checkpoints (PyTorch 2.6+ weights_only=True)
torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])

# Fix PosixPath instantiation error when loading Linux checkpoints on Windows
if platform.system() == "Windows":
    pathlib.PosixPath = pathlib.WindowsPath


_LOGGER = logging.getLogger("piper_train.export_onnx")

OPSET_VERSION = 15


def build_infer_forward(
    model: SynthesizerTrn,
    *,
    stochastic: bool = True,
) -> callable:
    """Build an inference-only forward function for ONNX export.

    The returned callable replaces ``model.forward`` before
    ``torch.onnx.export()`` so that the exported graph contains only
    the inference path (no discriminator, no training loss).

    This is a thin wrapper around :meth:`SynthesizerTrn.infer` that
    handles scale unpacking, ``onnx_export_mode`` management, and
    return-value transformation.

    Parameters
    ----------
    model : SynthesizerTrn
        The generator model (``model_g``). Must already have
        ``remove_weight_norm()`` applied on ``model.dec``.
    stochastic : bool
        If True, sample z_p with noise (production default).
        If False, use the mean (deterministic / debug).

    Returns
    -------
    callable
        A forward function with signature::

            infer_forward(text, text_lengths, scales,
                          sid=None, lid=None, prosody_features=None,
                          speaker_embedding=None,
                          speaker_embedding_mask=None)
            -> (audio: Tensor, durations: Tensor)
    """
    # Configure stochastic/deterministic mode ONCE at build time
    # (not inside forward, to avoid "state_dict changed during tracing" errors).
    # model.onnx_export_mode: controls noise injection (True = deterministic).
    # model.dp.onnx_export_mode: same for duration predictor.
    # model.dec.onnx_export_mode: makes the decoder return fullband only (always True for export).
    model.onnx_export_mode = not stochastic
    if hasattr(model, "dp"):
        model.dp.onnx_export_mode = not stochastic

    def infer_forward(
        text,
        text_lengths,
        scales,
        sid=None,
        lid=None,
        prosody_features=None,
        speaker_embedding=None,
        speaker_embedding_mask=None,
    ):
        noise_scale = scales[0]
        length_scale = scales[1]
        noise_scale_w = scales[2]

        # model.infer() uses onnx_export_mode to decide whether to add noise:
        #   onnx_export_mode=True  → z_p = m_p          (deterministic)
        #   onnx_export_mode=False → z_p = m_p + noise   (stochastic)
        # We set it here to match the stochastic flag, restoring the
        # onnx_export_mode is set globally via set_export_mode() before
        # torch.onnx.export(). Do NOT toggle it here — changing module
        # attributes inside the traced forward causes
        # "state_dict changed after running the tracer" errors.
        audio, _attn, _y_mask, _latents, durations = model.infer(
            text,
            text_lengths,
            sid=sid,
            lid=lid,
            noise_scale=noise_scale,
            length_scale=length_scale,
            noise_scale_w=noise_scale_w,
            prosody_features=prosody_features,
            speaker_embedding=speaker_embedding,
            speaker_embedding_mask=speaker_embedding_mask,
        )

        return audio, durations

    return infer_forward


def apply_ema_shadow_params(
    decoder: torch.nn.Module,
    shadow_params: dict,
) -> tuple[int, int]:
    """Apply pre-loaded EMA shadow parameters to the decoder module.

    This is the pure-logic function that copies shadow parameters into
    *decoder* **in-place** without any file I/O.  It can be unit-tested
    with in-memory dicts (no checkpoint files needed).

    IMPORTANT: This must be called BEFORE ``remove_weight_norm()``, because
    EMA shadow params use ``weight_g``/``weight_v`` keys. ``remove_weight_norm()``
    fuses them into a single ``weight`` tensor, making EMA keys unmatchable.

    Parameters
    ----------
    decoder : torch.nn.Module
        The decoder sub-module (``model_g.dec``) whose parameters will be
        overwritten with EMA shadow values.
    shadow_params : dict
        Mapping of parameter name → shadow tensor, typically from
        ``checkpoint["ema_generator_state"]["shadow_params"]``.

    Returns
    -------
    (applied, skipped) : tuple[int, int]
        Number of parameters applied and skipped.
    """
    applied = 0
    skipped = 0
    dec_params = dict(decoder.named_parameters())
    with torch.no_grad():
        for name, shadow_param in shadow_params.items():
            if name in dec_params:
                dec_params[name].copy_(shadow_param)
                applied += 1
            else:
                skipped += 1

    if applied > 0:
        _LOGGER.info(
            "Applied EMA weights to decoder: %d parameters (skipped %d)",
            applied,
            skipped,
        )
    else:
        _LOGGER.warning("EMA state found but no matching decoder parameters")

    return applied, skipped


def apply_ema_weights(
    decoder: torch.nn.Module,
    checkpoint_path: str | Path,
) -> tuple[int, int]:
    """High-level convenience: load checkpoint and apply EMA shadow weights.

    Loads the checkpoint, extracts ``ema_generator_state.shadow_params``,
    and delegates to :func:`apply_ema_shadow_params`.

    Parameters
    ----------
    decoder : torch.nn.Module
        The decoder sub-module (``model_g.dec``) whose parameters will be
        overwritten with EMA shadow values.
    checkpoint_path : str | Path
        Path to the ``.ckpt`` file containing ``ema_generator_state``.

    Returns
    -------
    (applied, skipped) : tuple[int, int]
        Number of parameters applied and skipped.
        ``(0, 0)`` if no EMA state was found in the checkpoint.
    """
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    ema_state = ckpt.get("ema_generator_state")

    if not ema_state or "shadow_params" not in ema_state:
        _LOGGER.info("No EMA state found in checkpoint, skipping EMA")
        del ckpt
        return 0, 0

    result = apply_ema_shadow_params(decoder, ema_state["shadow_params"])
    del ckpt
    return result


def should_unify_emb_lang(
    unify_flag: bool | None,
    num_speakers: int,
    num_languages: int,
) -> bool:
    """Determine whether emb_lang unification should be performed.

    Parameters
    ----------
    unify_flag : bool or None
        CLI flag value. None means auto-detect.
    num_speakers : int
        Number of speakers in the model.
    num_languages : int
        Number of languages in the model.

    Returns
    -------
    bool
        True if emb_lang should be unified.
    """
    if unify_flag is None:
        return (num_speakers <= 1) and (num_languages > 1)
    return unify_flag


def unify_emb_lang_weights(model_g, source: int = 0) -> None:
    """Copy emb_lang[source] to all other language embeddings.

    Parameters
    ----------
    model_g : SynthesizerTrn
        The generator model with emb_lang attribute.
    source : int
        Source language index to copy from.

    Raises
    ------
    ValueError
        If source is out of range.
    """
    num_languages = model_g.n_languages
    if source < 0 or source >= num_languages:
        raise ValueError(
            f"--unify-emb-lang-source must be 0..{num_languages - 1}, got {source}"
        )
    with torch.no_grad():
        emb_lang = model_g.emb_lang.weight  # [num_languages, gin_channels]
        source_emb = emb_lang[source].clone()
        for i in range(num_languages):
            if i != source:
                emb_lang[i].copy_(source_emb)
    _LOGGER.info(
        "Unified emb_lang: copied lang[%d] to all %d languages",
        source,
        num_languages,
    )


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


def set_export_mode(model: torch.nn.Module, mode: bool = True) -> None:
    """Set onnx_export_mode on all submodules that support it."""
    for m in model.modules():
        if hasattr(m, "onnx_export_mode"):
            m.onnx_export_mode = mode


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
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable stochastic sampling (z_p = m_p + noise * noise_scale). "
        "Default: enabled. Use --no-stochastic for deterministic (debugging用).",
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable FP16 conversion (default: FP16 enabled)",
    )
    parser.add_argument(
        "--unify-emb-lang",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Unify emb_lang embeddings for single-speaker multilingual models. "
        "Default: auto (enabled when num_speakers <= 1 and num_languages > 1). "
        "Use --no-unify-emb-lang to disable.",
    )
    parser.add_argument(
        "--unify-emb-lang-source",
        type=int,
        default=0,
        help="Source language index for emb_lang unification (default: 0).",
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
    num_languages = getattr(model_g, "n_languages", 1)

    # Enable ONNX export mode for all compatible modules.
    # This makes the decoder emit fullband-only output and applies other
    # ONNX-specific behaviors. The stochastic/deterministic override on
    # model and duration predictor is applied later by build_infer_forward.
    set_export_mode(model_g, True)
    _LOGGER.info("Export mode enabled (stochastic=%s)", args.stochastic)

    # Inference only
    model_g.eval()

    # Unify emb_lang embeddings for single-speaker multilingual models
    # Must be done BEFORE torch.onnx.export(); EMA does not affect emb_lang
    do_unify = should_unify_emb_lang(args.unify_emb_lang, num_speakers, num_languages)

    if do_unify and num_languages > 1:
        try:
            unify_emb_lang_weights(model_g, source=args.unify_emb_lang_source)
        except ValueError as e:
            parser.error(str(e))
    elif do_unify and num_languages <= 1:
        _LOGGER.info(
            "Skipping emb_lang unification: model has only %d language(s)",
            num_languages,
        )

    # Apply EMA weights to decoder if available (always applied when present)
    # IMPORTANT: EMA must be applied BEFORE remove_weight_norm(), because EMA shadow
    # params use weight_g/weight_v keys. remove_weight_norm() fuses them into a single
    # "weight" tensor, making EMA keys unmatchable.
    apply_ema_weights(model_g.dec, args.checkpoint)

    with torch.no_grad():
        model_g.dec.remove_weight_norm()

    # Check if model uses prosody features
    has_prosody = getattr(model_g, "prosody_dim", 0) > 0

    model_g.forward = build_infer_forward(model_g, stochastic=args.stochastic)

    dummy_input_length = 50
    sequences = torch.randint(
        low=0, high=num_symbols, size=(1, dummy_input_length), dtype=torch.long
    )
    sequence_lengths = torch.LongTensor([sequences.size(1)])

    # Determine which optional inputs to include.
    # These flags control BOTH dummy_input and input_names so they stay in sync.
    include_sid = num_speakers > 1 or num_languages > 1
    include_lid = num_languages > 1

    sid: torch.LongTensor | None = None
    if include_sid:
        # Multi-speaker: real speaker ID needed.
        # Single-speaker multilingual: sid=0 placeholder to maintain correct
        # positional argument order in infer_forward (sid before lid).
        sid = torch.LongTensor([0])

    lid: torch.LongTensor | None = None
    if include_lid:
        lid = torch.LongTensor([0])

    # noise, noise_w, length
    scales = torch.FloatTensor([0.667, 1.0, 0.8])

    # Prosody features [batch, phonemes, 3] - A1/A2/A3 values
    # Use int64 (long) so that .float() in models.py creates explicit Cast node in ONNX graph
    prosody_features: torch.Tensor | None = None
    if has_prosody:
        prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

    # Build dummy input tuple and input_names using the same flags
    dummy_input_list: list = [sequences, sequence_lengths, scales]
    input_names = ["input", "input_lengths", "scales"]
    dynamic_axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "output": {0: "batch_size", 2: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }

    if include_sid:
        dummy_input_list.append(sid)
        input_names.append("sid")
        dynamic_axes["sid"] = {0: "batch_size"}
    if include_lid:
        dummy_input_list.append(lid)
        input_names.append("lid")
        dynamic_axes["lid"] = {0: "batch_size"}
    if has_prosody:
        dummy_input_list.append(prosody_features)
        input_names.append("prosody_features")
        dynamic_axes["prosody_features"] = {0: "batch_size", 1: "phonemes"}
        _LOGGER.info(
            "Exporting model with prosody features support (prosody_dim=%d)",
            model_g.prosody_dim,
        )

    # Speaker embedding inputs (voice cloning support)
    # Always include these optional inputs so the ONNX graph supports
    # both sid-based and speaker-embedding-based inference.
    speaker_emb_dim = 256  # ECAPA-TDNN default output dimension
    dummy_speaker_embedding = torch.zeros(1, speaker_emb_dim, dtype=torch.float32)
    dummy_speaker_embedding_mask = torch.ones(1, 1, dtype=torch.int64)

    dummy_input_list.append(dummy_speaker_embedding)
    input_names.append("speaker_embedding")
    # axis 1 (emb_dim=256) is fixed at export time by spk_proj weights
    dynamic_axes["speaker_embedding"] = {0: "batch_size"}

    dummy_input_list.append(dummy_speaker_embedding_mask)
    input_names.append("speaker_embedding_mask")
    dynamic_axes["speaker_embedding_mask"] = {0: "batch_size"}

    _LOGGER.info(
        "Exporting model with speaker_embedding support (emb_dim=%d)",
        speaker_emb_dim,
    )

    dummy_input = tuple(dummy_input_list)

    # Pre-run to trigger lazy module initialization (e.g. _ensure_spk_proj
    # creates nn.Linear on first forward). Without this, torch.jit.trace
    # detects state_dict changes and raises RuntimeError.
    with torch.no_grad():
        model_g(*dummy_input)

    # Export - always include durations output
    output_names = ["output", "durations"]

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
    _LOGGER.info("Exported model to %s (mode: %s)", args.output, mode)

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

    # Apply FP16 conversion (default: enabled)
    # Uses a temporary file for atomic replacement to avoid data corruption
    if not args.no_fp16:
        fp32_size = args.output.stat().st_size
        tmp_fp16 = args.output.with_suffix(".onnx.fp16_tmp")
        try:
            convert_fp16(args.output, tmp_fp16)
            tmp_fp16.replace(args.output)
        except Exception:
            tmp_fp16.unlink(missing_ok=True)
            raise
        fp16_size = args.output.stat().st_size
        reduction_pct = (
            ((fp32_size - fp16_size) / fp32_size) * 100 if fp32_size > 0 else 0
        )
        _LOGGER.info(
            "FP16 conversion: %.1f MB -> %.1f MB (%.1f%% reduction)",
            fp32_size / (1024 * 1024),
            fp16_size / (1024 * 1024),
            reduction_pct,
        )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
