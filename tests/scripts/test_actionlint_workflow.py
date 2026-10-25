"""Contract tests for .github/workflows/actionlint.yml.

The workflow ran with ``continue-on-error: true`` and the pre-commit hook
passed ``-shellcheck=``, so 256 shellcheck findings (including PowerShell
scripts parsed as bash) stayed green. These tests keep the gate failing on a
finding and keep CI and pre-commit on the same actionlint.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ACTIONLINT_YML = WORKFLOWS / "actionlint.yml"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(ACTIONLINT_YML.read_text(encoding="utf-8"))


def _steps(workflow: dict) -> dict[str, dict]:
    return {s["name"]: s for s in workflow["jobs"]["actionlint"]["steps"] if "name" in s}


def _install_env(workflow: dict) -> dict:
    return _steps(workflow)["Install actionlint and shellcheck (pinned)"]["env"]


def _pre_commit_actionlint() -> tuple[dict, dict]:
    data = yaml.safe_load(PRE_COMMIT.read_text(encoding="utf-8"))
    for repo in data["repos"]:
        if repo.get("repo") == "https://github.com/rhysd/actionlint":
            hooks = {h["id"]: h for h in repo["hooks"]}
            return repo, hooks["actionlint"]
    raise AssertionError("actionlint hook missing from .pre-commit-config.yaml")


def test_no_continue_on_error(workflow):
    job = workflow["jobs"]["actionlint"]
    assert "continue-on-error" not in job
    for step in job["steps"]:
        assert "continue-on-error" not in step, step.get("name")


def test_versions_are_pinned_with_checksums(workflow):
    env = _install_env(workflow)
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(env["ACTIONLINT_VERSION"]))
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(env["SHELLCHECK_VERSION"]))
    for key in ("ACTIONLINT_SHA256", "SHELLCHECK_SHA256"):
        assert re.fullmatch(r"[0-9a-f]{64}", str(env[key])), key
    script = _steps(workflow)["Install actionlint and shellcheck (pinned)"]["run"]
    assert script.count("sha256sum -c -") == 2
    # the moving "latest" download script is not used
    assert "download-actionlint.bash" not in ACTIONLINT_YML.read_text(encoding="utf-8")


def test_check_step_runs_the_pinned_shellcheck(workflow):
    env = _install_env(workflow)
    script = _steps(workflow)["Check workflow files"]["run"]
    assert "-shellcheck " in script
    assert f"shellcheck-v{env['SHELLCHECK_VERSION']}/shellcheck" in script


def test_pre_commit_uses_the_same_actionlint_with_shellcheck(workflow):
    repo, hook = _pre_commit_actionlint()
    assert repo["rev"] == f"v{_install_env(workflow)['ACTIONLINT_VERSION']}"
    assert not any(str(a).startswith("-shellcheck") for a in hook.get("args", []))


def _literal_windows(runs_on) -> bool:
    return isinstance(runs_on, str) and runs_on.startswith("windows")


def test_windows_only_run_steps_declare_their_shell():
    """On a job whose runs-on is an expression, actionlint cannot tell the
    step runs on Windows and parses a PowerShell script as bash (SC1050 etc.).
    The default shell there is pwsh anyway, so the step must say so."""
    missing = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        wf_shell = ((data.get("defaults") or {}).get("run") or {}).get("shell")
        for name, job in (data.get("jobs") or {}).items():
            if _literal_windows(job.get("runs-on")):
                continue
            job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
            for step in job.get("steps") or []:
                cond = str(step.get("if", ""))
                if "run" not in step or "== 'Windows'" not in cond:
                    continue
                if not (step.get("shell") or job_shell or wf_shell):
                    missing.append(f"{path.name}:{name}:{step.get('name')}")
    assert missing == []
