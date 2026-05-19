#!/usr/bin/env python3
"""docs/ fenced code blocks の audit / execution gate (T-009 + 後続).

現在は ``--audit`` サブモード (T-009) のみ実装:

- ``docs/`` 配下の Markdown を walk
- GFM fenced code blocks を抽出
- 3 カテゴリ (executable / needs_placeholder / skip_warranted) に分類
- 結果を JSON で出力 (`--output`)
- silent-zero 防御: ``Collected blocks ...`` を stderr に必ず echo

``--audit`` のみで T-010 (execute mode) は別 PR で追加する。

Exit codes:
  0 — audit 成功 (drift なし、 または audit JSON snapshot に一致)
  1 — silent-zero 検出 (block 数 0)、 または snapshot との drift
  2 — spec / fixture 不在、 入力エラー
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from doc_examples.classifier import (
    CATEGORY_EXECUTABLE,
    CATEGORY_NEEDS_PLACEHOLDER,
    CATEGORY_SKIP_WARRANTED,
    ClassifierConfig,
    classify,
    load_config,
    normalize_language,
)
from doc_examples.extractor import FencedBlock, walk_docs
from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "docs" / "spec" / "doc-examples-contract.toml"
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "doc_examples_audit" / "audit.json"


def _silent_zero_log(per_language: Counter[str], total: int) -> None:
    """Echo the contract-required ``Collected blocks`` line to stderr."""
    line = (
        f"Collected blocks (total={total}): "
        f"bash={per_language.get('bash', 0)} "
        f"python={per_language.get('python', 0)} "
        f"rust={per_language.get('rust', 0)} "
        f"csharp={per_language.get('csharp', 0)} "
        f"go={per_language.get('go', 0)} "
        f"wasm={per_language.get('wasm', 0)}"
    )
    print(line, file=sys.stderr)
    if total == 0:
        print(
            "::warning::audit found 0 fenced blocks — "
            "include_glob mismatch or markdown parser broke?",
            file=sys.stderr,
        )


def _audit_scope(config_data: dict) -> tuple[list[str], list[str]]:
    scope = config_data.get("audit_scope", {})
    return (
        list(scope.get("include_glob", ["docs/**/*.md"])),
        list(scope.get("exclude_dirs", [])),
    )


def _classify_all(blocks: list[FencedBlock], config: ClassifierConfig) -> list[dict]:
    out: list[dict] = []
    for blk in blocks:
        canon_lang = normalize_language(blk.language, config)
        classification = classify(
            language=blk.language,
            body=blk.body,
            config=config,
        )
        out.append(
            {
                "file": blk.file,
                "line_start": blk.line_start,
                "line_end": blk.line_end,
                "language_raw": blk.language,
                "language": canon_lang or blk.language,
                "category": classification.category,
                "suggested_action": classification.suggested_action,
                "placeholders_detected": classification.placeholders_detected,
                "directives_detected": classification.directives_detected,
                "env_dependencies": classification.env_dependencies,
                "hash_sha1": blk.hash_sha1,
            }
        )
    return out


def _summarise(records: list[dict]) -> dict:
    totals: Counter[str] = Counter()
    by_language: dict[str, Counter[str]] = {}
    for rec in records:
        cat = rec["category"]
        lang = rec["language"] or "unknown"
        totals[cat] += 1
        by_language.setdefault(lang, Counter())[cat] += 1

    return {
        "totals": {
            CATEGORY_EXECUTABLE: int(totals.get(CATEGORY_EXECUTABLE, 0)),
            CATEGORY_NEEDS_PLACEHOLDER: int(totals.get(CATEGORY_NEEDS_PLACEHOLDER, 0)),
            CATEGORY_SKIP_WARRANTED: int(totals.get(CATEGORY_SKIP_WARRANTED, 0)),
            "total": len(records),
        },
        "by_language": {
            lang: {
                CATEGORY_EXECUTABLE: int(cnt.get(CATEGORY_EXECUTABLE, 0)),
                CATEGORY_NEEDS_PLACEHOLDER: int(cnt.get(CATEGORY_NEEDS_PLACEHOLDER, 0)),
                CATEGORY_SKIP_WARRANTED: int(cnt.get(CATEGORY_SKIP_WARRANTED, 0)),
            }
            for lang, cnt in sorted(by_language.items())
        },
    }


def build_audit_payload(
    blocks: list[FencedBlock],
    config: ClassifierConfig,
    *,
    generated_at: str | None = None,
) -> dict:
    records = _classify_all(blocks, config)
    summary = _summarise(records)
    return {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": summary["totals"],
        "by_language": summary["by_language"],
        "blocks": records,
    }


def run_audit(args: argparse.Namespace) -> int:
    if not args.config.exists():
        print(f"ERROR: contract missing: {args.config}", file=sys.stderr)
        return 2

    config_data = tomllib.loads(args.config.read_text(encoding="utf-8"))
    include_glob, exclude_dirs = _audit_scope(config_data)
    config = load_config(args.config)

    blocks = walk_docs(
        docs_root=args.docs_root,
        include_glob=include_glob,
        exclude_dirs=exclude_dirs,
        repo_root=args.repo_root,
    )

    per_language: Counter[str] = Counter()
    for blk in blocks:
        per_language[normalize_language(blk.language, config) or "unknown"] += 1
    _silent_zero_log(per_language, total=len(blocks))

    payload = build_audit_payload(
        blocks,
        config,
        generated_at=args.generated_at,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        try:
            shown = args.output.relative_to(args.repo_root)
        except ValueError:
            shown = args.output
        print(f"audit written to {shown}", file=sys.stderr)

    if args.check_snapshot:
        snapshot = args.check_snapshot
        if not snapshot.exists():
            print(f"ERROR: snapshot missing: {snapshot}", file=sys.stderr)
            return 2
        actual = json.loads(json.dumps(payload))
        expected = json.loads(snapshot.read_text(encoding="utf-8"))
        actual.pop("generated_at", None)
        expected.pop("generated_at", None)
        if actual != expected:
            print(
                "ERROR: audit drifted from snapshot. Re-run with "
                "--output to regenerate, then commit the change.",
                file=sys.stderr,
            )
            return 1

    if len(blocks) == 0:
        return 1

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    audit = sub.add_parser(
        "audit",
        help="Walk docs/, classify fenced blocks, emit JSON.",
    )
    audit.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    audit.add_argument(
        "--docs-root",
        type=Path,
        default=REPO_ROOT / "docs",
    )
    audit.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    audit.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Where to write audit JSON (default: stdout only). "
        f"Canonical: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)}",
    )
    audit.add_argument(
        "--check-snapshot",
        type=Path,
        default=None,
        help="Compare audit against this snapshot; non-zero exit on drift.",
    )
    audit.add_argument(
        "--generated-at",
        default=None,
        help="Pin generated_at field (UTC ISO8601) for reproducible runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.mode == "audit":
        return run_audit(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
