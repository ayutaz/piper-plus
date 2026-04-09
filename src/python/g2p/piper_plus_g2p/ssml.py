"""SSML (Speech Synthesis Markup Language) basic tag parser.

Supports a subset of SSML W3C spec:
- <speak> root element
- <break time="500ms"/> or <break time="1s"/> for silence
- <break strength="medium"/> for predefined silence durations
- <prosody rate="slow">text</prosody> for speech rate control

Unknown tags are gracefully degraded by extracting their text content.
XML syntax errors cause a fallback to plain-text processing.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum

_LOGGER = logging.getLogger(__name__)

# Limit SSML input size to mitigate XML parsing DoS (e.g. billion laughs).
_MAX_SSML_SIZE = 100_000  # 100 KB

__all__ = ["BreakStrength", "SSMLSegment", "SSMLParser"]


class BreakStrength(Enum):
    """Predefined break strength levels per W3C SSML spec."""

    NONE = "none"  # 0ms
    X_WEAK = "x-weak"  # 100ms
    WEAK = "weak"  # 200ms
    MEDIUM = "medium"  # 400ms
    STRONG = "strong"  # 700ms
    X_STRONG = "x-strong"  # 1000ms


@dataclass
class SSMLSegment:
    """A segment produced by SSML parsing.

    Attributes
    ----------
    text : str
        Text to phonemize. Empty string indicates a silence-only segment.
    break_ms : int
        Silence duration in milliseconds to insert after this segment.
    rate : float
        Speech rate multiplier. Maps to ``length_scale`` at synthesis time.
        Values > 1.0 mean slower speech; values < 1.0 mean faster speech.
    """

    text: str
    break_ms: int = 0
    rate: float = 1.0


class SSMLParser:
    """Parser for a basic subset of SSML tags.

    Class-level constants map symbolic names to concrete durations/rates.
    All methods are static so the parser carries no mutable state.
    """

    BREAK_STRENGTH_MS: dict[str, int] = {
        "none": 0,
        "x-weak": 100,
        "weak": 200,
        "medium": 400,
        "strong": 700,
        "x-strong": 1000,
    }

    RATE_NAMES: dict[str, float] = {
        "x-slow": 1.5,
        "slow": 1.25,
        "medium": 1.0,
        "fast": 0.8,
        "x-fast": 0.6,
    }

    # Regex for detecting SSML: starts with optional whitespace then <speak
    _RE_SSML = re.compile(r"^\s*<speak[\s>]", re.DOTALL)

    @staticmethod
    def is_ssml(text: str) -> bool:
        """Return True if *text* looks like an SSML document.

        Detection is based on the presence of a ``<speak`` opening tag
        near the start of the string.
        """
        return bool(SSMLParser._RE_SSML.search(text))

    @staticmethod
    def parse(ssml_text: str) -> list[SSMLSegment]:
        """Parse an SSML string into a list of :class:`SSMLSegment`.

        If *ssml_text* is not valid XML the entire string is returned as
        a single plain-text segment (graceful fallback).

        Parameters
        ----------
        ssml_text : str
            SSML markup or plain text.

        Returns
        -------
        list[SSMLSegment]
            Ordered segments ready for phonemization.
        """
        if not SSMLParser.is_ssml(ssml_text):
            # Plain text -- return as a single segment.
            return [SSMLSegment(text=ssml_text)]

        if len(ssml_text) > _MAX_SSML_SIZE:
            raise ValueError(
                f"SSML input too large: {len(ssml_text)} bytes (max: {_MAX_SSML_SIZE})"
            )

        try:
            root = ET.fromstring(ssml_text)  # noqa: S314
        except ET.ParseError:
            _LOGGER.warning(
                "SSML parse error; falling back to plain text: %s",
                ssml_text[:120],
            )
            # Strip the <speak> wrapper heuristically so the user still
            # gets audio output instead of silence.
            stripped = re.sub(r"<[^>]*>", "", ssml_text).strip()
            return [SSMLSegment(text=stripped if stripped else ssml_text)]

        segments: list[SSMLSegment] = []
        SSMLParser._walk(root, rate=1.0, segments=segments)

        # Merge empty-text segments that have no break into neighbours
        merged = SSMLParser._merge(segments)
        return merged if merged else [SSMLSegment(text="")]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _walk(
        element: ET.Element,
        rate: float,
        segments: list[SSMLSegment],
    ) -> None:
        """Recursively walk the element tree and populate *segments*."""
        tag = SSMLParser._local_tag(element.tag)

        if tag == "break":
            break_ms = SSMLParser._resolve_break(element)
            segments.append(SSMLSegment(text="", break_ms=break_ms, rate=rate))
            # <break/> has no children or tail of its own (self-closing),
            # but handle tail text if present.
            if element.tail and element.tail.strip():
                segments.append(SSMLSegment(text=element.tail.strip(), rate=rate))
            return

        # Determine rate for this scope
        if tag == "prosody":
            rate_attr = element.get("rate")
            if rate_attr is not None:
                rate = SSMLParser._parse_rate(rate_attr)

        # element.text is the text before the first child
        if element.text and element.text.strip():
            segments.append(SSMLSegment(text=element.text.strip(), rate=rate))

        # Recurse into children
        for child in element:
            SSMLParser._walk(child, rate=rate, segments=segments)
            # tail text after each child element
            if child.tail and child.tail.strip():
                # The tail inherits the *parent's* rate, not the child's.
                segments.append(SSMLSegment(text=child.tail.strip(), rate=rate))

    @staticmethod
    def _resolve_break(element: ET.Element) -> int:
        """Compute break duration in ms from a ``<break>`` element."""
        time_attr = element.get("time")
        if time_attr is not None:
            return SSMLParser._parse_break_time(time_attr)

        strength_attr = element.get("strength")
        if strength_attr is not None:
            return SSMLParser.BREAK_STRENGTH_MS.get(strength_attr.lower(), 400)

        # Default break with no attributes -> medium
        return SSMLParser.BREAK_STRENGTH_MS["medium"]

    @staticmethod
    def _parse_break_time(time_str: str) -> int:
        """Convert ``'500ms'`` or ``'1s'`` to milliseconds.

        Returns 0 for unparseable values.
        """
        time_str = time_str.strip().lower()
        if time_str.endswith("ms"):
            try:
                return int(float(time_str[:-2]))
            except ValueError:
                _LOGGER.warning("Invalid break time: %s", time_str)
                return 0
        if time_str.endswith("s"):
            try:
                return int(float(time_str[:-1]) * 1000)
            except ValueError:
                _LOGGER.warning("Invalid break time: %s", time_str)
                return 0
        # Bare number -- assume milliseconds
        try:
            return int(float(time_str))
        except ValueError:
            _LOGGER.warning("Invalid break time: %s", time_str)
            return 0

    @staticmethod
    def _parse_rate(rate_str: str) -> float:
        """Convert a rate specification to a float multiplier.

        Accepted formats:
        - Named: ``'slow'``, ``'fast'``, etc.
        - Percentage: ``'120%'`` (120% speaking rate -> length_scale 0.833)

        The returned value is the *length_scale* multiplier: > 1.0 is
        slower, < 1.0 is faster.
        """
        rate_str = rate_str.strip().lower()

        # Named rate
        if rate_str in SSMLParser.RATE_NAMES:
            return SSMLParser.RATE_NAMES[rate_str]

        # Percentage
        if rate_str.endswith("%"):
            try:
                pct = float(rate_str[:-1])
                if pct <= 0:
                    _LOGGER.warning("Invalid rate percentage: %s", rate_str)
                    return 1.0
                # 120% speaking rate means faster -> length_scale = 100/120
                return 100.0 / pct
            except ValueError:
                _LOGGER.warning("Invalid rate percentage: %s", rate_str)
                return 1.0

        # Bare float (treat as direct multiplier for length_scale)
        try:
            val = float(rate_str)
            if val <= 0:
                _LOGGER.warning("Invalid rate value: %s", rate_str)
                return 1.0
            return val
        except ValueError:
            _LOGGER.warning("Unrecognized rate: %s", rate_str)
            return 1.0

    @staticmethod
    def _local_tag(tag: str) -> str:
        """Strip XML namespace prefix if present."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def _merge(segments: list[SSMLSegment]) -> list[SSMLSegment]:
        """Remove empty-text segments with zero break (no-ops)."""
        return [s for s in segments if s.text.strip() or s.break_ms > 0]
