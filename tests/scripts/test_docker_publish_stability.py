"""Prevent cache stalls and rebuilding different bytes for Docker Hub."""

import copy
import importlib.util
import subprocess
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


def test_root_release_does_not_rebuild_the_docker_release_again():
    data = workflow()
    triggers = data.get("on", data.get(True))
    assert triggers["push"]["tags"] == ["docker-v*"]


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
    assert "python ci/release_docker/run_public_runtime.py" in text
    source = (ROOT / "ci/release_docker/run_public_runtime.py").read_text(
        encoding="utf-8"
    )
    assert 'os.environ["RELEASE_VERSION"]' in source
    assert 'os.environ["RELEASE_SOURCE"]' in source
    assert 'ghcr["digest"] == hub["digest"]' in source
    assert 'for registry, image in (("ghcr", ghcr), ("dockerhub", hub))' in source
    assert "verify_and_pull(" in source


def runtime_module(monkeypatch, tmp_path):
    for name, value in {
        "RELEASE_VERSION": "2.0.1",
        "RELEASE_SOURCE": "a" * 40,
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_REPOSITORY": "ayutaz/piper-plus",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "public_runtime", ROOT / "ci/release_docker/run_public_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_runtime_verifies_and_pulls_the_identical_immutable_reference(
    monkeypatch, tmp_path
):
    module = runtime_module(monkeypatch, tmp_path)
    reference = "docker.io/owner/api@sha256:" + "b" * 64
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return type("Result", (), {"stdout": b'[{"verified":true}]'})()

    module.verify_and_pull(reference, tmp_path / "signature.json", runner)
    assert len(calls) == 2
    assert calls[0][0:2] == ["cosign", "verify"]
    assert calls[1][0:2] == ["docker", "pull"]
    assert calls[0][-1] == calls[1][-1] == reference
    assert (
        "https://github.com/ayutaz/piper-plus/.github/workflows/docker-build.yml@refs/tags/docker-v2.0.1"
        in calls[0]
    )
    assert "a" * 40 in calls[0]


def test_invalid_public_signature_stops_before_pull(monkeypatch, tmp_path):
    module = runtime_module(monkeypatch, tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args)

    with pytest.raises(subprocess.CalledProcessError):
        module.verify_and_pull(
            "ghcr.io/owner/api@sha256:" + "b" * 64, tmp_path / "signature.json", runner
        )
    assert len(calls) == 1
    assert calls[0][0] == "cosign"


def test_public_runtime_rejects_a_mutable_tag(monkeypatch, tmp_path):
    module = runtime_module(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="immutable"):
        module.verify_and_pull("ghcr.io/owner/api:2.0.1", tmp_path / "signature.json")


@pytest.mark.parametrize("status", [401, 404])
def test_public_hub_retries_then_returns_a_resolved_image(
    monkeypatch, tmp_path, status
):
    module = runtime_module(monkeypatch, tmp_path)
    attempts = []
    waits = []
    fetch = object()
    expected = {"digest": "sha256:" + "b" * 64}

    def resolve(repository, version, source, arches, fetcher):
        assert (repository, version, source, arches, fetcher) == (
            "owner/api",
            "2.0.1",
            "a" * 40,
            ["amd64"],
            fetch,
        )
        attempts.append(repository)
        if len(attempts) == 1:
            raise module.urllib.error.HTTPError(
                "https://registry", status, "pending", {}, None
            )
        return expected

    result, public_fetch = module.resolve_public_hub(
        "owner/api", ["amd64"], lambda repository: fetch, resolve, waits.append
    )
    assert result is expected
    assert public_fetch is fetch
    assert len(attempts) == 2
    assert waits == [15]


@pytest.mark.parametrize("status, attempts_expected", [(404, 24), (503, 1)])
def test_public_hub_failure_raises_without_an_uninitialized_result(
    monkeypatch, tmp_path, status, attempts_expected
):
    module = runtime_module(monkeypatch, tmp_path)
    attempts = []
    waits = []

    def resolve(*args):
        attempts.append(args)
        raise module.urllib.error.HTTPError(
            "https://registry", status, "unavailable", {}, None
        )

    with pytest.raises(module.urllib.error.HTTPError) as error:
        module.resolve_public_hub(
            "owner/api", ["amd64"], lambda repository: object(), resolve, waits.append
        )
    assert error.value.code == status
    assert len(attempts) == attempts_expected
    assert len(waits) == attempts_expected - 1
