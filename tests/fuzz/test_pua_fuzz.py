"""Property-based tests for ``piper_plus_g2p.encode.pua.map_token``.

Invariants:

1. Mapping any single-character input returns the same single character
   (single-codepoint tokens are pass-through by contract).
2. For known multi-codepoint tokens in ``FIXED_PUA_MAPPING``, ``map_token``
   returns a length-1 string whose codepoint matches the table.
3. ``strict=True`` on an unknown multi-codepoint token raises
   ``UnmappedMultiCodepointTokenError`` (and only that exception).
4. ``strict=False`` on an unknown multi-codepoint token never raises and
   returns the input unchanged.
"""

from __future__ import annotations

import warnings

import pytest
from hypothesis import assume, given, strategies as st

pua = pytest.importorskip("piper_plus_g2p.encode.pua")

map_token = pua.map_token
FIXED_PUA_MAPPING: dict[str, int] = pua.FIXED_PUA_MAPPING
UnmappedMultiCodepointTokenError = pua.UnmappedMultiCodepointTokenError


# Single non-surrogate character.
_single_char = st.characters(blacklist_categories=("Cs",))

# Multi-codepoint string (length 2..8) of non-surrogate, non-control chars.
_multi_codepoint = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
    min_size=2,
    max_size=8,
)


@given(ch=_single_char)
def test_single_char_passthrough(ch: str) -> None:
    """Single-character tokens are returned unchanged in both modes."""
    assert map_token(ch) == ch
    assert map_token(ch, strict=True) == ch


@given(token=st.sampled_from(list(FIXED_PUA_MAPPING.keys())))
def test_known_token_maps_to_pua_char(token: str) -> None:
    """Every entry in the fixed table maps to its expected PUA codepoint."""
    mapped = map_token(token, strict=True)
    assert len(mapped) == 1
    assert ord(mapped) == FIXED_PUA_MAPPING[token]


@given(token=_multi_codepoint)
def test_unknown_strict_raises(token: str) -> None:
    """`strict=True` on unknown multi-codepoint tokens raises only the
    documented exception type."""
    # Filter intent: we only want tokens that the fixed table does NOT
    # know about, otherwise `map_token(strict=True)` would succeed and
    # the `pytest.raises` block below would fail.
    assume(token not in FIXED_PUA_MAPPING)
    # Filter intent: re-assert multi-codepoint after the previous filter —
    # the `_multi_codepoint` strategy already guarantees min_size=2, but
    # we keep this check explicit so Hypothesis can shrink to the smallest
    # multi-codepoint counterexample if an invariant ever regresses.
    assume(len(token) > 1)
    with pytest.raises(UnmappedMultiCodepointTokenError):
        map_token(token, strict=True)


@given(token=_multi_codepoint)
def test_unknown_nonstrict_passes_through(token: str) -> None:
    """`strict=False` on unknown multi-codepoint tokens returns the input
    unchanged and emits at most a warning."""
    # Filter intent: exclude tokens present in the fixed PUA table so we
    # exercise the *unknown* path (known tokens would be remapped to a
    # PUA codepoint and the `result == token` assertion would fail).
    assume(token not in FIXED_PUA_MAPPING)
    # Filter intent: defensive re-check that the token is multi-codepoint
    # so this test does not silently overlap with `test_single_char_passthrough`.
    assume(len(token) > 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = map_token(token, strict=False)
    assert result == token
