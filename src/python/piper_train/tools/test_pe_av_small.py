"""Phase 0 PoC: facebook/pe-av-small 動作確認スクリプト.

Style Vector Conditioning + PE-A Emotion Loss 機能の前提調査。
`facebook/pe-av-small` (arxiv:2512.19687) が HuggingFace Hub から
`transformers.AutoModel.from_pretrained` 経由でロード可能かを検証する。

See:
    - docs/research/implementation-plan/tickets/phase-0/P0-T01.md
    - docs/research/implementation-plan/tickets/phase-0/P0-T02.md
    - docs/research/implementation-plan/phase-0-1.md §Phase 0
"""

import logging

import torch
import torch.nn.functional as F
import transformers
from transformers import AutoModel

_LOGGER = logging.getLogger(__name__)


def test_loading() -> torch.nn.Module:
    """Load facebook/pe-av-small via AutoModel.from_pretrained.

    Returns:
        The loaded model instance (for reuse in test_inference / benchmark).

    Raises:
        Exception: on any loading failure. The exception is logged with a
            fallback guidance pointing to facebookresearch/perception_models
            (Option B, see phase-0-1.md §0.2).
    """
    _LOGGER.info(
        "env: transformers=%s, torch=%s",
        transformers.__version__,
        torch.__version__,
    )
    _LOGGER.info("Loading facebook/pe-av-small from HF Hub...")
    try:
        model = AutoModel.from_pretrained(
            "facebook/pe-av-small",
            trust_remote_code=True,
        )
    except Exception:
        _LOGGER.exception("AutoModel.from_pretrained failed")
        _LOGGER.error(
            "Fallback (Option B): clone https://github.com/facebookresearch/perception_models"
            " and import PE-AV class directly. See phase-0-1.md §0.2."
        )
        raise

    cls_name = type(model).__name__
    _LOGGER.info("Model class: %s", cls_name)
    config = getattr(model, "config", None)
    _LOGGER.info("config class: %s", type(config).__name__ if config is not None else "<none>")

    candidate_methods = [
        m for m in dir(model) if m.startswith(("get_", "encode_", "extract_"))
    ]
    _LOGGER.info("Candidate API methods: %s", candidate_methods)
    _LOGGER.info("has get_audio_embeds: %s", hasattr(model, "get_audio_embeds"))
    return model


def _invoke_model(model: torch.nn.Module, audio: torch.Tensor) -> tuple[torch.Tensor, str]:
    """Run inference with either `get_audio_embeds()` or `forward()`.

    Args:
        model: Loaded PE-A model.
        audio: Audio tensor. Shape is decided by the caller (2D or 3D).

    Returns:
        Tuple of (embedding tensor, method name used).
    """
    with torch.no_grad():
        if hasattr(model, "get_audio_embeds"):
            embeddings = model.get_audio_embeds(audio)
            return embeddings, "get_audio_embeds"
        _LOGGER.info("get_audio_embeds() not found, trying forward()...")
        output = model(audio)
        if isinstance(output, dict):
            embeddings = output.get("audio_embeds") or output.get("embeddings")
            if embeddings is None:
                raise RuntimeError(
                    f"forward() returned a dict without 'audio_embeds'/'embeddings' keys: "
                    f"{list(output.keys())}"
                )
        else:
            embeddings = output
        return embeddings, "forward"


def test_inference(model: torch.nn.Module) -> torch.Tensor:
    """Run inference with dummy 16 kHz audio and report embedding shape.

    Tries both 2D (``[B, T]``) and 3D (``[B, 1, T]``) input shapes to
    determine which one the model accepts. Logs embedding dimension, L2
    norm before/after normalization, and whether the model already
    outputs unit vectors.

    Args:
        model: Loaded PE-A model instance (from ``test_loading``).

    Returns:
        The embedding tensor (post-inference, pre-normalization).

    Raises:
        RuntimeError: if neither 2D nor 3D input shape produces a valid
            embedding output.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _LOGGER.info("Using device: %s", device)
    model = model.to(device).eval()

    sample_rate = 16000
    duration_s = 3
    num_samples = sample_rate * duration_s

    shapes_to_try = [
        ("2D [B, T]", (1, num_samples)),
        ("3D [B, 1, T]", (1, 1, num_samples)),
    ]

    last_error: Exception | None = None
    for shape_label, shape in shapes_to_try:
        audio = torch.randn(*shape, dtype=torch.float32, device=device)
        _LOGGER.info("Trying input shape %s: %s", shape_label, tuple(audio.shape))
        try:
            embeddings, method = _invoke_model(model, audio)
        except Exception as exc:
            _LOGGER.warning("Shape %s failed: %s", shape_label, exc)
            last_error = exc
            continue

        _LOGGER.info("Method used: %s (shape=%s)", method, shape_label)
        _LOGGER.info("Embedding tensor shape: %s", tuple(embeddings.shape))
        _LOGGER.info("Embedding dim (last axis): %d", embeddings.size(-1))

        flat = embeddings.view(embeddings.size(0), -1)
        norm_before = torch.norm(flat, dim=-1).mean().item()
        _LOGGER.info("Mean L2 norm (before normalize): %.4f", norm_before)

        flat_norm = F.normalize(flat, dim=-1)
        norm_after = torch.norm(flat_norm, dim=-1).mean().item()
        _LOGGER.info("Mean L2 norm (after normalize): %.4f", norm_after)

        if abs(norm_before - 1.0) < 1e-3:
            _LOGGER.info("Model output is already L2-normalized (norm ~1.0)")
        else:
            _LOGGER.info(
                "Model output is NOT L2-normalized; apply F.normalize() before style bank storage"
            )

        return embeddings

    raise RuntimeError(
        "All tried input shapes failed. Last error: %r" % (last_error,)
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    _LOGGER.info("=== Phase 0 PoC: facebook/pe-av-small (loading + inference) ===")
    model = test_loading()
    test_inference(model)
    _LOGGER.info("=== Inference test complete ===")
