"""GFM fenced code block extraction (T-009).

Uses markdown-it-py with the GFM-compatible preset so the audit catches
the same fenced blocks GitHub's renderer does. Inline ``<pre><code>``
HTML is intentionally ignored (out of scope per the contract).

The extractor returns lightweight dataclasses; classification is in
``classifier.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class FencedBlock:
    """One GFM fenced code block.

    Attributes:
        file:        Path relative to repo root, forward slashes.
        line_start:  1-based line number of the opening fence.
        line_end:    1-based line number of the closing fence.
        language:    Canonical language tag (after alias resolution by
                     the caller). ``""`` if the info string was empty.
        info_string: Raw info string as authored (e.g. ``"py3 # comment"``).
        body:        The block's contents, newline-terminated lines.
        hash_sha1:   SHA-1 of ``body`` (used as the audit primary key).
    """

    file: str
    line_start: int
    line_end: int
    language: str
    info_string: str
    body: str
    hash_sha1: str


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _make_md() -> MarkdownIt:
    """Return a parser that matches GitHub's fenced-block recognition.

    ``commonmark`` already handles GFM-style triple-backtick fences and
    info strings; avoiding ``gfm-like`` keeps us off the optional
    linkify-it-py dependency, which the audit doesn't need.
    """
    return MarkdownIt("commonmark")


def extract_from_text(text: str, file: str) -> list[FencedBlock]:
    """Extract fenced blocks from a markdown string.

    Lines numbers come from markdown-it tokens' ``map`` field — that is
    [start, end_exclusive) in 0-indexed terms. We convert to 1-indexed
    inclusive on both ends to match how editors / GitHub display them.
    """
    md = _make_md()
    tokens = md.parse(text)
    blocks: list[FencedBlock] = []
    for tok in tokens:
        if tok.type != "fence":
            continue
        info_string = (tok.info or "").strip()
        language = info_string.split(maxsplit=1)[0] if info_string else ""
        body = tok.content or ""
        line_map = tok.map or (0, 0)
        line_start = line_map[0] + 1
        line_end = line_map[1]
        blocks.append(
            FencedBlock(
                file=file,
                line_start=line_start,
                line_end=line_end,
                language=language,
                info_string=info_string,
                body=body,
                hash_sha1=_sha1(body),
            )
        )
    return blocks


def extract_from_file(
    path: Path,
    *,
    repo_root: Path,
) -> list[FencedBlock]:
    """Extract fenced blocks from a markdown file on disk."""
    text = path.read_text(encoding="utf-8")
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return extract_from_text(text, file=rel)


def walk_docs(
    docs_root: Path,
    *,
    include_glob: list[str],
    exclude_dirs: list[str],
    repo_root: Path,
) -> list[FencedBlock]:
    """Walk ``docs_root`` matching ``include_glob`` minus ``exclude_dirs``.

    ``include_glob`` patterns are relative to ``repo_root``. Exclusion is
    by path-prefix match against forward-slash relative path.
    """
    out: list[FencedBlock] = []
    seen: set[Path] = set()
    for pattern in include_glob:
        for path in sorted(repo_root.glob(pattern), key=lambda p: p.as_posix()):
            if not path.is_file():
                continue
            if path in seen:
                continue
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                rel = path.as_posix()
            if any(rel == ex or rel.startswith(f"{ex}/") for ex in exclude_dirs):
                continue
            seen.add(path)
            out.extend(extract_from_file(path, repo_root=repo_root))
    return out
