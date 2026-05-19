#!/usr/bin/env python3
"""docs/spec/test-flake-retry-contract.toml ↔ runtime retry config gate (M2 T-008).

Verifies that what the spec declares for each runtime under
[python] / [rust] / [go] / [csharp] is actually wired up in the
implementation.

Today only Python is at `status = "phase-1"` — that means:
  (a) the runtime test depends on a pinned retry tool, AND
  (b) the workflow exercises that tool's retry flag.

Runtimes still in `status = "proposed"` are informational: we only check
that the spec entry is well-formed (so a typo cannot ship), and we DO
NOT require the dependency / flag to exist yet. Once their phase advances
the gate naturally upgrades them.

The `retry-count-max-2` invariant is enforced for every runtime that
emits a numeric retry value (Python: `--reruns N`). Anything > 2 fails
even at `status = "proposed"`, because the invariant is policy, not
phase.

Exit codes:
  0 -- spec aligned with implementation under current phase
  1 -- drift detected (missing dep, bad ci flag, retry > 2, etc.)
  2 -- spec / target file missing or malformed
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
SPEC = REPO_ROOT / "docs" / "spec" / "test-flake-retry-contract.toml"

PYTHON_PYPROJECT = REPO_ROOT / "src" / "python_run" / "pyproject.toml"
PYTHON_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"

# `--reruns N` may appear with `=` or whitespace. Capture N.
RERUNS_RE = re.compile(r"--reruns(?:=|\s+)(\d+)")

# Phases that REQUIRE the runtime entry to be reflected in real config.
ENFORCING_PHASES = {"phase-1", "phase-2"}


def _silent_zero_log(*, runtimes_seen: int, runtimes_enforced: int) -> None:
    msg = (
        f"Collected retry policies (runtimes={runtimes_seen}, "
        f"enforced={runtimes_enforced})"
    )
    print(msg, file=sys.stderr)
    if runtimes_seen == 0:
        print(
            "::warning::test-flake-retry-contract has zero runtimes — "
            "did the [meta].applies_to list shrink unintentionally?",
            file=sys.stderr,
        )


def load_spec(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return tomllib.loads(path.read_text(encoding="utf-8"))


def check_python(
    spec_entry: dict,
    retry_max: int,
    pyproject_path: Path,
    workflow_path: Path,
) -> list[str]:
    errors: list[str] = []
    enforcing = spec_entry.get("status") in ENFORCING_PHASES

    package = spec_entry.get("package")
    if not package:
        errors.append("[python].package missing in spec")

    # 1. pyproject dependency wired up (when enforcing).
    if enforcing:
        if not pyproject_path.exists():
            errors.append(f"[python] pyproject.toml missing: {pyproject_path}")
        else:
            text = pyproject_path.read_text(encoding="utf-8")
            if package and package not in text:
                errors.append(
                    f"[python] {pyproject_path.name} does not pin "
                    f"'{package}' (required by status={spec_entry.get('status')})"
                )

    # 2. workflow exercises --reruns AND every value is <= retry_max.
    if workflow_path.exists():
        text = workflow_path.read_text(encoding="utf-8")
        observed = [int(n) for n in RERUNS_RE.findall(text)]
        if enforcing and not observed:
            errors.append(
                f"[python] {workflow_path.name} has no `--reruns N` step "
                f"but spec status={spec_entry.get('status')} requires one"
            )
        for n in observed:
            if n > retry_max:
                errors.append(
                    f"[python] {workflow_path.name} uses --reruns {n} "
                    f"(invariant: retry-count-max-{retry_max})"
                )
    elif enforcing:
        errors.append(f"[python] workflow missing: {workflow_path}")

    return errors


def check_proposed_runtime(name: str, spec_entry: dict) -> list[str]:
    """Validate the shape of a proposed-phase entry (no impl checks)."""
    errors: list[str] = []
    if "status" not in spec_entry:
        errors.append(f"[{name}].status missing")
    if "package" not in spec_entry:
        errors.append(f"[{name}].package missing")
    if "ci_flag" not in spec_entry:
        errors.append(f"[{name}].ci_flag missing")
    return errors


def check(spec: dict) -> tuple[list[str], int, int]:
    """Returns (errors, runtimes_seen, runtimes_enforced)."""
    errors: list[str] = []
    meta = spec.get("meta", {})
    applies_to = list(meta.get("applies_to", []))
    retry_max = int(meta.get("retry_count_max", 2))

    enforced = 0
    for name in applies_to:
        entry = spec.get(name)
        if not isinstance(entry, dict):
            errors.append(f"[{name}] section missing (declared in applies_to)")
            continue
        if entry.get("status") in ENFORCING_PHASES:
            enforced += 1
        if name == "python":
            errors.extend(
                check_python(entry, retry_max, PYTHON_PYPROJECT, PYTHON_WORKFLOW)
            )
        else:
            errors.extend(check_proposed_runtime(name, entry))

    invariants = spec.get("invariants", [])
    invariant_names = {inv.get("name") for inv in invariants}
    required = {"no-blanket-retry", "retry-count-max-2", "ci-only-retry"}
    missing = required - invariant_names
    if missing:
        errors.append(
            f"[[invariants]] missing required: {sorted(missing)}; "
            "do not remove invariants — they are policy, not phase."
        )

    return errors, len(applies_to), enforced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=SPEC)
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except FileNotFoundError:
        print(f"ERROR: spec missing: {args.spec}", file=sys.stderr)
        return 2
    except tomllib.TOMLDecodeError as exc:
        print(f"ERROR: spec malformed: {exc}", file=sys.stderr)
        return 2

    errors, seen, enforced = check(spec)
    _silent_zero_log(runtimes_seen=seen, runtimes_enforced=enforced)

    if errors:
        print(
            f"test-flake-retry-contract drift ({len(errors)} issues):", file=sys.stderr
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("test-flake-retry-contract aligned with implementation", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
