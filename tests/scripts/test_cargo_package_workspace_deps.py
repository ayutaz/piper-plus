"""``cargo package`` in pull request CI must also package its workspace deps.

``bundle-size-gate.yml`` ran ``cargo package -p piper-plus`` on its own.
Cargo then resolves ``piper-plus-g2p`` (a path dependency inside the
workspace) from the crates.io index, so the version bump PR for Rust 0.5.3
(#899) failed with ``failed to select a version for the requirement
piper-plus-g2p = "^0.5.3"``: the new version is only uploaded by the release
itself. Every Rust version bump would fail the same way.

When the workspace dependencies are passed in the same invocation
(``cargo package -p piper-plus-g2p -p piper-plus``), Cargo packages them
together and resolves them from a local staging registry instead.

The release workflows are exempt: they publish each dependency to crates.io
before packaging the crate that needs it.
"""

from __future__ import annotations

import re
import shlex
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RUST_ROOT = REPO_ROOT / "src" / "rust"

# Publish dependencies to crates.io before packaging the dependants.
EXEMPT_WORKFLOWS = {"release-rust.yml", "g2p-rust-publish.yml"}


def _workspace_packages() -> dict[Path, str]:
    """Map each workspace member directory to its package name."""
    workspace = tomllib.loads((RUST_ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    members = {}
    for member in workspace["workspace"]["members"]:
        manifest = tomllib.loads((RUST_ROOT / member / "Cargo.toml").read_text(encoding="utf-8"))
        members[(RUST_ROOT / member).resolve()] = manifest["package"]["name"]
    return members


def _path_deps(package: str, members: dict[Path, str]) -> set[str]:
    """Workspace packages that ``package`` depends on through ``path``."""
    directory = next(d for d, name in members.items() if name == package)
    manifest = tomllib.loads((directory / "Cargo.toml").read_text(encoding="utf-8"))
    deps: set[str] = set()
    for table in ("dependencies", "build-dependencies"):
        for spec in manifest.get(table, {}).values():
            if isinstance(spec, dict) and "path" in spec:
                deps.add(members[(directory / spec["path"]).resolve()])
    return deps


def _packaged(command: str) -> list[str]:
    """Package names given with ``-p`` / ``--package`` to ``cargo package``."""
    tokens = shlex.split(command)
    names = []
    for i, token in enumerate(tokens):
        if token in ("-p", "--package") and i + 1 < len(tokens):
            names.append(tokens[i + 1])
        elif token.startswith("--package="):
            names.append(token.split("=", 1)[1])
    return names


def _cargo_package_commands() -> list[tuple[str, str]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name in EXEMPT_WORKFLOWS:
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job in (data.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = step.get("run") or ""
                for line in run.splitlines():
                    if re.search(r"\bcargo package\b", line):
                        found.append((path.name, line.strip()))
    return found


COMMANDS = _cargo_package_commands()


def test_bundle_size_gate_packages_a_crate():
    assert any(name == "bundle-size-gate.yml" for name, _ in COMMANDS)


@pytest.mark.parametrize(("workflow", "command"), COMMANDS)
def test_workspace_path_deps_are_packaged_together(workflow, command):
    members = _workspace_packages()
    packaged = _packaged(command)
    assert packaged, f"{workflow}: give the crate with -p: {command}"
    missing = set()
    for package in packaged:
        missing |= _path_deps(package, members) - set(packaged)
    assert not missing, (
        f"{workflow}: `{command}` resolves {sorted(missing)} from crates.io, "
        "which fails on a version bump before the release publishes it; "
        "add them with -p in the same command"
    )
