#!/usr/bin/env python3
"""Every continue-on-error in .github/workflows must be on the allowlist.

The allowlist is docs/spec/continue-on-error-allowlist.toml. The gate fails
when:

* a workflow has a ``continue-on-error`` that is not literally ``false`` and
  no allowlist entry matches it (workflow file, job id, step name),
* an entry matches nothing (the key was removed; drop the entry),
* an entry has no reason, an unknown kind or field, or is a job-level ``harmless``
  entry (a whole job can always hide a check),
* a ``tracked`` entry has no valid ``expires`` date, or the date has passed.

Usage:
    uv run python scripts/check_continue_on_error.py
    uv run python scripts/check_continue_on_error.py --today 2027-02-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import tomllib
from pathlib import Path

import yaml
from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = Path("docs/spec/continue-on-error-allowlist.toml")
KINDS = ("harmless", "tracked")
FIELDS = {"workflow", "job", "step", "kind", "expires", "reason"}


def find_sites(root: Path) -> dict[tuple[str, str, str], str]:
    """Map (workflow, job, step) to the continue-on-error value.

    ``step`` is the step name (or ``uses`` when unnamed); ``""`` means the
    key sits on the job itself.
    """
    sites: dict[tuple[str, str, str], str] = {}
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        wf = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader) or {}
        for job_id, job in (wf.get("jobs") or {}).items():
            value = job.get("continue-on-error")
            if value is not None and value != "false":
                sites[(path.name, job_id, "")] = value
            for step in job.get("steps") or []:
                value = step.get("continue-on-error")
                if value is not None and value != "false":
                    label = step.get("name") or step.get("uses") or "<unnamed step>"
                    sites[(path.name, job_id, label)] = value
    return sites


def check(root: Path, today: dt.date) -> list[str]:
    errors: list[str] = []
    entries = tomllib.loads((root / ALLOWLIST).read_text(encoding="utf-8")).get("entry", [])
    sites = find_sites(root)

    seen: set[tuple[str, str, str]] = set()
    for i, entry in enumerate(entries, 1):
        key = (entry.get("workflow", ""), entry.get("job", ""), entry.get("step", ""))
        where = f"entry {i} ({key[0]} / {key[1]} / {key[2] or '<job>'})"
        if key in seen:
            errors.append(f"{where}: duplicate entry")
        seen.add(key)
        unknown = sorted(set(entry) - FIELDS)
        if unknown:
            errors.append(f"{where}: unknown field(s) {unknown}")
        if key not in sites:
            errors.append(f"{where}: no such continue-on-error any more; remove the entry")
        kind = entry.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}: kind must be one of {KINDS}, got {kind!r}")
        if not str(entry.get("reason", "")).strip():
            errors.append(f"{where}: reason is empty")
        if kind == "harmless" and not key[2]:
            errors.append(f"{where}: a job-level continue-on-error cannot be 'harmless'")
        if kind == "tracked":
            raw = entry.get("expires")
            try:
                expires = dt.date.fromisoformat(str(raw))
            except ValueError:
                errors.append(f"{where}: tracked entries need expires = YYYY-MM-DD, got {raw!r}")
                continue
            if expires < today:
                errors.append(
                    f"{where}: expired on {expires}; fix the check and remove "
                    "continue-on-error, or renew the entry with a new reason"
                )

    for key, value in sites.items():
        if key not in seen:
            errors.append(
                f"{key[0]} / {key[1]} / {key[2] or '<job>'}: continue-on-error: {value} "
                f"is not in {ALLOWLIST.as_posix()} (add an entry with a reason, "
                "and an expiry date if it hides a check)"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = ap.parse_args(argv)
    errors = check(args.root, args.today)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK: every continue-on-error is in {ALLOWLIST.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
