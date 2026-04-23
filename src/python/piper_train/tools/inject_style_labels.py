#!/usr/bin/env python3
"""Inject ``style_vector_path`` and ``emotion`` fields into a dataset manifest.

Use cases:

1. Attach a ``emotion`` label to every utterance in an existing 6-language
   dataset.jsonl so that Phase 4 PE-A loss can sample per-emotion centroids.
2. Pair each utterance with a per-utterance PE-A embedding written by
   :mod:`piper_train.tools.build_pea_style_bank` under ``--per-utterance-dir``.
3. Optionally pre-compute per-utterance ``.npy`` style vectors by looking up
   the emotion's centroid inside a ``.npz`` style bank (``--style-bank`` +
   ``--output-dir``).

Input manifest (``--input-dataset``) is JSONL with one utterance per line.
Each record is expected to expose ``audio_path`` or ``audio_norm_path`` so
the tool can derive ``utt_id = Path(audio_path).stem``.

Emotion sources:

* ``--emotion-map <json>``: JSON dict mapping friendly labels to data-specific
  codes (e.g. ``{"happy": "HAP", "sad": "SAD", ...}``). Used together with
  ``--emotion-csv`` to translate dataset-provided codes into the canonical
  vocabulary of the style bank.
* ``--emotion-csv <file>``: CSV (``utt_id,emotion``) providing per-utterance
  labels. Values are looked up through the emotion map if one is supplied.
* ``--default-emotion <name>``: fall-back label for utterances with no CSV
  entry. Defaults to ``neutral``.

Output: a new JSONL at ``--output-manifest`` (or overwrite input) with two
extra fields per row: ``emotion`` and ``style_vector_path`` (relative to
``--dataset-dir`` when available; absolute otherwise; ``None`` if no .npy
found).
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_kwargs):  # type: ignore[misc]
        return iterable

_LOGGER = logging.getLogger("inject_style_labels")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_emotion_mapping_from_csv(csv_path: Path) -> dict[str, str]:
    """Return ``{utt_id: emotion}`` from a ``utt_id,emotion`` CSV.

    Lines starting with ``#`` are treated as comments.
    """
    mapping: dict[str, str] = {}
    with open(csv_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",", 1)
            if len(parts) != 2:
                continue
            utt_id, emotion = parts
            mapping[utt_id.strip()] = emotion.strip().lower()
    return mapping


def load_emotion_map(path: Path) -> dict[str, str]:
    """Return an emotion-translation dict from a JSON file.

    The JSON format is ``{"friendly_label": "dataset_code"}``. We invert it so
    CSV values (``dataset_code``) can be translated into friendly labels,
    which is the direction the style bank uses.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Emotion map must be a JSON object, got {type(raw).__name__}")
    # Invert: value (dataset code, e.g. "HAP") -> friendly label (e.g. "happy").
    # Keys are lowercased because the CSV loader also lowercases its values,
    # so look-ups remain consistent regardless of user input casing.
    inverted: dict[str, str] = {}
    for friendly, code in raw.items():
        code_key = str(code).strip().lower()
        friendly_lc = str(friendly).strip().lower()
        inverted[code_key] = friendly_lc
        # Also accept the reverse direction for robustness.
        inverted.setdefault(friendly_lc, friendly_lc)
    return inverted


def validate_emotions_against_bank(
    emotion_mapping: dict[str, str], style_bank_path: Path
) -> set[str]:
    """Return the set of emotion labels in ``emotion_mapping`` that are absent from the bank."""
    bank = np.load(str(style_bank_path), allow_pickle=True)
    if "emotion_names" not in bank.files:
        raise ValueError(f"Style bank {style_bank_path} missing 'emotion_names'")
    bank_emotions = {str(e).lower() for e in bank["emotion_names"].tolist()}
    mapping_emotions = {str(v).lower() for v in emotion_mapping.values()}
    return mapping_emotions - bank_emotions


# ---------------------------------------------------------------------------
# Core injection
# ---------------------------------------------------------------------------


def _resolve_emotion(
    utt_id: str,
    audio_path: str,
    emotion_csv_mapping: dict[str, str],
    emotion_translation: dict[str, str],
    default_emotion: str,
) -> str:
    """Resolve the emotion label for a single utterance."""
    raw = None
    if utt_id and utt_id in emotion_csv_mapping:
        raw = emotion_csv_mapping[utt_id]
    elif audio_path and audio_path in emotion_csv_mapping:
        raw = emotion_csv_mapping[audio_path]
    if raw is None:
        return default_emotion.lower()
    # Translate through map if provided.
    if emotion_translation:
        return emotion_translation.get(raw, raw).lower()
    return raw.lower()


def _resolve_style_vector_path(
    utt_id: str,
    style_vectors_dir: Optional[Path],
    dataset_dir: Optional[Path],
    output_dir: Optional[Path],
    emotion: str,
    emotion_centroids: Optional[dict[str, np.ndarray]],
) -> Optional[str]:
    """Resolve (or materialise) a ``.npy`` style vector for the utterance."""
    # 1. Prefer a pre-computed per-utterance vector.
    if style_vectors_dir is not None:
        candidate = style_vectors_dir / f"{utt_id}.npy"
        if candidate.exists():
            return _relative_if_possible(candidate, dataset_dir)

    # 2. Materialise from style bank centroids.
    if (
        emotion_centroids is not None
        and output_dir is not None
        and emotion in emotion_centroids
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{utt_id}.npy"
        if not target.exists():
            np.save(str(target), emotion_centroids[emotion])
        return _relative_if_possible(target, dataset_dir)

    return None


def _relative_if_possible(path: Path, root: Optional[Path]) -> str:
    if root is None:
        return str(path)
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _load_bank_centroids(style_bank_path: Path) -> dict[str, np.ndarray]:
    bank = np.load(str(style_bank_path), allow_pickle=True)
    names = [str(n).lower() for n in bank["emotion_names"].tolist()]
    centroids = bank["emotion_centroids"].astype(np.float32)
    return {name: centroids[i] for i, name in enumerate(names)}


def inject_style_labels(
    input_dataset: Path,
    output_manifest: Optional[Path],
    dataset_dir: Optional[Path] = None,
    style_vectors_dir: Optional[Path] = None,
    emotion_csv_mapping: Optional[dict[str, str]] = None,
    emotion_translation: Optional[dict[str, str]] = None,
    default_emotion: str = "neutral",
    style_bank_path: Optional[Path] = None,
    output_vectors_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Walk the input JSONL and emit a manifest with emotion + style_vector_path.

    Returns a stats dict with keys: ``total``, ``with_vector``, ``skipped``,
    ``emotion_counts``.
    """
    input_dataset = Path(input_dataset)
    output_manifest = Path(output_manifest) if output_manifest else input_dataset
    emotion_csv_mapping = dict(emotion_csv_mapping or {})
    emotion_translation = dict(emotion_translation or {})

    emotion_centroids: Optional[dict[str, np.ndarray]] = None
    if style_bank_path is not None and output_vectors_dir is not None:
        emotion_centroids = _load_bank_centroids(style_bank_path)

    counts: Counter[str] = Counter()
    total = 0
    with_vector = 0
    skipped_vector = 0

    # Stream read -> stream write to avoid loading 500k rows into memory.
    tmp_out = Path(str(output_manifest) + ".tmp")
    tmp_out.parent.mkdir(parents=True, exist_ok=True)
    with open(input_dataset, "r", encoding="utf-8") as src, open(
        tmp_out, "w", encoding="utf-8"
    ) as dst:
        for line in tqdm(src, desc="Injecting labels"):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                _LOGGER.warning("Skipping malformed JSONL line: %s", exc)
                continue

            audio_path = item.get("audio_norm_path") or item.get("audio_path") or ""
            utt_id = Path(audio_path).stem if audio_path else ""

            if "emotion" in item and item["emotion"] is not None:
                _LOGGER.debug(
                    "Overwriting existing emotion for utt_id=%s", utt_id
                )
            emotion = _resolve_emotion(
                utt_id=utt_id,
                audio_path=audio_path,
                emotion_csv_mapping=emotion_csv_mapping,
                emotion_translation=emotion_translation,
                default_emotion=default_emotion,
            )
            item["emotion"] = emotion
            counts[emotion] += 1

            vec_path = _resolve_style_vector_path(
                utt_id=utt_id,
                style_vectors_dir=style_vectors_dir,
                dataset_dir=dataset_dir,
                output_dir=output_vectors_dir,
                emotion=emotion,
                emotion_centroids=emotion_centroids,
            )
            if vec_path is not None:
                with_vector += 1
                item["style_vector_path"] = vec_path
            else:
                if style_vectors_dir is not None or emotion_centroids is not None:
                    skipped_vector += 1
                item["style_vector_path"] = None

            dst.write(json.dumps(item, ensure_ascii=False) + "\n")
            total += 1

    tmp_out.replace(output_manifest)
    _LOGGER.info(
        "Injection complete: total=%d, with_vector=%d, skipped_vector=%d",
        total,
        with_vector,
        skipped_vector,
    )
    _LOGGER.info("Emotion distribution: %s", dict(counts))
    return {
        "total": total,
        "with_vector": with_vector,
        "skipped": skipped_vector,
        "emotion_counts": dict(counts),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_argv(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject emotion + style_vector_path fields into a dataset manifest",
    )
    parser.add_argument("--input-dataset", type=Path, required=True)
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=None,
        help="Output JSONL path (default: overwrite --input-dataset)",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Root of the dataset; used to write relative style_vector_path",
    )
    parser.add_argument(
        "--style-vectors-dir",
        type=Path,
        default=None,
        help="Existing directory containing <utt_id>.npy embeddings",
    )
    parser.add_argument(
        "--emotion-csv",
        type=Path,
        default=None,
        help="CSV mapping utt_id,emotion",
    )
    parser.add_argument(
        "--emotion-map",
        type=Path,
        default=None,
        help="JSON dict mapping friendly label -> dataset code (inverted internally)",
    )
    parser.add_argument(
        "--default-emotion",
        default="neutral",
        help="Fallback label when an utterance has no CSV mapping",
    )
    parser.add_argument(
        "--style-bank",
        type=Path,
        default=None,
        help=(
            "Optional .npz style bank. If combined with --output-dir, "
            "per-utterance vectors are materialised from the bank's centroids."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write materialised <utt_id>.npy files (requires --style-bank)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_argv(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    emotion_csv_mapping: dict[str, str] = {}
    if args.emotion_csv is not None:
        emotion_csv_mapping = load_emotion_mapping_from_csv(args.emotion_csv)
        _LOGGER.info("Loaded %d emotion CSV entries", len(emotion_csv_mapping))

    emotion_translation: dict[str, str] = {}
    if args.emotion_map is not None:
        emotion_translation = load_emotion_map(args.emotion_map)
        _LOGGER.info("Loaded emotion map: %d keys", len(emotion_translation))

    if args.style_bank is not None and emotion_csv_mapping:
        missing = validate_emotions_against_bank(emotion_csv_mapping, args.style_bank)
        if missing:
            _LOGGER.warning("Emotions in CSV not present in style bank: %s", sorted(missing))

    if args.output_dir is not None and args.style_bank is None:
        _LOGGER.warning(
            "--output-dir is ignored because --style-bank was not provided"
        )

    inject_style_labels(
        input_dataset=args.input_dataset,
        output_manifest=args.output_manifest,
        dataset_dir=args.dataset_dir,
        style_vectors_dir=args.style_vectors_dir,
        emotion_csv_mapping=emotion_csv_mapping,
        emotion_translation=emotion_translation,
        default_emotion=args.default_emotion,
        style_bank_path=args.style_bank,
        output_vectors_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
