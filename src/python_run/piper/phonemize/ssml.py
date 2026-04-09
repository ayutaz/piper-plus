"""SSML integration for the piper-plus runtime phonemization pipeline.

Provides :func:`process_ssml` which detects SSML input, splits it into
segments, and returns typed segments that the synthesis caller can
iterate over.

The canonical SSML parser lives in ``piper_plus_g2p.ssml``.  When that
package is available it is used directly.  Otherwise a lightweight
fallback is bundled here so that the runtime stays self-contained.

Usage at synthesis time::

    from piper.phonemize.ssml import process_ssml, SynthesisSegment

    segments = process_ssml(text)
    for seg in segments:
        if seg.phoneme_text:
            phoneme_ids = phonemize_and_encode(seg.phoneme_text)
            audio = synthesize(phoneme_ids, length_scale=seg.length_scale)
            # ... write audio ...
        if seg.silence_samples > 0:
            # ... append zero samples ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass


_LOGGER = logging.getLogger(__name__)

# Try importing the canonical parser from the G2P package.  If it is not
# installed (the runtime package does not list it as a hard dependency),
# fall back to a minimal re-implementation that covers the same SSML
# subset without adding a new requirement.
try:
    from piper_plus_g2p.ssml import SSMLParser, SSMLSegment  # noqa: F401
except ImportError:
    import re
    import xml.etree.ElementTree as ET
    from dataclasses import dataclass as _dataclass

    @_dataclass
    class SSMLSegment:  # type: ignore[no-redef]
        text: str
        break_ms: int = 0
        rate: float = 1.0

    class SSMLParser:  # type: ignore[no-redef]
        BREAK_STRENGTH_MS = {
            "none": 0,
            "x-weak": 100,
            "weak": 200,
            "medium": 400,
            "strong": 700,
            "x-strong": 1000,
        }
        RATE_NAMES = {
            "x-slow": 1.5,
            "slow": 1.25,
            "medium": 1.0,
            "fast": 0.8,
            "x-fast": 0.6,
        }
        _RE_SSML = re.compile(r"^\s*<speak[\s>]", re.DOTALL)

        @staticmethod
        def is_ssml(text: str) -> bool:
            return bool(SSMLParser._RE_SSML.search(text))

        @staticmethod
        def parse(ssml_text: str) -> list:
            if not SSMLParser.is_ssml(ssml_text):
                return [SSMLSegment(text=ssml_text)]
            try:
                root = ET.fromstring(ssml_text)  # noqa: S314
            except ET.ParseError:
                stripped = re.sub(r"<[^>]*>", "", ssml_text).strip()
                return [SSMLSegment(text=stripped if stripped else ssml_text)]
            segments: list = []
            SSMLParser._walk(root, 1.0, segments)
            merged = [s for s in segments if s.text.strip() or s.break_ms > 0]
            return merged if merged else [SSMLSegment(text="")]

        @staticmethod
        def _walk(element, rate, segments):
            tag = element.tag.split("}", 1)[-1] if "}" in element.tag else element.tag
            if tag == "break":
                bms = SSMLParser._resolve_break(element)
                segments.append(SSMLSegment(text="", break_ms=bms, rate=rate))
                if element.tail and element.tail.strip():
                    segments.append(SSMLSegment(text=element.tail.strip(), rate=rate))
                return
            if tag == "prosody":
                ra = element.get("rate")
                if ra is not None:
                    rate = SSMLParser._parse_rate(ra)
            if element.text and element.text.strip():
                segments.append(SSMLSegment(text=element.text.strip(), rate=rate))
            for child in element:
                SSMLParser._walk(child, rate, segments)
                if child.tail and child.tail.strip():
                    segments.append(SSMLSegment(text=child.tail.strip(), rate=rate))

        @staticmethod
        def _resolve_break(element):
            t = element.get("time")
            if t is not None:
                return SSMLParser._parse_break_time(t)
            s = element.get("strength")
            if s is not None:
                return SSMLParser.BREAK_STRENGTH_MS.get(s.lower(), 400)
            return 400

        @staticmethod
        def _parse_break_time(time_str):
            time_str = time_str.strip().lower()
            if time_str.endswith("ms"):
                try:
                    return int(float(time_str[:-2]))
                except ValueError:
                    return 0
            if time_str.endswith("s"):
                try:
                    return int(float(time_str[:-1]) * 1000)
                except ValueError:
                    return 0
            try:
                return int(float(time_str))
            except ValueError:
                return 0

        @staticmethod
        def _parse_rate(rate_str):
            rate_str = rate_str.strip().lower()
            if rate_str in SSMLParser.RATE_NAMES:
                return SSMLParser.RATE_NAMES[rate_str]
            if rate_str.endswith("%"):
                try:
                    pct = float(rate_str[:-1])
                    return 100.0 / pct if pct > 0 else 1.0
                except ValueError:
                    return 1.0
            try:
                val = float(rate_str)
                return val if val > 0 else 1.0
            except ValueError:
                return 1.0


__all__ = ["SynthesisSegment", "process_ssml"]


@dataclass
class SynthesisSegment:
    """A segment ready for the synthesis pipeline.

    Attributes
    ----------
    phoneme_text : str
        Text to be phonemized. Empty string means silence-only.
    length_scale : float
        Duration multiplier passed to the VITS decoder.
        Derived from ``SSMLSegment.rate``.
    silence_ms : int
        Silence to insert after this segment's audio, in milliseconds.
    """

    phoneme_text: str
    length_scale: float = 1.0
    silence_ms: int = 0

    @property
    def silence_samples(self) -> int:
        """Number of zero samples at 22050 Hz for the requested silence."""
        return int(self.silence_ms * 22.05)


def process_ssml(text: str) -> list[SynthesisSegment]:
    """Convert input text (plain or SSML) into synthesis segments.

    Parameters
    ----------
    text : str
        Raw text or SSML markup.

    Returns
    -------
    list[SynthesisSegment]
        Segments suitable for sequential synthesis.  Each segment carries
        the text to phonemize, a ``length_scale`` derived from SSML
        ``<prosody rate>``, and a post-segment silence duration.
    """
    ssml_segments = SSMLParser.parse(text)

    result: list[SynthesisSegment] = []
    for seg in ssml_segments:
        result.append(
            SynthesisSegment(
                phoneme_text=seg.text,
                length_scale=seg.rate,
                silence_ms=seg.break_ms,
            )
        )

    return result
