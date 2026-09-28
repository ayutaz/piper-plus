#!/usr/bin/env python3
"""A gate only guards what its trigger lets it see.

GitHub skips a workflow entirely when nothing in its ``on.*.paths`` list
changed, and pre-commit skips a hook when nothing matches its ``files:``
regex. So a job that asserts "file X exists" or "file X is in sync" never runs
on a PR that touches only X -- the one change it was written to catch.

This was not hypothetical:

* ``timing-parity.yml`` declared "If you remove a parity test, this workflow
  fails -- that is intentional", yet none of the six parity tests its
  ``per-runtime-presence`` job checks were in ``paths:``. Deleting one skipped
  the workflow.
* The ``reverse-map-parity`` pre-commit hook read
  ``src/rust/piper-cli/src/main.rs`` but did not list it, so a CLI-only change
  never ran the hook.
* ``docs/spec/loanword-mirrors.toml`` -- the declaration of WHICH mirrors the
  ZH-EN gate compares -- appears in no workflow trigger and in no hook's
  ``files:``. Deleting a ``[[groups]]`` entry shrinks coverage silently, and
  the gate that would notice does not run.

What counts as "guarding" is narrow on purpose. For a workflow it is a path
named on a line that ASSERTS something (``diff``, ``cmp``, ``test -f``, the
``check`` helper presence jobs use, ``--check``, ``::error``) plus any
``scripts/{check,test,verify}_*.py`` the workflow invokes -- a checker has to
re-run when the checker itself changes. Merely reading a file, for a cache key
or as build input, does not count; requiring a trigger entry for every read
produced ~85 findings, and a gate needing 85 exemptions is a gate nobody
maintains. For a pre-commit hook the referenced set is the paths its script
names, which for a sync gate IS the list it compares.

Residual over-reporting (a doc link, a transitive import) is what ``ALLOWLIST``
is for -- every entry carries a reason, so an exemption is a decision someone
wrote down rather than an oversight.

One class gets no exemption at all: a ``docs/spec/*-mirrors.toml`` file must be
in the trigger of the gate that reads it. It is the list of things to compare,
so editing it is exactly when the comparison must re-run.

Exit codes: 0 = every trigger covers what it guards, 1 = at least one gap.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github/workflows"
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

# Paths that look repo-relative and carry a file extension.
PATH_RE = re.compile(
    r"(?<![\w./-])"
    r"((?:src|scripts|docs|tests|test|cmake|android|Sources|data|tools|docker)"
    r"/[\w./-]+\.\w{1,6})"
)

# A mirror declaration is the list of files a gate compares. Editing it changes
# the gate's coverage, so it must always re-run. No allowlist entry may exempt
# one of these.
MIRROR_DECLARATION_RE = re.compile(r"^docs/spec/[\w-]+-mirrors\.toml$")

# (trigger, referenced path) pairs that are deliberately NOT wired up.
# Key: workflow filename or "precommit:<hook-id>". Value: {path: reason}.
ALLOWLIST: dict[str, dict[str, str]] = {
    "cli-help-extract.yml": {
        "src/rust/Cargo.toml": (
            "read only to discover the workspace version string; a version bump "
            "already triggers via src/rust/piper-cli/**"
        ),
    },
    "coinstall-smoke.yml": {
        "docs/design/piper-plus-module-rename-v2.md": (
            "prose reference in a comment, not an artifact the job checks"
        ),
    },
    "python-tests.yml": {
        "docs/spec/test-flake-retry-contract.toml": (
            "read by the retry wrapper for its own settings; the contract has "
            "its own gate (test-flake-retry-contract) which does list it"
        ),
    },
    "release-shared-lib.yml": {
        "docs/reference/ios-shared-lib.md": "documentation link only",
        "scripts/generate_model_card.py": (
            "invoked only on tag releases, where the workflow runs regardless "
            "of paths (push tags has no paths filter)"
        ),
    },
    "test-hf-space.yml": {
        "src/python/piper_train/vits/utils.py": (
            "transitive import of infer_onnx.py, which is listed"
        ),
        "src/python/piper_train/vits/wavfile.py": (
            "transitive import of infer_onnx.py, which is listed"
        ),
        "test/models/multilingual-test-medium.onnx.json": (
            "test asset used for a smoke run; regenerating it is gated by "
            "model-sha256-manifest instead"
        ),
    },
    "webui-test.yml": {
        "test/models/multilingual-test-medium.onnx": (
            "test asset used for a smoke run, not an artifact under review"
        ),
    },
    "integration-tests-issue-426.yml": {
        "src/python/tests/test_infer_onnx_speaker_embedding_integration.py": (
            "run by python-tests.yml, which covers src/python/** already"
        ),
    },
    "precommit:no-legacy-piper-imports": {
        "scripts/check_secret_path_reference.py": (
            "named only in prose (a comment explaining the allowlist "
            "convention this gate borrowed); that gate has its own hook"
        ),
    },
    "precommit:speaker-encoder-contract": {
        "docs/reference/speaker-encoder-contract.md": "documentation link only",
    },
}


# This gate cannot analyse itself with its own heuristic. Every path in
# ALLOWLIST is a string literal in this file, so "paths the script names"
# treats them as files it inspects -- including the *-mirrors.toml entries,
# which the not-exemptible rule then flags. They are configuration data, not
# inputs whose content is compared.
#
# The hook is not left unguarded by the exclusion: its `files:` regex lists
# this script, so editing the gate re-runs the gate.
SELF_ANALYSIS_EXEMPT_SCRIPTS = {"scripts/check_trigger_coverage.py"}


def tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return set(out.stdout.split())


def glob_covers(path: str, globs: list[str]) -> bool:
    for pattern in globs:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"):
            return True
        if "**" in pattern:
            regex = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
            if re.fullmatch(regex, path):
                return True
    return False


def workflow_path_filters(text: str) -> list[list[str]] | None:
    """One glob list per `paths:` block, NOT their union.

    Each block belongs to a different event (`pull_request`, `push`, ...) and
    every one of them must cover what the workflow guards. Taking the union
    hides the asymmetric case: a path listed under `push` but missing from
    `pull_request` means the guard does not run at review time, which is when
    it matters. Measured -- removing one parity test path from only the
    `pull_request` block left a union-based check green.

    Returns None when no event filters by path (the workflow always runs).
    A `paths-ignore` list also means "runs unless excluded", so it is treated
    as unfiltered rather than being inverted.
    """
    if re.search(r"\n\s*paths-ignore:\s*\n", text):
        return None
    blocks = re.findall(
        r"\n(\s*)paths:\s*\n"
        r"((?:\s*-\s*['\"][^'\"]+['\"][^\n]*\n|\s*#[^\n]*\n|\s*\n)+)",
        text,
    )
    if not blocks:
        return None
    filters = [re.findall(r"-\s*['\"]([^'\"]+)['\"]", body) for _indent, body in blocks]
    filters = [f for f in filters if f]
    return filters or None


# A workflow line that ASSERTS something about a file, as opposed to merely
# reading it. Only these count as "guarding".
#
# The distinction matters: a job that `cat`s a lockfile for a cache key does
# not guard it, and demanding a trigger entry for every such read would need
# ~85 allowlist entries -- a gate nobody would maintain, so a gate that would
# be bypassed. Narrowing to assertions keeps the finding set small enough that
# each one is a real decision.
ASSERTION_RE = re.compile(
    r"""(?x)
      \bdiff\b                    # diff committed vs regenerated
    | \bcmp\b
    | \btest\s+-[ef]\b           # test -f X
    | \[\s*!?\s*-[ef]\s         # [ -f X ] / [ ! -f X ]
    | ^\s*check\s                 # the `check()` helper used by presence jobs
    | --check\b                   # regenerate-and-compare mode
    | \bsha256sum\b
    | ::error
    """,
    re.MULTILINE,
)

# A gate script the workflow invokes. Editing the checker must re-run it,
# otherwise a broken checker ships in the same PR that broke it.
GATE_SCRIPT_RE = re.compile(r"(scripts/(?:check|test|verify)_[\w_]+\.py)")


def referenced_paths(text: str, tracked: set[str]) -> set[str]:
    """Repo files the workflow ASSERTS on, plus the gate scripts it invokes."""
    found: set[str] = set()
    for block in re.findall(r"run:[^\n]*\n((?:[ \t]+[^\n]*\n|\n)+)", text):
        for line in block.splitlines():
            if ASSERTION_RE.search(line):
                for candidate in PATH_RE.findall(line):
                    if candidate in tracked:
                        found.add(candidate)
            for candidate in GATE_SCRIPT_RE.findall(line):
                if candidate in tracked:
                    found.add(candidate)
        # Mirror declarations always count, however they are referenced.
        for candidate in PATH_RE.findall(block):
            if candidate in tracked and MIRROR_DECLARATION_RE.match(candidate):
                found.add(candidate)
    return found


def check_workflows(tracked: set[str]) -> list[str]:
    failures: list[str] = []
    for workflow in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8", errors="replace")
        filters = workflow_path_filters(text)
        if filters is None:
            continue
        allowed = ALLOWLIST.get(workflow.name, {})
        for path in sorted(referenced_paths(text, tracked)):
            uncovered = sum(1 for globs in filters if not glob_covers(path, globs))
            if uncovered == 0:
                continue
            note = ""
            if MIRROR_DECLARATION_RE.match(path):
                note = " [MIRROR DECLARATION -- not exemptible]"
            elif path in allowed:
                continue
            where = (
                "every paths: filter"
                if uncovered == len(filters)
                else f"{uncovered} of its {len(filters)} paths: filters"
            )
            failures.append(
                f"{workflow.name}: guards {path} but {where} fails to match "
                f"it{note}"
            )
    return failures


def precommit_hooks() -> list[tuple[str, str, str]]:
    """(hook_id, script_relpath, files_regex) for script-backed hooks."""
    text = PRECOMMIT_CONFIG.read_text(encoding="utf-8", errors="replace")
    hooks: list[tuple[str, str, str]] = []
    for block in re.split(r"\n      - id: ", text)[1:]:
        hook_id = block.split("\n", 1)[0].strip()
        entry = re.search(r"entry:\s*(.+)", block)
        files = re.search(r"\n        files:\s*(.+)", block)
        if not entry or not files:
            continue
        script = re.search(r"(scripts/[\w_]+\.py)", entry.group(1))
        if not script:
            continue
        hooks.append((hook_id, script.group(1), files.group(1).strip()))
    return hooks


def check_precommit(tracked: set[str]) -> list[str]:
    failures: list[str] = []
    for hook_id, script_rel, pattern in precommit_hooks():
        if script_rel in SELF_ANALYSIS_EXEMPT_SCRIPTS:
            continue
        script = REPO_ROOT / script_rel
        if not script.is_file():
            failures.append(f"precommit:{hook_id}: entry script missing: {script_rel}")
            continue
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            failures.append(f"precommit:{hook_id}: files: regex does not compile: {exc}")
            continue

        source = script.read_text(encoding="utf-8", errors="replace")
        read_paths = {p for p in PATH_RE.findall(source) if p in tracked}
        allowed = ALLOWLIST.get(f"precommit:{hook_id}", {})
        for path in sorted(read_paths):
            if regex.search(path):
                continue
            if MIRROR_DECLARATION_RE.match(path):
                failures.append(
                    f"precommit:{hook_id}: reads {path} but files: does not "
                    "match it [MIRROR DECLARATION -- not exemptible]"
                )
                continue
            if path in allowed:
                continue
            failures.append(
                f"precommit:{hook_id}: reads {path} but files: does not match it"
            )
    return failures


def check_allowlist_is_live(tracked: set[str]) -> list[str]:
    """An allowlist entry for a path nobody references any more is dead weight.

    Without this, exemptions accumulate and quietly start covering paths that
    a later edit brought back into scope.
    """
    failures: list[str] = []
    for key, entries in sorted(ALLOWLIST.items()):
        for path, reason in sorted(entries.items()):
            if not reason.strip():
                failures.append(f"ALLOWLIST[{key}][{path}] has an empty reason")
            if path not in tracked:
                failures.append(
                    f"ALLOWLIST[{key}][{path}] names a path that is not tracked; "
                    "drop the entry"
                )
    return failures


def main() -> int:
    tracked = tracked_files()
    failures = (
        check_allowlist_is_live(tracked)
        + check_workflows(tracked)
        + check_precommit(tracked)
    )

    if failures:
        print(
            f"ERROR: {len(failures)} trigger(s) do not cover what they guard:",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nAdd the path to the trigger, or add an ALLOWLIST entry with a "
            "reason in scripts/check_trigger_coverage.py.\n"
            "A docs/spec/*-mirrors.toml file can never be allowlisted: it is "
            "the list of files the gate compares, so editing it is exactly "
            "when the gate must re-run.",
            file=sys.stderr,
        )
        return 1

    n_wf = sum(
        1
        for w in WORKFLOW_DIR.glob("*.yml")
        if workflow_path_filters(w.read_text(encoding="utf-8", errors="replace"))
        is not None
    )
    print(
        f"OK: {n_wf} path-filtered workflow(s) and "
        f"{sum(1 for _, script, _ in precommit_hooks() if script not in SELF_ANALYSIS_EXEMPT_SCRIPTS)}"
        " script-backed pre-commit hook(s) cover what they guard"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
