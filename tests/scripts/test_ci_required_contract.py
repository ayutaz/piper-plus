"""Contract tests for the ``ci-required`` job (.github/workflows/ci.yml).

``ci-required`` is the check the dev ruleset requires. It did not need
``changes``, the job that decides which test jobs run: when ``changes``
failed, every test job depending on it was skipped, and ``ci-required``
accepted skipped, so the required check passed with no test run.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SCRIPT = REPO_ROOT / "scripts" / "check_ci_required.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_ci_required", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def job(ci) -> dict:
    return ci["jobs"]["ci-required"]


@pytest.fixture(scope="module")
def always_run(job) -> list[str]:
    run = " ".join(step.get("run", "") for step in job["steps"])
    match = re.search(r"--always-run (\S+)", run)
    assert match, run
    return match.group(1).split(",")


def test_ci_required_needs_every_other_job(ci, job):
    """A job left out of needs can fail without failing the required check."""
    others = set(ci["jobs"]) - {"ci-required"}
    assert set(job["needs"]) == others


def test_changes_must_succeed(always_run):
    assert "changes" in always_run


def test_always_run_jobs_have_no_condition(ci, always_run):
    """A job that may legitimately be skipped cannot be required to succeed."""
    for name in always_run:
        assert name in ci["jobs"], name
        assert "if" not in ci["jobs"][name], name


def test_path_filtered_jobs_depend_on_changes(ci, always_run):
    """Skipped is accepted only for jobs gated by `changes`; anything else
    that can be skipped must be in --always-run or explain itself here."""
    for name, spec in ci["jobs"].items():
        if name == "ci-required" or name in always_run:
            continue
        needs = spec.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        assert "changes" in needs, name
        assert "needs.changes.outputs" in spec.get("if", ""), name


def test_ci_required_runs_even_when_upstream_fails(job):
    """`always()`, not `!cancelled()`: a skipped required check counts as a pass."""
    assert job["if"] == "always()"


def test_verdict_is_fed_every_result(job):
    env = [step.get("env", {}) for step in job["steps"]]
    assert {"NEEDS": "${{ toJSON(needs) }}"} in env


ALWAYS = ["release-contract", "changes", "wasm-onnx-contract"]


def _needs(**results):
    return {name: {"result": result, "outputs": {}} for name, result in results.items()}


def test_failed_changes_fails_even_though_tests_were_skipped():
    needs = _needs(**{
        "release-contract": "success", "changes": "failure",
        "wasm-onnx-contract": "success", "cpp-tests": "skipped",
        "python-tests": "skipped",
    })
    problems = _load_script().verdict(needs, ALWAYS)
    assert problems == ["changes: failure"]


def test_skipped_path_filtered_jobs_pass_when_changes_succeeded():
    needs = _needs(**{
        "release-contract": "success", "changes": "success",
        "wasm-onnx-contract": "success", "cpp-tests": "skipped",
        "python-tests": "success",
    })
    assert _load_script().verdict(needs, ALWAYS) == []


@pytest.mark.parametrize("result", ["failure", "cancelled"])
def test_failed_or_cancelled_test_job_fails(result):
    needs = _needs(**{
        "release-contract": "success", "changes": "success",
        "wasm-onnx-contract": "success", "rust-tests": result,
    })
    assert _load_script().verdict(needs, ALWAYS) == [f"rust-tests: {result}"]


def test_skipped_always_run_job_fails():
    needs = _needs(**{
        "release-contract": "skipped", "changes": "success", "wasm-onnx-contract": "success",
    })
    assert _load_script().verdict(needs, ALWAYS) == ["release-contract: skipped"]


def test_always_run_job_missing_from_needs_fails():
    needs = _needs(**{"release-contract": "success", "wasm-onnx-contract": "success"})
    assert _load_script().verdict(needs, ALWAYS) == [
        "changes: not in needs (it must always run)"
    ]


def test_cli_exit_codes():
    def run(needs):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--always-run", ",".join(ALWAYS)],
            env={**os.environ, "NEEDS": json.dumps(needs)},
            capture_output=True,
            text=True,
        ).returncode

    ok = _needs(**{"release-contract": "success", "changes": "success",
                   "wasm-onnx-contract": "success", "cpp-tests": "skipped"})
    bad = dict(ok, changes={"result": "failure"})
    assert run(ok) == 0
    assert run(bad) == 1
