"""Tests for --resume-from-multispeaker-checkpoint transfer logic in __main__.py.

Covers:
1. freeze_dp is auto-enabled when multispeaker checkpoint is specified
2. freeze_dp is set *before* model creation (order matters for save_hyperparameters)
3. gin_channels is correctly set for single-speaker + multilingual models

All tests call the extracted ``apply_transfer_defaults()`` function directly
instead of duplicating the production logic.
"""

import argparse

import pytest

torch = pytest.importorskip("torch")

from piper_train.__main__ import apply_transfer_defaults  # noqa: E402


# ---------------------------------------------------------------------------
# Test 1: multispeaker checkpoint enables freeze_dp
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_multispeaker_checkpoint_enables_freeze_dp():
    """--resume-from-multispeaker-checkpoint sets freeze_dp=True."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint="/fake/path.ckpt",
        freeze_dp=False,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=1, num_languages=1)
    assert args.freeze_dp is True


@pytest.mark.unit
def test_multispeaker_checkpoint_no_override_when_already_true():
    """freeze_dp stays True if already set."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint="/fake/path.ckpt",
        freeze_dp=True,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=1, num_languages=1)
    assert args.freeze_dp is True


@pytest.mark.unit
def test_no_multispeaker_checkpoint_leaves_freeze_dp_false():
    """freeze_dp remains False when no multispeaker checkpoint."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint=None,
        freeze_dp=False,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=1, num_languages=1)
    assert args.freeze_dp is False


# ---------------------------------------------------------------------------
# Test 2: freeze_dp is set before model creation (order verification)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_freeze_dp_set_before_model_creation():
    """freeze_dp must be True in both args and vars(args) after apply_transfer_defaults.

    This is a regression test for the timing bug where args.freeze_dp = True
    was set *after* model creation, causing save_hyperparameters() to capture
    freeze_dp=False.
    """
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint="/fake/path.ckpt",
        freeze_dp=False,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=1, num_languages=1)
    # At the point where VitsModel(**vars(args)) would be called, freeze_dp must be True
    dict_args = vars(args)
    assert dict_args["freeze_dp"] is True
    assert args.freeze_dp is True


# ---------------------------------------------------------------------------
# Test 3: gin_channels set for single-speaker + multilingual
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gin_channels_set_for_single_speaker_multilingual():
    """gin_channels auto-sets to 512 when num_speakers=1 but num_languages>1.

    Regression test for the bug where gin_channels condition only checked
    num_speakers > 1, ignoring multilingual single-speaker models.
    """
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint=None,
        freeze_dp=False,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=1, num_languages=6)
    assert vars(args)["gin_channels"] == 512


@pytest.mark.unit
def test_gin_channels_not_set_for_single_speaker_single_language():
    """gin_channels stays 0 for single-speaker, single-language models."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint=None,
        freeze_dp=False,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=1, num_languages=1)
    assert vars(args)["gin_channels"] == 0


@pytest.mark.unit
def test_gin_channels_auto_512_for_multispeaker():
    """gin_channels must auto-set to 512 when num_speakers > 1 and not explicitly set.

    Regression test for bug where argparse default value (0) in dict_args
    caused 'gin_channels not in dict_args' to always be False.
    """
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint=None,
        freeze_dp=False,
        gin_channels=0,
    )
    apply_transfer_defaults(args, num_speakers=80, num_languages=1)
    assert vars(args)["gin_channels"] == 512, (
        f"gin_channels should be 512 for 80 speakers, got {vars(args)['gin_channels']}"
    )


@pytest.mark.unit
def test_gin_channels_respects_explicit_value():
    """gin_channels should not be overridden when explicitly set."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint=None,
        freeze_dp=False,
        gin_channels=256,
    )
    apply_transfer_defaults(args, num_speakers=80, num_languages=1)
    assert vars(args)["gin_channels"] == 256, (
        "gin_channels should remain 256 when explicitly set"
    )
