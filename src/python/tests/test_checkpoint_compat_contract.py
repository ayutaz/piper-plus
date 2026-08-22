"""Run the published-checkpoint compatibility gate as part of the test suite.

The gate itself lives in ``scripts/check_checkpoint_compat.py`` and is wired
into pre-commit. Exposing it here as well means it also runs in the
``python-tests`` matrix, so the ratchet holds even for contributors who have
not installed the git hooks.

See ``docs/spec/checkpoint-compat-contract.toml`` for what is pinned and why.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


pytest.importorskip("torch", reason="torch required to rebuild the model")

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE = REPO_ROOT / "scripts" / "check_checkpoint_compat.py"


@pytest.mark.unit
def test_published_checkpoints_still_load() -> None:
    """Every published checkpoint must load into the current model.

    Runs in a subprocess so the gate is exercised exactly as CI runs it,
    including its exit code and operator-facing message.
    """
    if not GATE.exists():  # pragma: no cover — layout guard
        pytest.skip(f"gate script not found at {GATE}")

    result = subprocess.run(
        [sys.executable, str(GATE)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, (
        "A published checkpoint no longer loads into the current model.\n"
        f"{result.stdout}\n{result.stderr}"
    )
