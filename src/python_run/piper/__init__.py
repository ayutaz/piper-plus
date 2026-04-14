from importlib.metadata import PackageNotFoundError, version

from .timing import (
    PhonemeTimingInfo,
    TimingResult,
    build_phoneme_id_reverse_map,
    durations_to_timing,
    timing_to_json,
    timing_to_json_compact,
    timing_to_srt,
    timing_to_tsv,
)
from .voice import PiperVoice


try:
    __version__ = version("piper-plus")
except PackageNotFoundError:
    # Fallback for development (running from source tree)
    from pathlib import Path

    _VERSION_FILE = Path(__file__).parent.parent.parent.parent / "VERSION"
    __version__ = (
        _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
    )

__all__ = [
    "PhonemeTimingInfo",
    "PiperVoice",
    "TimingResult",
    "__version__",
    "build_phoneme_id_reverse_map",
    "durations_to_timing",
    "timing_to_json",
    "timing_to_json_compact",
    "timing_to_srt",
    "timing_to_tsv",
]
