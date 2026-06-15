"""Tests for scripts/check_a1_a2_isolation.py (AI-15).

Covers the four A-1 / A-2 isolation invariants. AI-03 and AI-08
prerequisite landings introduce the ``_forward_1d`` def and the
``dec_wavehax`` sibling. The legacy three NotImplementedError-bodied
tests are kept (individually skipped) until those land; the newly
added tests below pin the contract surface that is concrete today
(onnx I/O lock schema, module constants, argparse CLI).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ONNX_IO_LOCK_PATH = REPO_ROOT / "scripts" / "onnx_io_spec.lock.json"


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
def a1_a2_isolation_module() -> Any:
    return _load_module("check_a1_a2_isolation")


# ---------------------------------------------------------------------------
# Legacy skipped tests (AI-15 skeleton — kept as TODO markers).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_forward_1d_branch_present():
    """AST scan of vits/mb_istft.py must find ``_forward_1d`` def.

    TODO(AI-15): wire fixture + invoke check.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_text_splitter_untouched(monkeypatch):
    """``check_text_splitter_untouched`` must pass when git diff returns 0 lines.

    TODO(AI-15): monkeypatch subprocess; assert no failures.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_onnx_io_spec_pinned():
    """input_names == ['input','input_lengths','scales','sid'] is invariant.

    TODO(AI-15): wire fixture + assertions.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Active tests (audit-derived; pin contract surfaces concrete today).
# ---------------------------------------------------------------------------


def test_onnx_io_spec_lock_pins_sid_fourth_input() -> None:
    """AI-15: onnx_io_spec.lock.json keeps ``sid`` as 4th input + ``output`` sole output.

    PR #222's ``sid`` -> ``speaker_embedding`` rename is deferred to AI-17;
    until then this lock file is the canonical pin that all 6 runtimes
    rely on. A typo here would silently bypass the AI-15 gate once the
    real implementation lands.
    """
    data = json.loads(ONNX_IO_LOCK_PATH.read_text())
    assert data["input_names"] == ["input", "input_lengths", "scales", "sid"], (
        "AI-15: input_names must keep 'sid' as the 4th canonical input (PR #222 deferred to AI-17)"
    )
    assert data["output_names"] == ["output"], (
        "AI-15: output_names must remain ['output'] (single canonical output)"
    )
    assert set(data["dynamic_axes"].keys()) == {
        "input",
        "input_lengths",
        "scales",
        "sid",
        "output",
    }, "AI-15: dynamic_axes must cover all 4 inputs + the output"
    assert data["dynamic_axes"]["output"] == {
        "0": "batch_size",
        "1": "channels",
        "2": "time",
    }, "AI-15: output dynamic axes must be (batch_size, channels, time)"


def test_a1_a2_isolation_module_constants_and_paths(
    a1_a2_isolation_module: Any,
) -> None:
    """AI-15: MB_ISTFT_PATH / MODELS_PATH / EXPORT_ONNX_PATH / TEXT_SPLITTER_PATH /
    ONNX_IO_SPEC_LOCK / ONNX_IO_SPEC_BUMP_TRAILER form the public contract surface.

    A silent rename would cause the AST walks (once wired) to target the
    wrong files, masking the gate.
    """
    mod = a1_a2_isolation_module
    assert mod.MB_ISTFT_PATH.name == "mb_istft.py"
    assert mod.MODELS_PATH.name == "models.py"
    assert mod.EXPORT_ONNX_PATH.name == "export_onnx.py"
    assert mod.TEXT_SPLITTER_PATH.name == "text_splitter.py"
    assert mod.ONNX_IO_SPEC_LOCK.name == "onnx_io_spec.lock.json"
    assert mod.ONNX_IO_SPEC_BUMP_TRAILER == "onnx-io-spec-bump:", (
        "AI-15: trailer literal must remain stable (documented escape hatch)"
    )


def test_a1_a2_isolation_strict_trailer_argparse_default_false(
    a1_a2_isolation_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """AI-15: --strict-trailer is store_true with default False; bare main([]) is no-op skeleton.

    Pins the AI-15 ticket-defined CLI contract (lines 103-104 of the
    script). A refactor flipping the default to True would silently
    break commit ergonomics for the documented manual stage.
    """
    mod = a1_a2_isolation_module
    with pytest.raises(SystemExit):
        mod.main(["--help"])
    out = capsys.readouterr().out
    assert "--strict-trailer" in out, (
        "AI-15: --strict-trailer flag must remain exposed in --help"
    )
    # Bare invocation is currently the skeleton no-op (returns 0 + breadcrumb).
    capsys.readouterr()
    rc = mod.main([])
    assert rc == 0
    err = capsys.readouterr().err
    assert "AI-15 skeleton" in err, (
        "AI-15: skeleton must emit 'AI-15 skeleton' breadcrumb to stderr"
    )
