"""Tests for MB-iSTFT-related CLI flag parsing in piper_train.__main__.

Verifies that --c-sub-stft is parsed correctly. The legacy --mb-istft
flag has been removed: MB-iSTFT is now the only decoder path.
"""

import pytest


pytest.importorskip("torch", reason="torch required for piper_train.__main__")


_BASE_ARGS = ["--dataset-dir", "/tmp/test", "--batch-size", "4"]


@pytest.mark.unit
def test_cli_c_sub_stft_default():
    """--c-sub-stft defaults to 1.0."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(_BASE_ARGS)
    assert args.c_sub_stft == 1.0


@pytest.mark.unit
def test_cli_c_sub_stft_custom_value():
    """--c-sub-stft accepts custom float value."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(
        ["--dataset-dir", "/tmp/test", "--batch-size", "4", "--c-sub-stft", "2.5"]
    )
    assert args.c_sub_stft == 2.5


@pytest.mark.unit
def test_cli_no_legacy_mb_istft_flag():
    """The legacy --mb-istft flag is no longer accepted."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([*_BASE_ARGS, "--mb-istft"])


# ----------------------------------------------------------------------
# AI-03: --decoder-type CLI flag (G-1.9 default-preservation gate)
# ----------------------------------------------------------------------


@pytest.mark.unit
def test_cli_decoder_type_default_and_choices(capsys):
    """``--decoder-type`` defaults to ``mb_istft_1d`` and validates choices.

    Pin for ``__main__.py`` L266-277. This is the user-facing G-1.9
    backward-compat gate: any change to the default or the accepted
    choices set silently changes every existing training command's
    behaviour, so it must be locked at the CLI surface.
    """
    from piper_train.__main__ import create_parser

    parser = create_parser()

    # Default path: omitting --decoder-type yields the legacy 1D backbone.
    args_default = parser.parse_args(_BASE_ARGS)
    assert args_default.decoder_type == "mb_istft_1d", (
        f"AI-03 G-1.9: default --decoder-type drifted to "
        f"{args_default.decoder_type!r} (expected 'mb_istft_1d')"
    )

    # Explicit new-decoder value survives parsing unchanged.
    args_new = parser.parse_args([*_BASE_ARGS, "--decoder-type", "istftnet2_mb_1d2d"])
    assert args_new.decoder_type == "istftnet2_mb_1d2d"

    # Bogus value: argparse choices reject with SystemExit (exit code 2).
    with pytest.raises(SystemExit):
        parser.parse_args([*_BASE_ARGS, "--decoder-type", "bogus"])

    # Stderr should mention the choices so users see valid options.
    err = capsys.readouterr().err
    assert "istftnet2_mb_1d2d" in err or "mb_istft_1d" in err, (
        f"argparse error did not mention the valid choices: {err!r}"
    )
