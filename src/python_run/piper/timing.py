"""Phoneme timing extraction from ONNX model duration output.

VITS models optionally output a ``durations`` tensor [1, phoneme_length]
containing the number of frames (hop_length-sized) each phoneme occupies.
This module converts frame counts to millisecond timestamps.

The calculation logic matches the Rust (``timing.rs``) and Go
(``timing.go``) implementations exactly.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass


logger = logging.getLogger(__name__)

DEFAULT_HOP_LENGTH: int = 256


@dataclass
class PhonemeTimingInfo:
    """Timing information for a single phoneme.

    Attributes
    ----------
    phoneme : str
        Phoneme token string. May be a regular character (e.g. ``'a'``, ``'k'``),
        a multi-char name (e.g. ``'ch'``, ``'N_m'``), or a PUA fallback
        (e.g. ``'U+E019'``) when no explicit mapping is provided.
    start_ms : float
        Start time in milliseconds from the beginning of the utterance.
    end_ms : float
        End time in milliseconds from the beginning of the utterance.
        Always equals the next phoneme's ``start_ms`` (continuous boundaries).
    duration_ms : float
        Duration of this phoneme in milliseconds (= ``end_ms - start_ms``).
        Non-negative; negative input frames are clamped to zero.
    """

    phoneme: str
    start_ms: float
    end_ms: float
    duration_ms: float


@dataclass
class TimingResult:
    """Complete timing result for a synthesized utterance.

    Attributes
    ----------
    phonemes : list[PhonemeTimingInfo]
        Phoneme-by-phoneme timing entries in synthesis order.
    total_duration_ms : float
        Total utterance duration in milliseconds. Equals the last phoneme's
        ``end_ms`` (or 0.0 for empty input).
    sample_rate : int
        Audio sample rate in Hz (e.g. 22050). Inherited from the model config.
    """

    phonemes: list[PhonemeTimingInfo]
    total_duration_ms: float
    sample_rate: int


def durations_to_timing(
    durations: Sequence[float],
    phoneme_tokens: Sequence[str],
    sample_rate: int,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> TimingResult:
    """Convert duration tensor output to timing information.

    Parameters
    ----------
    durations:
        Duration values (frame counts) from the ONNX output tensor.
    phoneme_tokens:
        Corresponding phoneme token strings (same length as *durations*).
    sample_rate:
        Audio sample rate (e.g. 22050).
    hop_length:
        STFT hop length (typically 256 for VITS).

    Returns
    -------
    TimingResult
        Timing result with start/end timestamps for each phoneme.

    Raises
    ------
    ValueError
        If inputs are invalid (length mismatch, non-positive rate/hop).
    """
    if len(durations) != len(phoneme_tokens):
        raise ValueError(
            f"length mismatch: durations has {len(durations)} elements "
            f"but phoneme_tokens has {len(phoneme_tokens)}"
        )
    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate}")
    if hop_length <= 0:
        raise ValueError(f"hop_length must be positive, got {hop_length}")

    frame_time_ms = (hop_length / sample_rate) * 1000.0

    phonemes: list[PhonemeTimingInfo] = []
    cursor_ms: float = 0.0

    for i, (dur, token) in enumerate(zip(durations, phoneme_tokens, strict=False)):
        if dur < 0:
            logger.warning(
                "negative phoneme duration clamped to 0: "
                "index=%d, phoneme=%r, value=%s",
                i,
                token,
                dur,
            )
        dur_frames = max(dur, 0.0)
        duration_ms = dur_frames * frame_time_ms
        start_ms = cursor_ms
        end_ms = cursor_ms + duration_ms

        phonemes.append(
            PhonemeTimingInfo(
                phoneme=token,
                start_ms=start_ms,
                end_ms=end_ms,
                duration_ms=duration_ms,
            )
        )

        cursor_ms = end_ms

    return TimingResult(
        phonemes=phonemes,
        total_duration_ms=cursor_ms,
        sample_rate=sample_rate,
    )


def timing_to_json(result: TimingResult) -> str:
    """Serialize a timing result to pretty-printed JSON."""
    return json.dumps(asdict(result), indent=2, ensure_ascii=False)


def timing_to_json_compact(result: TimingResult) -> str:
    """Serialize a timing result to compact (single-line) JSON."""
    return json.dumps(asdict(result), ensure_ascii=False)


def timing_to_tsv(result: TimingResult) -> str:
    """Serialize a timing result to TSV with a header line.

    Format matches the Rust and Go implementations::

        start_ms\\tend_ms\\tduration_ms\\tphoneme
        0.000\\t11.610\\t11.610\\ta
    """
    lines: list[str] = ["start_ms\tend_ms\tduration_ms\tphoneme\n"]
    for p in result.phonemes:
        # Escape tab and newline characters to preserve TSV format.
        escaped = p.phoneme.replace("\t", "\\t").replace("\n", "\\n")
        lines.append(
            f"{p.start_ms:.3f}\t{p.end_ms:.3f}\t{p.duration_ms:.3f}\t{escaped}\n"
        )
    return "".join(lines)


def timing_to_srt(result: TimingResult) -> str:
    """Serialize a timing result to SRT subtitle format.

    Matches the Rust implementation (``TimingResult::to_srt``).
    """
    parts: list[str] = []
    for i, p in enumerate(result.phonemes, 1):
        start = _format_srt_timestamp(p.start_ms)
        end = _format_srt_timestamp(p.end_ms)
        parts.append(f"{i}\n{start} --> {end}\n{p.phoneme}\n\n")
    return "".join(parts)


def _format_srt_timestamp(ms: float) -> str:
    """Format milliseconds as SRT timestamp: ``HH:MM:SS,mmm``."""
    total_ms = round(ms)
    millis = total_ms % 1000
    total_secs = total_ms // 1000
    secs = total_secs % 60
    total_mins = total_secs // 60
    mins = total_mins % 60
    hours = total_mins // 60
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def build_phoneme_id_reverse_map(
    phoneme_id_map: dict[str, list[int]],
    pua_to_multi_char: dict[str, str] | None = None,
) -> dict[int, str]:
    """Build a reverse map from phoneme ID to display name.

    Parameters
    ----------
    phoneme_id_map:
        Mapping from config.json: ``{"a": [5], ...}``.  Each key is a
        phoneme character and the value is a list of integer IDs assigned
        to that phoneme.
    pua_to_multi_char:
        Optional mapping from PUA single characters to human-readable
        multi-character names (e.g. ``{"\\uE019": "N_m"}``).

    Returns
    -------
    dict[int, str]
        Mapping from phoneme ID to display name.  PUA characters
        (U+E000..U+F8FF) without an explicit mapping are rendered as
        ``U+XXXX``.
    """
    if pua_to_multi_char is None:
        pua_to_multi_char = {}

    reverse_map: dict[int, str] = {}

    for char, ids in phoneme_id_map.items():
        # Determine the display name for this character.
        if char in pua_to_multi_char:
            display = pua_to_multi_char[char]
        elif len(char) == 1 and 0xE000 <= ord(char) <= 0xF8FF:
            display = f"U+{ord(char):04X}"
        else:
            display = char

        for phoneme_id in ids:
            # First-wins semantics: preserve the first mapping seen for an ID.
            # Matches the JS implementation in src/wasm/openjtalk-web/src/timing.js.
            if phoneme_id not in reverse_map:
                reverse_map[phoneme_id] = display

    return reverse_map
