#!/usr/bin/env python3
"""ZH-EN loanword JSON 同期チェッカー.

10 箇所の zh_en_loanword.json (Python source + 9 mirrors) を byte-for-byte
一致させる (一方向コピー). PR #397 の Python ZH-EN code-switching 実装を
全ランタイム (Rust × 2 crate / Go / C# / WASM / C++ / Kotlin / Swift) に
展開する際の CI gate. + 8 fixture mirrors (cross-runtime test matrix).

Source of truth: src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
他の 9 mirror を直接編集しても --fix では Python source 内容に上書きされる.
JSON 変更を提案する場合は必ず Python source を編集すること.

Phase 6a (Day 1) では --allow-missing で path 未存在は warn のみ.
TICKET-01〜05 が順次 copy を追加するたびに hash check が走り出す.

Usage:
    python scripts/check_loanword_consistency.py              # チェックのみ (CI 用)
    python scripts/check_loanword_consistency.py --fix         # Python source → 9 mirror 一方向コピー
    python scripts/check_loanword_consistency.py --schema-only # schema のみ
    python scripts/check_loanword_consistency.py --diff        # --fix 前の dry-run 差分表示
    python scripts/check_loanword_consistency.py --allow-missing # Phase 6a モード: missing path は warn のみ

Exit codes:
    0 -- すべて同期済 (または --allow-missing で missing が warn 扱い)
    1 -- 1 つ以上の mismatch / schema 違反
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE = REPO_ROOT / "src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json"

# 9 mirror copies (Python source を含めると計 10 ファイル). 各 TICKET-01〜05 が
# 自分のランタイム copy を追加してゆく. Kotlin Android G2P と Swift G2P は Rust
# crate 経由で transitively 担保されていたが、CI gate を直接担保にするため
# 両ランタイムの own mirror を sync 対象に追加 (Issue #388 / #387 follow-up).
COPIES: list[Path] = [
    REPO_ROOT / "src/python_run/piper/phonemize/data/zh_en_loanword.json",
    # Rust 2 crate (§8.5: piper-plus-g2p と piper-core の重複維持)
    REPO_ROOT / "src/rust/piper-plus-g2p/data/zh_en_loanword.json",
    REPO_ROOT / "src/rust/piper-core/data/zh_en_loanword.json",
    REPO_ROOT / "src/go/phonemize/data/zh_en_loanword.json",
    REPO_ROOT / "src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json",
    REPO_ROOT / "src/wasm/g2p/data/zh_en_loanword.json",
    REPO_ROOT / "src/cpp/data/zh_en_loanword.json",
    # Kotlin Android G2P AAR (io.github.ayutaz:piper-plus-g2p-android) — bundled
    # into AAR `assets/` by AGP, accessible via `Context.assets.open(...)`.
    REPO_ROOT / "android/piper-plus-g2p/src/main/assets/zh_en_loanword.json",
    # Swift G2P (PiperPlusG2P SPM product) — declared as a `.process` resource
    # in Package.swift so it ships inside `Bundle.module` for both iOS and macOS.
    REPO_ROOT / "Sources/PiperPlusG2P/Resources/zh_en_loanword.json",
]

# Cross-runtime fixture matrix. TICKET-06b (Day 14) で導入.
FIXTURE_SRC = REPO_ROOT / "tests/fixtures/g2p/zh_en_loanword_matrix.json"
FIXTURE_MIRRORS: list[Path] = [
    REPO_ROOT / "src/go/phonemize/testdata/zh_en_loanword_matrix.json",
    REPO_ROOT / "src/csharp/PiperPlus.Core.Tests/Phonemize/TestData/zh_en_loanword_matrix.json",
    REPO_ROOT / "src/cpp/tests/fixtures/zh_en_loanword_matrix.json",
    REPO_ROOT / "src/wasm/g2p/test/fixtures/zh_en_loanword_matrix.json",
    # YELLOW-3: Rust 2 crate 対称テストのため両 crate 配下に mirror
    REPO_ROOT / "src/rust/piper-plus-g2p/tests/fixtures/zh_en_loanword_matrix.json",
    REPO_ROOT / "src/rust/piper-core/tests/fixtures/zh_en_loanword_matrix.json",
    # Kotlin Android G2P androidTest assets — same g2p_fixtures/ subdir layout
    # the existing syncG2pFixture Gradle task uses for phoneme_test_cases.json.
    # Committed as a static mirror so the sync gate enforces it directly
    # (rather than relying on a build-time copy task).
    REPO_ROOT / "android/piper-plus-g2p/src/androidTest/assets/g2p_fixtures/zh_en_loanword_matrix.json",
    # Swift G2P XCTest — placed under Tests/.../Fixtures/ so it can be loaded
    # via Bundle.module once the testTarget gains a `resources:` declaration.
    REPO_ROOT / "tests/PiperPlusG2PTests/Fixtures/zh_en_loanword_matrix.json",
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate_schema(p: Path) -> None:
    """Python と同じ schema validation を CI で再実行.

    エラー書式は Python `_load_loanword_data` と一致させる:
        f"{p}: '{section}.{key}' must be list[str], got {value!r}"

    Forward-compat (YELLOW-5): Python source `_load_loanword_data` は
    ``version`` フィールドを要求しない (不存在/型違いを silently 受理) ため、
    ここでも同じ動作を取り、`schema_version: 2` 等の未来形式を block しない。
    Unknown top-level fields も同様に許容する。
    """
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top-level must be a JSON object")
    for section in ("acronyms", "loanwords", "letter_fallback"):
        m = data.get(section, {})
        if not isinstance(m, dict):
            raise ValueError(
                f"{p}: section '{section}' must be a mapping, got "
                f"{type(m).__name__}"
            )
        for k, v in m.items():
            if not isinstance(v, list) or not all(isinstance(e, str) for e in v):
                raise ValueError(
                    f"{p}: '{section}.{k}' must be list[str], got {v!r}"
                )


def show_diff(src: Path, dst: Path) -> None:
    """Python source と mirror の unified diff を表示 (dry-run)."""
    src_lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    dst_lines = (
        dst.read_text(encoding="utf-8").splitlines(keepends=True)
        if dst.exists()
        else []
    )
    diff = difflib.unified_diff(
        dst_lines, src_lines,
        fromfile=str(dst.relative_to(REPO_ROOT)),
        tofile=str(src.relative_to(REPO_ROOT)),
        n=1,
    )
    sys.stdout.writelines(diff)


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Python source → 9 mirror 一方向コピー")
    parser.add_argument("--schema-only", action="store_true", help="hash check skip、schema のみ")
    parser.add_argument("--diff", action="store_true", help="--fix 前の dry-run 差分表示")
    parser.add_argument(
        "--allow-missing", action="store_true",
        help="Phase 6a (Day 1): missing path は warn のみ. TICKET-01〜05 完了で外す",
    )
    args = parser.parse_args(argv)

    if not SOURCE.exists():
        print(f"ERROR: source missing: {SOURCE}", file=sys.stderr)
        return 1

    try:
        validate_schema(SOURCE)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"SCHEMA ERROR: {e}", file=sys.stderr)
        return 1

    if args.schema_only:
        print(f"OK schema: {SOURCE.relative_to(REPO_ROOT)}")
        return 0

    src_hash = sha256(SOURCE)
    print(f"Source: {src_hash} ({SOURCE.relative_to(REPO_ROOT)})")

    failed: list[str] = []
    warnings: list[str] = []
    fixed: list[str] = []

    def _process(target: Path) -> None:
        rel = target.relative_to(REPO_ROOT)
        if not target.exists():
            if args.fix:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(SOURCE, target)
                fixed.append(f"created {rel}")
                return
            if args.allow_missing:
                warnings.append(f"MISSING (allowed) {rel}")
                return
            failed.append(f"MISSING {rel}")
            return
        if sha256(target) == src_hash:
            return
        if args.diff:
            show_diff(SOURCE, target)
        if args.fix:
            shutil.copy2(SOURCE, target)
            fixed.append(f"synced {rel}")
            return
        failed.append(f"MISMATCH {rel}")

    for copy in COPIES:
        _process(copy)

    if FIXTURE_SRC.exists():
        fx_hash = sha256(FIXTURE_SRC)
        for mirror in FIXTURE_MIRRORS:
            rel = mirror.relative_to(REPO_ROOT)
            if not mirror.exists():
                if args.fix:
                    mirror.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(FIXTURE_SRC, mirror)
                    fixed.append(f"created fixture {rel}")
                    continue
                if args.allow_missing:
                    warnings.append(f"FIXTURE MISSING (allowed) {rel}")
                    continue
                failed.append(f"FIXTURE MISSING {rel}")
                continue
            if sha256(mirror) != fx_hash:
                if args.diff:
                    show_diff(FIXTURE_SRC, mirror)
                if args.fix:
                    shutil.copy2(FIXTURE_SRC, mirror)
                    fixed.append(f"synced fixture {rel}")
                    continue
                failed.append(f"FIXTURE OUT OF SYNC {rel}")
    elif not args.allow_missing:
        warnings.append(
            f"FIXTURE SRC MISSING {FIXTURE_SRC.relative_to(REPO_ROOT)} "
            "(TICKET-06b で導入予定)"
        )

    for w in warnings:
        print(f"  WARN  {w}")
    for f in fixed:
        print(f"  FIXED  {f}")

    if failed:
        print("", file=sys.stderr)
        for f in failed:
            print(f"  FAIL  {f}", file=sys.stderr)
        print(
            f"\n{len(failed)} file(s) out of sync. "
            f"Run with --fix to copy from {SOURCE.relative_to(REPO_ROOT)}.",
            file=sys.stderr,
        )
        return 1

    if not warnings and not fixed:
        print(f"\nOK All {len(COPIES)} copies + {len(FIXTURE_MIRRORS)} fixture mirrors in sync")
    elif fixed and not failed:
        print(f"\nOK applied {len(fixed)} fix(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
