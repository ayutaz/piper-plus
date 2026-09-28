"""Source-text helpers shared by the cross-runtime presence gates.

A gate that greps source for an idiom must not be satisfiable by PROSE. That
is not hypothetical: `check_reverse_map_parity.py` asserted that C++ emits
`U+XXXX` for unnamed PUA codepoints, and the assertion passed for years
because `isClosingPunctuation` annotates its cases as
`// U+0029  Right Parenthesis` -- while C++ had no such fallback at all
(issue #656, C++ half). The inverse bites too: a gate that BANS an idiom will
fire on a comment explaining why that idiom was rejected.

Both are fixed the same way -- strip comments before matching.
"""

from __future__ import annotations

import re


# Comment syntax per file extension.
LINE_COMMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    ".py": ("#",),
    ".rs": ("//",),
    ".go": ("//",),
    ".js": ("//",),
    ".ts": ("//",),
    ".cs": ("//",),
    ".c": ("//",),
    ".cpp": ("//",),
    ".h": ("//",),
    ".hpp": ("//",),
    ".toml": ("#",),
}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments(source: str, suffix: str) -> str:
    """Remove line and block comments so prose cannot satisfy a code check.

    Deliberately crude: string literals are not tracked, so a ``//`` inside a
    string is also dropped. That direction is safe for a presence gate -- it
    can only make the gate stricter, never let a missing implementation
    through. A gate that BANS an idiom is likewise only made stricter, because
    the ban is evaluated against less text, not more.

    An unknown extension falls back to treating both ``#`` and ``//`` as
    comment starts, which is the conservative choice for the same reason.
    """
    prefixes = LINE_COMMENT_PREFIXES.get(suffix, ("#", "//"))
    if suffix != ".py":
        source = _BLOCK_COMMENT.sub(" ", source)
    out: list[str] = []
    for line in source.split("\n"):
        cut = len(line)
        for prefix in prefixes:
            idx = line.find(prefix)
            if idx != -1:
                cut = min(cut, idx)
        out.append(line[:cut])
    return "\n".join(out)
