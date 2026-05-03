"""PE-A (Perception Encoder - Audio) model and style bank loaders.

This module centralises the three loader utilities used by the PE-A emotion
perceptual loss in ``piper_train.vits.lightning``:

* :func:`load_pea_emotion_model` — load ``facebook/pe-av-small`` via
  ``transformers`` (preferred) or the ``perception_models`` package (fallback).
* :func:`load_style_bank` — read the ``.npz`` produced by
  ``build_pea_style_bank.py`` / validated by ``validate_style_bank.py``.
* :func:`grad_enabled_embedder_forward` — forward-wrapper that keeps the DAC
  encoder + bottleneck path differentiable so gradients flow back to ``y_hat``
  while PE-A weights stay frozen.

The .npz schema (matches ``piper_train.tools.build_pea_style_bank``)::

    emotion_names      : object (str)  [N]   — e.g. ["angry", "happy", ...]
    emotion_centroids  : float32        [N, D]   (L2-normalised rows)
    global_centroid    : float32        [D]     (raw mean, not re-normalised)

Note
----
The ``grad_enabled_embedder_forward`` signature mirrors the fork
(``yusuke-ai/piper-plus`` commit ``314b3355``, ``lightning.py:274-293``) so that
``types.MethodType``-binding to the Transformers embedder works unchanged. Call
sites bind it as an instance method (``embedder.forward = types.MethodType(
grad_enabled_embedder_forward, embedder)``).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch


_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PE-A model loader (two-candidate fallback)
# ---------------------------------------------------------------------------


_PEA_INSTALL_HINT = (
    "Could not load PE-A model %r. Tried:\n"
    "  1) transformers.AutoModel.from_pretrained(..., trust_remote_code=True)\n"
    "  2) perception_models (facebookresearch/perception_models)\n"
    "Fix with ONE of:\n"
    "  - uv sync --extra pea                         (recommended; pulls the\n"
    "    git dependency declared in pyproject.toml's [project.optional-dependencies])\n"
    "  - pip install 'transformers>=4.57'            (when PE-A auto-class lands upstream)\n"
    "  - pip install git+https://github.com/facebookresearch/perception_models.git\n"
    "Underlying errors:\n"
    "  transformers : %s\n"
    "  perception_models : %s\n"
)


def load_pea_emotion_model(
    model_name: str = "facebook/pe-av-small",
    device: torch.device | None = None,
) -> torch.nn.Module:
    """Load the PE-A audio encoder in ``eval()`` mode with all params frozen.

    Two candidate loaders are tried in order:

    1. ``transformers.AutoModel.from_pretrained(model_name,
       trust_remote_code=True)``. Known to fail today because the
       ``model_type=pe_audio_video`` auto-class is not yet upstreamed.
    2. ``perception_models`` (Meta's ``facebookresearch/perception_models`` pip
       package). If installed, ``PeAudioVideoModel.from_pretrained`` is used.

    If BOTH loaders fail a descriptive ``ImportError`` is raised with the
    install hints.

    Parameters
    ----------
    model_name:
        Either a HuggingFace repo id (default ``facebook/pe-av-small``) or a
        local path accepted by ``from_pretrained``.
    device:
        Optional torch device. When given, the model is moved to it.

    Returns
    -------
    torch.nn.Module
        Frozen model in ``eval()`` mode (``requires_grad=False`` on every
        parameter). DAC-encoder gradient control is applied separately via
        :func:`grad_enabled_embedder_forward` at call time.
    """

    transformers_err: Exception | None = None
    perception_models_err: Exception | None = None

    # --- Attempt 1: transformers.AutoModel (preferred, thin) ---
    try:
        from transformers import AutoModel  # type: ignore

        _LOGGER.info("Loading PE-A model via transformers.AutoModel: %s", model_name)
        model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
    except Exception as err:  # noqa: BLE001 — we re-raise below if both fail
        transformers_err = err
        _LOGGER.info("transformers.AutoModel failed for %s: %s", model_name, err)
        model = None  # type: ignore[assignment]

    # --- Attempt 2: perception_models (Meta's internal class) ---
    if model is None:
        try:
            # pylint: disable=import-outside-toplevel
            try:
                from transformers import PeAudioVideoModel  # type: ignore
            except ImportError:
                # Older fork path: the model class is exposed by perception_models
                from perception_models.apps.av import (  # type: ignore
                    PeAudioVideoModel,
                )

            _LOGGER.info("Loading PE-A model via PeAudioVideoModel: %s", model_name)
            model = PeAudioVideoModel.from_pretrained(model_name)
        except Exception as err:  # noqa: BLE001
            perception_models_err = err
            _LOGGER.info("PeAudioVideoModel loader failed for %s: %s", model_name, err)

    if model is None:
        raise ImportError(
            _PEA_INSTALL_HINT % (model_name, transformers_err, perception_models_err)
        )

    # Freeze the model — the perceptual loss keeps PE-A weights static while
    # letting gradients propagate back to ``y_hat`` through the embedder.
    model.eval()
    for param in model.parameters():
        param.requires_grad_(False)

    if device is not None:
        model = model.to(device)

    return model


# ---------------------------------------------------------------------------
# Style bank loader
# ---------------------------------------------------------------------------


def load_style_bank(
    path: Path | str,
) -> tuple[list[str], torch.Tensor, torch.Tensor]:
    """Load a PE-A style bank ``.npz`` file.

    Parameters
    ----------
    path:
        Filesystem path to the ``.npz`` produced by
        ``piper_train.tools.build_pea_style_bank``.

    Returns
    -------
    tuple
        ``(emotion_names, emotion_centroids, global_centroid)`` where

        - ``emotion_names`` is a list of emotion labels (``list[str]``).
        - ``emotion_centroids`` is a ``FloatTensor`` of shape ``[N, D]``
          (NOT re-normalised here; callers apply ``F.normalize`` when
          registering the buffer).
        - ``global_centroid`` is a ``FloatTensor`` of shape ``[D]``.
    """

    bank_path = Path(path)
    bank = np.load(str(bank_path), allow_pickle=True)

    required_keys = ("emotion_names", "emotion_centroids", "global_centroid")
    missing = [k for k in required_keys if k not in bank.files]
    if missing:
        raise KeyError(
            f"Style bank {bank_path} is missing required keys: {missing}. "
            "Expected schema: emotion_names, emotion_centroids, global_centroid"
        )

    emotion_names = [str(name) for name in bank["emotion_names"].tolist()]
    emotion_centroids = torch.as_tensor(bank["emotion_centroids"], dtype=torch.float32)
    global_centroid = torch.as_tensor(bank["global_centroid"], dtype=torch.float32)

    _LOGGER.info(
        "Loaded style bank: path=%s, N=%d, D=%d",
        bank_path,
        emotion_centroids.shape[0],
        emotion_centroids.shape[1],
    )
    return emotion_names, emotion_centroids, global_centroid


# ---------------------------------------------------------------------------
# DAC gradient-control forward wrapper
# ---------------------------------------------------------------------------


def grad_enabled_embedder_forward(
    embedder_self,
    input_values: torch.Tensor,
    padding_mask: torch.Tensor | None = None,
):
    """Fork-compatible DAC embedder forward that keeps gradients flowing.

    The upstream Transformers PE-A embedder wraps the DAC encoder in a
    ``torch.no_grad()`` context (because DAC is a pretrained codec). For a
    *perceptual* loss we keep the PE-A weights frozen but gradients must still
    reach the generator output ``y_hat``. This wrapper re-implements the
    embedder's forward path with ``cudnn.flags(enabled=False)`` — required for
    the 1-D convolution paths in DAC to be backward-safe — and without the
    ``no_grad`` block.

    This mirrors the fork (``yusuke-ai/piper-plus`` commit ``314b3355``,
    ``lightning.py:274-293``). Call sites bind it onto the live embedder
    instance via ``types.MethodType``::

        import types
        from piper_train.perception.pea_loader import grad_enabled_embedder_forward
        embedder = pea_model.audio_model.audio_encoder.embedder
        embedder.forward = types.MethodType(grad_enabled_embedder_forward, embedder)

    Parameters
    ----------
    embedder_self:
        The embedder instance (``audio_model.audio_encoder.embedder``). Bound by
        ``types.MethodType`` so this is conceptually ``self``.
    input_values:
        Float audio waveform ``[B, T]`` at PE-A's expected sample rate.
    padding_mask:
        Optional per-sample padding mask; sub-sampled to DAC's hop length.

    Returns
    -------
    tuple
        ``(inputs_embeds, padding_mask)``.
    """

    with torch.backends.cudnn.flags(enabled=False):
        hidden_states = embedder_self.dac_encoder(input_values)
        hidden_states = embedder_self.bottleneck(hidden_states)

    codec_features = hidden_states.transpose(1, 2)
    inputs_embeds = embedder_self.data_proj(codec_features)
    if padding_mask is not None:
        padding_mask = padding_mask[:, :: embedder_self.config.dac_config.hop_length]
    return inputs_embeds, padding_mask


__all__ = [
    "load_pea_emotion_model",
    "load_style_bank",
    "grad_enabled_embedder_forward",
]
