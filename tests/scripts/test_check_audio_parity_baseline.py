"""Tests for scripts/check_audio_parity_baseline.py (AI-15).

These tests pin the behavioural contract of the [mb_istft_1d] audio
parity baseline drift gate. The legacy two NotImplementedError-bodied
tests remain skipped via per-function decorators until the AI-15
implementation lands; the newly added tests below pin the contract
surface that is concrete today (lock JSON schema, module constants,
argparse CLI, package importability).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_audio_parity_baseline.py"
LOCK_PATH = REPO_ROOT / "scripts" / "audio_parity_baseline.lock.json"


def _load_module(name: str) -> Any:
    """Load a scripts/check_*.py module via importlib.

    scripts/ has no __init__.py, so we cannot use ``from scripts import X``.
    This helper mirrors the pattern in test_check_action_sha_drift.py.
    """
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
def audio_parity_baseline_module() -> Any:
    return _load_module("check_audio_parity_baseline")


# ---------------------------------------------------------------------------
# Legacy skipped tests (AI-15 skeleton — kept as TODO markers, individually
# skipped so newly-added active tests are NOT swept by a module-level skip).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_baseline_drift_detected(tmp_path, monkeypatch, capsys):
    """A mutated [mb_istft_1d] contract field must produce non-zero exit.

    Contract: when ``docs/spec/audio-parity-contract.toml`` and
    ``scripts/audio_parity_baseline.lock.json`` disagree on any of the
    PINNED_FIELDS, the script exits 1 with ``AI-15 baseline drift`` in
    stderr.

    TODO(AI-15): build tmp toml + lock fixtures, run main, assert
    exit_code == 1 and 'AI-15 baseline drift' in capsys.readouterr().err.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_baseline_bump_with_trailer_accepted(tmp_path, monkeypatch, capsys):
    """``--update-baseline`` + trailer-bearing commit must succeed and rewrite.

    Contract: when the caller passes ``--update-baseline`` AND the HEAD
    commit message carries ``audio-parity-baseline-bump:``, the lock
    file is rewritten and the script exits 0.

    TODO(AI-15): monkeypatch the git-log subprocess to return a fake
    trailer-bearing commit; assert exit_code == 0 and lock.json updated.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Active tests (audit-derived; pin contract surfaces concrete today).
# ---------------------------------------------------------------------------


def test_audio_parity_lock_json_is_valid_json_with_required_fields() -> None:
    """AI-15: scripts/audio_parity_baseline.lock.json schema + canonical values.

    Pins that the shipped pin file parses as JSON, contains the
    ``mb_istft_1d`` section, that every field listed in
    ``PINNED_FIELDS`` is present in the section, and that each field
    carries its canonical numeric value (27 / 4.05 / 1.10 / 30 / 22050).
    """
    mod = _load_module("check_audio_parity_baseline")
    data = json.loads(LOCK_PATH.read_text())
    assert "mb_istft_1d" in data, "lock.json must define [mb_istft_1d] section"
    section = data["mb_istft_1d"]

    # Canonical values (CLAUDE.md / README.md Benchmark).
    assert section["expected_p50_ms"] == 27, (
        "expected_p50_ms must remain pinned at 27 (Xeon E5-2650 v4 / 25 phoneme EN)"
    )
    assert section["expected_proxy_mos_mean"] == 4.05
    assert section["expected_params_m"] == 1.10
    assert section["expected_snr_floor_db"] == 30
    assert section["sample_rate"] == 22050

    # Every PINNED_FIELDS entry must be present in the section.
    for field in mod.PINNED_FIELDS:
        assert field in section, (
            f"AI-15: PINNED_FIELDS entry {field!r} missing from lock.json mb_istft_1d section"
        )


def test_audio_parity_baseline_module_constants_contract(
    audio_parity_baseline_module: Any,
) -> None:
    """AI-15: PINNED_FIELDS / BUMP_TRAILER / *_PATH module constants are stable.

    These constants form the public contract referenced by docs and
    pre-commit hooks. A silent rename would break the documented escape
    hatch (e.g. trailer prefix) or repoint the gate at a non-existent
    file.
    """
    mod = audio_parity_baseline_module
    assert mod.PINNED_FIELDS == (
        "expected_p50_ms",
        "expected_proxy_mos_mean",
        "expected_params_m",
        "expected_snr_floor_db",
        "sample_rate",
    ), "PINNED_FIELDS tuple must remain stable (documented in CLAUDE.md / README)"
    assert mod.BUMP_TRAILER == "audio-parity-baseline-bump:", (
        "BUMP_TRAILER literal must remain stable (documented escape hatch)"
    )
    assert mod.CONTRACT_PATH.name == "audio-parity-contract.toml"
    assert mod.LOCK_PATH.name == "audio_parity_baseline.lock.json"


def test_audio_parity_baseline_argparse_defaults_and_flag(
    audio_parity_baseline_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """AI-15: argparse exposes --update-baseline / --contract / --lock with stable defaults.

    Pins the CLI surface invoked from ``.pre-commit-config.yaml``: the
    flag is store_true (default False), the path overrides default to
    the canonical lock + contract files.
    """
    mod = audio_parity_baseline_module
    with pytest.raises(SystemExit):
        mod.main(["--help"])
    out = capsys.readouterr().out
    assert "--update-baseline" in out
    assert "--contract" in out
    assert "--lock" in out


def test_all_check_scripts_importable_and_skeleton_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AI-15: all 5 check_*.py skeleton scripts import + return 0 on bare invoke.

    Pins the 'AI-15 skeleton' stderr breadcrumb so a future PR cannot
    silently delete it (and thus mask that the gate is still a no-op).
    Each script must expose a ``main(argv)`` callable.
    """
    expected_modules = (
        "check_audio_parity_baseline",
        "check_a1_a2_isolation",
        "check_expected_p50_ms_gate",
        "check_freeze_dp_compat",
        "check_pr222_pr537_isolation_checklist",
    )
    for name in expected_modules:
        mod = _load_module(name)
        assert hasattr(mod, "main"), f"AI-15: {name} must expose main(argv)"
        # Re-set capsys boundary so we capture this iteration's stderr only.
        capsys.readouterr()
        rc = mod.main([])
        assert rc == 0, f"AI-15: skeleton {name}.main([]) must return 0"
        captured = capsys.readouterr()
        assert "AI-15 skeleton" in captured.err, (
            f"AI-15: {name} must emit 'AI-15 skeleton' breadcrumb to stderr"
        )
