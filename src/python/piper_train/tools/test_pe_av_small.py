"""Phase 0 PoC: facebook/pe-av-small 動作確認スクリプト.

Style Vector Conditioning + PE-A Emotion Loss 機能の前提調査。
`facebook/pe-av-small` (arxiv:2512.19687) が HuggingFace Hub から
`transformers.AutoModel.from_pretrained` 経由でロード可能かを検証する。

See:
    - docs/research/implementation-plan/tickets/phase-0/P0-T01.md
    - docs/research/implementation-plan/phase-0-1.md §Phase 0
"""

import logging

import torch
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    _LOGGER.info("=== Phase 0 PoC: facebook/pe-av-small (loading only) ===")
    test_loading()
    _LOGGER.info("=== Loading test complete ===")
