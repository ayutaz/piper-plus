#!/usr/bin/env python3
"""AI-15 regression-guard: ``--freeze-dp`` auto-enable invariant.

The training driver (``src/python/piper_train/__main__.py``) auto-enables
``args.freeze_dp = True`` whenever
``--resume-from-multispeaker-checkpoint`` is provided. CLAUDE.md /
"学習補助" pins this auto-enable as a behavioural invariant; removing it
would cause silent catastrophic forgetting on resumed fine-tunes.

This script walks the AST of ``__main__.py`` and asserts the assignment
exists. ``test_freeze_dp.py`` is intentionally NOT touched here (G-1.9
keeps existing tests unchanged); they cover the behavioural pass / fail,
this script covers the structural presence.

NOTE: This is a SKELETON for AI-15. The AST search is stubbed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
TRAIN_MAIN_PATH = REPO_ROOT / "src/python/piper_train/__main__.py"


def _find_freeze_dp_auto_enable(path: Path = TRAIN_MAIN_PATH) -> bool:
    """Return True if the freeze-dp auto-enable assignment is present.

    Target pattern:
        if args.resume_from_multispeaker_checkpoint:
            args.freeze_dp = True

    Or equivalent ast.If / ast.Assign combination where the test refers
    to ``resume_from_multispeaker_checkpoint`` and the body assigns
    ``args.freeze_dp = True``.

    TODO(AI-15): use ast.parse + ast.walk; surface line numbers to ease
    review when the invariant is intentionally relocated.
    """
    # TODO(AI-15): implement AST walk for the auto-enable pattern.
    raise NotImplementedError(
        f"TODO(AI-15): _find_freeze_dp_auto_enable against {path}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the freeze-dp compatibility gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Assert the --resume-from-multispeaker-checkpoint -> "
            "--freeze-dp auto-enable invariant remains intact in "
            "piper_train/__main__.py."
        )
    )
    parser.add_argument(
        "--main-path",
        type=Path,
        default=TRAIN_MAIN_PATH,
        help="Override the __main__.py path (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    # TODO(AI-15): wire the check:
    #   if not _find_freeze_dp_auto_enable(args.main_path):
    #       print drift message to stderr; return 1
    # TODO(AI-15): note that test_freeze_dp.py is intentionally untouched
    # (G-1.9 append-only rule).
    _ = args  # silence unused while skeleton
    print(
        "AI-15 skeleton: check_freeze_dp_compat.py not yet implemented",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
