"""Property-based tests for the Python SSML parser.

Targets ``piper_plus_g2p.ssml.SSMLParser``. Invariants:

1. ``parse`` never raises an unexpected exception (only ``ValueError`` for
   over-size input, which we keep below the limit).
2. ``is_ssml`` is deterministic.
3. Every returned ``SSMLSegment`` has a positive finite ``rate``.
4. ``break_ms`` is non-negative.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, strategies as st

ssml = pytest.importorskip("piper_plus_g2p.ssml")

SSMLParser = ssml.SSMLParser
SSMLSegment = ssml.SSMLSegment

# 100KB is the hard cap inside SSMLParser.parse; stay well under it.
_MAX_INPUT = 50_000


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Arbitrary unicode text — covers ASCII, BMP, surrogates-excluded.
_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),  # exclude surrogates
    min_size=0,
    max_size=2_000,
)


def _ssml_fragment() -> st.SearchStrategy[str]:
    """Generate plausible SSML fragments mixing valid and noisy tags."""
    tag_choices = st.sampled_from(
        [
            "<break/>",
            '<break time="100ms"/>',
            '<break time="2s"/>',
            '<break strength="medium"/>',
            '<break strength="x-strong"/>',
            '<prosody rate="slow">',
            '<prosody rate="fast">',
            "</prosody>",
            "<unknown>",
            "</unknown>",
        ]
    )
    inner = st.lists(
        st.one_of(tag_choices, _text_strategy),
        min_size=0,
        max_size=20,
    ).map("".join)
    return inner.map(lambda body: f"<speak>{body}</speak>")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@given(text=_text_strategy)
def test_parse_never_panics_on_arbitrary_text(text: str) -> None:
    """`parse` must handle any unicode string without raising."""
    if len(text.encode("utf-8")) > _MAX_INPUT:
        return
    segments = SSMLParser.parse(text)
    assert isinstance(segments, list)
    # Stronger invariant: every element is the dataclass we expect, and the
    # `rate` field stays within the clamp window enforced by `parse_rate`
    # (`0.5x` slowest .. `10.0x` fastest after percentage conversion).
    assert all(isinstance(seg, SSMLSegment) for seg in segments)
    assert all(
        0.5 <= seg.rate <= 10.0 for seg in segments if hasattr(seg, "rate")
    )
    for seg in segments:
        assert math.isfinite(seg.rate) and seg.rate > 0.0, seg
        assert seg.break_ms >= 0, seg


@given(text=_ssml_fragment())
def test_parse_handles_ssml_fragments(text: str) -> None:
    """Parser must accept generated SSML-shaped strings without crashing."""
    if len(text.encode("utf-8")) > _MAX_INPUT:
        return
    segments = SSMLParser.parse(text)
    for seg in segments:
        assert seg.rate > 0.0
        assert seg.break_ms >= 0


@given(text=_text_strategy)
def test_is_ssml_is_deterministic(text: str) -> None:
    """Calling `is_ssml` twice must return the same answer."""
    assert SSMLParser.is_ssml(text) == SSMLParser.is_ssml(text)


@given(text=_ssml_fragment())
def test_parse_yields_at_least_one_segment(text: str) -> None:
    """A non-empty SSML document always produces >=1 segment (the parser
    falls back to a single plain-text segment on errors)."""
    if len(text.encode("utf-8")) > _MAX_INPUT:
        return
    segments = SSMLParser.parse(text)
    assert len(segments) >= 1
