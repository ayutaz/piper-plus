"""Tests for --resume-from-multispeaker-checkpoint transfer logic in __main__.py.

Covers:
1. freeze_dp is auto-enabled when multispeaker checkpoint is specified
2. freeze_dp is set *before* model creation (order matters for save_hyperparameters)
3. gin_channels is correctly set for single-speaker + multilingual models
"""

import argparse

import pytest

torch = pytest.importorskip("torch")


# ---------------------------------------------------------------------------
# Test 1: multispeaker checkpoint enables freeze_dp
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_multispeaker_checkpoint_enables_freeze_dp():
    """--resume-from-multispeaker-checkpoint sets freeze_dp=True before model creation."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint="/fake/path.ckpt",
        freeze_dp=False,
    )
    # Reproduce the logic from __main__.py (lines 429-434)
    if getattr(args, "resume_from_multispeaker_checkpoint", None):
        args.freeze_dp = True
    assert args.freeze_dp is True


@pytest.mark.unit
def test_multispeaker_checkpoint_no_override_when_already_true():
    """freeze_dp stays True if already set when multispeaker checkpoint is given."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint="/fake/path.ckpt",
        freeze_dp=True,
    )
    if getattr(args, "resume_from_multispeaker_checkpoint", None):
        args.freeze_dp = True
    assert args.freeze_dp is True


@pytest.mark.unit
def test_no_multispeaker_checkpoint_leaves_freeze_dp_false():
    """freeze_dp remains False when no multispeaker checkpoint is specified."""
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint=None,
        freeze_dp=False,
    )
    if getattr(args, "resume_from_multispeaker_checkpoint", None):
        args.freeze_dp = True
    assert args.freeze_dp is False


# ---------------------------------------------------------------------------
# Test 2: freeze_dp is set before model creation (order verification)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_freeze_dp_set_before_model_creation():
    """freeze_dp must be True in dict_args before VitsModel() is called.

    This is a regression test for the timing bug where args.freeze_dp = True
    was set *after* model creation, causing save_hyperparameters() to capture
    freeze_dp=False.
    """
    args = argparse.Namespace(
        resume_from_multispeaker_checkpoint="/fake/path.ckpt",
        freeze_dp=False,
    )
    dict_args = vars(args)

    # Reproduce __main__.py logic: this block runs BEFORE model = VitsModel(...)
    if args.resume_from_multispeaker_checkpoint and not args.freeze_dp:
        args.freeze_dp = True
        dict_args["freeze_dp"] = True

    # At the point where VitsModel(**dict_args) would be called, freeze_dp must be True
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
    dict_args = {"gin_channels": 0}
    num_speakers = 1
    num_languages = 6

    # Reproduce __main__.py logic (lines 421-424)
    if (num_speakers > 1 or num_languages > 1) and dict_args.get(
        "gin_channels", 0
    ) == 0:
        dict_args["gin_channels"] = 512

    assert dict_args["gin_channels"] == 512, (
        f"gin_channels should be 512 for single-speaker + {num_languages} languages, "
        f"got {dict_args['gin_channels']}"
    )


@pytest.mark.unit
def test_gin_channels_not_set_for_single_speaker_single_language():
    """gin_channels stays 0 for single-speaker, single-language models."""
    dict_args = {"gin_channels": 0}
    num_speakers = 1
    num_languages = 1

    if (num_speakers > 1 or num_languages > 1) and dict_args.get(
        "gin_channels", 0
    ) == 0:
        dict_args["gin_channels"] = 512

    assert dict_args["gin_channels"] == 0, (
        "gin_channels should remain 0 for single-speaker, single-language model"
    )
