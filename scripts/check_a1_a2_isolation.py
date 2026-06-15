#!/usr/bin/env python3
"""AI-15 regression-guard: A-1 / A-2 isolation invariants.

This script enforces the structural invariants that protect the existing
[mb_istft_1d] decoder branch from accidental coupling when the new A-1 /
A-2 / FLY-TTS variants land. It does NOT execute models or run training;
it only walks ASTs and (where applicable) inspects ``git diff``.

Four invariants are checked:

1. ``_forward_1d`` branch present in ``src/python/piper_train/vits/mb_istft.py``
   and a ``decoder_type == 'mb_istft_1d'`` dispatch path in
   ``MBiSTFTGenerator.forward``.
2. ``dec_wavehax`` sibling defined in ``src/python/piper_train/vits/models.py``
   alongside the existing decoder, gated by ``enable_wavehax`` flag.
3. ``src/python_run/piper/text_splitter.py`` is untouched by the current
   diff (``git diff HEAD~1 --stat`` returns 0 lines for that file).
4. ONNX export I/O spec in
   ``src/python/piper_train/export_onnx.py`` matches the pinned
   ``scripts/onnx_io_spec.lock.json`` (input_names / output_names /
   dynamic_axes).

NOTE: This is a SKELETON for AI-15. Real AST walks and diff hooks are
stubbed and the script is currently a no-op success.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
MB_ISTFT_PATH = REPO_ROOT / "src/python/piper_train/vits/mb_istft.py"
MODELS_PATH = REPO_ROOT / "src/python/piper_train/vits/models.py"
EXPORT_ONNX_PATH = REPO_ROOT / "src/python/piper_train/export_onnx.py"
TEXT_SPLITTER_PATH = REPO_ROOT / "src/python_run/piper/text_splitter.py"
ONNX_IO_SPEC_LOCK = REPO_ROOT / "scripts/onnx_io_spec.lock.json"

# Trailer required when the ONNX I/O spec lock changes.
ONNX_IO_SPEC_BUMP_TRAILER = "onnx-io-spec-bump:"


def check_forward_1d_branch(path: Path = MB_ISTFT_PATH) -> list[str]:
    """Assert ``_forward_1d`` def and ``decoder_type=='mb_istft_1d'`` branch.

    TODO(AI-15): use ``ast.parse(path.read_text())`` and walk for
    FunctionDef('_forward_1d') and an If(Compare(Name('decoder_type'),
    [Eq()], [Constant('mb_istft_1d')])) inside MBiSTFTGenerator.forward.
    """
    # TODO(AI-15): AST walk for _forward_1d + dispatch branch.
    raise NotImplementedError(
        f"TODO(AI-15): check_forward_1d_branch against {path}"
    )


def check_dec_wavehax_sibling(path: Path = MODELS_PATH) -> list[str]:
    """Assert ``dec_wavehax`` sibling + ``enable_wavehax`` flag are defined.

    TODO(AI-15): AST walk for an ``ast.Assign(targets=[Name('dec_wavehax')])``
    in the SynthesizerTrn class, and a corresponding boolean flag field.
    """
    # TODO(AI-15): AST walk for dec_wavehax + enable_wavehax flag.
    raise NotImplementedError(
        f"TODO(AI-15): check_dec_wavehax_sibling against {path}"
    )


def check_text_splitter_untouched(path: Path = TEXT_SPLITTER_PATH) -> list[str]:
    """Assert ``text_splitter.py`` has 0 diff lines vs ``HEAD~1``.

    TODO(AI-15): subprocess.run(['git', 'diff', 'HEAD~1', '--numstat',
    str(path)]) and parse the (added, removed, file) tuple; non-zero -> drift.
    """
    # TODO(AI-15): subprocess git diff --numstat parse.
    raise NotImplementedError(
        f"TODO(AI-15): check_text_splitter_untouched against {path}"
    )


def check_onnx_io_spec_pinned(
    export_path: Path = EXPORT_ONNX_PATH,
    lock_path: Path = ONNX_IO_SPEC_LOCK,
) -> list[str]:
    """Assert export_onnx.py's I/O spec matches the pinned lock file.

    TODO(AI-15): AST walk for ``input_names = [...]``, ``output_names = [...]``,
    and ``dynamic_axes = {...}`` assignments in export_onnx.py; compare to
    the JSON lock file with set / dict equality.
    """
    # TODO(AI-15): AST extraction + JSON compare; raise drift list.
    raise NotImplementedError(
        f"TODO(AI-15): check_onnx_io_spec_pinned against {export_path} vs {lock_path}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the A-1 / A-2 isolation gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Enforce the four A-1 / A-2 isolation invariants documented "
            "in the AI-15 ticket. Failure exits non-zero with the list "
            "of violated invariants."
        )
    )
    parser.add_argument(
        "--strict-trailer",
        action="store_true",
        help=(
            f"If the ONNX I/O spec lock is touched, require the HEAD "
            f"commit message to include the {ONNX_IO_SPEC_BUMP_TRAILER!r} "
            "trailer (covers CODEOWNERS-style escalation)."
        ),
    )
    args = parser.parse_args(argv)

    # TODO(AI-15): wire the four checks and accumulate failures:
    #   failures.extend(check_forward_1d_branch())
    #   failures.extend(check_dec_wavehax_sibling())
    #   failures.extend(check_text_splitter_untouched())
    #   failures.extend(check_onnx_io_spec_pinned())
    #   if args.strict_trailer and onnx_io_spec_lock_touched():
    #       require trailer
    _ = args  # silence unused while skeleton
    print(
        "AI-15 skeleton: check_a1_a2_isolation.py not yet implemented",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
