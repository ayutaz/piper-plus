"""Prevent cache stalls and rebuilding different bytes for Docker Hub."""

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow():
    return yaml.safe_load(
        (ROOT / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
    )


def test_real_workflow_has_bounded_independent_caches_and_no_hub_rebuild():
    assert load("check_docker_publish_stability").check(workflow()) == []


@pytest.mark.parametrize("mutation", ["shared", "timeout", "fatal", "rebuild"])
def test_guard_rejects_publication_regressions(mutation):
    data = copy.deepcopy(workflow())
    steps = data["jobs"]["build-python-inference"]["steps"]
    build = next(s for s in steps if s.get("id") == "build")
    if mutation == "shared":
        build["with"]["cache-to"] = "type=gha,mode=max"
    elif mutation == "timeout":
        build["with"]["cache-to"] = "type=gha,scope=gpu,ignore-error=true"
    elif mutation == "fatal":
        build["with"]["cache-to"] = "type=gha,scope=gpu,timeout=2m"
    else:
        steps.append(
            {
                "uses": "docker/build-push-action@v6",
                "with": {"tags": "docker.io/example/api:2.0.1"},
            }
        )
    assert load("check_docker_publish_stability").check(data)


def test_copy_preserves_every_platform_and_verifies_remote_bytes(tmp_path):
    module = load("publish_docker_mirror")
    raw = b'{"manifests":[]}'
    digest = "sha256:" + module.hashlib.sha256(raw).hexdigest()
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return type("Result", (), {"stdout": raw})()

    module.publish(
        "ghcr.io/example/api",
        digest,
        ["owner/api:2.0.1", "owner/api:latest"],
        tmp_path,
        runner,
    )
    copies = [c for c in calls if "copy" in c]
    assert len(copies) == 2
    assert all("--all" in c and "--preserve-digests" in c for c in copies)
    assert all(f"docker://ghcr.io/example/api@{digest}" in c for c in copies)
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_copy_rejects_remote_digest_mismatch(tmp_path):
    module = load("publish_docker_mirror")

    def runner(args, **kwargs):
        return type("Result", (), {"stdout": b"changed manifest"})()

    with pytest.raises(ValueError, match="digest"):
        module.publish(
            "ghcr.io/example/api",
            "sha256:" + "a" * 64,
            ["owner/api:2.0.1"],
            tmp_path,
            runner,
        )


def test_release_consumer_uses_tag_source_and_verifies_both_registries():
    text = (ROOT / ".github/workflows/release-docker-consumer.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_run:" in text
    assert "ref: ${{ env.RELEASE_TAG }}" in text
    assert '--certificate-github-workflow-sha "$RELEASE_SOURCE"' in text
    assert "ghcr.io/${GITHUB_REPOSITORY}" in text
    assert "docker.io/${DOCKERHUB_OWNER}" in text
    assert "python ci/release_docker/run_public_runtime.py" in text
    source = (ROOT / "ci/release_docker/run_public_runtime.py").read_text(
        encoding="utf-8"
    )
    assert 'os.environ["RELEASE_VERSION"]' in source
    assert 'os.environ["RELEASE_SOURCE"]' in source
    assert 'ghcr["digest"] == hub["digest"]' in source
