"""A workflow that installs an npm package outside the lockfile must pin it.

``runtime-parity-deep.yml`` skips the full ``npm install`` of
``src/wasm/openjtalk-web`` and installs only ``onnxruntime-node`` with
``--no-package-lock``. The command named no version, so every run took the
latest release. onnxruntime-node 1.31.1 was published to npm before the
matching ``Microsoft.ML.OnnxRuntime.Gpu.Linux`` 1.31.1 reached NuGet, and its
install script failed with ``Failed to find specific package versions`` on
every pull request, while ``package-lock.json`` still records 1.30.0.

A ``--no-package-lock`` install of a package that the lockfile records must
take the lockfile's version, so these jobs test what ``npm ci`` installs
elsewhere and a new upstream release cannot break them.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
LOCKFILE = REPO_ROOT / "src" / "wasm" / "openjtalk-web" / "package-lock.json"


def _locked_packages() -> set[str]:
    lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))
    prefix = "node_modules/"
    return {
        key[len(prefix) :]
        for key in lock["packages"]
        if key.startswith(prefix) and "/node_modules/" not in key[len(prefix) :]
    }


def _run_commands():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (data.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                run = step.get("run")
                if isinstance(run, str):
                    yield path.name, job_name, run


def _unpinned_installs(run: str, locked: set[str]) -> list[str]:
    found = []
    for line in run.splitlines():
        if "npm install" not in line or "--no-package-lock" not in line:
            continue
        for token in shlex.split(line, posix=True, comments=True):
            if token.startswith("-") or token in {"npm", "install"}:
                continue
            # "name" or "@scope/name" with no "@version" part.
            if token in locked:
                found.append(token)
    return found


def test_lockfile_lists_onnxruntime_node():
    assert "onnxruntime-node" in _locked_packages()


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        ("npm install --no-save --no-package-lock onnxruntime-node", ["onnxruntime-node"]),
        ('npm install --no-save --no-package-lock "onnxruntime-node@${VERSION}"', []),
        ("npm install --no-save --no-package-lock onnxruntime-node@1.30.0", []),
        ('npm install --no-save "@piper-plus/g2p@file:../g2p"', []),
    ],
)
def test_detector(run, expected):
    assert _unpinned_installs(run, {"onnxruntime-node"}) == expected


def test_no_workflow_installs_a_locked_package_without_a_version():
    locked = _locked_packages()
    offenders = [
        f"{workflow} / {job}: {pkg}"
        for workflow, job, run in _run_commands()
        for pkg in _unpinned_installs(run, locked)
    ]
    assert not offenders, (
        "npm install --no-package-lock of a package recorded in "
        "src/wasm/openjtalk-web/package-lock.json must name the locked version: "
        + ", ".join(offenders)
    )


def test_parity_job_reads_the_version_from_the_lockfile():
    text = (WORKFLOWS / "runtime-parity-deep.yml").read_text(encoding="utf-8")
    assert re.search(r"package-lock\.json", text), (
        "runtime-parity-deep.yml should take onnxruntime-node's version from "
        "package-lock.json rather than a second hard-coded pin"
    )
