"""Tests for scripts/check_pr222_pr537_isolation_checklist.py (AI-15 skeleton).

Pins the presence of the 5 reviewer checkboxes added to the PR template.
Skipped until AI-17 finalises the template alignment with PR #222.
"""

from __future__ import annotations

import pytest

# TODO(AI-15): switch to real import once the script is implemented:
# from scripts import check_pr222_pr537_isolation_checklist
pytestmark = pytest.mark.skip(reason="awaiting AI-15 implementation")


def test_5_checkboxes_present(tmp_path):
    """A PR body with all 5 required checkboxes passes; missing one fails.

    Contract: when the markdown contains exactly the 5 ``- [ ]`` /
    ``- [x]`` lines (default decoder_type 不変 / [mb_istft_1d] audio
    parity 不変 / ONNX I/O 不変 / PR #537 TF32/bf16-mixed / freeze-dp
    互換), the script exits 0. Removing any one line must yield exit 1.

    TODO(AI-15): write a fake PR body to tmp_path containing all 5
    checkboxes; invoke main(['--pr-body', str(path)]); assert exit 0.
    Drop one line, re-invoke, assert exit 1 and the missing label in
    stderr.
    """
    # TODO(AI-15): wire tmp_path + main(argv).
    raise NotImplementedError
