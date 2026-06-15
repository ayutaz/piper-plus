"""Tests for scripts/check_pr222_pr537_isolation_checklist.py (AI-15).

Pins the presence of the 5 reviewer checkboxes added to the PR template
and the structural template invariants (Risk Level / Affected Components
/ Type). The legacy NotImplementedError test remains skipped via per-
function decorator (awaits AI-15 markdown parser); the newly added
tests below pin the contract surface that is concrete today.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PR_TEMPLATE_PATH = REPO_ROOT / ".github" / "pull_request_template.md"


def _load_module(name: str) -> Any:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        name,
        REPO_ROOT / "scripts" / f"{name}.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pr222_pr537_isolation_module() -> Any:
    return _load_module("check_pr222_pr537_isolation_checklist")


# ---------------------------------------------------------------------------
# Legacy skipped test (AI-15 skeleton — kept as TODO marker).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_5_checkboxes_present(tmp_path):
    """A PR body with all 5 required checkboxes passes; missing one fails.

    TODO(AI-15): wire tmp_path + main(argv).
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Active tests (audit-derived; pin template structure + module constants).
# ---------------------------------------------------------------------------


def test_pr_template_contains_decoder_regression_guard_section_and_5_checkboxes() -> (
    None
):
    """AI-15: pull_request_template.md ships the Decoder Regression Guard section + 5 checkboxes.

    A future PR could silently delete this section; without this test
    the skeleton script (which is a no-op today) cannot catch the
    regression. Counts ``- [ ]`` lines under the section header to
    pin exactly 5 checkboxes.
    """
    body = PR_TEMPLATE_PATH.read_text()
    assert "## Decoder Regression Guard (AI-15)" in body, (
        "AI-15: pull_request_template.md must contain the "
        "'## Decoder Regression Guard (AI-15)' section header"
    )
    for token in (
        "default decoder_type 不変",
        "[mb_istft_1d] audio parity 不変",
        "ONNX I/O 不変",
        "PR #537 TF32/bf16-mixed",
        "freeze-dp 互換",
    ):
        assert token in body, (
            f"AI-15: required checklist token {token!r} missing from PR template"
        )

    # Count `- [ ]` checkbox lines inside the Decoder Regression Guard
    # section. The next `## ` header terminates the section.
    section_marker = "## Decoder Regression Guard (AI-15)"
    section_start = body.index(section_marker) + len(section_marker)
    next_header_match = re.search(r"\n## ", body[section_start:])
    section_end = (
        section_start + next_header_match.start()
        if next_header_match
        else len(body)
    )
    section_body = body[section_start:section_end]
    # Match `- [ ]` lines (the template ships unchecked) at the start of a line.
    checkbox_lines = re.findall(r"^- \[ \] ", section_body, flags=re.MULTILINE)
    assert len(checkbox_lines) == 5, (
        f"AI-15: Decoder Regression Guard section must contain exactly 5 "
        f"unchecked checkboxes, found {len(checkbox_lines)}"
    )


def test_pr_template_preserves_risk_level_affected_components_type_sections(
    pr222_pr537_isolation_module: Any,
) -> None:
    """AI-15: REQUIRED_TEMPLATE_SECTIONS + REQUIRED_CHECKBOXES are present + stable.

    Verifies the public contract the script will enforce: the template
    still carries the three section headers, and the module's tuple of
    required checkboxes matches the documented 5-item list.
    """
    mod = pr222_pr537_isolation_module
    body = PR_TEMPLATE_PATH.read_text()
    for hdr in mod.REQUIRED_TEMPLATE_SECTIONS:
        assert hdr in body, (
            f"AI-15: PR template must still contain {hdr!r} section header"
        )
    assert mod.REQUIRED_CHECKBOXES == (
        "default decoder_type 不変",
        "[mb_istft_1d] audio parity 不変",
        "ONNX I/O 不変",
        "PR #537 TF32/bf16-mixed",
        "freeze-dp 互換",
    ), "AI-15: REQUIRED_CHECKBOXES tuple must remain stable (5-item contract)"
