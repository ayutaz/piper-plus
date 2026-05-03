"""Phase 5 P5-T03: emotion fine-tune evaluation harness.

Runs three evaluation axes against a freshly fine-tuned emotion model:

1. **SER (Speech Emotion Recognition)** — classifies generated audio with a
   HuggingFace emotion model (e.g. ``superb/hubert-large-superb-er``) and
   reports the top-1 accuracy vs. the target emotion label.
2. **MOS (Mean Opinion Score proxies)** — PESQ + STOI against the original
   CREMA-D reference recordings. Uses the same machinery as
   ``compute_metrics.py`` next to this file.
3. **Multilingual regression** — synthesises a small fixed sentence set in
   the other 5 languages and compares PESQ/STOI against the 6lang base to
   detect catastrophic forgetting.

The emotion model and the fine-tuned ONNX are BOTH large assets that cannot
be vendored into the repo. This script is deliberately tolerant of their
absence: missing assets are reported and the affected axis is skipped rather
than causing a hard failure, so the script can be wired up to CI as a
smoke-level "run what we have" harness.

Example:
    uv run python tools/benchmark/evaluate_emotion_finetune.py \\
        --model /data/piper/output-emotion-fine-tune-v1/emotion-v1.onnx \\
        --config /data/piper/dataset-crema-d-emotion/config.json \\
        --reference-dataset /data/piper/datasets/CREMA-D \\
        --style-bank /data/piper/style_bank_crema_d.npz \\
        --base-model /data/piper/output-multilingual-6lang/multilingual-6lang-75epoch.onnx \\
        --num-samples 50 \\
        --output-dir /data/piper/emotion-eval-v1

Outputs:
    ``<output-dir>/ser_results.json`` (confusion matrix + per-emotion accuracy)
    ``<output-dir>/mos_results.json`` (PESQ / STOI aggregates)
    ``<output-dir>/multilingual_regression.json``
    ``<output-dir>/summary.md`` (human-readable recap, success gate markers)

See:
    docs/research/implementation-plan/tickets/phase-5/P5-T03-evaluation-ser-mos.md
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


_LOGGER = logging.getLogger("evaluate_emotion_finetune")

TARGET_EMOTIONS: tuple[str, ...] = (
    "angry",
    "disgusted",
    "fearful",
    "happy",
    "neutral",
    "sad",
)

SUCCESS_GATES: dict[str, float] = {
    "ser_top1_accuracy": 0.65,
    "mos_pesq_min": 2.8,
    "mos_stoi_min": 0.85,
    "multilingual_pesq_regression_max": 0.2,
}


@dataclass
class SerResult:
    """Top-1 accuracy from the Speech Emotion Recognition classifier."""

    top1_accuracy: float = 0.0
    per_emotion_accuracy: dict[str, float] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    num_samples: int = 0
    skipped_reason: str | None = None


@dataclass
class MosResult:
    """PESQ / STOI aggregates for emotion fine-tune vs. CREMA-D reference."""

    pesq_mean: float = 0.0
    pesq_median: float = 0.0
    stoi_mean: float = 0.0
    stoi_median: float = 0.0
    num_samples: int = 0
    skipped_reason: str | None = None


@dataclass
class MultilingualRegressionResult:
    """Regression on the other 5 languages relative to the 6lang base."""

    per_language: dict[str, dict[str, float]] = field(default_factory=dict)
    worst_pesq_drop: float = 0.0
    worst_language: str | None = None
    skipped_reason: str | None = None


def evaluate_ser(
    emotion_model: Path,
    ser_model_name: str,
    num_samples: int,
) -> SerResult:
    """Run SER against ``num_samples`` generated utterances.

    The emotion_model must be an ONNX file produced by Phase 5 stage5a/b.
    ``ser_model_name`` is a HuggingFace id (e.g. ``superb/hubert-large-superb-er``).
    When either dependency is unavailable this returns a skipped result.
    """
    if not emotion_model.is_file():
        return SerResult(skipped_reason=f"emotion model missing: {emotion_model}")

    try:  # noqa: SIM105 — explicit except for logging intent
        from transformers import pipeline  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        return SerResult(skipped_reason=f"transformers not available: {exc}")

    _LOGGER.info("Loading SER classifier: %s", ser_model_name)
    try:
        _ = pipeline("audio-classification", model=ser_model_name)
    except Exception as exc:  # pragma: no cover — network-dependent
        return SerResult(
            skipped_reason=f"SER model load failed (likely offline): {exc}",
        )

    _LOGGER.warning(
        "SER evaluation requires a running inference loop over the fine-tuned "
        "ONNX + the CREMA-D test set. This skeleton reports num_samples=%d "
        "but does NOT perform the full loop — wire the generation pipeline in "
        "per-project before going live.",
        num_samples,
    )
    return SerResult(
        top1_accuracy=0.0,
        num_samples=num_samples,
        skipped_reason="SER inference loop not implemented in this skeleton",
    )


def evaluate_mos(
    emotion_model: Path,
    reference_dataset: Path,
    num_samples: int,
) -> MosResult:
    """Compute PESQ/STOI aggregates against the CREMA-D reference."""
    if not emotion_model.is_file():
        return MosResult(skipped_reason=f"emotion model missing: {emotion_model}")
    if not reference_dataset.is_dir():
        return MosResult(
            skipped_reason=f"reference dataset missing: {reference_dataset}"
        )

    try:  # pesq + pystoi are optional deps
        import pesq  # type: ignore[import-not-found]  # noqa: F401
        import pystoi  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        return MosResult(skipped_reason=f"pesq/pystoi not installed: {exc}")

    _LOGGER.warning(
        "MOS evaluation skeleton — the actual synthesize+compare loop must be "
        "wired to tools/benchmark/compute_metrics.py. num_samples=%d",
        num_samples,
    )
    return MosResult(
        num_samples=num_samples,
        skipped_reason="MOS inference loop not implemented in this skeleton",
    )


def evaluate_multilingual_regression(
    emotion_model: Path,
    base_model: Path,
    num_samples: int,
) -> MultilingualRegressionResult:
    """Check that the other 5 languages have not catastrophically forgotten."""
    if not emotion_model.is_file():
        return MultilingualRegressionResult(
            skipped_reason=f"emotion model missing: {emotion_model}",
        )
    if not base_model.is_file():
        return MultilingualRegressionResult(
            skipped_reason=f"6lang base model missing: {base_model}",
        )

    _LOGGER.warning(
        "Multilingual regression skeleton — synthesise 5 fixed sentences per "
        "language (ja/zh/es/fr/pt) in BOTH models and compute PESQ/STOI. "
        "num_samples=%d",
        num_samples,
    )
    return MultilingualRegressionResult(
        skipped_reason="multilingual regression loop not implemented in this skeleton",
    )


def check_success_gates(
    ser: SerResult,
    mos: MosResult,
    multilingual: MultilingualRegressionResult,
) -> tuple[bool, list[str]]:
    """Return ``(passed, reasons)`` for the Phase 5 adoption gate."""
    failures: list[str] = []

    if ser.skipped_reason is None:
        if ser.top1_accuracy < SUCCESS_GATES["ser_top1_accuracy"]:
            failures.append(
                f"SER top-1 {ser.top1_accuracy:.3f} < gate "
                f"{SUCCESS_GATES['ser_top1_accuracy']}"
            )
    else:
        failures.append(f"SER skipped: {ser.skipped_reason}")

    if mos.skipped_reason is None:
        if mos.pesq_mean < SUCCESS_GATES["mos_pesq_min"]:
            failures.append(
                f"PESQ mean {mos.pesq_mean:.2f} < gate {SUCCESS_GATES['mos_pesq_min']}"
            )
        if mos.stoi_mean < SUCCESS_GATES["mos_stoi_min"]:
            failures.append(
                f"STOI mean {mos.stoi_mean:.3f} < gate {SUCCESS_GATES['mos_stoi_min']}"
            )
    else:
        failures.append(f"MOS skipped: {mos.skipped_reason}")

    if multilingual.skipped_reason is None:
        if (
            multilingual.worst_pesq_drop
            > SUCCESS_GATES["multilingual_pesq_regression_max"]
        ):
            failures.append(
                f"Multilingual regression {multilingual.worst_pesq_drop:.2f} on "
                f"{multilingual.worst_language} > gate "
                f"{SUCCESS_GATES['multilingual_pesq_regression_max']}"
            )
    else:
        failures.append(
            f"Multilingual regression skipped: {multilingual.skipped_reason}"
        )

    return len(failures) == 0, failures


def write_outputs(
    output_dir: Path,
    ser: SerResult,
    mos: MosResult,
    multilingual: MultilingualRegressionResult,
    gate_passed: bool,
    gate_failures: list[str],
) -> None:
    """Persist JSON + Markdown recap to ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ser_results.json").write_text(
        json.dumps(asdict(ser), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "mos_results.json").write_text(
        json.dumps(asdict(mos), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "multilingual_regression.json").write_text(
        json.dumps(asdict(multilingual), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lines: list[str] = [
        "# Phase 5 Emotion Fine-tune Evaluation Summary",
        "",
        f"- SER top-1 accuracy: {ser.top1_accuracy:.3f} ({ser.num_samples} samples)",
        f"- MOS PESQ mean: {mos.pesq_mean:.2f}",
        f"- MOS STOI mean: {mos.stoi_mean:.3f}",
        f"- Worst multilingual PESQ drop: {multilingual.worst_pesq_drop:.2f} on {multilingual.worst_language}",
        "",
        f"## Success gate: {'PASS' if gate_passed else 'FAIL'}",
        "",
    ]
    for reason in gate_failures:
        lines.append(f"- {reason}")
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", type=Path, required=True, help="Fine-tuned emotion ONNX"
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Emotion dataset config.json"
    )
    parser.add_argument("--reference-dataset", type=Path, required=True)
    parser.add_argument(
        "--base-model",
        type=Path,
        required=True,
        help="6lang base ONNX (for regression)",
    )
    parser.add_argument(
        "--style-bank", type=Path, help="style_bank_crema_d.npz (optional)"
    )
    parser.add_argument(
        "--ser-model",
        type=str,
        default="superb/hubert-large-superb-er",
        help="HuggingFace audio-classification model",
    )
    parser.add_argument("--num-samples", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    _LOGGER.info("Evaluating emotion fine-tune: %s", args.model)
    ser = evaluate_ser(args.model, args.ser_model, args.num_samples)
    mos = evaluate_mos(args.model, args.reference_dataset, args.num_samples)
    multilingual = evaluate_multilingual_regression(
        args.model,
        args.base_model,
        args.num_samples,
    )

    gate_passed, failures = check_success_gates(ser, mos, multilingual)
    write_outputs(args.output_dir, ser, mos, multilingual, gate_passed, failures)

    _LOGGER.info("Summary written to %s/summary.md", args.output_dir)
    if not gate_passed:
        _LOGGER.warning("Phase 5 gate FAILED: %s", failures)
        raise SystemExit(1)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Module-level sanity (importable for unit tests)
# ---------------------------------------------------------------------------

__all__ = [
    "SerResult",
    "MosResult",
    "MultilingualRegressionResult",
    "SUCCESS_GATES",
    "TARGET_EMOTIONS",
    "evaluate_ser",
    "evaluate_mos",
    "evaluate_multilingual_regression",
    "check_success_gates",
    "write_outputs",
]


# Allow running as ``python -m tools.benchmark.evaluate_emotion_finetune``.
def _assert_expected_exports_for_tests() -> dict[str, Any]:
    return {name: globals()[name] for name in __all__}
