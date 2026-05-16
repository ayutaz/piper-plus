#!/usr/bin/env python3
"""Deprecated API lingering documentation detection.

v1.12.0 で削除された機能 (HiFi-GAN / Flask / HTS-voice / `--mb-istft` flag /
Unity UPM) のような **archive 済み API キーワード** が docs/ や README に
「廃止」 「archived」 「removed」 「deprecated」 等の注釈なしで残存していないか
を検出する。

検出パターン:
  - docs/ や README で `--mb-istft` のような廃止 flag が「使う / 推奨」 文脈
    で言及されていないか
  - Flask / HTS-voice 等の廃止 dep が「使い方説明」 文脈で残存していないか

archive 済み判定:
  各廃止キーワードの周辺 (前後 2 行) に以下の語が無ければ「未マーク残存」 と
  flag する:
    - archived / archive / アーカイブ / アーカイブ済
    - removed / 削除 / 廃止 / deprecated / 非推奨
    - 「v<X.Y.Z> で削除」 等

docs/migration/* と CHANGELOG.md は例外 (歴史的記述として残してよい)。

Usage:
    python scripts/check_deprecated_api_lingering.py
    python scripts/check_deprecated_api_lingering.py --verbose
    python scripts/check_deprecated_api_lingering.py --strict   # exit 1 on hit

Exit codes:
    0 -- hit なし or non-strict mode (warning だけ)
    1 -- --strict 指定で未マーク残存検出
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 検査対象パス (`docs/`, `README*.md`)、 example / archive は除外。
DOC_GLOBS = ["README*.md", "docs/**/*.md", "src/*/README.md"]

# 検査対象外パス
EXCLUDE_PREFIXES = (
    "docs/migration/",
    "docs/archive/",
    "CHANGELOG-archive.md",
    "CHANGELOG.md",  # 歴史的記述 OK
    "docs/spec/",    # contract spec は archived 注釈フォーマットが別
)

# (キーワード, 廃止 version, 説明) の組
DEPRECATED_ITEMS: list[tuple[str, str, str]] = [
    ("--mb-istft", "v1.12.0", "MB-iSTFT は常時有効化、 flag は廃止"),
    ("Flask", "v1.12.0", "HTTP server を FastAPI に置換"),
    ("HTS-voice", "v1.12.0", "Python ランタイムから依存削除"),
    ("HTS voice", "v1.12.0", "HTS-voice の表記揺れ"),
    ("HiFi-GAN Decoder", "v1.12.0", "MB-iSTFT に統一"),
    ("Unity UPM", "v1.12.0", "別 repo ayutaz/uPiper に移管"),
]

# キーワードの周辺で「廃止 / archived / removed」 と判定する語
# 多言語 README に対応するため各言語の対応語を網羅。
ARCHIVED_MARKERS = re.compile(
    r"(archived|アーカイブ|removed|削除|廃止|deprecated|非推奨|"
    r"レガシー|legacy|obsolete|v1\.\d+\.\d+\s*で|"
    r"no longer|もはや|past tense|"
    # 中国語 / 韓国語 / ロマンス諸語の対応語
    r"移除|废弃|提除|删除|폐지|제거|구식|"
    r"supprim|suppressã|elimin|obsolet|deprecat|"
    r"Breaking changes|Changements incompatibles|"
    r"Mudanças incompat|Cambios incompatibles|"
    r"Wichtige Änderungen|주요 변경사항|重大变更|破壊的変更)",
    re.IGNORECASE,
)

# Breaking banner 行 (canonical / 翻訳問わず) は archive 文脈と判定する。
# `> **📢 v1.12.0 Breaking changes ...` のような行を skip。
BANNER_LINE_RE = re.compile(r"^>\s*\*?\*?\s*(?:📢|🚨|⚠️)")


def find_doc_files() -> list[Path]:
    out: list[Path] = []
    for spec in DOC_GLOBS:
        for path in REPO_ROOT.glob(spec):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
                continue
            out.append(path)
    return sorted(set(out))


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, keyword, surrounding_text) for un-archived hits."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    # Build keyword regexes once with word boundaries to avoid false positives:
    # plain "flask" in laboratory text, unrelated "HTS" acronyms, "--mb-istft"
    # inside a code block discussing v1.11 history, etc. Each keyword becomes
    # a regex that requires non-alphanumeric / start-of-line context on both
    # sides. CLI flags like `--mb-istft` keep their leading `--` and must not
    # be followed by additional flag chars.
    keyword_patterns: list[tuple[str, re.Pattern[str]]] = []
    for kw, _ver, _desc in DEPRECATED_ITEMS:
        # Escape any regex special and surround with strict boundaries.
        # Avoid `\b` for `--mb-istft` (leading `-` is non-word) — instead
        # require leading non-alnum and trailing non-alnum/`-`.
        escaped = re.escape(kw)
        pat = re.compile(
            rf"(?:^|[^A-Za-z0-9_-]){escaped}(?:$|[^A-Za-z0-9_])",
            re.IGNORECASE,
        )
        keyword_patterns.append((kw, pat))

    hits: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines, start=1):
        # Breaking banner 行は内容問わず archive 文脈と判定 (multi-lingual)
        if BANNER_LINE_RE.match(line.strip()):
            continue
        for keyword, pat in keyword_patterns:
            if not pat.search(line):
                continue
            # 前後 2 行を文脈として archive marker を検査
            ctx_start = max(0, idx - 3)
            ctx_end = min(len(lines), idx + 2)
            context = " ".join(lines[ctx_start:ctx_end])
            if ARCHIVED_MARKERS.search(context):
                continue
            hits.append((idx, keyword, line.strip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="未マーク残存があれば exit 1 (default: warning のみ)",
    )
    args = parser.parse_args()

    docs = find_doc_files()
    total_hits = 0
    findings: list[tuple[Path, int, str, str]] = []

    for doc in docs:
        for ln, kw, line in scan_file(doc):
            total_hits += 1
            findings.append((doc, ln, kw, line))

    if args.verbose:
        print(f"scanned {len(docs)} doc files for {len(DEPRECATED_ITEMS)} deprecated keywords")

    if findings:
        print(
            f"deprecated API lingering {('error' if args.strict else 'warning')}s: "
            f"{total_hits} hit(s)",
            file=sys.stderr,
        )
        last_doc: Path | None = None
        for doc, ln, kw, line in findings:
            rel = doc.relative_to(REPO_ROOT)
            if doc != last_doc:
                print(f"\n  {rel}:", file=sys.stderr)
                last_doc = doc
            print(f"    L{ln} [{kw}] {line[:90]}", file=sys.stderr)
        print(
            "\nFix: add `(removed in vX.Y.Z)` / 「廃止」 / 「archived」 等の注釈を "
            "近接コンテキストに追加するか、 言及自体を削除する。\n"
            "(non-strict mode: warning only — re-run with --strict to fail)",
            file=sys.stderr,
        )
        return 1 if args.strict else 0

    if args.verbose:
        print("OK: no un-archived deprecated API references found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
