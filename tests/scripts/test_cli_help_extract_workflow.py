"""The CLI help drift workflow captures every runtime and blocks drift (#813)."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/cli-help-extract.yml"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(job):
    return {step.get("name", ""): step for step in job["steps"]}


def test_cpp_help_is_built_and_captured():
    """The C++ step was a stub that wrote an empty file (CAPTURE_FAILED)."""
    steps = _steps(_workflow()["jobs"]["extract"])
    run = steps["Build C++ + capture --help"]["run"]
    assert "cmake --build build" in run
    assert "--target piper" in run
    assert "./build/piper-plus --help" in run
    assert ": > /tmp/cli-help/cpp-raw.txt" not in run
    assert not steps["Build C++ + capture --help"].get("continue-on-error", False)
    sanitize = steps["Sanitize"]["run"]
    assert "cpp)    src='./build/piper-plus --help'" in sanitize


def test_capture_uses_an_english_ui_culture():
    """A Japanese UI culture localized the C# help headings (#813)."""
    env = _workflow()["jobs"]["extract"].get("env", {})
    assert env.get("LC_ALL") == "C.UTF-8"
    assert env.get("LANG") == "C.UTF-8"


def test_canonical_format_tests_run_in_the_workflow():
    """test_sanitize_cli_help.py checked the canonical header, but no CI job
    ran it, so header-less canonicals were merged (#813)."""
    job = _workflow()["jobs"]["drift-check"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "tests/scripts/test_sanitize_cli_help.py" in commands
    assert "tests/scripts/test_cli_help_extract_workflow.py" in commands


def test_drift_fails_pull_requests():
    """Drift was only reported (continue-on-error), so it reached dev."""
    steps = _steps(_workflow()["jobs"]["drift-check"])
    gate = steps["Fail on drift (pull request)"]
    assert gate["if"] == (
        "github.event_name == 'pull_request' && steps.diff.outputs.diff_count != '0'"
    )
    assert "exit 1" in gate["run"]
