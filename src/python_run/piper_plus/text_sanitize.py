"""Strip control characters from a text before it is read.

The rule is shared by every runtime: docs/spec/input-sanitize-contract.toml.
``\\n``, ``\\t`` and ``\\r`` stay (sentence splitting and SSML use them); VT,
FF and NEL (U+000B, U+000C, U+0085) separate words, so they become a space;
every other control character (Unicode category Cc) is removed. Format
characters (U+200D, U+FEFF), separators (U+2028) and NBSP stay.
"""

from __future__ import annotations

import unicodedata


__all__ = ["strip_control_chars"]

_TO_SPACE = "\u000b\u000c\u0085"
_NOT_REMOVED = "\n\t\r" + _TO_SPACE


def strip_control_chars(text: str) -> str:
    """Return *text* cleaned by the input-sanitize rule.

    Idempotent, and returns *text* itself when there is nothing to change.
    """
    if not any(unicodedata.category(ch) == "Cc" and ch not in "\n\t\r" for ch in text):
        return text
    return "".join(
        " " if ch in _TO_SPACE else ch
        for ch in text
        if unicodedata.category(ch) != "Cc" or ch in _NOT_REMOVED
    )
