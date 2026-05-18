"""Unit tests for scripts/audio_quality_metrics.py (M2.1).

These exercise the pure-Python diff / rendering / Bencher-JSON path; the
PESQ / STOI / UTMOS / Whisper integration runs only inside the CI workflow.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "audio_quality_metrics.py"
MANIFEST = REPO_ROOT / "tests" / "fixtures" / "audio-corpus" / "manifest.json"


def _load():
    spec = importlib.util.spec_from_file_location("audio_quality_metrics", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def aqm():
    return _load()


@pytest.fixture
def baseline():
    return {
        "schema_version": 1,
        "thresholds": {
            "pesq_wb_min_drop": 0.15,
            "stoi_min_drop": 0.02,
            "utmos22_min_drop": 0.10,
            "wer_max_increase": 0.05,
        },
        "samples": [
            {
                "id": "ja-short-001",
                "metrics": {"pesq_wb": 4.20, "stoi": 0.95, "utmos22": 3.80, "wer": 0.00},
            },
            {
                "id": "en-long-001",
                "metrics": {"pesq_wb": 4.05, "stoi": 0.92, "utmos22": 3.70, "wer": 0.02},
            },
        ],
    }


def _rows(aqm, **overrides):
    return [
        aqm.MetricsRow(
            id="ja-short-001",
            language="ja",
            category="short",
            pesq_wb=overrides.get("ja_pesq", 4.20),
            stoi=overrides.get("ja_stoi", 0.95),
            utmos22=overrides.get("ja_utmos", 3.80),
            wer=overrides.get("ja_wer", 0.00),
        ),
        aqm.MetricsRow(
            id="en-long-001",
            language="en",
            category="long",
            pesq_wb=overrides.get("en_pesq", 4.05),
            stoi=overrides.get("en_stoi", 0.92),
            utmos22=overrides.get("en_utmos", 3.70),
            wer=overrides.get("en_wer", 0.02),
        ),
    ]


def test_diff_no_change_no_regressions(aqm, baseline):
    report = aqm.compute_diff(_rows(aqm), baseline)
    assert report.regressions == 0
    assert report.samples_checked == 2
    assert not report.missing_baseline


def test_diff_pesq_drop_above_threshold_is_regression(aqm, baseline):
    rows = _rows(aqm, ja_pesq=4.20 - 0.20)
    report = aqm.compute_diff(rows, baseline)
    assert report.regressions == 1
    flagged = [r for r in report.rows if r.regression]
    assert flagged[0].metric == "pesq_wb"
    assert flagged[0].id == "ja-short-001"


def test_diff_pesq_drop_below_threshold_not_flagged(aqm, baseline):
    rows = _rows(aqm, ja_pesq=4.20 - 0.10)
    report = aqm.compute_diff(rows, baseline)
    assert report.regressions == 0


def test_diff_wer_increase_is_regression(aqm, baseline):
    rows = _rows(aqm, en_wer=0.02 + 0.10)
    report = aqm.compute_diff(rows, baseline)
    assert report.regressions == 1
    flagged = [r for r in report.rows if r.regression]
    assert flagged[0].metric == "wer"


def test_diff_handles_empty_baseline(aqm):
    """Bootstrap path — first PR where baseline.samples is still []."""
    empty = {"schema_version": 1, "thresholds": {}, "samples": []}
    rows = _rows(aqm)
    report = aqm.compute_diff(rows, empty)
    assert report.regressions == 0
    assert report.missing_baseline is True
    for row in report.rows:
        assert row.baseline is None
        assert row.delta is None
        assert row.regression is False


def test_diff_handles_missing_metric(aqm, baseline):
    rows = _rows(aqm)
    rows[0].utmos22 = None
    report = aqm.compute_diff(rows, baseline)
    deltas = [r for r in report.rows if r.id == "ja-short-001" and r.metric == "utmos22"]
    assert deltas[0].delta is None


def test_render_markdown_includes_header(aqm, baseline):
    report = aqm.compute_diff(_rows(aqm), baseline)
    md = aqm.render_markdown(report)
    assert "## Audio MOS Proxy" in md
    assert "Samples checked: **2**" in md


def test_to_bencher_json_skips_missing_metrics(aqm):
    rows = [
        aqm.MetricsRow(
            id="x", language="ja", category="short",
            pesq_wb=4.0, stoi=None, utmos22=float("nan"), wer=0.01,
        )
    ]
    payload = aqm.to_bencher_json(rows)
    assert "x.pesq_wb" in payload
    assert "x.wer" in payload
    assert "x.stoi" not in payload
    assert "x.utmos22" not in payload


def test_manifest_loads(aqm):
    samples = aqm.load_manifest(MANIFEST)
    assert len(samples) == 30  # 6 languages × 5 categories
    languages = {s["language"] for s in samples}
    assert languages == {"ja", "en", "zh", "es", "fr", "pt"}


def test_synthesize_stubs_emits_zero_filled_metrics(aqm, tmp_path):
    out = tmp_path / "metrics.json"
    bencher = tmp_path / "bencher.json"
    args = aqm.build_parser().parse_args([
        "synthesize-stubs",
        "--manifest", str(MANIFEST),
        "--output", str(out),
        "--bencher-json", str(bencher),
    ])
    rc = args.func(args)
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["samples"]) == 30
    assert all(v == 0.0 for v in data["samples"][0]["metrics"].values())
    bencher_payload = json.loads(bencher.read_text(encoding="utf-8"))
    assert len(bencher_payload) == 30 * 4


def test_diff_cli_writes_markdown(aqm, tmp_path, baseline):
    metrics_path = tmp_path / "metrics.json"
    baseline_path = tmp_path / "baseline.json"
    out_path = tmp_path / "diff.md"
    metrics_path.write_text(json.dumps({
        "schema_version": 1,
        "samples": [r.to_dict() for r in _rows(aqm)],
    }))
    baseline_path.write_text(json.dumps(baseline))
    args = aqm.build_parser().parse_args([
        "diff",
        "--metrics", str(metrics_path),
        "--baseline", str(baseline_path),
        "--output", str(out_path),
    ])
    rc = args.func(args)
    assert rc == 0
    assert "## Audio MOS Proxy" in out_path.read_text(encoding="utf-8")


def test_is_regression_handles_nan(aqm):
    assert aqm.is_regression("pesq_wb", float("nan"), {"pesq_wb_min_drop": 0.15}) is False
