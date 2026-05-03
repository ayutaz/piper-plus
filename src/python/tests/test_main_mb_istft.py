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
