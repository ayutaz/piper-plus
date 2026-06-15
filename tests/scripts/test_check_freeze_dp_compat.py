"""Tests for scripts/check_freeze_dp_compat.py (AI-15 skeleton).

Pins the CLAUDE.md "学習補助" invariant: when
``--resume-from-multispeaker-checkpoint`` is supplied, the training
driver auto-enables ``--freeze-dp``. Skipped until AI-15 implementation.
"""

from __future__ import annotations

import pytest

# TODO(AI-15): switch to real import once the script is implemented:
# from scripts import check_freeze_dp_compat
pytestmark = pytest.mark.skip(reason="awaiting AI-15 implementation")


def test_freeze_dp_auto_enable_path_exists():
    """AST scan of __main__.py must locate the auto-enable assignment.

    Contract: when ``_find_freeze_dp_auto_enable`` runs against the
    current piper_train/__main__.py source, it returns True. Removing
    the auto-enable would constitute a silent regression of the
    documented "学習補助" invariant in CLAUDE.md.

    TODO(AI-15): call _find_freeze_dp_auto_enable() on the real
    REPO_ROOT path and assert it returns True. Also build a tmp_path
    source missing the assignment and assert it returns False.
    """
    # TODO(AI-15): wire AST fixtures + assertions.
    raise NotImplementedError
