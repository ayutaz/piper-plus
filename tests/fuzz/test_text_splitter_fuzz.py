"""Property-based tests for ``piper.text_splitter.split_sentences``.

Invariants:

1. The function never raises on arbitrary unicode input.
2. No returned chunk is empty.
3. Every non-whitespace character from the input appears in the output in
   the same order (the splitter must be lossless modulo whitespace).
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

ts = pytest.importorskip("piper.text_splitter")

split_sentences = ts.split_sentences

_terminators = "..!?。！？．"
_closing = ")]}\"'」』）］】｣”’»"

_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),  # exclude surrogates
    min_size=0,
    max_size=2_000,
)


def _structured_text() -> st.SearchStrategy[str]:
    """Generate text with realistic sentence-terminator density."""
    word = st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters=_terminators + _closing,
        ),
        min_size=0,
        max_size=20,
    )
    term = st.sampled_from(list(_terminators))
    close = st.sampled_from(["", *list(_closing)])
    space = st.sampled_from(["", " ", "\n", "\t", "  "])

    sentence = st.tuples(word, term, close, space).map(lambda t: "".join(t))
    return st.lists(sentence, min_size=0, max_size=30).map("".join)


@given(text=_text_strategy)
def test_split_sentences_never_panics(text: str) -> None:
    out = split_sentences(text)
    assert isinstance(out, list)


@given(text=_text_strategy)
def test_no_empty_chunk(text: str) -> None:
    for chunk in split_sentences(text):
        assert chunk, f"empty chunk produced for input {text!r}"


@given(text=_text_strategy)
def test_lossless_non_whitespace(text: str) -> None:
    """All non-whitespace chars must survive splitting in the same order."""
    chunks = split_sentences(text)
    original = "".join(ch for ch in text if not ch.isspace())
    joined = "".join(ch for chunk in chunks for ch in chunk if not ch.isspace())
    assert original == joined, (
        f"text_splitter dropped chars: input={text!r} chunks={chunks!r}"
    )


@given(text=_structured_text())
def test_structured_input_lossless(text: str) -> None:
    """Same lossless invariant under a more realistic input distribution."""
    chunks = split_sentences(text)
    original = "".join(ch for ch in text if not ch.isspace())
    joined = "".join(ch for chunk in chunks for ch in chunk if not ch.isspace())
    assert original == joined
