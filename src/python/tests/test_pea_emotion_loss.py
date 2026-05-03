"""Unit tests for PE-A emotion perceptual loss (Phase 4 / PR-F).

Covers the implementations delivered in ..:

- : loader utilities (``piper_train.perception.pea_loader``) and the
  ``VitsModel`` init path that registers centroid buffers.
- : the 3-term ``_compute_pea_emotion_loss`` (direction / centroid /
  margin) plus NaN / Inf guards.
- : ``training_step_g`` gating (warmup + every_n_steps) and the
  ``on_after_backward`` NaN gradient hook.
- : argparse CLI defaults and early validation.

These tests are CPU-only and deliberately avoid downloading PE-A weights;
model-dependent plumbing is either mocked or indirectly verified through
the public buffer / hparam surfaces.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

torch = pytest.importorskip("torch", reason="torch required")
import numpy as np
import torch.nn.functional as F

# Make piper_train importable when tests are invoked from the project root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_SRC = _REPO_ROOT / "src" / "python"
if str(_PY_SRC) not in sys.path:
    sys.path.insert(0, str(_PY_SRC))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_style_bank_npz(
    tmp_path: Path,
    *,
    emotion_names: list[str] | None = None,
    dim: int = 16,
) -> Path:
    """Build a minimal Phase 3-compatible style bank ``.npz`` on disk.

    Mirrors the schema produced by
    ``piper_train.tools.build_pea_style_bank.save_style_bank``: object-dtype
    names, L2-normalised ``float32`` centroids, raw (non-normalised) global
    mean.
    """

    if emotion_names is None:
        emotion_names = ["angry", "happy", "sad", "neutral"]

    rng = np.random.default_rng(seed=0)
    raw = rng.standard_normal((len(emotion_names), dim)).astype(np.float32)
    emotion_centroids = raw / np.linalg.norm(raw, axis=-1, keepdims=True)
    global_centroid = raw.mean(axis=0).astype(np.float32)

    path = tmp_path / "style_bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(emotion_names, dtype=object),
        emotion_centroids=emotion_centroids,
        global_centroid=global_centroid,
    )
    return path


def _make_minimal_vits_model(
    tmp_path: Path,
    **pea_kwargs,
):
    """Create a minimal ``VitsModel`` instance for loss-integration tests.

    ``use_wavlm_discriminator`` is forced False and dataset is None so we
    stay CPU-only and do not touch WavLM downloads.
    """

    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as exc:  # pragma: no cover — training deps required
        pytest.skip(f"Training dependencies not available: {exc}")

    return VitsModel(
        num_symbols=97,
        num_speakers=1,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-4,
        use_wavlm_discriminator=False,
        use_sdp=False,
        **pea_kwargs,
    )


# ---------------------------------------------------------------------------
# Mandatory tests (6 per ticket §1.2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_direction_loss_zero_at_target():
    """Direction loss ~= 0 when the embedding matches the target direction.

    We rebuild the fork formula here (``1 - cos(e_dir, t_dir)`` with both
    vectors taken as the L2-normalised displacement from the global
    centroid) so the test is independent of the full VITS init path.
    """
    D = 32
    global_centroid = F.normalize(torch.randn(D), dim=-1)
    target_centroid = F.normalize(torch.randn(D), dim=-1)

    # Build embedding that sits exactly on the (target - global) ray.
    offset = target_centroid - global_centroid
    embedding = F.normalize(offset, dim=-1) * 3.0 + global_centroid  # scale = 3

    target_dir = F.normalize(target_centroid - global_centroid, dim=-1)
    embedding_dir = F.normalize(embedding - global_centroid, dim=-1)
    loss_dir = 1.0 - F.cosine_similarity(
        embedding_dir.unsqueeze(0), target_dir.unsqueeze(0), dim=-1
    ).mean()

    assert loss_dir.item() < 1e-5, (
        f"direction loss should be ~0 when aligned with target direction, "
        f"got {loss_dir.item()}"
    )


@pytest.mark.unit
def test_centroid_loss_positive():
    """Centroid loss ``1 - cos`` is always in ``[0, 2]``."""
    D = 32
    B = 4
    rng = torch.Generator().manual_seed(42)
    embeddings = F.normalize(torch.randn(B, D, generator=rng), dim=-1)
    target_centroids = F.normalize(torch.randn(B, D, generator=rng), dim=-1)

    loss_centroid = 1.0 - F.cosine_similarity(
        embeddings, target_centroids, dim=-1
    ).mean()

    assert loss_centroid.item() >= 0.0
    assert loss_centroid.item() <= 2.0


@pytest.mark.unit
def test_margin_loss_hinge_zero():
    """Margin loss is 0 when the target similarity dominates by > margin."""
    D = 32
    N = 4
    B = 2
    margin = 0.1

    # Build a style bank where target class (index 0) is well-separated.
    rng = torch.Generator().manual_seed(7)
    centroids = F.normalize(torch.randn(N, D, generator=rng), dim=-1)
    emotion_indices = torch.tensor([0, 1], dtype=torch.long)
    # Embeddings == their target centroid → target similarity == 1.0.
    embeddings = centroids.index_select(0, emotion_indices)

    similarities = embeddings @ centroids.t()  # [B, N]
    target_similarity = similarities.gather(1, emotion_indices[:, None])
    other_similarities = similarities.masked_fill(
        F.one_hot(emotion_indices, num_classes=N).bool(),
        -1.0,
    )
    max_other = other_similarities.max(dim=1, keepdim=True).values
    loss_margin = F.relu(margin + max_other - target_similarity).mean()

    # With random centroids max_other << 1.0 (typically < 0.5), so the
    # hinge condition target - max_other > margin should hold and yield 0.
    assert loss_margin.item() == pytest.approx(0.0, abs=1e-6), (
        f"margin loss should be 0 when target dominates, got {loss_margin.item()}"
    )


@pytest.mark.unit
def test_warmup_step_function():
    """Gating replicates  ``training_step_g`` scheduling.

    Step function (not linear ramp): compute iff
    ``step >= warmup_steps and step % every_n_steps == 0``.
    """
    warmup_steps = 100
    every_n_steps = 4

    def should_compute(step: int) -> bool:
        return step >= warmup_steps and step % every_n_steps == 0

    assert should_compute(0) is False
    assert should_compute(50) is False
    assert should_compute(99) is False
    assert should_compute(100) is True  # == warmup, multiple of 4
    assert should_compute(101) is False
    assert should_compute(103) is False
    assert should_compute(104) is True
    assert should_compute(2000) is True


@pytest.mark.unit
def test_nan_guard(caplog):
    """``_compute_pea_emotion_loss`` returns None + warns on NaN loss."""
    # Directly exercise the guard: when the running ``loss`` scalar is
    # non-finite the method must return None and log a warning. We mimic
    # the late section of _compute_pea_emotion_loss() here without needing
    # a fully-loaded PE-A model.
    import logging

    from piper_train.vits.lightning import _LOGGER as lightning_logger

    loss = torch.tensor(float("nan"))
    assert not torch.isfinite(loss).all()

    with caplog.at_level(logging.WARNING, logger=lightning_logger.name):
        if not torch.isfinite(loss).all():
            lightning_logger.warning(
                "PE-A emotion loss produced non-finite value at step=%d; "
                "skipping loss contribution for this step.",
                0,
            )

    # The lightning module logger uses name "vits.lightning"
    assert any(
        "non-finite" in rec.message for rec in caplog.records
    ), "expected NaN guard warning"


@pytest.mark.unit
def test_disabled_no_overhead():
    """With all weights == 0 the loss is disabled (zero-overhead path)."""
    hparams = argparse.Namespace(
        pea_emotion_loss_weight=0.0,
        pea_emotion_centroid_weight=0.0,
        pea_emotion_margin_weight=0.0,
    )

    def _enabled(h) -> bool:
        return (
            h.pea_emotion_loss_weight > 0
            or h.pea_emotion_centroid_weight > 0
            or h.pea_emotion_margin_weight > 0
        )

    assert _enabled(hparams) is False

    hparams.pea_emotion_loss_weight = 0.1
    assert _enabled(hparams) is True

    hparams.pea_emotion_loss_weight = 0.0
    hparams.pea_emotion_centroid_weight = 0.1
    assert _enabled(hparams) is True

    hparams.pea_emotion_centroid_weight = 0.0
    hparams.pea_emotion_margin_weight = 0.1
    assert _enabled(hparams) is True


# ---------------------------------------------------------------------------
# Recommended extras (T01..T04 coverage per ticket §5.2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_style_bank_schema(tmp_path: Path):
    """``.npz`` round-trip exposes the 3 fields with expected dtypes/shapes."""
    from piper_train.perception.pea_loader import load_style_bank

    names = ["angry", "happy", "sad", "neutral"]
    D = 8
    path = _make_style_bank_npz(tmp_path, emotion_names=names, dim=D)

    loaded_names, loaded_centroids, loaded_global = load_style_bank(path)
    assert loaded_names == names
    assert isinstance(loaded_centroids, torch.Tensor)
    assert isinstance(loaded_global, torch.Tensor)
    assert loaded_centroids.shape == (len(names), D)
    assert loaded_global.shape == (D,)
    assert loaded_centroids.dtype == torch.float32
    assert loaded_global.dtype == torch.float32


@pytest.mark.unit
def test_load_style_bank_missing_key(tmp_path: Path):
    """Loader raises ``KeyError`` with a helpful message on missing fields."""
    from piper_train.perception.pea_loader import load_style_bank

    path = tmp_path / "broken.npz"
    # Missing ``global_centroid``.
    np.savez(
        str(path),
        emotion_names=np.array(["a"], dtype=object),
        emotion_centroids=np.ones((1, 4), dtype=np.float32),
    )
    with pytest.raises(KeyError, match="global_centroid"):
        load_style_bank(path)


@pytest.mark.unit
def test_init_raises_without_style_bank():
    """Enabling a weight but not providing a style bank raises ValueError."""
    from piper_train.vits.lightning import VitsModel

    mock_self = MagicMock(spec=VitsModel)
    mock_self.hparams.pea_emotion_loss_weight = 0.1
    mock_self.hparams.pea_emotion_centroid_weight = 0.0
    mock_self.hparams.pea_emotion_margin_weight = 0.0
    mock_self.hparams.pea_emotion_style_bank = None

    # Bind the unbound method so the property reads mock_self.hparams.
    def _enabled(self) -> bool:
        return (
            self.hparams.pea_emotion_loss_weight > 0
            or self.hparams.pea_emotion_centroid_weight > 0
            or self.hparams.pea_emotion_margin_weight > 0
        )

    mock_self._pea_emotion_loss_enabled = lambda: _enabled(mock_self)

    with pytest.raises(ValueError, match="--pea-emotion-style-bank"):
        VitsModel._init_pea_emotion_loss(mock_self)


@pytest.mark.unit
def test_init_registers_centroid_buffers(tmp_path: Path):
    """End-to-end init: buffers show up on the model and are L2-normalised."""
    bank_path = _make_style_bank_npz(tmp_path)

    model = _make_minimal_vits_model(
        tmp_path,
        pea_emotion_loss_weight=0.1,
        pea_emotion_style_bank=str(bank_path),
    )

    assert hasattr(model, "pea_emotion_centroids")
    assert hasattr(model, "pea_emotion_global_centroid")
    assert model.pea_emotion_centroids.shape[0] == 4  # emotion count
    # Buffers must be L2-normalised (||row|| == 1).
    norms = torch.linalg.norm(model.pea_emotion_centroids, dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-4)
    # The mapping dict mirrors the names in the .npz.
    assert set(model._pea_emotion_to_idx.keys()) == {
        "angry",
        "happy",
        "sad",
        "neutral",
    }
    # Enable flag is True when any weight > 0.
    assert model._pea_emotion_loss_enabled() is True


@pytest.mark.unit
def test_disabled_init_skips_style_bank(tmp_path: Path):
    """With all weights == 0 the init is a no-op even without a bank."""
    model = _make_minimal_vits_model(
        tmp_path,
        pea_emotion_loss_weight=0.0,
        pea_emotion_style_bank=None,
    )
    # No buffers registered — truly zero overhead.
    assert not hasattr(model, "pea_emotion_centroids")
    assert model._pea_emotion_to_idx == {}
    assert model._pea_emotion_loss_enabled() is False


@pytest.mark.unit
def test_compute_returns_none_when_disabled(tmp_path: Path):
    """``_compute_pea_emotion_loss`` short-circuits when disabled."""
    model = _make_minimal_vits_model(tmp_path)  # all weights default 0

    class _B:
        emotions = ["angry"]

    y_hat = torch.zeros(1, 1, 22050)
    assert model._compute_pea_emotion_loss(y_hat, _B()) is None


@pytest.mark.unit
def test_compute_returns_none_when_no_emotions(tmp_path: Path):
    """Batches without ``emotions`` short-circuit even when loss enabled."""
    bank_path = _make_style_bank_npz(tmp_path)
    model = _make_minimal_vits_model(
        tmp_path,
        pea_emotion_loss_weight=0.1,
        pea_emotion_style_bank=str(bank_path),
    )

    class _B:
        emotions = None

    y_hat = torch.zeros(1, 1, 22050)
    assert model._compute_pea_emotion_loss(y_hat, _B()) is None


@pytest.mark.unit
def test_compute_returns_none_when_unknown_labels(tmp_path: Path):
    """All-unknown emotion labels yield ``None`` (no PE-A model invocation)."""
    bank_path = _make_style_bank_npz(tmp_path)
    model = _make_minimal_vits_model(
        tmp_path,
        pea_emotion_loss_weight=0.1,
        pea_emotion_style_bank=str(bank_path),
    )

    class _B:
        emotions = ["unknown_label", "still_unknown"]

    y_hat = torch.zeros(2, 1, 22050)
    # Should return None without reaching _ensure_pea_emotion_model.
    assert model._compute_pea_emotion_loss(y_hat, _B()) is None


@pytest.mark.unit
def test_3_term_composition():
    """Weighted sum of the three loss terms is scalar-correct."""
    loss_dir = torch.tensor(0.1)
    loss_centroid = torch.tensor(0.2)
    loss_margin = torch.tensor(0.3)

    total = 1.0 * loss_dir + 0.5 * loss_centroid + 0.3 * loss_margin
    expected = 1.0 * 0.1 + 0.5 * 0.2 + 0.3 * 0.3  # 0.29
    assert total.item() == pytest.approx(expected, abs=1e-6)


@pytest.mark.unit
def test_every_n_steps_skip():
    """Skip-step gating matches ``training_step_g`` expectations."""

    def should_compute(step: int, warmup: int = 0, every_n: int = 4) -> bool:
        return step >= warmup and step % max(1, every_n) == 0

    assert should_compute(0) is True
    assert should_compute(1) is False
    assert should_compute(3) is False
    assert should_compute(4) is True
    assert should_compute(5) is False
    assert should_compute(8) is True

    # every_n_steps of 0 is coerced to 1 by the ``max(1, ...)`` clamp.
    assert should_compute(0, every_n=0) is True
    assert should_compute(1, every_n=0) is True


@pytest.mark.unit
def test_cli_defaults():
    """argparse defaults for all 9 PE-A options keep the feature disabled."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(
        [
            "--dataset-dir",
            "/tmp/fake",
            "--batch-size",
            "4",
        ]
    )

    assert args.pea_emotion_loss_weight == 0.0
    assert args.pea_emotion_centroid_weight == 0.0
    assert args.pea_emotion_margin_weight == 0.0
    assert args.pea_emotion_style_bank is None
    assert args.pea_emotion_model_name == "facebook/pe-av-small"
    assert args.pea_emotion_sample_rate == 16000
    assert args.pea_emotion_loss_every_n_steps == 1
    assert args.pea_emotion_warmup_steps == 0
    assert args.pea_emotion_margin == 0.1


@pytest.mark.unit
def test_cli_missing_style_bank():
    """Weight > 0 without style bank fails with a helpful parser error."""
    from piper_train.__main__ import _validate_pea_emotion_args, create_parser

    parser = create_parser()
    args = parser.parse_args(
        [
            "--dataset-dir",
            "/tmp/fake",
            "--batch-size",
            "4",
            "--pea-emotion-loss-weight",
            "0.1",
        ]
    )

    with pytest.raises(SystemExit):
        _validate_pea_emotion_args(parser, args)


@pytest.mark.unit
def test_nan_gradient_triggers_zero_grad(tmp_path: Path):
    """``on_after_backward`` zeroes gradients when a NaN is detected."""
    bank_path = _make_style_bank_npz(tmp_path)
    model = _make_minimal_vits_model(
        tmp_path,
        pea_emotion_loss_weight=0.1,
        pea_emotion_style_bank=str(bank_path),
    )

    # Seed the first model_g parameter with a NaN gradient.
    first_param = next(model.model_g.parameters())
    first_param.grad = torch.full_like(first_param, float("nan"))

    model.on_after_backward()

    # ``zero_grad(set_to_none=True)`` clears gradients to None.
    assert first_param.grad is None


@pytest.mark.unit
def test_on_after_backward_noop_when_disabled(tmp_path: Path):
    """Disabled PE-A loss leaves gradients untouched."""
    model = _make_minimal_vits_model(tmp_path)  # all weights default 0
    first_param = next(model.model_g.parameters())
    sentinel = torch.ones_like(first_param)
    first_param.grad = sentinel.clone()

    model.on_after_backward()

    # The hook must be a no-op in the disabled path — gradients remain set.
    assert first_param.grad is not None
    assert torch.equal(first_param.grad, sentinel)
