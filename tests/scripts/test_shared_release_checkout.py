"""Release-only jobs must have their scripts and reject unrelated recovery runs."""

import fnmatch
import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_sparse_release_checkout_contains_every_executed_script():
    workflow = yaml.load(
        (ROOT / ".github/workflows/release-shared-lib.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["release"]["steps"]
    patterns = steps[0]["with"]["sparse-checkout"].splitlines()
    for path in ("scripts/generate_model_card.py", "scripts/release_checksums.py"):
        assert any(fnmatch.fnmatch(path, pattern) for pattern in patterns), (
            f"Release checkout omits {path}"
        )


def recovery():
    spec = importlib.util.spec_from_file_location(
        "shared_recovery", ROOT / "scripts/check_shared_release_recovery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "unrelated"),
        ("head_branch", "dev"),
        ("event", "pull_request"),
        ("path", ".github/workflows/ci.yml"),
        ("status", "in_progress"),
    ],
)
def test_recovery_rejects_unrelated_or_incomplete_build(field, value):
    module = recovery()
    run = {
        "head_sha": "a" * 40,
        "head_branch": "v2.0.1",
        "event": "push",
        "path": ".github/workflows/release-shared-lib.yml",
        "status": "completed",
    }
    run[field] = value
    with pytest.raises(ValueError):
        module.validate_run(run, "a" * 40, "v2.0.1")


def test_recovery_accepts_only_the_expected_publish_failure():
    module = recovery()
    jobs = [
        {"name": "Build windows-x64", "conclusion": "success"},
        {
            "name": "Create Release",
            "conclusion": "failure",
            "steps": [{"name": "Generate checksums", "conclusion": "failure"}],
        },
    ]
    module.validate_jobs(jobs)
    jobs[0]["conclusion"] = "failure"
    with pytest.raises(ValueError):
        module.validate_jobs(jobs)


def test_artifact_digest_and_single_expected_member_are_required(tmp_path):
    import hashlib
    import zipfile

    module = recovery()
    path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("expected.zip", b"native bytes")
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert module.artifact_payload(path, digest, "expected.zip") == b"native bytes"
    with pytest.raises(ValueError):
        module.artifact_payload(path, "sha256:" + "0" * 64, "expected.zip")
    with pytest.raises(ValueError):
        module.artifact_payload(path, digest, "another.zip")


@pytest.mark.parametrize(
    "release",
    [
        {"isDraft": False, "assets": []},
        {
            "isDraft": True,
            "assets": [{"name": "libpiper_plus-ios-v2.0.1.xcframework.zip"}],
        },
    ],
)
def test_recovery_never_overwrites_published_or_existing_payloads(release):
    with pytest.raises(ValueError):
        recovery().validate_draft(release, "v2.0.1")


def test_recovery_workflow_checks_out_immutable_source_and_never_overwrites():
    workflow = yaml.load(
        (ROOT / ".github/workflows/release-verify.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["recover-shared"]
    assert "recover_shared_run" in job["if"]
    assert job["steps"][0]["with"]["ref"] == "v${{ inputs.version }}"
    assert job["steps"][1]["with"]["ref"] == "${{ github.sha }}"
    scripts = "\n".join(step.get("run", "") for step in job["steps"])
    assert "check_shared_release_recovery.py" in scripts
    assert "--clobber" not in scripts and "git push" not in scripts
    assert "isDraft" in scripts
    assert "inputs.recover_shared_run == ''" in workflow["jobs"]["gate"]["if"]
