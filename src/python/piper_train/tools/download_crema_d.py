#!/usr/bin/env python3
"""Download CREMA-D dataset and prepare LJSpeech-style metadata.

CREMA-D (Crowd-sourced Emotional Multimodal Actors Dataset) is a dataset of
7,442 audio clips from 91 actors (46 female, 45 male) performing 12 sentences
with 6 emotions (angry, disgusted, fearful, happy, neutral, sad).

License: Open Database License (ODbL) 1.0 + Community License (commercial OK,
attribution recommended).

Reference:
    Cao et al. 2014, "CREMA-D: Crowd-sourced Emotional Multimodal Actors Dataset"
    https://github.com/CheyneyComputerScience/CREMA-D

Usage:
    # Full download + metadata generation
    uv run python -m piper_train.tools.download_crema_d \\
        --data-dir /data/piper/datasets/CREMA-D

    # Skip download if directory already exists
    uv run python -m piper_train.tools.download_crema_d \\
        --data-dir /data/piper/datasets/CREMA-D \\
        --skip-if-exists

    # Only verify + regenerate metadata (assumes repo already cloned)
    uv run python -m piper_train.tools.download_crema_d \\
        --data-dir /data/piper/datasets/CREMA-D \\
        --verify-only

Output layout (after successful run)::

    <data-dir>/
        AudioWAV/
            1001_DFA_ANG_XX.wav
            ...
        metadata.csv          # LJSpeech-compatible: <utt_id>|<text>|<emotion>
        emotions.csv          # <utt_id>,<emotion>  (for inject_style_labels.py)
        LICENSE_CREMA_D.txt   # ODbL license text (if extractable)
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import time
from pathlib import Path

try:
    import soundfile as sf
except ImportError:  # pragma: no cover - handled at runtime
    sf = None  # type: ignore[assignment]

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - fallback when tqdm missing in tests
    def tqdm(iterable, **_kwargs):  # type: ignore[misc]
        return iterable

_LOGGER = logging.getLogger("download_crema_d")

CREMA_D_REPO = "https://github.com/CheyneyComputerScience/CREMA-D.git"
EXPECTED_WAV_COUNT = 7442

# Filename convention: <speaker>_<sentence>_<emotion>_<intensity>.wav
# e.g. 1001_DFA_ANG_XX.wav  --> actor 1001, sentence DFA, emotion ANG, intensity XX
EMOTION_CODE_MAP = {
    "ANG": "angry",
    "DIS": "disgusted",
    "FEA": "fearful",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}

# CREMA-D 12 sentences (official order)
SENTENCE_MAP = {
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

# License attribution (copied if the repo's LICENSE file cannot be located)
_FALLBACK_LICENSE_TEXT = """\
CREMA-D is distributed under the Open Database License (ODbL) 1.0 and the
Community License as described in the official repository:
https://github.com/CheyneyComputerScience/CREMA-D

Citation:
    Cao, H., Cooper, D. G., Keutmann, M. K., Gur, R. C., Nenkova, A., &
    Verma, R. (2014). CREMA-D: Crowd-sourced Emotional Multimodal Actors
    Dataset. IEEE Transactions on Affective Computing, 5(4), 377-390.

ODbL 1.0 full text: https://opendatacommons.org/licenses/odbl/1-0/
"""


def parse_filename(stem: str) -> tuple[str, str, str, str] | None:
    """Parse CREMA-D filename stem into (speaker, sentence, emotion, intensity).

    Returns ``None`` if the filename does not match the 4-part convention.
    """
    parts = stem.split("_")
    if len(parts) < 4:
        return None
    speaker, sentence, emotion_code, intensity = parts[:4]
    return speaker, sentence, emotion_code, intensity


def download(data_dir: Path, skip_if_exists: bool = False) -> None:
    """Clone CREMA-D repository via ``git clone --depth=1``."""
    if data_dir.exists():
        if skip_if_exists:
            _LOGGER.info("Skipping download; directory already exists: %s", data_dir)
            return
        if any(data_dir.iterdir()):
            _LOGGER.warning(
                "Target directory is not empty: %s -- git clone may fail", data_dir
            )
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    _LOGGER.info("Cloning CREMA-D from %s into %s", CREMA_D_REPO, data_dir)
    start = time.time()
    subprocess.run(
        ["git", "clone", "--depth=1", CREMA_D_REPO, str(data_dir)],
        check=True,
    )
    elapsed = time.time() - start
    _LOGGER.info("git clone finished in %.1fs", elapsed)


def verify(data_dir: Path, sample_n: int = 100) -> dict:
    """Verify WAV count and sample format. Returns a stats dict.

    Args:
        data_dir: CREMA-D directory (must contain ``AudioWAV/``).
        sample_n: Number of WAVs to sample-verify for samplerate/bitdepth.

    Returns:
        ``{"wav_count": int, "bad_files": list[tuple[str, str]]}``
    """
    audio_dir = data_dir / "AudioWAV"
    if not audio_dir.exists():
        raise FileNotFoundError(f"AudioWAV directory not found: {audio_dir}")

    wav_files = sorted(audio_dir.glob("*.wav"))
    wav_count = len(wav_files)
    _LOGGER.info("WAV count: %d (expected ~%d)", wav_count, EXPECTED_WAV_COUNT)
    if abs(wav_count - EXPECTED_WAV_COUNT) > 1:
        _LOGGER.warning(
            "WAV count deviates from expected: got %d, expected ~%d",
            wav_count,
            EXPECTED_WAV_COUNT,
        )

    bad_files: list[tuple[str, str]] = []
    if sf is None:
        _LOGGER.warning(
            "soundfile not available -- skipping per-file format verification"
        )
    else:
        sample_files = wav_files[:sample_n]
        for wav_file in tqdm(sample_files, desc="Verifying sample"):
            try:
                info = sf.info(str(wav_file))
                if info.samplerate != 16000:
                    bad_files.append((wav_file.name, f"sr={info.samplerate}"))
                if info.subtype != "PCM_16":
                    bad_files.append((wav_file.name, f"subtype={info.subtype}"))
            except Exception as exc:  # pragma: no cover - defensive
                bad_files.append((wav_file.name, str(exc)))

    if bad_files:
        _LOGGER.warning(
            "Found %d problematic files (sample of %d)", len(bad_files), sample_n
        )
        for fn, err in bad_files[:10]:
            _LOGGER.warning("  %s: %s", fn, err)

    return {"wav_count": wav_count, "bad_files": bad_files}


def generate_metadata(data_dir: Path) -> dict:
    """Generate ``metadata.csv`` and ``emotions.csv`` from AudioWAV filenames.

    Returns a dict summarising counts per emotion plus skipped entries.
    """
    audio_dir = data_dir / "AudioWAV"
    if not audio_dir.exists():
        raise FileNotFoundError(f"AudioWAV directory not found: {audio_dir}")

    metadata_path = data_dir / "metadata.csv"
    emotions_path = data_dir / "emotions.csv"

    emotion_counts: dict[str, int] = {}
    skipped: list[str] = []
    total = 0

    with open(metadata_path, "w", encoding="utf-8") as meta_f, open(
        emotions_path, "w", encoding="utf-8"
    ) as emo_f:
        meta_f.write(
            "# CREMA-D metadata (utt_id|text|emotion) -- "
            "License: ODbL 1.0 + Community License\n"
        )
        emo_f.write("# utt_id,emotion\n")
        for wav_file in sorted(audio_dir.glob("*.wav")):
            parsed = parse_filename(wav_file.stem)
            if parsed is None:
                _LOGGER.warning("Skipping malformed filename: %s", wav_file.name)
                skipped.append(wav_file.name)
                continue
            _speaker, sentence_code, emotion_code, _intensity = parsed
            emotion = EMOTION_CODE_MAP.get(emotion_code)
            if not emotion:
                _LOGGER.warning(
                    "Unknown emotion code '%s' in %s", emotion_code, wav_file.name
                )
                skipped.append(wav_file.name)
                continue
            text = SENTENCE_MAP.get(sentence_code, sentence_code)
            utt_id = wav_file.stem
            meta_f.write(f"{utt_id}|{text}|{emotion}\n")
            emo_f.write(f"{utt_id},{emotion}\n")
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            total += 1

    _LOGGER.info(
        "metadata.csv (%d rows) and emotions.csv written under %s",
        total,
        data_dir,
    )
    _LOGGER.info("Emotion distribution: %s", emotion_counts)
    return {
        "total": total,
        "skipped": skipped,
        "emotion_counts": emotion_counts,
        "metadata_path": str(metadata_path),
        "emotions_path": str(emotions_path),
    }


def copy_license(data_dir: Path) -> Path:
    """Copy LICENSE file from the repo (or write fallback ODbL text)."""
    license_out = data_dir / "LICENSE_CREMA_D.txt"

    # CREMA-D repo historically provides LICENSE.txt at the root.
    candidate_names = ["LICENSE.txt", "LICENSE", "LICENSE.md"]
    for name in candidate_names:
        src = data_dir / name
        if src.exists() and src.is_file():
            shutil.copy(src, license_out)
            _LOGGER.info("Copied license from %s -> %s", src, license_out)
            return license_out

    license_out.write_text(_FALLBACK_LICENSE_TEXT, encoding="utf-8")
    _LOGGER.info(
        "License source file not found; wrote fallback attribution to %s",
        license_out,
    )
    return license_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download CREMA-D dataset and build LJSpeech-style metadata",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Target directory (will be created if missing)",
    )
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Skip git clone if --data-dir already exists",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip download; only verify and regenerate metadata",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    start = time.time()

    if not args.verify_only:
        download(args.data_dir, skip_if_exists=args.skip_if_exists)

    stats = verify(args.data_dir)
    _LOGGER.info("Verify stats: wav_count=%d", stats["wav_count"])

    generate_metadata(args.data_dir)
    copy_license(args.data_dir)

    elapsed = time.time() - start
    _LOGGER.info(
        "CREMA-D preparation complete in %.1fs: %s", elapsed, args.data_dir
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
