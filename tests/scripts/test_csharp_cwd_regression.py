"""Ensure the removed-cwd reproducer stays a mandatory behavioral CI check."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_ci_proves_old_launcher_fails_and_current_launcher_passes():
    data = yaml.safe_load(
        (ROOT / ".github/workflows/csharp-cwd-regression.yml").read_text(
            encoding="utf-8"
        )
    )
    job = data["jobs"]["regression"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert not job.get("continue-on-error", False)
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "Version_FromDeletedParentDirectory_Succeeds" in commands
    assert 'test "$baseline_status" -ne 0' in commands
    assert "FileNotFoundException" in commands
    assert "git restore" in commands
    assert commands.count("dotnet test") == 2
    assert '--collect:"XPlat Code Coverage"' in commands
