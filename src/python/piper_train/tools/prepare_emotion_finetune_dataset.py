"""CREMA-D (or similar emotion corpus) → piper-train fine-tune dataset.

Converts a directory of CREMA-D ``AudioWAV/`` files into a piper-train-compatible
dataset (``dataset.jsonl`` + ``config.json``) suitable for feeding the
``--style-vector-dim 256`` fine-tune path.

Usage:
    uv run python -m piper_train.tools.prepare_emotion_finetune_dataset \\
        --crema-d-dir /data/piper/datasets/CREMA-D \\
        --style-vectors-dir /data/piper/style_vectors_crema_d \\
        --output-dir /data/piper/dataset-crema-d-emotion \\
        --base-config /data/piper/dataset-multilingual-6lang-filtered/config.json \\
        --style-vector-dim 256

The style_vectors directory is expected to already contain one ``.npy`` file
per utterance (same stem as the WAV file) — produced earlier by
``build_pea_style_bank.py --per-utterance-dir``.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path


_LOGGER = logging.getLogger("prepare_emotion_finetune_dataset")

# CREMA-D emotion tag (filename token) -> canonical lowercase label
EMOTION_MAP: dict[str, str] = {
    "ANG": "angry",
    "DIS": "disgusted",
    "FEA": "fearful",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}

# CREMA-D ships 12 fixed sentences keyed by three-letter ID
CREMA_D_SENTENCES: dict[str, str] = {
    "IEO": "It's eleven o'clock.",
    "TIE": "That is exactly what happened.",
    "IOM": "I'm on my way to the meeting.",
    "IWW": "I wonder what this is about.",
    "TAI": "The airplane is almost full.",
    "MTI": "Maybe tomorrow it will be cold.",
    "IWL": "I would like a new alarm clock.",
    "ITH": "I think I have a doctor's appointment.",
    "DFA": "Don't forget a jacket.",
    "ITS": "I think I've seen this before.",
    "TSI": "The surface is slick.",
    "WSI": "We'll stop in a couple of minutes.",
}

DEFAULT_STYLE_VECTOR_DIM = 256
DEFAULT_STYLE_CONDITION_MODE = "global"
DEFAULT_STYLE_CONDITION_DROPOUT = 0.1


def _get_crema_d_text(sentence_code: str) -> str:
    """Resolve the English text for a CREMA-D sentence token (``IEO`` etc.)."""
    return CREMA_D_SENTENCES.get(sentence_code, "")


def _iter_wav_files(audio_wav_dir: Path) -> list[Path]:
    """Return a sorted list of CREMA-D WAV files."""
    return sorted(p for p in audio_wav_dir.glob("*.wav") if p.is_file())


def _parse_filename(wav_path: Path) -> tuple[str, str, str, str] | None:
    """Parse ``<speaker>_<sentence>_<emotion>_<intensity>.wav`` → tuple.

    Returns None on malformed filenames.
    """
    parts = wav_path.stem.split("_")
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def build_crema_d_manifest(
    crema_d_dir: Path,
    style_vectors_dir: Path,
    output_dir: Path,
    base_config_path: Path,
    style_vector_dim: int = DEFAULT_STYLE_VECTOR_DIM,
    style_condition_mode: str = DEFAULT_STYLE_CONDITION_MODE,
    style_condition_dropout: float = DEFAULT_STYLE_CONDITION_DROPOUT,
    audio_subdir: str = "AudioWAV",
) -> tuple[int, int]:
    """Convert a CREMA-D corpus into a piper-train dataset.

    Reads WAV files from ``crema_d_dir/audio_subdir/`` (default ``AudioWAV/``),
    pairs each with a pre-computed ``<stem>.npy`` in ``style_vectors_dir``, and
    writes ``output_dir/dataset.jsonl`` + ``output_dir/config.json``.

    Args:
        crema_d_dir: Root directory of the CREMA-D corpus (must contain
            ``AudioWAV/`` — or whatever ``audio_subdir`` points at).
        style_vectors_dir: Directory with per-utterance ``<stem>.npy`` files
            produced by build_pea_style_bank.py ``--per-utterance-dir``.
        output_dir: Destination for ``dataset.jsonl`` and ``config.json``.
        base_config_path: Path to a reference piper-train config.json (typically
            the 6lang base dataset config). ``phoneme_id_map``, ``num_languages``,
            ``prosody_dim``, etc. are inherited verbatim.
        style_vector_dim: Dim written to ``config.json``. Must match the actual
            .npy vector length.
        style_condition_mode: Value for ``style_condition_mode`` in config.
        style_condition_dropout: Value for ``style_condition_dropout`` in config.
        audio_subdir: Subdirectory under ``crema_d_dir`` that holds the WAV
            files (CREMA-D's default is ``AudioWAV``).

    Returns:
        ``(n_written, n_skipped)`` — counts for reporting.
    """
    audio_wav_dir = crema_d_dir / audio_subdir
    if not audio_wav_dir.is_dir():
        raise FileNotFoundError(
            f"Audio subdirectory not found: {audio_wav_dir}. "
            f"Pass --audio-subdir to override if your layout differs."
        )

    if not style_vectors_dir.is_dir():
        raise FileNotFoundError(f"style vectors dir not found: {style_vectors_dir}")

    if not base_config_path.is_file():
        raise FileNotFoundError(f"base config not found: {base_config_path}")

    with base_config_path.open("r", encoding="utf-8") as handle:
        base_config = json.load(handle)

    wav_files = _iter_wav_files(audio_wav_dir)
    if not wav_files:
        raise RuntimeError(f"No WAV files found under {audio_wav_dir}")

    speakers = sorted({_parse_filename(p)[0] for p in wav_files if _parse_filename(p)})
    speaker_id_map = {spk: idx for idx, spk in enumerate(speakers)}
    _LOGGER.info(
        "Found %d WAV files, %d unique speakers", len(wav_files), len(speakers)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "dataset.jsonl"

    n_written = 0
    n_skipped = 0
    with jsonl_path.open("w", encoding="utf-8") as f_out:
        for wav_path in wav_files:
            parsed = _parse_filename(wav_path)
            if parsed is None:
                _LOGGER.warning("Malformed filename, skipping: %s", wav_path.name)
                n_skipped += 1
                continue
            spk, sent, emo, _intensity = parsed
            if emo not in EMOTION_MAP:
                _LOGGER.warning("Unknown emotion %s, skipping: %s", emo, wav_path.name)
                n_skipped += 1
                continue

            text = _get_crema_d_text(sent)
            if not text:
                _LOGGER.warning(
                    "Unknown sentence code %s, skipping: %s", sent, wav_path.name
                )
                n_skipped += 1
                continue

            style_vec_path = style_vectors_dir / f"{wav_path.stem}.npy"
            if not style_vec_path.exists():
                _LOGGER.warning("Missing style vector, skipping: %s", style_vec_path)
                n_skipped += 1
                continue

            record = {
                "audio_path": str(wav_path.resolve()),
                "text": text,
                "speaker": spk,
                "speaker_id": speaker_id_map[spk],
                "language": "en",
                "style_vector_path": str(style_vec_path.resolve()),
                "emotion": EMOTION_MAP[emo],
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_written += 1

    _LOGGER.info(
        "Wrote %d samples to %s (%d skipped)", n_written, jsonl_path, n_skipped
    )

    # config.json — inherit everything from the 6lang base, then override
    config = dict(base_config)
    config["num_speakers"] = len(speakers)
    config["style_vector_dim"] = style_vector_dim
    config["style_condition_mode"] = style_condition_mode
    config["style_condition_dropout"] = style_condition_dropout
    config.setdefault("audio", {}).setdefault("sample_rate", 22050)

    # Keep num_languages from the base (don't accidentally collapse to 1 —
    # the 6lang base checkpoint's emb_lang must stay intact for fine-tune).
    config_path = output_dir / "config.json"
    with config_path.open("w", encoding="utf-8") as f_out:
        json.dump(config, f_out, indent=2, ensure_ascii=False)
    _LOGGER.info(
        "Wrote config: %s (num_speakers=%d, style_vector_dim=%d)",
        config_path,
        len(speakers),
        style_vector_dim,
    )

    return n_written, n_skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crema-d-dir", type=Path, required=True)
    parser.add_argument("--style-vectors-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument(
        "--style-vector-dim", type=int, default=DEFAULT_STYLE_VECTOR_DIM
    )
    parser.add_argument(
        "--style-condition-mode", type=str, default=DEFAULT_STYLE_CONDITION_MODE
    )
    parser.add_argument(
        "--style-condition-dropout", type=float, default=DEFAULT_STYLE_CONDITION_DROPOUT
    )
    parser.add_argument(
        "--audio-subdir",
        type=str,
        default="AudioWAV",
        help="Subdirectory under --crema-d-dir holding the WAV files (default: AudioWAV)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    build_crema_d_manifest(
        crema_d_dir=args.crema_d_dir,
        style_vectors_dir=args.style_vectors_dir,
        output_dir=args.output_dir,
        base_config_path=args.base_config,
        style_vector_dim=args.style_vector_dim,
        style_condition_mode=args.style_condition_mode,
        style_condition_dropout=args.style_condition_dropout,
        audio_subdir=args.audio_subdir,
    )


if __name__ == "__main__":
    main()
