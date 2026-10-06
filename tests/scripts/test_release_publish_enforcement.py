"""Execute release shell steps: failed/missing publications must fail the job."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def step(name, job, title):
    return next(
        s for s in workflow(name)["jobs"][job]["steps"] if s.get("name") == title
    )


def shell(tmp_path, script, stubs=None, env=None):
    commands = tmp_path / "commands"
    commands.mkdir(exist_ok=True)
    for name, body in (stubs or {}).items():
        executable = commands / name
        executable.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        executable.chmod(0o755)
    bash = (
        str(
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            / "Git/bin/bash.exe"
        )
        if os.name == "nt"
        else shutil.which("bash")
    )
    posix_path = commands.as_posix()
    scratch = tmp_path.as_posix()
    if os.name == "nt":
        posix_path = "/" + posix_path[0].lower() + posix_path[2:]
        scratch = "/" + scratch[0].lower() + scratch[2:]
    script = re.sub(r"\$\{\{.*?\}\}", "0.8.0", script)
    script = script.replace("/tmp/", scratch + "/")
    return subprocess.run(
        [bash, "-c", f'export PATH="{posix_path}:$PATH"\n' + script],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_ENV": str(tmp_path / "env"), **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "job,title,stubs",
    [
        ("verify-npm", "Verify provenance on npm registry", {"npm": "exit 1"}),
        ("verify-npm", "Verify SLSA attestation via gh CLI", {"npm": "exit 1"}),
        ("verify-crates", "Verify crates.io metadata", {"curl": "printf 404"}),
        ("verify-nuget", "Download + verify NuGet packages", {"curl": "printf 404"}),
        (
            "verify-maven",
            "Verify Maven Central availability + SLSA",
            {"curl": "printf 404"},
        ),
    ],
)
def test_missing_published_package_fails(tmp_path, job, title, stubs):
    script = step("release-verify.yml", job, title)["run"]
    result = shell(tmp_path, script, stubs)
    assert result.returncode != 0, result.stdout + result.stderr


def test_pypi_install_failure_fails(tmp_path):
    executable = tmp_path / "verify-venv/bin/pip"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    executable.chmod(0o755)
    script = step(
        "release-verify.yml", "verify-pypi", "Verify pip can install (smoke)"
    )["run"]
    result = shell(tmp_path, script, {"python3": "exit 0"})
    assert result.returncode != 0, result.stdout + result.stderr


def test_bad_npm_attestation_fails(tmp_path):
    script = step(
        "release-verify.yml", "verify-npm", "Verify SLSA attestation via gh CLI"
    )["run"]
    result = shell(
        tmp_path,
        script,
        {
            "npm": "touch package.tgz",
            "gh": "exit 1",
        },
    )
    assert result.returncode != 0, result.stdout + result.stderr


def test_release_creation_never_deletes_an_existing_release_or_tag():
    script = step("dev-create-release.yml", "create_release", "Create Release")["run"]
    assert "gh release delete" not in script
    assert "push origin --delete" not in script


def test_missing_nuget_credential_fails(tmp_path):
    script = step("dev-create-release.yml", "publish_nuget", "Publish to NuGet")["run"]
    result = shell(tmp_path, script, env={"NUGET_API_KEY": ""})
    assert result.returncode != 0, result.stdout + result.stderr


def test_missing_crates_credential_fails(tmp_path):
    script = step(
        "dev-create-release.yml",
        "publish_crates",
        "Publish piper-plus-g2p (dependency)",
    )["run"]
    result = shell(tmp_path, script, env={"CARGO_REGISTRY_TOKEN": ""})
    assert result.returncode != 0, result.stdout + result.stderr


def test_missing_wheels_fail(tmp_path):
    (tmp_path / "dist").mkdir()
    script = step("dev-create-release.yml", "publish_pypi", "Check wheels")["run"]
    result = shell(tmp_path, script)
    assert result.returncode != 0, result.stdout + result.stderr


def test_verify_uses_publishing_revision_in_all_checkouts():
    jobs = workflow("release-verify.yml")["jobs"]
    gate_checkout = jobs["gate"]["steps"][0]
    assert "github.event.workflow_run.head_sha" in gate_checkout.get("with", {}).get(
        "ref", ""
    )
    assert "source_sha" in jobs["gate"]["outputs"]
    for name, job in jobs.items():
        if name.startswith("verify-"):
            checkout = job["steps"][0]
            assert "needs.gate.outputs.source_sha" in checkout.get("with", {}).get(
                "ref", ""
            )


def test_release_version_is_validated_without_mutating_checkout_version():
    steps = workflow("dev-create-release.yml")["jobs"]["create_release"]["steps"]
    assert not any(s.get("name") == "Update VERSION file dynamically" for s in steps)
    script = next(s["run"] for s in steps if s.get("name") == "Validate version format")
    assert "grep -qE" in script


@pytest.mark.parametrize("result", ["success", "failure", "skipped", "cancelled"])
def test_release_summary_is_a_real_gate(tmp_path, result):
    script = step("dev-create-release.yml", "release_summary", "Summary")["run"]
    script = re.sub(r"\$\{\{ needs\.[^.]+\.result \}\}", result, script)
    outcome = shell(
        tmp_path, script, env={"GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    )
    assert (outcome.returncode == 0) == (result == "success")


def test_crates_are_packaged_attested_and_published_in_dependency_order():
    steps = workflow("dev-create-release.yml")["jobs"]["publish_crates"]["steps"]
    positions = []
    for crate, title in [
        ("piper-plus-g2p", "Publish piper-plus-g2p (dependency)"),
        ("piper-plus", "Publish piper-plus (core)"),
        ("piper-plus-cli", "Publish piper-plus-cli"),
    ]:
        packed = next(
            i for i, s in enumerate(steps) if s.get("name") == f"Package {crate}"
        )
        attested = next(
            i for i, s in enumerate(steps) if s.get("name") == f"Attest {crate}"
        )
        published = next(i for i, s in enumerate(steps) if s.get("name") == title)
        positions.extend([packed, attested, published])
    assert positions == sorted(positions)


def test_release_contracts_are_always_required_on_prs():
    ci = workflow("ci.yml")
    job = ci["jobs"]["release-contract"]
    assert "if" not in job
    assert "release-contract" in ci["jobs"]["ci-required"]["needs"]
    assert any(
        "test_release_publish_enforcement.py" in s.get("run", "") for s in job["steps"]
    )
    gate = ci["jobs"]["ci-required"]
    assert any(
        s.get("run") == 'test "$RELEASE_CONTRACT_RESULT" = "success"'
        for s in gate["steps"]
    )


def test_shared_library_release_stays_draft_until_verification():
    release = workflow("release-shared-lib.yml")["jobs"]["release"]
    upload = next(
        s for s in release["steps"] if "action-gh-release" in s.get("uses", "")
    )
    assert upload["with"]["draft"] == "true"


@pytest.mark.parametrize(
    "upstream,packages",
    [
        ("npm publish", "npm"),
        ("Manual Release", "pypi,nuget,crates"),
        ("Release Rust patch", "crates"),
        ("Release Shared Library", ""),
        ("Release Kotlin G2P (Maven Central)", "maven"),
    ],
)
def test_post_publish_verifies_only_the_registries_that_workflow_publishes(
    tmp_path, upstream, packages
):
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    output = tmp_path / "output"
    script = step("release-verify.yml", "gate", "Resolve version + package list")["run"]
    result = shell(
        tmp_path,
        script,
        {"git": "printf '0123456789abcdef\\n'"},
        env={
            "INPUT_VERSION": "",
            "INPUT_PACKAGES": "",
            "UPSTREAM_WORKFLOW": upstream,
            "EVENT_NAME": "workflow_run",
            "GITHUB_OUTPUT": str(output),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"packages={packages}\n" in output.read_text(encoding="utf-8")


def test_python_g2p_manual_publication_is_guarded_and_serialized():
    config = workflow("g2p-python-ci.yml")
    assert (
        config["on"]["workflow_dispatch"]["inputs"]["release_tag"]["required"] == "true"
    )
    assert "release_tag" in config["concurrency"]["group"]
    assert (
        config["concurrency"]["cancel-in-progress"]
        == "${{ github.event_name == 'pull_request' }}"
    )
    publish = config["jobs"]["publish"]
    assert "workflow_dispatch" in publish["if"]
    assert "validate-release" in publish["needs"]


def g2p_release_repository(tmp_path):
    source = tmp_path / "src/python/g2p"
    source.mkdir(parents=True)
    (source / "pyproject.toml").write_text(
        '[project]\nversion = "0.3.0"\n', encoding="utf-8"
    )
    (source / "dictionary.json").write_text('{"original": true}\n', encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check_python_release_wheel.py").write_text(
        "# wheel verifier\n", encoding="utf-8"
    )

    def git(*args):
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release-test@example.invalid",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init")
    git("add", ".")
    git("commit", "-m", "release source")
    git("tag", "python-g2p-v0.3.0")
    ci = tmp_path / ".github/workflows"
    ci.mkdir(parents=True)
    (ci / "g2p-python-ci.yml").write_text("# add manual dispatch\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "CI recovery only")
    return git, source


def g2p_release_guard(tmp_path, tag="python-g2p-v0.3.0"):
    script = step(
        "g2p-python-ci.yml", "validate-release", "Validate Python G2P release source"
    )["run"]
    return shell(
        tmp_path,
        script,
        env={
            "EVENT_NAME": "workflow_dispatch",
            "RELEASE_TAG": tag,
            "GITHUB_REF": "refs/heads/dev",
            "GITHUB_OUTPUT": str(tmp_path / "guard-output"),
        },
    )


def test_g2p_manual_release_accepts_ci_only_changes(tmp_path):
    g2p_release_repository(tmp_path)
    result = g2p_release_guard(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["committed", "dirty", "untracked"])
def test_g2p_manual_release_rejects_changed_package(tmp_path, kind):
    git, source = g2p_release_repository(tmp_path)
    if kind == "untracked":
        (source / "injected.json").write_text("{}\n", encoding="utf-8")
    else:
        (source / "dictionary.json").write_text('{"changed": true}\n', encoding="utf-8")
        if kind == "committed":
            git("add", ".")
            git("commit", "-m", "changed package source")
    result = g2p_release_guard(tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "tag", ["python-g2p-v0.4.0", "python-g2p-v0.3.0;touch injected"]
)
def test_g2p_manual_release_rejects_invalid_or_mismatched_tag(tmp_path, tag):
    g2p_release_repository(tmp_path)
    result = g2p_release_guard(tmp_path, tag)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not (tmp_path / "injected").exists()


def test_g2p_manual_release_rejects_missing_tag(tmp_path):
    git, _ = g2p_release_repository(tmp_path)
    git("tag", "-d", "python-g2p-v0.3.0")
    result = g2p_release_guard(tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr
def test_rust_patch_requires_actual_inference_and_immutable_tag():
    data = workflow("release-rust.yml")
    jobs = data["jobs"]
    assert jobs["create_release"]["needs"] == ["validate", "test"]
    assert jobs["publish_crates"]["needs"] == "create_release"
    assert jobs["rust-cli"]["needs"] == "create_release"
    validation = step("release-rust.yml", "validate", "Validate immutable Rust tag")[
        "run"
    ]
    assert "refs/tags/rust-v${RELEASE_VERSION}^{commit}" in validation
    assert "git rev-parse HEAD" in validation
    assert "workspace" in validation
    steps = jobs["test"]["steps"]
    assert any("build_embedding_fixture.py" in s.get("run", "") for s in steps)
    assert any("--test test_embedding_dimensions" in s.get("run", "") for s in steps)
    archive_steps = jobs["rust-cli"]["steps"]
    assert any(
        s.get("uses", "").startswith("actions/attest-build-provenance@")
        for s in archive_steps
    )
    assert "--clobber" not in str(archive_steps)


def test_rust_pr_ci_requires_real_embedding_fixture_inference():
    steps = workflow("rust-tests.yml")["jobs"]["test"]["steps"]
    assert any("build_embedding_fixture.py" in s.get("run", "") for s in steps)
    assert any("--test test_embedding_dimensions" in s.get("run", "") for s in steps)
