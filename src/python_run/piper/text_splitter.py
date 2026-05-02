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


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks suitable for streaming synthesis.

    Splits on sentence-ending punctuation while preserving the punctuation at
    the end of each chunk. Handles both Japanese (。！？) and Western (.!?)
    sentence terminators. Trailing closing punctuation (e.g. ``」 ）``) is
    consumed as part of the same sentence.

    Consecutive whitespace between sentences is trimmed. Empty input or
    whitespace-only input returns an empty list.
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

        if ch in _SENTENCE_TERMINATORS:
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
