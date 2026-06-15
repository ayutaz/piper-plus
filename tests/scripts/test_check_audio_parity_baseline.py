"""Tests for scripts/check_audio_parity_baseline.py (AI-15 skeleton).

These tests pin the behavioural contract of the [mb_istft_1d] audio
parity baseline drift gate. They are skipped until the AI-15 ticket
moves out of skeleton state.
"""

from __future__ import annotations

import pytest

# TODO(AI-15): once the script is implemented, switch this import to
# ``from scripts import check_audio_parity_baseline``.
pytestmark = pytest.mark.skip(reason="awaiting AI-15 implementation")


def test_baseline_drift_detected(tmp_path, monkeypatch, capsys):
    """A mutated [mb_istft_1d] contract field must produce non-zero exit.

    Contract: when ``docs/spec/audio-parity-contract.toml`` and
    ``scripts/audio_parity_baseline.lock.json`` disagree on any of the
    PINNED_FIELDS, the script exits 1 with ``AI-15 baseline drift`` in
    stderr.

    TODO(AI-15): build tmp toml + lock fixtures, run main, assert
    exit_code == 1 and 'AI-15 baseline drift' in capsys.readouterr().err.
    """
    # TODO(AI-15): wire fixtures.
    raise NotImplementedError


def test_baseline_bump_with_trailer_accepted(tmp_path, monkeypatch, capsys):
    """``--update-baseline`` + trailer-bearing commit must succeed and rewrite.

    Contract: when the caller passes ``--update-baseline`` AND the HEAD
    commit message carries ``audio-parity-baseline-bump:``, the lock
    file is rewritten and the script exits 0.

    TODO(AI-15): monkeypatch the git-log subprocess to return a fake
    trailer-bearing commit; assert exit_code == 0 and lock.json updated.
    """
    # TODO(AI-15): wire fixtures + monkeypatch subprocess.run.
    raise NotImplementedError
