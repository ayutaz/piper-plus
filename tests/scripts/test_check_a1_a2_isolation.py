"""Tests for scripts/check_a1_a2_isolation.py (AI-15 skeleton).

Covers the four A-1 / A-2 isolation invariants. AI-03 and AI-08
prerequisite landings introduce the ``_forward_1d`` def and the
``dec_wavehax`` sibling, so these tests are skipped until those land.
"""

from __future__ import annotations

import pytest

# TODO(AI-15): switch to a real import once the script is implemented:
# from scripts import check_a1_a2_isolation
pytestmark = pytest.mark.skip(reason="awaiting AI-15 implementation")


def test_forward_1d_branch_present():
    """AST scan of vits/mb_istft.py must find ``_forward_1d`` def.

    Contract: ``check_forward_1d_branch`` returns an empty list when the
    ``_forward_1d`` FunctionDef and ``decoder_type=='mb_istft_1d'`` branch
    are both present.

    TODO(AI-15): construct a minimal source string with the expected
    pattern, write to tmp_path, call the check, assert empty failures.
    """
    # TODO(AI-15): wire fixture + invoke check.
    raise NotImplementedError


def test_text_splitter_untouched(monkeypatch):
    """``check_text_splitter_untouched`` must pass when git diff returns 0 lines.

    Contract: when ``git diff HEAD~1 --numstat`` against
    ``text_splitter.py`` reports 0 added / 0 removed lines, the check
    returns an empty failure list.

    TODO(AI-15): monkeypatch subprocess.run to return a fake stdout
    ``b"0\t0\tsrc/python_run/piper/text_splitter.py\n"``.
    """
    # TODO(AI-15): monkeypatch subprocess; assert no failures.
    raise NotImplementedError


def test_onnx_io_spec_pinned():
    """input_names == ['input','input_lengths','scales','sid'] is invariant.

    Contract: ``check_onnx_io_spec_pinned`` compares the AST-extracted
    input_names list to the pinned lock and returns failures when they
    diverge.

    TODO(AI-15): build a fake export_onnx.py source with input_names
    that matches the lock, assert no failures; mutate one entry and
    assert a descriptive failure message.
    """
    # TODO(AI-15): wire fixture + assertions.
    raise NotImplementedError
