"""Contract tests for .github/workflows/sbom.yml.

The workflow was green while three of its six SBOMs were wrong or missing:
both npm steps failed without node_modules behind ``continue-on-error``, the
Rust upload looked for files cargo-cyclonedx never writes, and the Python
SBOM described the runner's bare environment instead of the packages. These
tests keep a missing or empty SBOM failing the job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sbom.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(workflow: dict):
    for name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            yield name, step


def test_no_continue_on_error(workflow):
    for name, job in workflow["jobs"].items():
        assert "continue-on-error" not in job, name
    for name, step in _steps(workflow):
        assert "continue-on-error" not in step, (name, step.get("name"))


def test_every_upload_fails_when_its_files_are_missing(workflow):
    uploads = [
        (name, step)
        for name, step in _steps(workflow)
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) >= 6
    for name, step in uploads:
        assert step["with"].get("if-no-files-found") == "error", name


def test_every_generator_checks_its_output_is_not_empty(workflow):
    for job_name in ("cyclonedx-python", "cyclonedx-rust", "cyclonedx-go", "cyclonedx-dotnet", "cyclonedx-npm"):
        runs = [s["run"] for s in workflow["jobs"][job_name]["steps"] if s.get("name", "").startswith("Generate")]
        assert runs, job_name
        for run in runs:
            assert "jq -e" in run and "components | length" in run, (job_name, run)


def test_tools_are_pinned():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "@latest" not in text
    for line in text.splitlines():
        cmd = line.strip()
        if re.match(r"(cargo install|dotnet tool install|npm install -g|go install|pip install)\b", cmd):
            assert re.search(r"--version|@\$|@v?\d|==", cmd), cmd


def test_python_sbom_comes_from_the_lock_file(workflow):
    run = "\n".join(s.get("run", "") for s in workflow["jobs"]["cyclonedx-python"]["steps"])
    assert "cyclonedx-py environment" not in run
    assert "uv export" in run and "--frozen" in run


def test_rust_upload_matches_cargo_cyclonedx_output(workflow):
    upload = next(s for s in workflow["jobs"]["cyclonedx-rust"]["steps"] if "upload-artifact" in str(s.get("uses")))
    # cargo-cyclonedx writes <crate dir>/<package>.cdx.json
    assert upload["with"]["path"] == "src/rust/*/*.cdx.json"
