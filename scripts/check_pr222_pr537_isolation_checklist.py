#!/usr/bin/env python3
"""AI-15 regression-guard: PR #222 / PR #537 isolation reviewer checklist.

This gate is consumed in two places:

1. Pre-commit (``stage: manual``) for maintainers who paste the PR body
   into a local markdown file before opening the PR.
2. CI (``contract-gates`` workflow) where ``${{ github.event.pull_request.body }}``
   is dumped to a tmp file and passed via ``--pr-body``.

The script greps for the 5 required ``- [ ]`` / ``- [x]`` checkboxes
under the ``## Decoder Regression Guard (AI-15)`` section (kept separate
from ``## Risk Level`` so the ``validate-pr-body`` gate that counts
``- [x]`` inside Risk Level is not contaminated by this checklist):

* default decoder_type 不変
* [mb_istft_1d] audio parity 不変
* ONNX I/O 不変
* PR #537 TF32/bf16-mixed
* freeze-dp 互換

It also verifies the upstream ``.github/pull_request_template.md`` still
contains its Risk Level / Affected Components / Type sections so a
template rewrite is caught immediately.

NOTE: This is a SKELETON for AI-15. Real markdown parsing is stubbed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
PR_TEMPLATE_PATH = REPO_ROOT / ".github/pull_request_template.md"

# Substrings (Japanese + EN markers) we expect to find as `- [ ]` lines
# under the Risk Level section. Order is not enforced.
REQUIRED_CHECKBOXES: tuple[str, ...] = (
    "default decoder_type 不変",
    "[mb_istft_1d] audio parity 不変",
    "ONNX I/O 不変",
    "PR #537 TF32/bf16-mixed",
    "freeze-dp 互換",
)

REQUIRED_TEMPLATE_SECTIONS: tuple[str, ...] = (
    "## Risk Level",
    "## Affected Components",
    "## Type",
)


def _load_pr_body(path: Path) -> str:
    """Read the PR body markdown.

    TODO(AI-15): handle missing file with clear stderr; strip CRLF.
    """
    # TODO(AI-15): path.read_text(encoding='utf-8'); normalise newlines.
    raise NotImplementedError(f"TODO(AI-15): _load_pr_body for {path}")


def _find_missing_checkboxes(body: str) -> list[str]:
    """Return the list of required checkboxes not present in ``body``.

    TODO(AI-15): for each substring in REQUIRED_CHECKBOXES, search for a
    line matching ``- [ ]`` or ``- [x]`` containing the substring; if
    none found, append the substring to the missing list.
    """
    # TODO(AI-15): regex `^- \[[ x]\] .*<substring>` with re.MULTILINE.
    raise NotImplementedError("TODO(AI-15): _find_missing_checkboxes")


def _verify_template_intact(path: Path = PR_TEMPLATE_PATH) -> list[str]:
    """Return the list of missing template section headers.

    TODO(AI-15): str.contains for each REQUIRED_TEMPLATE_SECTIONS entry.
    """
    # TODO(AI-15): read template + check each header still present.
    raise NotImplementedError(f"TODO(AI-15): _verify_template_intact {path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the PR #222 / PR #537 isolation checklist gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify the AI-15 reviewer checklist is present in a PR body "
            "markdown file and that the source template still carries the "
            "Risk Level / Affected Components / Type sections."
        )
    )
    parser.add_argument(
        "--pr-body",
        type=Path,
        required=False,
        help=(
            "Path to a markdown file containing the PR body (CI writes "
            "${{ github.event.pull_request.body }} to a tmp file)."
        ),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=PR_TEMPLATE_PATH,
        help="Override the pull_request_template.md path.",
    )
    args = parser.parse_args(argv)

    # TODO(AI-15): wire the pipeline:
    #   if args.pr_body:
    #       body = _load_pr_body(args.pr_body)
    #       missing = _find_missing_checkboxes(body)
    #       if missing: emit + accumulate failures.
    #   template_drift = _verify_template_intact(args.template)
    #   if template_drift: emit + accumulate failures.
    # TODO(AI-15): handoff semantic verification (does the maintainer
    # actually agree?) to the /code-review skill rather than enforcing
    # `- [x]` here.
    _ = args  # silence unused while skeleton
    print(
        "AI-15 skeleton: check_pr222_pr537_isolation_checklist.py "
        "not yet implemented",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
