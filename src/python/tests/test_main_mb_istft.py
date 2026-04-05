"""Tests for --mb-istft CLI flag parsing in piper_train.__main__.

Verifies that create_parser correctly handles --mb-istft, --c-sub-stft,
and that --mb-istft with --quality high is rejected.
"""

import subprocess
import sys

import pytest


# Minimal required args for create_parser().parse_args() to succeed
# (--dataset-dir and --batch-size are both required)
_BASE_ARGS = ["--dataset-dir", "/tmp/test", "--batch-size", "4"]


@pytest.mark.unit
def test_cli_mb_istft_flag_parsed():
    """--mb-istft sets args.mb_istft to True."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args([*_BASE_ARGS, "--mb-istft"])
    assert args.mb_istft is True


@pytest.mark.unit
def test_cli_mb_istft_default_false():
    """mb_istft defaults to False when not specified."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(_BASE_ARGS)
    assert args.mb_istft is False


@pytest.mark.unit
def test_cli_c_sub_stft_default():
    """--c-sub-stft defaults to 1.0."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(_BASE_ARGS)
    assert args.c_sub_stft == 1.0


@pytest.mark.unit
def test_cli_mb_istft_with_quality_high_errors():
    """--mb-istft combined with --quality high must fail."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "piper_train",
            "--dataset-dir",
            "/tmp/test",
            "--batch-size",
            "4",
            "--mb-istft",
            "--quality",
            "high",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "not supported" in result.stderr.lower() or "error" in result.stderr.lower()


@pytest.mark.unit
def test_cli_c_sub_stft_custom_value():
    """--c-sub-stft accepts custom float value."""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(
        ["--dataset-dir", "/tmp/test", "--batch-size", "4", "--c-sub-stft", "2.5"]
    )
    assert args.c_sub_stft == 2.5
