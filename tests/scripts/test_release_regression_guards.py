"""Regressions observed during the 2.0 release must fail before publication."""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text("utf-8"))


def test_required_rust_ci_runs_actual_onnx_cache_regressions():
    jobs = workflow("ci.yml")["jobs"]
    steps = jobs["rust-tests"]["steps"]
    fixture = next(
        i
        for i, s in enumerate(steps)
        if "build_embedding_fixture.py" in s.get("run", "")
    )
    inference = next(
        i
        for i, s in enumerate(steps)
        if "--test test_embedding_dimensions" in s.get("run", "")
    )
    assert fixture < inference
    assert "--features onnx" in steps[inference]["run"]
    assert not steps[inference].get("continue-on-error", False)
    assert "rust-tests" in jobs["ci-required"]["needs"]


def test_release_regressions_are_required_and_available_as_commit_hook():
    jobs = workflow("ci.yml")["jobs"]
    command = "\n".join(s.get("run", "") for s in jobs["release-contract"]["steps"])
    assert "python scripts/check_release_regressions.py" in command
    runner = (ROOT / "scripts/check_release_regressions.py").read_text("utf-8")
    for name in (
        "test_docker_release_tags.py",
        "test_docker_signature_recovery.py",
        "test_release_regression_guards.py",
    ):
        assert name in runner
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text("utf-8"))
    hook = next(
        h
        for r in config["repos"]
        for h in r["hooks"]
        if h["id"] == "release-regressions"
    )
    assert hook["language"] == "python"
    assert hook["entry"] == "python scripts/check_release_regressions.py"
    assert hook["pass_filenames"] is False


def test_every_docker_release_signer_verifies_the_signature():
    jobs = workflow("docker-build.yml")["jobs"]
    for name, job in jobs.items():
        if name.startswith("build-") and any(
            s.get("name") == "Sign the published image" for s in job["steps"]
        ):
            sign = next(
                s for s in job["steps"] if s.get("name") == "Sign the published image"
            )
            assert "cosign verify" in sign["run"], name
            assert "--certificate-identity" in sign["run"], name
            assert "--certificate-github-workflow-sha" in sign["run"], name
            assert not sign.get("continue-on-error", False)
    sign = next(
        s
        for s in workflow("release-docker-signatures.yml")["jobs"]["sign"]["steps"]
        if s.get("name") == "Sign verified immutable image digests"
    )
    assert "cosign verify" in sign["run"]


def run_shell(script, tmp_path):
    bash = shutil.which("bash")
    if os.name == "nt":
        bash = "C:/Program Files/Git/bin/bash.exe"
    assert bash and Path(bash).is_file(), (
        "Bash is required for workflow execution tests"
    )
    script_path = tmp_path / "step.sh"
    script_path.write_text(script, encoding="utf-8")
    return subprocess.run(
        [bash, script_path.as_posix()],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": str(tmp_path / "bin") + os.pathsep + os.environ["PATH"],
            "GITHUB_WORKFLOW_REF": "ayutaz/piper-plus/.github/workflows/cosign-release-artifacts.yml@refs/tags/v2.0.0",
            "GITHUB_SHA": "a" * 40,
        },
    )


def signer_script():
    return next(
        s["run"]
        for s in workflow("cosign-release-artifacts.yml")["jobs"]["sign"]["steps"]
        if s.get("name") == "Sign each asset with cosign (keyless OIDC)"
    )


@pytest.mark.parametrize("failure", ["none", "sign", "verify", "no-bundle"])
def test_blob_signer_fails_on_missing_signature_and_never_signs_bundles(
    tmp_path, failure
):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "payload.zip").write_bytes(b"actual payload")
    (artifacts / "old.zip.cosign.bundle").write_bytes(b"existing signature")
    binary = tmp_path / "bin"
    binary.mkdir()
    stub = binary / "cosign"
    stub.write_text(
        f"""#!/bin/bash
case "$1" in
  sign-blob)
    test '{failure}' != sign || exit 1
    test '{failure}' != no-bundle || exit 0
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "--bundle" ]; then printf signed > "$2"; fi
      shift
    done ;;
  verify-blob) test '{failure}' != verify ;;
  *) exit 99 ;;
esac
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    result = run_shell(signer_script(), tmp_path)
    assert (result.returncode != 0) is (failure != "none"), (
        result.stdout + result.stderr
    )
    assert not (artifacts / "old.zip.cosign.bundle.cosign.bundle").exists()
    if failure == "none":
        assert (artifacts / "payload.zip.cosign.bundle").is_file()


def test_blob_signer_rejects_empty_asset_inventory(tmp_path):
    (tmp_path / "artifacts").mkdir()
    assert run_shell(signer_script(), tmp_path).returncode != 0


def test_blob_download_excludes_existing_cosign_bundles(tmp_path):
    step = next(
        s
        for s in workflow("cosign-release-artifacts.yml")["jobs"]["sign"]["steps"]
        if s.get("name") == "Download release assets"
    )
    # Execute the actual download filter, not a second copy of its expression.
    script = (
        "printf '%s\\n' cli.zip cli.zip.sig cli.zip.pem cli.zip.cosign.bundle | "
        + step["run"].split("| ", 1)[1].split("\\\n", 1)[0]
    )
    result = run_shell(script, tmp_path)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["cli.zip"]


def checksum_module():
    path = ROOT / "scripts/release_checksums.py"
    spec = importlib.util.spec_from_file_location("release_checksums", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checksum_manifest_works_with_flat_release_downloads(tmp_path):
    module = checksum_module()
    nested = tmp_path / "builder/platform"
    nested.mkdir(parents=True)
    (nested / "cli.tar.gz").write_bytes(b"archive bytes")
    manifest = module.generate(tmp_path / "builder")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    shutil.copy(nested / "cli.tar.gz", downloads)
    module.verify(downloads, manifest)
    assert "platform/" not in manifest
    (downloads / "cli.tar.gz").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        module.verify(downloads, manifest)


def test_duplicate_release_names_are_rejected(tmp_path):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "same.zip").write_bytes(folder.encode())
    with pytest.raises(ValueError, match="duplicate"):
        checksum_module().generate(tmp_path)


@pytest.mark.parametrize(
    "name", ["../escape.zip", "sub/cli.zip", "cli.zip\nother", "C:\\cli.zip"]
)
def test_checksum_verifier_rejects_nonflat_names(tmp_path, name):
    with pytest.raises(ValueError):
        checksum_module().verify(tmp_path, f"{'a' * 64}  {name}\n")


def test_shared_release_verifies_download_layout_before_upload():
    steps = workflow("release-shared-lib.yml")["jobs"]["release"]["steps"]
    checksum = next(s for s in steps if s.get("name") == "Generate checksums")
    assert "scripts/release_checksums.py" in checksum["run"]
    assert "--verify" in checksum["run"]
