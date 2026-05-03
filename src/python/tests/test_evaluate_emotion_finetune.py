""": tests for the evaluation harness (no model needed)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS_BENCHMARK = Path(__file__).resolve().parents[3] / "tools" / "benchmark"
sys.path.insert(0, str(TOOLS_BENCHMARK))

from evaluate_emotion_finetune import (  # noqa: E402 — dynamic sys.path
    SUCCESS_GATES,
    TARGET_EMOTIONS,
    MosResult,
    MultilingualRegressionResult,
    SerResult,
    check_success_gates,
    evaluate_mos,
    evaluate_multilingual_regression,
    evaluate_ser,
    write_outputs,
)


def test_target_emotions_covers_crema_d() -> None:
    """Phase 5 evaluates the full 6-emotion CREMA-D taxonomy."""
    assert TARGET_EMOTIONS == (
        "angry", "disgusted", "fearful", "happy", "neutral", "sad",
    )


def test_success_gates_have_expected_thresholds() -> None:
    """Contract with Phase 5 README — gates determine adoption."""
    assert SUCCESS_GATES["ser_top1_accuracy"] == 0.65
    assert SUCCESS_GATES["mos_pesq_min"] == 2.8
    assert SUCCESS_GATES["mos_stoi_min"] == 0.85
    assert SUCCESS_GATES["multilingual_pesq_regression_max"] == 0.2


def test_evaluate_ser_missing_model_skips(tmp_path: Path) -> None:
    """A missing ONNX must not raise — the SER axis is reported as skipped."""
    result = evaluate_ser(tmp_path / "missing.onnx", "dummy/model", num_samples=5)
    assert isinstance(result, SerResult)
    assert result.skipped_reason is not None
    assert "missing" in result.skipped_reason


def test_evaluate_mos_missing_model_skips(tmp_path: Path) -> None:
    result = evaluate_mos(tmp_path / "missing.onnx", tmp_path, num_samples=5)
    assert isinstance(result, MosResult)
    assert result.skipped_reason is not None


def test_evaluate_mos_missing_reference_skips(tmp_path: Path) -> None:
    onnx_file = tmp_path / "model.onnx"
    onnx_file.write_bytes(b"not a real onnx")
    result = evaluate_mos(onnx_file, tmp_path / "missing_dataset", num_samples=5)
    assert result.skipped_reason is not None
    assert "reference dataset missing" in result.skipped_reason


def test_evaluate_multilingual_regression_missing_model_skips(tmp_path: Path) -> None:
    result = evaluate_multilingual_regression(
        tmp_path / "missing.onnx", tmp_path / "base.onnx", num_samples=5,
    )
    assert isinstance(result, MultilingualRegressionResult)
    assert result.skipped_reason is not None


def test_check_gate_reports_all_skips_as_failures() -> None:
    """When every axis is skipped, the gate MUST fail."""
    ser = SerResult(skipped_reason="no model")
    mos = MosResult(skipped_reason="no pesq")
    multi = MultilingualRegressionResult(skipped_reason="no base")
    passed, failures = check_success_gates(ser, mos, multi)
    assert passed is False
    assert len(failures) == 3
    assert any("SER skipped" in f for f in failures)
    assert any("MOS skipped" in f for f in failures)
    assert any("Multilingual regression skipped" in f for f in failures)


def test_check_gate_passes_when_all_axes_meet_thresholds() -> None:
    ser = SerResult(top1_accuracy=0.70, num_samples=50)
    mos = MosResult(pesq_mean=3.2, stoi_mean=0.90, num_samples=50)
    multi = MultilingualRegressionResult(worst_pesq_drop=0.1, worst_language="ja")
    passed, failures = check_success_gates(ser, mos, multi)
    assert passed is True
    assert failures == []


def test_check_gate_fails_on_low_ser() -> None:
    ser = SerResult(top1_accuracy=0.40, num_samples=50)
    mos = MosResult(pesq_mean=3.2, stoi_mean=0.90, num_samples=50)
    multi = MultilingualRegressionResult(worst_pesq_drop=0.1, worst_language="ja")
    passed, failures = check_success_gates(ser, mos, multi)
    assert passed is False
    assert any("SER top-1" in f and "< gate" in f for f in failures)


def test_write_outputs_produces_four_files(tmp_path: Path) -> None:
    ser = SerResult(top1_accuracy=0.70, num_samples=50)
    mos = MosResult(pesq_mean=3.0, stoi_mean=0.88, num_samples=50)
    multi = MultilingualRegressionResult(worst_pesq_drop=0.1, worst_language="ja")
    write_outputs(tmp_path, ser, mos, multi, True, [])
    assert (tmp_path / "ser_results.json").is_file()
    assert (tmp_path / "mos_results.json").is_file()
    assert (tmp_path / "multilingual_regression.json").is_file()
    assert (tmp_path / "summary.md").is_file()

    # JSON files should roundtrip.
    ser_json = json.loads((tmp_path / "ser_results.json").read_text(encoding="utf-8"))
    assert ser_json["top1_accuracy"] == 0.70

    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "PASS" in summary
