"""Tests for --keep-emb-g (frozen emb_g retention during multispeaker transfer).

When fine-tuning a multispeaker model to a single speaker, --keep-emb-g
retains the original emb_g embedding layer (frozen) so that global
conditioning via speaker embedding is preserved in the fine-tuned model.
Without it, single-speaker models drop emb_g entirely.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_model(
    num_speakers=1,
    num_languages=2,
    keep_emb_g=False,
    freeze_dp=False,
    gin_channels=0,
):
    """Create a minimal VitsModel with keep_emb_g setting."""
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    model = VitsModel(
        num_symbols=97,
        num_speakers=num_speakers,
        num_languages=num_languages,
        dataset=None,
        batch_size=4,
        learning_rate=2e-5,
        freeze_dp=freeze_dp,
        keep_emb_g=keep_emb_g,
        gin_channels=gin_channels,
        use_wavlm_discriminator=False,
    )
    return model


@pytest.mark.unit
def test_keep_emb_g_creates_emb_g():
    """When keep_emb_g=True and num_speakers >= 2, model should have emb_g layer.

    The emb_g embedding is created by SynthesizerTrn when n_speakers > 1.
    With keep_emb_g=True during transfer, this layer should be retained
    even though the fine-tune target may be single-speaker.
    """
    model = _make_model(num_speakers=2, keep_emb_g=True)
    assert hasattr(model.model_g, "emb_g"), (
        "Model with num_speakers >= 2 and keep_emb_g=True should have emb_g"
    )
    assert model.model_g.emb_g is not None, (
        "emb_g should not be None when num_speakers >= 2"
    )


@pytest.mark.unit
@pytest.mark.xfail(
    reason="keep_emb_g freezing not yet wired in configure_optimizers()",
    strict=True,
)
def test_keep_emb_g_frozen():
    """emb_g.weight.requires_grad should be False after transfer with keep_emb_g.

    When keep_emb_g is set, the embedding weights should be frozen to prevent
    the pretrained speaker embeddings from drifting during fine-tuning.
    """
    model = _make_model(num_speakers=5, keep_emb_g=True)
    # Trigger configure_optimizers to apply freezing logic
    model.configure_optimizers()

    assert hasattr(model.model_g, "emb_g"), "Model should have emb_g layer"
    assert not model.model_g.emb_g.weight.requires_grad, (
        "emb_g.weight.requires_grad should be False when keep_emb_g=True "
        "(frozen to preserve pretrained speaker embeddings)"
    )


@pytest.mark.unit
def test_keep_emb_g_conditioning():
    """_get_global_conditioning should return non-None g when n_speakers >= 2.

    Even with frozen emb_g, the model should still produce a global
    conditioning vector from the speaker embedding for downstream modules.
    """
    model = _make_model(num_speakers=5, num_languages=2, keep_emb_g=True)

    sid = torch.LongTensor([0])
    lid = torch.LongTensor([0])
    g = model.model_g._get_global_conditioning(sid=sid, lid=lid)

    assert g is not None, (
        "_get_global_conditioning should return non-None g when n_speakers >= 2"
    )
    # g shape: [batch, gin_channels, 1]
    assert g.dim() == 3, f"g should be 3-dimensional, got {g.dim()}"
    assert g.shape[0] == 1, f"Batch dim should be 1, got {g.shape[0]}"
    assert g.shape[2] == 1, f"Last dim should be 1, got {g.shape[2]}"


@pytest.mark.unit
def test_no_keep_emb_g_fallback():
    """Without keep_emb_g, single-speaker model should have no emb_g (old behavior).

    This verifies backward compatibility: when keep_emb_g is False (default),
    a single-speaker model with num_languages > 1 relies solely on emb_lang
    for global conditioning, and emb_g is not created.
    """
    model = _make_model(
        num_speakers=1,
        num_languages=2,
        keep_emb_g=False,
    )

    has_emb_g = hasattr(model.model_g, "emb_g")
    if has_emb_g:
        # SynthesizerTrn only creates emb_g when n_speakers > 1
        # For single-speaker, emb_g should not exist
        pytest.fail(
            "Single-speaker model without keep_emb_g should not have emb_g"
        )
