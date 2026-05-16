#!/usr/bin/env python3
# Wave 5-10 — TODO/FIXME/HACK/XXX comment age check.
#
# Why: 1 年以上 経過した TODO は「対応予定だったが忘れた」 候補。 個別の
#   対応の有無は判断できないが、 age が一定期間以上なら code reviewer が
#   issue 化 / 削除 判断を促す signal として warning 表示する。
#
# How to apply: warning-only (block しない)。 各 TODO 行について git blame
#   で author-date を取得、 threshold (default 180 day = 6 month) を超えた
#   ら ::warning:: を出力。 git history が浅い (shallow clone) 場合は silent skip。

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WARN_DAYS = 180  # 6 months

TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

# Include source code only (exclude vendored / generated / archive).
INCLUDE_DIRS = [
    "src/python",
    "src/python_run",
    "src/rust/piper-core/src",
    "src/rust/piper-cli/src",
    "src/rust/piper-python/src",
    "src/rust/piper-wasm/src",
    "src/rust/piper-plus-g2p/src",
    "src/go/piperplus",
    "src/go/phonemize",
    "src/csharp/PiperPlus.Core",
    "src/csharp/PiperPlus.Cli",
    "src/wasm/openjtalk-web/src",
    "src/wasm/g2p/src",
    "src/cpp",
]
EXCLUDE_FILE_PATTERNS = re.compile(
    r"\.(lock|min\.js|generated\..*|onnx|wav|pb)$"
)
EXCLUDE_DIR_PARTS = {"target", "node_modules", "build", "dist", "obj", "bin", "__pycache__"}


def _list_tracked_files() -> list[Path]:
    """git ls-files で tracked file のみ列挙 (untracked / gitignored を排除)。"""
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    files = []
    for line in out.splitlines():
        path = Path(line)
        if EXCLUDE_FILE_PATTERNS.search(line):
            continue
        if any(p in EXCLUDE_DIR_PARTS for p in path.parts):
            continue
        if not any(line.startswith(inc) for inc in INCLUDE_DIRS):
            continue
        files.append(ROOT / path)
    return files


def _blame_date(path: Path, lineno: int) -> dt.date | None:
    """Return git blame author-date for a specific line, or None on error."""
    try:
        out = subprocess.check_output(
            [
                "git", "blame", "--porcelain",
                "-L", f"{lineno},{lineno}",
                str(path.relative_to(ROOT)),
            ],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    for raw_line in out.splitlines():
        if raw_line.startswith("author-time "):
            ts = int(raw_line.split()[1])
            return dt.datetime.fromtimestamp(ts).date()
    return None


def main() -> int:
    today = dt.date.today()
    files = _list_tracked_files()
    if not files:
        print("[check_todo_age] no tracked source files found; skip")
        return 0

    findings: list[tuple[Path, int, str, int]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not TODO_RE.search(line):
                continue
            date = _blame_date(path, lineno)
            if date is None:
                continue
            age = (today - date).days
            if age < WARN_DAYS:
                continue
            tag_match = TODO_RE.search(line)
            tag = tag_match.group(1).upper() if tag_match else "TODO"
            findings.append((path, lineno, tag, age))

    if not findings:
        print(f"[check_todo_age] OK — no TODO/FIXME older than {WARN_DAYS} days")
        return 0

    for path, lineno, tag, age in findings:
        rel = path.relative_to(ROOT)
        print(
            f"::warning file={rel},line={lineno}::{tag} comment is {age} days old "
            f"(threshold {WARN_DAYS}d) — consider opening an issue or removing"
        )

    print(
        f"\n[check_todo_age] {len(findings)} stale TODO/FIXME/HACK/XXX "
        f"comment(s) detected (warning-only, not blocking).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
