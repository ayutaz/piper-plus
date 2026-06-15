"""Tests for scripts/check_expected_p50_ms_gate.py (AI-15 skeleton).

Pins the +/-10 % tolerance behaviour for ``[mb_istft_1d]`` and the strict
ceiling behaviour for the three new variants. Skipped until AI-12 lands
the metrics.json schema.
"""

from __future__ import annotations

import pytest

# TODO(AI-15): switch to real import after AI-12 finalises metrics.json:
# from scripts import check_expected_p50_ms_gate
pytestmark = pytest.mark.skip(reason="awaiting AI-15 implementation")


def test_mb_istft_1d_tolerance_10pct(tmp_path):
    """mb_istft_1d with rtf_p50_ms=29.6 passes; 29.8 fails.

    Contract: with the contract pinned at 27 ms and a +/-10 % envelope,
    measurements <= 29.7 must pass and measurements > 29.7 must fail
    with a clear drift message.

    TODO(AI-15): write a synthetic metrics.json with rtf_p50_ms=29.6
    and assert exit 0; rewrite with rtf_p50_ms=29.8 and assert exit 1.
    """
    # TODO(AI-15): wire tmp_path fixture + main(argv).
    raise NotImplementedError


def test_istftnet2_mb_strict_target(tmp_path):
    """istftnet2_mb_1d2d with rtf_p50_ms=18 passes; 19 fails.

    Contract: the new variants are bounded by a strict ceiling (no
    upward tolerance), so 18 ms (<= 18) passes and 19 ms fails.

    TODO(AI-15): write synthetic metrics.json + contract section with
    target=18; assert pass at 18, fail at 19.
    """
    # TODO(AI-15): wire fixture + assertion.
    raise NotImplementedError
