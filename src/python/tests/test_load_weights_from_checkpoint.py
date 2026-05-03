"""Tests for --load_weights_from_checkpoint (shape-aware partial load).

Covers:
- Loading compatible weights from an existing checkpoint while preserving
  freshly-initialised tensors (e.g. newly-added style_proj layer).
- Logging a warning for shape-mismatched tensors and skipping them.
- Strict-mode behaviour on missing keys.
"""

from __future__ import annotations

import logging

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_vits_model(**overrides):
    """Create a small VitsModel with WavLM disabled for unit tests."""
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    kwargs = dict(
        num_symbols=100,
        num_speakers=4,
        num_languages=2,
        sample_rate=22050,
        dataset=None,
        batch_size=2,
        learning_rate=2e-4,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.1,
        use_spectral_norm=False,
        gin_channels=128,
        use_sdp=True,
        segment_size=512,
        prosody_dim=0,
        use_wavlm_discriminator=False,
    )
    kwargs.update(overrides)
    return VitsModel(**kwargs)


@pytest.mark.unit
def test_shape_aware_partial_load(tmp_path, caplog):
    """既存チェックポイント (dim=0) から style_proj 付きモデル (dim=16) へロード.

    All common tensors should be restored; the newly introduced style_proj
    retains its zero-initialised state because the source checkpoint does
    not contain matching keys.
    """
    from piper_train.__main__ import load_checkpoint_weights

    torch.manual_seed(0)
    model_old = _make_vits_model(style_vector_dim=0, style_condition_mode="global")
    ckpt_path = tmp_path / "old.ckpt"
    torch.save({"state_dict": model_old.state_dict()}, ckpt_path)

    torch.manual_seed(1)
    model_new = _make_vits_model(
        style_vector_dim=16,
        style_condition_mode="global",
    )

    # style_proj is present in model_new but not in the old checkpoint.
    assert model_new.model_g.style_proj is not None
    style_proj_weight_before = (
        model_new.model_g.style_proj[-1].weight.detach().clone()
    )

    caplog.set_level(logging.INFO, logger="piper_train")
    load_checkpoint_weights(str(ckpt_path), model_new)

    # Common tensors should match the old checkpoint.
    old_sd = model_old.state_dict()
    for key, value in old_sd.items():
        loaded = model_new.state_dict()[key]
        assert torch.equal(loaded, value), f"Mismatch for key {key}"

    # style_proj remains zero-initialised (was not in the old checkpoint).
    style_proj_weight_after = model_new.model_g.style_proj[-1].weight
    assert torch.equal(style_proj_weight_before, style_proj_weight_after)
    assert torch.all(style_proj_weight_after == 0)


@pytest.mark.unit
def test_skip_mismatched_shape_logs_warning(tmp_path, caplog):
    """Shape 不一致テンソルはスキップ、warning ログ出力."""
    from piper_train.__main__ import load_checkpoint_weights

    # Saved checkpoint has a larger vocab size: emb shape mismatches.
    model_big = _make_vits_model(num_symbols=200)
    ckpt_path = tmp_path / "big.ckpt"
    torch.save({"state_dict": model_big.state_dict()}, ckpt_path)

    model_small = _make_vits_model(num_symbols=100)

    caplog.set_level(logging.WARNING, logger="piper_train")
    load_checkpoint_weights(str(ckpt_path), model_small)

    warning_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    # At least one warning mentions the mismatched embedding shape.
    assert any(
        "Skipped mismatched tensor" in msg and "model_g.enc_p.emb.weight" in msg
        for msg in warning_messages
    ), f"Expected mismatched-shape warning in logs, got: {warning_messages}"


@pytest.mark.unit
def test_strict_true_raises_on_missing(tmp_path):
    """strict=True のダイレクト load_state_dict では Missing / Unexpected key で RuntimeError.

    ``load_checkpoint_weights`` itself uses strict=True internally on the
    *filtered* state dict (which always matches keys), so we exercise the
    underlying contract directly.
    """
    model = _make_vits_model()
    sd = model.state_dict()
    # Remove a required key to force strict mode to fail.
    partial_sd = {k: v for k, v in sd.items() if not k.startswith("model_g.enc_p.")}
    with pytest.raises(RuntimeError, match="Missing key"):
        model.load_state_dict(partial_sd, strict=True)
