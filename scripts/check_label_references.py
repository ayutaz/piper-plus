#!/usr/bin/env python3
"""GitHub label reference gate.

CI config names labels as bare strings. Nothing verified that those strings
correspond to labels that actually exist, so a reference to a label nobody
ever created failed silently — or, worse, loudly at the wrong time:

  * ``.github/dependabot.yml`` asked for ``dependencies`` / ``automated`` on
    every bot PR across 11 ecosystems. Neither label existed, so Dependabot
    posted an error comment on each PR and every bot PR shipped unlabelled.
  * ``.github/workflows/security-issue-routing.yml`` runs
    ``gh issue edit --add-label "needs-triage,roadmap"`` under
    ``set -euo pipefail``. ``gh`` errors on an unknown label, so the security
    routing step fails outright.
  * ``actions/stale`` was told to exempt ``help-wanted`` while the repository
    label is spelled ``help wanted``. The exemption never matched.
  * ``scripts/first_pr_fast_lane.py`` promotes contract gates back to blocker
    when ``run-full-gate`` is attached. That label did not exist either, so
    the escape hatch could not be used without first creating it by hand.

``.github/labels.yml`` already declared itself the source-of-truth for the
label catalogue. This gate makes that claim enforceable: every label named by
CI config must be declared there.

The repository side is not checked here (it needs a token and this gate runs
offline, on three OSes, with no install step). There is no ``gh label sync``
subcommand — ``.github/labels.yml`` used to document one, which is why the
catalogue was never applied to the repository. Emit real commands instead::

    python scripts/check_label_references.py --emit-create-commands

Extraction is a deliberate allowlist of known label-bearing keys rather than a
generic ``labels:`` sweep — ``docker-build.yml`` carries ``labels:`` keys that
hold OCI image metadata, not GitHub labels, and a gate that reports those
would be noise.

Exit codes:
    0 -- every referenced label is declared in .github/labels.yml
    1 -- undeclared label reference(s), or the scan found nothing to check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_YML = REPO_ROOT / ".github" / "labels.yml"
DEPENDABOT_YML = REPO_ROOT / ".github" / "dependabot.yml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
FAST_LANE_SCRIPT = REPO_ROOT / "scripts" / "first_pr_fast_lane.py"

# `- name: <label>` at the top level of .github/labels.yml.
DECLARED_RE = re.compile(r"^- name:\s*(.+?)\s*$", re.MULTILINE)
# `  color: "RRGGBB"` on the line following a declaration.
COLOR_RE = re.compile(r'^[ ]+color:\s*"?([0-9A-Fa-f]{6})"?\s*$')

# `labels:` block in dependabot.yml, followed by `- "value"` items.
DEPENDABOT_LABELS_RE = re.compile(
    r"^(?P<indent>[ ]*)labels:[ ]*\n(?P<items>(?:[ ]*-[ ]*.+\n)+)", re.MULTILINE
)

# actions/stale inputs that take a single label name.
STALE_SINGLE_KEYS = (
    "stale-issue-label",
    "close-issue-label",
    "stale-pr-label",
    "close-pr-label",
)
# actions/stale inputs that take a comma-separated label list.
STALE_LIST_KEYS = (
    "exempt-issue-labels",
    "exempt-pr-labels",
    "only-labels",
    "any-of-labels",
)

# `gh issue|pr edit ... --add-label "a,b"` (also --remove-label).
GH_LABEL_FLAG_RE = re.compile(
    r"--(?:add|remove)-label[ =]+(?P<q>[\"']?)(?P<value>[^\"'\n]+)(?P=q)"
)

# `PROMOTE_LABEL = "run-full-gate"` in first_pr_fast_lane.py.
PROMOTE_LABEL_RE = re.compile(r'^PROMOTE_LABEL\s*=\s*["\'](?P<value>[^"\']+)["\']', re.M)


def _strip_scalar(raw: str) -> str:
    """Strip YAML quoting and trailing comments from a scalar value."""
    value = raw.strip()
    if value and value[0] in "\"'" and value[-1] == value[0] and len(value) >= 2:
        return value[1:-1]
    # An unquoted scalar may carry a trailing `# comment`.
    return value.split("#", 1)[0].strip()


def _split_list(raw: str) -> list[str]:
    return [part.strip() for part in _strip_scalar(raw).split(",") if part.strip()]


def declared_labels(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return {_strip_scalar(m.group(1)) for m in DECLARED_RE.finditer(text)}


def _from_dependabot(path: Path) -> list[tuple[str, str, int]]:
    """Return (label, source, line) for every dependabot `labels:` entry."""
    out: list[tuple[str, str, int]] = []
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(REPO_ROOT).as_posix()
    for match in DEPENDABOT_LABELS_RE.finditer(text):
        base_line = text[: match.start("items")].count("\n") + 1
        for offset, item in enumerate(match.group("items").splitlines()):
            value = _strip_scalar(item.lstrip().lstrip("-"))
            if value:
                out.append((value, rel, base_line + offset))
    return out


def _from_workflow(path: Path) -> list[tuple[str, str, int]]:
    """Return (label, source, line) for label-bearing keys in one workflow."""
    out: list[tuple[str, str, int]] = []
    rel = path.relative_to(REPO_ROOT).as_posix()
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        for key in STALE_SINGLE_KEYS:
            if stripped.startswith(f"{key}:"):
                value = _strip_scalar(stripped.split(":", 1)[1])
                if value and "${{" not in value:
                    out.append((value, rel, lineno))
        for key in STALE_LIST_KEYS:
            if stripped.startswith(f"{key}:"):
                raw = stripped.split(":", 1)[1]
                if "${{" in raw:
                    continue
                for value in _split_list(raw):
                    out.append((value, rel, lineno))
        for match in GH_LABEL_FLAG_RE.finditer(line):
            raw = match.group("value")
            if "${{" in raw or "$" in raw:
                continue
            for value in _split_list(raw):
                out.append((value, rel, lineno))
    return out


def _from_fast_lane(path: Path) -> list[tuple[str, str, int]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    match = PROMOTE_LABEL_RE.search(text)
    if not match:
        return []
    lineno = text[: match.start()].count("\n") + 1
    rel = path.relative_to(REPO_ROOT).as_posix()
    return [(match.group("value"), rel, lineno)]


def collect_references() -> list[tuple[str, str, int]]:
    refs = _from_dependabot(DEPENDABOT_YML)
    refs += _from_fast_lane(FAST_LANE_SCRIPT)
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        refs += _from_workflow(workflow)
    return refs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print every referenced label and its source, then exit 0.",
    )
    parser.add_argument(
        "--emit-create-commands",
        action="store_true",
        help=(
            "Print a `gh label create --force` line per declared label, then "
            "exit 0. There is no `gh label sync` subcommand, so this is how "
            "the catalogue gets applied to the repository."
        ),
    )
    return parser


def declared_colors(path: Path) -> dict[str, str]:
    """Return {label: RRGGBB} for declarations that carry a color."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        declared = DECLARED_RE.match(line)
        if declared:
            current = _strip_scalar(declared.group(1))
            continue
        color = COLOR_RE.match(line)
        if color and current:
            out[current] = color.group(1).upper()
            current = None
    return out


def emit_create_commands() -> int:
    colors = declared_colors(LABELS_YML)
    names = declared_labels(LABELS_YML)
    missing_color = sorted(names - set(colors))
    if missing_color:
        print(
            f"ERROR: no color declared for {missing_color}", file=sys.stderr
        )
        return 1
    print("# `--force` updates an existing label instead of failing, so these")
    print("# commands are safe to re-run. None of them deletes anything.")
    for name in sorted(names):
        print(f"gh label create {name!r} --color {colors[name]} --force")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.emit_create_commands:
        return emit_create_commands()

    declared = declared_labels(LABELS_YML)
    if not declared:
        print(
            f"ERROR: no labels declared in {LABELS_YML} — "
            "the catalogue is the source-of-truth and must not be empty.",
            file=sys.stderr,
        )
        return 1

    refs = collect_references()
    if not refs:
        # The same silent-zero failure this gate exists to prevent: an
        # extraction rule that stops matching must be loud, not green.
        print(
            "ERROR: scan found 0 label references — extraction rules are stale "
            "(dependabot.yml / workflows / first_pr_fast_lane.py all changed?).",
            file=sys.stderr,
        )
        return 1

    if args.list:
        for label, source, line in sorted(refs):
            mark = "ok " if label in declared else "MISS"
            print(f"{mark} {label!r:28} {source}:{line}")
        return 0

    undeclared: dict[str, list[str]] = {}
    for label, source, line in refs:
        if label not in declared:
            undeclared.setdefault(label, []).append(f"{source}:{line}")

    print(
        f"Checked {len(refs)} label reference(s) against "
        f"{len(declared)} declared label(s) in .github/labels.yml"
    )

    if undeclared:
        print("\nERROR: labels referenced by CI config but not declared:", file=sys.stderr)
        for label in sorted(undeclared):
            sites = ", ".join(sorted(set(undeclared[label])))
            print(f"  - {label!r}\n      {sites}", file=sys.stderr)
        print(
            "\nAdd each label to .github/labels.yml (with a color and a "
            "description), then apply the catalogue to the repository:\n"
            "    python scripts/check_label_references.py "
            "--emit-create-commands\n"
            "If the reference itself is wrong, fix the spelling at the call "
            "site instead — GitHub label names are case- and space-sensitive "
            "('help wanted' is not 'help-wanted').",
            file=sys.stderr,
        )
        return 1

    print("OK every referenced label is declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
