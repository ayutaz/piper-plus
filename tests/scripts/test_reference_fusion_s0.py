"""G0 decisions are mechanical: any regression blocks trim; g-side needs wins."""

import importlib.util
from pathlib import Path


_PATH = Path(__file__).resolve().parents[2] / "scripts/run_reference_fusion_s0.py"
_SPEC = importlib.util.spec_from_file_location("reference_fusion_s0", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _cell(campplus, ecapa, cer, **flags):
    return {
        "cell": "c",
        "campplus_delta": campplus,
        "ecapa_delta": ecapa,
        "cer_delta": cer,
        "flags": {"goodhart": False, **flags},
    }


def test_trim_adopted_only_when_every_cell_is_non_regressing():
    assert _MODULE.trim_decision([_cell(0.0, 0.001, 0.0), _cell(0.01, 0.0, -0.1)])[
        "adopt_trim"
    ]
    for bad in (_cell(-1e-6, 0.1, 0.0), _cell(0.1, -1e-6, 0.0), _cell(0.1, 0.1, 1e-6)):
        result = _MODULE.trim_decision([_cell(0.1, 0.1, 0.0), bad])
        assert not result["adopt_trim"]
        assert len(result["failures"]) == 1
    assert not _MODULE.trim_decision([_cell(0.1, 0.1, 0.0, goodhart=True)])[
        "adopt_trim"
    ]
    assert not _MODULE.trim_decision([])["adopt_trim"]


def test_g_side_average_requires_both_encoders_better_without_cer_loss():
    assert _MODULE.averaging_decision([_cell(0.01, 0.01, 0.0)])["position"] == "g"
    for cell in (_cell(0.01, 0.0, 0.0), _cell(0.0, 0.01, 0.0), _cell(0.1, 0.1, 0.01)):
        assert _MODULE.averaging_decision([cell])["position"] == "embedding"


def test_stats_fail_only_when_clearly_worse_and_flag_weak_evidence():
    base = {"auc": 0.95, "gap": 0.30, "n_speakers": 24}
    ok = _MODULE.stats_decision({"auc": 0.94, "gap": 0.31, "n_speakers": 24}, base)
    assert ok["passes"] and not ok["weak_evidence"]
    assert not _MODULE.stats_decision(
        {"auc": 0.92, "gap": 0.40, "n_speakers": 24}, base
    )["passes"]
    assert not _MODULE.stats_decision(
        {"auc": 0.99, "gap": 0.29, "n_speakers": 24}, base
    )["passes"]
    assert _MODULE.stats_decision({"auc": 0.95, "gap": 0.3, "n_speakers": 4}, base)[
        "weak_evidence"
    ]
