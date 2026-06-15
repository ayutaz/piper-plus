"""Tests for scripts/check_expected_p50_ms_gate.py (AI-15).

Pins the +/-10 % tolerance behaviour for ``[mb_istft_1d]`` and the strict
ceiling behaviour for the three new variants. The legacy two
NotImplementedError-bodied tests remain skipped via per-function
decorators (awaiting AI-12 metrics.json schema); the newly added tests
below pin the policy constants and CLI surface that are concrete today.
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
def expected_p50_ms_gate_module() -> Any:
    return _load_module("check_expected_p50_ms_gate")


# ---------------------------------------------------------------------------
# Legacy skipped tests (AI-15 skeleton — awaiting AI-12 metrics.json).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_mb_istft_1d_tolerance_10pct(tmp_path):
    """mb_istft_1d with rtf_p50_ms=29.6 passes; 29.8 fails.

    TODO(AI-15): wire tmp_path fixture + main(argv).
    """
    raise NotImplementedError


@pytest.mark.skip(reason="awaiting AI-15 implementation")
def test_istftnet2_mb_strict_target(tmp_path):
    """istftnet2_mb_1d2d with rtf_p50_ms=18 passes; 19 fails.

    TODO(AI-15): wire fixture + assertion.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Active tests (audit-derived; pin policy constants + CLI surface).
# ---------------------------------------------------------------------------


def test_expected_p50_ms_tolerance_and_strict_variant_constants(
    expected_p50_ms_gate_module: Any,
) -> None:
    """AI-15: TOLERANCE_VARIANTS / STRICT_VARIANTS / DEFAULT_*_PATH define the gate policy.

    These dictionaries are the entire policy surface (±10 % for
    mb_istft_1d; strict ceiling for the three new variants). Silent
    edits would change gate semantics undetectably while the script
    body is still a skeleton.
    """
    mod = expected_p50_ms_gate_module
    assert mod.TOLERANCE_VARIANTS == {"mb_istft_1d": 0.10}, (
        "AI-15: mb_istft_1d tolerance must remain ±10% (documented policy)"
    )
    assert mod.STRICT_VARIANTS == (
        "istftnet2_mb_1d2d",
        "mswavehax",
        "fly_convnext6",
    ), "AI-15: STRICT_VARIANTS must enumerate the three new variants"
    assert mod.DEFAULT_METRICS_PATH.name == "metrics.json", (
        "AI-15: metrics.json default must remain stable (AI-12 artifact)"
    )
    assert mod.CONTRACT_PATH.name == "audio-parity-contract.toml"


def test_expected_p50_ms_argparse_from_metrics_default(
    expected_p50_ms_gate_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """AI-15: --from-metrics CLI default points at tools/benchmark/metrics.json.

    Pins that ``--help`` exposes ``--from-metrics`` referencing the
    canonical metrics.json filename, and that bare ``main([])``
    returns 0 with the skeleton stderr breadcrumb.
    """
    mod = expected_p50_ms_gate_module
    with pytest.raises(SystemExit):
        mod.main(["--help"])
    out = capsys.readouterr().out
    assert "--from-metrics" in out, (
        "AI-15: --from-metrics flag must remain exposed in --help"
    )
    assert "metrics.json" in out, (
        "AI-15: --help must mention metrics.json default path"
    )
    # Bare invocation must remain a 0-return skeleton with the AI-15 breadcrumb.
    capsys.readouterr()
    rc = mod.main([])
    assert rc == 0
    err = capsys.readouterr().err
    assert "AI-15 skeleton" in err, (
        "AI-15: skeleton must emit 'AI-15 skeleton' breadcrumb to stderr"
    )
