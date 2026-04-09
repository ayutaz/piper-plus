"""Speaker Encoder Evaluation.

Evaluates a speaker encoder model using same-speaker / different-speaker
audio pairs.  Computes cosine similarities and Equal Error Rate (EER).

Test pairs file format (TSV, one pair per line):
    <label>\\t<audio_path_1>\\t<audio_path_2>
where <label> is 1 for same-speaker and 0 for different-speaker pairs.

Example:
    1\\t/data/spk001/utt1.wav\\t/data/spk001/utt2.wav
    0\\t/data/spk001/utt1.wav\\t/data/spk002/utt1.wav

Usage:
    uv run python -m piper_train.speaker_encoder.evaluate \\
        --model speaker_encoder.onnx \\
        --test-pairs test_pairs.txt \\
        --output results.json

    # With PyTorch checkpoint
    uv run python -m piper_train.speaker_encoder.evaluate \\
        --model speaker_encoder.ckpt \\
        --test-pairs test_pairs.txt \\
        --output results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger("piper_train.speaker_encoder.evaluate")


def load_test_pairs(pairs_path: Path) -> list[tuple[int, str, str]]:
    """Load test pairs from a TSV file.

    Args:
        pairs_path: Path to the test pairs file.

    Returns:
        List of (label, path1, path2) tuples.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If a line has an invalid format.
    """
    if not pairs_path.exists():
        raise FileNotFoundError(f"Test pairs file not found: {pairs_path}")

    pairs: list[tuple[int, str, str]] = []
    with open(pairs_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise ValueError(
                    f"Invalid format at line {line_num}: expected 3 tab-separated "
                    f"fields (label, path1, path2), got {len(parts)}"
                )
            label = int(parts[0])
            if label not in (0, 1):
                raise ValueError(
                    f"Invalid label at line {line_num}: expected 0 or 1, got {label}"
                )
            pairs.append((label, parts[1], parts[2]))

    return pairs


def compute_eer(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """Compute Equal Error Rate (EER) and the corresponding threshold.

    EER is the operating point where the false acceptance rate (FAR)
    equals the false rejection rate (FRR).

    Args:
        labels: 1-D array of ground-truth labels (1 = same, 0 = different).
        scores: 1-D array of cosine similarity scores.

    Returns:
        (eer, threshold) where eer is in [0, 1] and threshold is the
        score value at the EER operating point.
    """
    labels = np.asarray(labels, dtype=np.int32)
    scores = np.asarray(scores, dtype=np.float64)

    n_positive = int(np.sum(labels == 1))
    n_negative = int(np.sum(labels == 0))

    if n_positive == 0 or n_negative == 0:
        _LOGGER.warning(
            "Cannot compute EER: need both positive and negative pairs "
            "(got %d positive, %d negative)",
            n_positive,
            n_negative,
        )
        return 0.0, 0.0

    # Sort thresholds from low to high so that FAR decreases and FRR increases
    thresholds = np.sort(np.unique(scores))

    # Vectorised FAR and FRR computation
    # For each threshold t:
    #   FAR(t)  = fraction of negative pairs with score >= t
    #   FRR(t)  = fraction of positive pairs with score <  t
    pos_scores = np.sort(scores[labels == 1])
    neg_scores = np.sort(scores[labels == 0])

    fars = np.array([np.sum(neg_scores >= t) / n_negative for t in thresholds])
    frrs = np.array([np.sum(pos_scores < t) / n_positive for t in thresholds])

    # Find the crossing point where FAR and FRR are closest
    diffs = fars - frrs
    # The EER is at the threshold where FAR crosses FRR.
    # Find the index where the sign changes (FAR goes from > FRR to < FRR).
    idx = np.argmin(np.abs(diffs))

    # Interpolate between the two nearest points for a more accurate EER
    if idx > 0 and diffs[idx - 1] * diffs[idx] < 0:
        # Linear interpolation between idx-1 and idx
        w = abs(diffs[idx - 1]) / (abs(diffs[idx - 1]) + abs(diffs[idx]))
        eer = fars[idx - 1] * (1 - w) + fars[idx] * w
        threshold = float(thresholds[idx - 1] * (1 - w) + thresholds[idx] * w)
    else:
        eer = (fars[idx] + frrs[idx]) / 2.0
        threshold = float(thresholds[idx])

    return float(eer), threshold


def evaluate(
    model_path: Path,
    pairs_path: Path,
) -> dict:
    """Run full speaker encoder evaluation.

    Args:
        model_path: Path to the ONNX or PyTorch model.
        pairs_path: Path to the test pairs TSV file.

    Returns:
        Dictionary with evaluation results including EER, threshold,
        per-pair scores, and timing information.
    """
    from .encoder import SpeakerEncoder  # noqa: PLC0415

    # Load model
    suffix = model_path.suffix.lower()
    if suffix == ".onnx":
        encoder = SpeakerEncoder.from_onnx(model_path)
    elif suffix in (".ckpt", ".pt", ".pth"):
        encoder = SpeakerEncoder.from_pytorch(model_path)
    else:
        raise ValueError(
            f"Unrecognised model format: {suffix}. Expected .onnx, .ckpt, .pt, or .pth"
        )

    # Load test pairs
    pairs = load_test_pairs(pairs_path)
    _LOGGER.info("Loaded %d test pairs from %s", len(pairs), pairs_path)

    # Collect unique audio paths to avoid redundant encoding
    unique_paths: set[str] = set()
    for _, path1, path2 in pairs:
        unique_paths.add(path1)
        unique_paths.add(path2)

    _LOGGER.info("Encoding %d unique audio files...", len(unique_paths))

    # Encode all unique audio files
    embeddings: dict[str, np.ndarray] = {}
    t0 = time.perf_counter()

    for audio_path in sorted(unique_paths):
        try:
            embeddings[audio_path] = encoder.encode(audio_path)
        except Exception as e:
            _LOGGER.error("Failed to encode %s: %s", audio_path, e)
            raise

    encode_time = time.perf_counter() - t0
    _LOGGER.info(
        "Encoded %d files in %.2f s (%.1f ms/file)",
        len(embeddings),
        encode_time,
        (encode_time / len(embeddings)) * 1000 if embeddings else 0,
    )

    # Compute pairwise similarities
    labels_list: list[int] = []
    scores_list: list[float] = []
    pair_results: list[dict] = []

    for label, path1, path2 in pairs:
        emb1 = embeddings[path1]
        emb2 = embeddings[path2]
        score = encoder.similarity(emb1, emb2)

        labels_list.append(label)
        scores_list.append(score)
        pair_results.append(
            {
                "label": label,
                "path1": path1,
                "path2": path2,
                "similarity": round(score, 6),
            }
        )

    labels_arr = np.array(labels_list, dtype=np.int32)
    scores_arr = np.array(scores_list, dtype=np.float64)

    # Compute EER
    eer, threshold = compute_eer(labels_arr, scores_arr)

    # Summary statistics
    same_mask = labels_arr == 1
    diff_mask = labels_arr == 0

    results = {
        "model": str(model_path),
        "test_pairs": str(pairs_path),
        "num_pairs": len(pairs),
        "num_same_speaker": int(same_mask.sum()),
        "num_diff_speaker": int(diff_mask.sum()),
        "eer": round(float(eer), 6),
        "eer_threshold": round(threshold, 6),
        "same_speaker_similarity": {
            "mean": round(float(scores_arr[same_mask].mean()), 6)
            if same_mask.any()
            else None,
            "std": round(float(scores_arr[same_mask].std()), 6)
            if same_mask.any()
            else None,
            "min": round(float(scores_arr[same_mask].min()), 6)
            if same_mask.any()
            else None,
            "max": round(float(scores_arr[same_mask].max()), 6)
            if same_mask.any()
            else None,
        },
        "diff_speaker_similarity": {
            "mean": round(float(scores_arr[diff_mask].mean()), 6)
            if diff_mask.any()
            else None,
            "std": round(float(scores_arr[diff_mask].std()), 6)
            if diff_mask.any()
            else None,
            "min": round(float(scores_arr[diff_mask].min()), 6)
            if diff_mask.any()
            else None,
            "max": round(float(scores_arr[diff_mask].max()), 6)
            if diff_mask.any()
            else None,
        },
        "encode_time_sec": round(encode_time, 3),
        "num_unique_files": len(embeddings),
        "pairs": pair_results,
    }

    _LOGGER.info(
        "EER: %.4f%% (threshold: %.4f) | "
        "Same-speaker similarity: %.4f +/- %.4f | "
        "Diff-speaker similarity: %.4f +/- %.4f",
        eer * 100,
        threshold,
        results["same_speaker_similarity"]["mean"] or 0,
        results["same_speaker_similarity"]["std"] or 0,
        results["diff_speaker_similarity"]["mean"] or 0,
        results["diff_speaker_similarity"]["std"] or 0,
    )

    return results


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate speaker encoder model using test pairs",
    )
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="Path to speaker encoder model (.onnx or .ckpt)",
    )
    parser.add_argument(
        "--test-pairs",
        type=Path,
        required=True,
        help="Path to test pairs TSV file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to output results JSON file (default: stdout)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    results = evaluate(args.model, args.test_pairs)

    # Output results
    results_json = json.dumps(results, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(results_json, encoding="utf-8")
        _LOGGER.info("Results written to %s", args.output)
    else:
        print(results_json)


if __name__ == "__main__":
    main()
