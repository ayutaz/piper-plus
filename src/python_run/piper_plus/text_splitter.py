"""Sentence-level text splitter for streaming synthesis.

Mirrors the Rust implementation in
``piper-core/src/streaming.rs::split_sentences`` and the C# implementation in
``PiperPlus.Core/Phonemize/TextSplitter.SplitSentences``. Keep these
implementations in sync — see ``docs/spec/text-splitter-contract.toml`` for
the shared specification (canonical character sets).
"""

from __future__ import annotations


_SENTENCE_TERMINATORS: frozenset[str] = frozenset(
    {
        ".",
        "!",
        "?",
        "。",  # U+3002 Ideographic Full Stop
        "！",  # U+FF01 Fullwidth Exclamation Mark
        "？",  # U+FF1F Fullwidth Question Mark
        "．",  # U+FF0E Fullwidth Full Stop (per text-splitter-contract.toml)
    }
)

_CLOSING_PUNCTUATION: frozenset[str] = frozenset(
    {
        ")",
        "]",
        "}",
        '"',
        "'",
        "」",  # 」
        "』",  # 』
        "）",  # ）
        "］",  # ］
        "】",  # 】
        "｣",  # ｣
        "”",  # ”
        "’",  # ’
        "»",  # »
    }
)

# Issue #831: g2p_en reads these full stops as part of the text around them
# ("3.14" is "three point one four", "e.g." is "for example"), and the
# training data is phonemized without splitting, so they do not end a
# sentence. See [[non_terminating_abbreviations]] in the contract.
_NON_TERMINATING_ABBREVIATIONS: tuple[str, ...] = ("e.g.", "i.e.")
_FULL_STOPS: frozenset[str] = frozenset({".", "．"})


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9" or "０" <= ch <= "９"


def _is_ascii_alnum(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _ends_sentence(chars: list[str], i: int) -> bool:
    """Whether the terminator ``chars[i]`` ends a sentence."""
    if chars[i] not in _FULL_STOPS:
        return True
    n = len(chars)
    if 0 < i < n - 1 and _is_digit(chars[i - 1]) and _is_digit(chars[i + 1]):
        return False
    for abbr in _NON_TERMINATING_ABBREVIATIONS:
        for j, abbr_ch in enumerate(abbr):
            if abbr_ch != ".":
                continue
            start = i - j
            end = start + len(abbr)
            if start < 0 or end > n:
                continue
            if "".join(chars[start:end]).lower() != abbr:
                continue
            if start == 0 or not _is_ascii_alnum(chars[start - 1]):
                return False
    return True


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks suitable for streaming synthesis.

    Splits on sentence-ending punctuation while preserving the punctuation at
    the end of each chunk. Handles both Japanese (。！？) and Western (.!?)
    sentence terminators. Trailing closing punctuation (e.g. ``」 ）``) is
    consumed as part of the same sentence.

    A full stop between two digits ("3.14") or inside "e.g." / "i.e." does
    not end a sentence (Issue #831).

    Consecutive whitespace between sentences is trimmed. Empty input or
    whitespace-only input returns an empty list.

    Examples
    --------
    >>> split_sentences("Hello. World!")
    ['Hello.', 'World!']
    >>> split_sentences("こんにちは。さようなら。")
    ['こんにちは。', 'さようなら。']
    >>> split_sentences("")
    []
    >>> split_sentences("   ")
    []
    >>> split_sentences("Hi.")
    ['Hi.']
    >>> split_sentences("Pi is 3.14, e.g. here. Next.")
    ['Pi is 3.14, e.g. here.', 'Next.']
    """
    if not text:
        return []

    sentences: list[str] = []
    current: list[str] = []

    chars = list(text)
    n = len(chars)
    i = 0

    while i < n:
        ch = chars[i]
        current.append(ch)
        i += 1

        if ch in _SENTENCE_TERMINATORS and _ends_sentence(chars, i - 1):
            while i < n and chars[i] in _CLOSING_PUNCTUATION:
                current.append(chars[i])
                i += 1

            trimmed = "".join(current).strip()
            if trimmed:
                sentences.append(trimmed)
            current.clear()

            while i < n and chars[i].isspace():
                i += 1

    trimmed = "".join(current).strip()
    if trimmed:
        sentences.append(trimmed)

    return sentences
