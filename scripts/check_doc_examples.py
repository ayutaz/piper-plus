#!/usr/bin/env python3
"""docs/ fenced code blocks の audit / execution gate.

Sub-commands:

- ``audit``: walk markdown, classify fenced blocks, emit JSON snapshot.
- ``execute``: load the audit JSON, run each ``executable`` block in a
  sandboxed subprocess (bash + python runners in v1), report per-block
  outcomes.

The ``execute`` sub-command runs in informational tier — every PR pass
is intended to surface drift without breaking the merge gate. Promote
to blocker only after a quiet-period (e.g. 4 weeks of zero false
positives) confirms the runners are stable.

Exit codes (audit):
  0 — drift なし or snapshot match
  1 — silent-zero (0 blocks) or snapshot drift
  2 — spec/fixture missing or input error

Exit codes (execute):
  0 — informational tier always exit 0 (sticky comment carries signal);
      promoted to non-zero only when ``--strict`` is set
  1 — ``--strict`` + at least one block failed / timed-out
  2 — audit JSON missing or malformed
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
from doc_examples.executor import (
    EXEC_FAIL,
    EXEC_PASS,
    EXEC_RUNNER_MISSING,
    EXEC_RUNNER_UNSUPPORTED,
    EXEC_TIMEOUT,
    RUNNERS,
    execute_block,
)
from doc_examples.extractor import FencedBlock, extract_from_file, walk_docs
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


UNKNOWN_LANGUAGE_BUCKET = "unknown"


def _classify_all(blocks: list[FencedBlock], config: ClassifierConfig) -> list[dict]:
    """Build per-block records.

    Unknown languages collapse to a single ``UNKNOWN_LANGUAGE_BUCKET``
    so a new exotic info string (``erlang``, ``zig`` …) doesn't churn
    ``by_language`` in the canonical snapshot. The raw info string is
    preserved in ``language_raw`` for traceability.
    """
    out: list[dict] = []
    for blk in blocks:
        canon_lang = normalize_language(blk.language, config)
        bucket = canon_lang or UNKNOWN_LANGUAGE_BUCKET
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
                "language": bucket,
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
        lang = rec["language"] or UNKNOWN_LANGUAGE_BUCKET
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
        per_language[
            normalize_language(blk.language, config) or UNKNOWN_LANGUAGE_BUCKET
        ] += 1
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


def _silent_zero_execute_log(
    *,
    observed_total: int,
    observed_per_language: Counter[str],
    expected_total: int,
) -> None:
    """Echo the contract-required execution Collected line + drift warnings."""
    line = (
        f"Collected executable blocks (N={observed_total}): "
        f"bash={observed_per_language.get('bash', 0)} "
        f"python={observed_per_language.get('python', 0)} "
        f"rust={observed_per_language.get('rust', 0)} "
        f"csharp={observed_per_language.get('csharp', 0)} "
        f"go={observed_per_language.get('go', 0)} "
        f"wasm={observed_per_language.get('wasm', 0)}"
    )
    print(line, file=sys.stderr)
    print(
        f"Expected from audit.totals.executable={expected_total}, "
        f"observed={observed_total}",
        file=sys.stderr,
    )
    if observed_total == 0 and expected_total > 0:
        # Only warn when the audit actually claimed executable blocks — an
        # empty audit (e.g. fixture / first-PR run with no executable
        # content yet) legitimately observes 0 and is not a regression.
        print(
            "::warning::audit JSON had executable blocks but execute mode "
            "saw 0 — runner dispatch broken or audit input mismatched?",
            file=sys.stderr,
        )
    elif observed_total > 0 and observed_total < (expected_total / 2):
        print(
            f"::warning::execute saw {observed_total} of expected "
            f"{expected_total} executable blocks (< 50%) — possible "
            "regression in classifier dispatch.",
            file=sys.stderr,
        )


def _execute_one(record: dict, args: argparse.Namespace) -> dict:
    """Wrap executor.execute_block with stale-audit detection."""
    file = record["file"]
    abs_path = args.repo_root / file
    stale = False
    if abs_path.exists():
        blocks = extract_from_file(abs_path, repo_root=args.repo_root)
        current_hash = next(
            (b.hash_sha1 for b in blocks if b.line_start == record["line_start"]),
            None,
        )
        if current_hash and current_hash != record["hash_sha1"]:
            stale = True
            print(
                f"::warning::Audit JSON stale: {file}:{record['line_start']} "
                f"(audit hash={record['hash_sha1'][:8]} current="
                f"{current_hash[:8]}). Re-run "
                f"`python scripts/check_doc_examples.py audit` and commit "
                f"the updated snapshot.",
                file=sys.stderr,
            )

    # Re-extract block body from the source file at the same hash to
    # avoid relying on audit JSON containing the full text (it doesn't).
    body = None
    if abs_path.exists():
        for blk in extract_from_file(abs_path, repo_root=args.repo_root):
            if blk.hash_sha1 == record["hash_sha1"]:
                body = blk.body
                break
    if body is None:
        return {
            "file": file,
            "line_start": record["line_start"],
            "language": record["language"],
            "hash_sha1": record["hash_sha1"],
            "status": "source_missing",
            "exit_code": None,
            "duration_sec": 0.0,
            "stale_audit": stale,
        }

    result = execute_block(
        block_hash=record["hash_sha1"],
        file=file,
        line_start=record["line_start"],
        language=record["language"],
        body=body,
        timeout_sec=args.timeout_sec,
        mode="real" if args.actually_run else "syntax",
    )
    return {
        "file": result.file,
        "line_start": result.line_start,
        "language": result.language,
        "hash_sha1": result.block_hash,
        "status": result.status,
        "exit_code": result.exit_code,
        "duration_sec": result.duration_sec,
        "stdout_tail": result.stdout_tail,
        "stderr_tail": result.stderr_tail,
        "stale_audit": stale,
    }


def _render_sticky_comment(
    summary: dict,
    results: list[dict],
    *,
    expected_total: int,
) -> str:
    """Format a markdown sticky-comment body for the gate result."""
    by_lang: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    for r in results:
        by_lang[r["language"]] += 1
        by_status[r["status"]] += 1

    fail_rows: list[str] = []
    stale_rows: list[str] = []
    for r in results:
        if r["status"] in (EXEC_FAIL, EXEC_TIMEOUT):
            fail_rows.append(
                f"| `{r['file']}:{r['line_start']}` | {r['language']} | "
                f"{r['status']} | exit={r.get('exit_code')} | "
                f"{r.get('duration_sec', 0):.2f}s |"
            )
        if r.get("stale_audit"):
            stale_rows.append(
                f"- `{r['file']}:{r['line_start']}` — audit hash="
                f"`{r['hash_sha1'][:8]}` (re-audit needed)"
            )

    lines = [
        "## doc-examples-gate report (informational)",
        "",
        f"Expected from audit.totals.executable: **{expected_total}**, "
        f"observed: **{len(results)}**.",
        "",
        "| Outcome | Count |",
        "|---|---|",
        f"| pass | {by_status.get(EXEC_PASS, 0)} |",
        f"| fail | {by_status.get(EXEC_FAIL, 0)} |",
        f"| timeout | {by_status.get(EXEC_TIMEOUT, 0)} |",
        f"| runner_unsupported | {by_status.get(EXEC_RUNNER_UNSUPPORTED, 0)} |",
        f"| runner_missing | {by_status.get(EXEC_RUNNER_MISSING, 0)} |",
        f"| source_missing | {by_status.get('source_missing', 0)} |",
        "",
        "Per language: "
        + ", ".join(f"`{lang}`={cnt}" for lang, cnt in sorted(by_lang.items())),
        "",
    ]
    if fail_rows:
        lines.extend(
            [
                "### Failures / timeouts",
                "",
                "| Location | Language | Status | Exit | Duration |",
                "|---|---|---|---|---|",
                *fail_rows,
                "",
            ]
        )
    if stale_rows:
        stale_blurb = (
            "Re-run `python scripts/check_doc_examples.py audit` and commit "
            "the updated `tests/fixtures/doc_examples_audit/audit.json` to "
            "clear these warnings:"
        )
        lines.extend(
            [
                "### Stale audit blocks",
                "",
                stale_blurb,
                "",
                *stale_rows,
                "",
            ]
        )
    return "\n".join(lines)


def run_execute(args: argparse.Namespace) -> int:
    audit_path = args.audit_input
    if not audit_path.exists():
        print(f"ERROR: audit JSON missing: {audit_path}", file=sys.stderr)
        return 2
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: audit JSON malformed: {exc}", file=sys.stderr)
        return 2

    expected_total = int(audit.get("totals", {}).get("executable", 0))
    executable_records = [
        rec
        for rec in audit.get("blocks", [])
        if rec.get("category") == CATEGORY_EXECUTABLE
    ]

    # Filter by --languages if provided (default: dispatch every executable
    # record). Languages we don't ship a runner for surface as
    # `runner_unsupported` so the sticky comment accounts for the full
    # audit total instead of silently dropping records.
    runner_languages = set(args.languages) if args.languages else None
    if runner_languages is not None:
        target = [r for r in executable_records if r["language"] in runner_languages]
        reported_runners = sorted(runner_languages)
    else:
        target = executable_records
        # Report the union of runner registry + observed languages so the
        # report makes it clear which languages flowed through.
        reported_runners = sorted(set(RUNNERS.keys()) | {r["language"] for r in target})

    observed_per_language: Counter[str] = Counter()
    results: list[dict] = []
    for rec in target:
        observed_per_language[rec["language"]] += 1
        results.append(_execute_one(rec, args))

    _silent_zero_execute_log(
        observed_total=len(results),
        observed_per_language=observed_per_language,
        expected_total=expected_total,
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "expected_total": expected_total,
                    "observed_total": len(results),
                    "runner_languages": reported_runners,
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.sticky_comment:
        args.sticky_comment.parent.mkdir(parents=True, exist_ok=True)
        args.sticky_comment.write_text(
            _render_sticky_comment(
                summary=audit.get("totals", {}),
                results=results,
                expected_total=expected_total,
            ),
            encoding="utf-8",
        )

    if args.strict:
        any_fail = any(r["status"] in (EXEC_FAIL, EXEC_TIMEOUT) for r in results)
        return 1 if any_fail else 0
    # Informational tier: always exit 0; signal is in the sticky comment.
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
        help=f"Where to write the audit JSON. Default: no file written; "
        f"only the stderr 'Collected blocks' summary is emitted. "
        f"Canonical snapshot path: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)}",
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

    execute = sub.add_parser(
        "execute",
        help="Run each executable block from the audit JSON in a sandbox.",
    )
    execute.add_argument(
        "--audit-input",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Audit JSON to consume (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)})",
    )
    execute.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    execute.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Restrict runners to these languages (default: bash + python).",
    )
    execute.add_argument(
        "--timeout-sec",
        type=int,
        default=60,
        help="Per-block subprocess timeout (default: 60s).",
    )
    execute.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a JSON report of per-block results to this path.",
    )
    execute.add_argument(
        "--sticky-comment",
        type=Path,
        default=None,
        help="Render a markdown sticky-comment body to this path.",
    )
    execute.add_argument(
        "--actually-run",
        action="store_true",
        help="Actually execute each block (default: syntax-validation only "
        "via `bash -n` / `python -m py_compile`). Real execution can be "
        "destructive — fenced docs blocks may call `rm`, `curl`, etc.",
    )
    execute.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on any fail/timeout (default: informational, exit 0).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.mode == "audit":
        return run_audit(args)
    if args.mode == "execute":
        return run_execute(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
