#!/usr/bin/env python3
"""Workflow `retention-days:` ↔ docs/spec/artifact-retention-contract.toml gate (M2 T-006).

Walks every `.github/workflows/*.yml`, extracts each
`actions/upload-artifact@<sha>` step's `with.retention-days`, and asserts
that the value matches one of the four categories declared in the spec
(ephemeral=1 / pr-debug=7 / regression-baseline=30 / release-publish=90).

Exit policy:
  spec [meta].mode == "warn" → drift exits 0 (::warning:: per step).
  spec [meta].mode == "fail" → drift exits 1 (::error:: per step).

  `--strict` overrides mode to "fail" (pre-push / release gate use).

Exit codes:
  0 -- aligned, OR mode=warn with drift (drift surfaced as ::warning::)
  1 -- mode=fail (or --strict) with drift
  2 -- spec missing / malformed / invalid mode
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "artifact-retention-contract.toml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# A `retention-days:` line may sit anywhere under a `with:` block. Walking
# the YAML stream proper (PyYAML) is robust against indentation but
# extracts a *graph*, not the surrounding step name needed for the
# violation report. The regex below scans for the literal directive line
# instead — same approach used by check_action_pins.py for SHA pins.
RETENTION_RE = re.compile(r"^\s*retention-days:\s*([^\s#]+)", re.MULTILINE)


def _silent_zero_log(*, workflows: int, steps: int) -> None:
    msg = f"Collected upload steps (workflows={workflows}, steps={steps})"
    print(msg, file=sys.stderr)
    if workflows == 0 or steps == 0:
        print(
            "::warning::artifact-retention scan found 0 upload steps —"
            " path filter mismatch?",
            file=sys.stderr,
        )


def load_spec(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return tomllib.loads(path.read_text(encoding="utf-8"))


def allowed_values(spec: dict) -> dict[int, str]:
    """Return {retention_days: category_name} from the spec."""
    out: dict[int, str] = {}
    for cat in spec.get("categories", []):
        if "name" in cat and "retention_days" in cat:
            out[int(cat["retention_days"])] = cat["name"]
    return out


def scan_workflows(workflows_dir: Path) -> list[tuple[Path, int, int]]:
    """Walk YAML files and yield (path, line_no, retention_days).

    Reads file content as text (regex). Skips files unreadable as utf-8.
    """
    results: list[tuple[Path, int, int]] = []
    if not workflows_dir.is_dir():
        return results
    for path in sorted(workflows_dir.glob("*.y*ml")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in RETENTION_RE.finditer(text):
            raw = m.group(1).strip().strip('"').strip("'")
            try:
                value = int(raw)
            except ValueError:
                # Templated value like ${{ env.RETENTION }} — out of scope.
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            results.append((path, line_no, value))
    return results


def evaluate(
    spec: dict,
    findings: list[tuple[Path, int, int]],
) -> tuple[list[str], int, int]:
    """Returns (violations, workflows_seen, steps_seen)."""
    allowed = allowed_values(spec)
    violations: list[str] = []
    workflows_seen: set[Path] = set()
    for path, line_no, value in findings:
        workflows_seen.add(path)
        if value not in allowed:
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                # Path is outside the repo (e.g. pytest tmp_path) — keep
                # absolute for clarity, no crash.
                rel = path
            violations.append(
                f"{rel}:{line_no} retention-days={value} is not in "
                f"allowed categories {sorted(allowed.keys())} "
                f"(spec categories: {sorted(allowed.values())})"
            )
    return violations, len(workflows_seen), len(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=WORKFLOWS_DIR,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Force mode=fail (overrides spec [meta].mode)",
    )
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except FileNotFoundError:
        print(f"ERROR: spec missing: {args.spec}", file=sys.stderr)
        return 2
    except tomllib.TOMLDecodeError as exc:
        print(f"ERROR: spec malformed: {exc}", file=sys.stderr)
        return 2

    mode = "fail" if args.strict else spec.get("meta", {}).get("mode", "warn")
    if mode not in ("warn", "fail"):
        print(
            f"ERROR: spec [meta].mode must be 'warn' or 'fail' (got {mode!r})",
            file=sys.stderr,
        )
        return 2

    findings = scan_workflows(args.workflows_dir)
    violations, workflows, steps = evaluate(spec, findings)
    _silent_zero_log(workflows=workflows, steps=steps)

    if not violations:
        print(
            "artifact-retention-contract.toml aligned with all upload steps",
            file=sys.stderr,
        )
        return 0

    severity = "::error::" if mode == "fail" else "::warning::"
    print(
        f"{len(violations)} retention-days violation(s) (mode={mode}):", file=sys.stderr
    )
    for v in violations:
        print(f"  {severity} {v}", file=sys.stderr)
    return 1 if mode == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
