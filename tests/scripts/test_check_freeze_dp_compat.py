"""Tests for scripts/check_freeze_dp_compat.py (AI-15).

Pins the CLAUDE.md "学習補助" invariant: when
``--resume-from-multispeaker-checkpoint`` is supplied, the training
driver auto-enables ``--freeze-dp``. The legacy NotImplementedError
test remains skipped via per-function decorator (awaits AI-15 AST
search); the newly added test below pins the module-constant + CLI
surface that is concrete today.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


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
def freeze_dp_compat_module() -> Any:
    return _load_module("check_freeze_dp_compat")


# ---------------------------------------------------------------------------
# Legacy skipped test (AI-15 skeleton — kept as TODO marker).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_freeze_dp_auto_enable_path_exists():
    """AST scan of __main__.py must locate the auto-enable assignment.

    TODO(AI-15): wire AST fixtures + assertions.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Active tests (audit-derived; pin module-constant + CLI surface).
# ---------------------------------------------------------------------------


def test_freeze_dp_compat_module_path_and_argparse(
    freeze_dp_compat_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """AI-15: TRAIN_MAIN_PATH + --main-path CLI override are stable.

    The constant points at src/python/piper_train/__main__.py; the
    override flag is documented in the AI-15 ticket. A silent rename in
    piper_train would silently break the gate once the AST search lands.
    """
    mod = freeze_dp_compat_module
    assert mod.TRAIN_MAIN_PATH.name == "__main__.py", (
        "AI-15: TRAIN_MAIN_PATH must point at piper_train/__main__.py"
    )
    assert "piper_train" in str(mod.TRAIN_MAIN_PATH), (
        "AI-15: TRAIN_MAIN_PATH must live under piper_train/"
    )
    with pytest.raises(SystemExit):
        mod.main(["--help"])
    out = capsys.readouterr().out
    assert "--main-path" in out, (
        "AI-15: --main-path override flag must remain exposed in --help"
    )
    # Bare invocation must remain a 0-return skeleton with the AI-15 breadcrumb.
    capsys.readouterr()
    rc = mod.main([])
    assert rc == 0
    err = capsys.readouterr().err
    assert "AI-15 skeleton" in err, (
        "AI-15: skeleton must emit 'AI-15 skeleton' breadcrumb to stderr"
    )
