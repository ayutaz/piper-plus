"""A signing repair must validate the exact public release images first."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml
from test_release_publish_enforcement import shell


ROOT = Path(__file__).resolve().parents[2]
REVISION = "71acf30c8e23e17b639fd40a8117415c3df55c0a"


def module():
    spec = importlib.util.spec_from_file_location(
        "docker_signature_resolution", ROOT / "scripts/resolve_docker_release_images.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def registry(architectures=("amd64", "arm64"), wrong_revision=None, wrong_version=None):
    routes = {}

    def descriptor(data, kind):
        raw = json.dumps(data, sort_keys=True).encode()
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        routes[f"/{kind}/{digest}"] = raw
        return {"digest": digest, "size": len(raw)}

    manifests = []
    for architecture in architectures:
        config = descriptor(
            {
                "os": "linux",
                "architecture": architecture,
                "config": {
                    "Labels": {
                        "org.opencontainers.image.revision": (
                            "a" * 40 if wrong_revision == architecture else REVISION
                        ),
                        "org.opencontainers.image.version": (
                            "9.9.9" if wrong_version == architecture else "2.0.0"
                        ),
                    }
                },
            },
            "blobs",
        )
        image = descriptor({"config": config, "layers": []}, "manifests")
        image["platform"] = {"os": "linux", "architecture": architecture}
        manifests.append(image)
    manifests.append(
        {
            "digest": "sha256:" + "0" * 64,
            "platform": {"os": "unknown", "architecture": "unknown"},
        }
    )
    routes["/manifests/2.0.0"] = json.dumps({"manifests": manifests}).encode()
    return routes


def resolve(routes):
    return module().resolve_image(
        "ayutaz/piper-plus/cpp-dev",
        "2.0.0",
        REVISION,
        {"amd64", "arm64"},
        routes.__getitem__,
    )


def test_exact_public_multiplatform_digest_is_selected():
    routes = registry()
    result = resolve(routes)
    assert result["reference"] == (
        "ghcr.io/ayutaz/piper-plus/cpp-dev@sha256:"
        + hashlib.sha256(routes["/manifests/2.0.0"]).hexdigest()
    )
    assert result["architectures"] == ["amd64", "arm64"]
    assert result["source_revision"] == REVISION


@pytest.mark.parametrize("architecture", ["amd64", "arm64"])
def test_any_platform_with_a_wrong_source_is_rejected(architecture):
    with pytest.raises(ValueError, match="revision"):
        resolve(registry(wrong_revision=architecture))


@pytest.mark.parametrize("architecture", ["amd64", "arm64"])
def test_any_platform_with_a_wrong_version_is_rejected(architecture):
    with pytest.raises(ValueError, match="version"):
        resolve(registry(wrong_version=architecture))


def test_missing_arm64_is_rejected():
    with pytest.raises(ValueError, match="architectures"):
        resolve(registry(architectures=("amd64",)))


@pytest.mark.parametrize("kind", ["manifests", "blobs"])
def test_tampered_registry_bytes_are_rejected(kind):
    routes = registry()
    path = next(path for path in routes if path.startswith(f"/{kind}/sha256:"))
    routes[path] += b" "
    with pytest.raises(ValueError, match="SHA256"):
        resolve(routes)


def test_missing_registry_manifest_fails():
    with pytest.raises(KeyError):
        resolve({})


def test_resolution_covers_every_approved_release_image():
    assert module().IMAGES == (
        ("cpp-dev", False),
        ("cpp-inference", False),
        ("python-train", False),
        ("python-inference", False),
        ("python-inference", True),
        ("webui", False),
        ("wyoming", False),
    )


@pytest.mark.parametrize(
    "name,cpu,job",
    [
        ("cpp-dev", False, "build-cpp-dev"),
        ("cpp-inference", False, "build-cpp-inference"),
        ("python-train", False, "build-python-train"),
        ("python-inference", False, "build-python-inference"),
        ("python-inference", True, "build-python-inference-cpu"),
        ("webui", False, "build-webui"),
        ("wyoming", False, "build-wyoming"),
    ],
)
def test_resolution_preserves_each_build_jobs_architectures(name, cpu, job):
    config = yaml.safe_load(
        (ROOT / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
    )
    build = next(
        step for step in config["jobs"][job]["steps"] if step.get("id") == "build"
    )
    expected = {
        platform.strip().split("/")[1]
        for platform in build["with"]["platforms"].split(",")
    }
    assert module().expected_architectures(name, cpu) == expected


def test_one_unpublished_image_leaves_no_signing_inputs(monkeypatch, tmp_path):
    script = module()
    output = tmp_path / "resolution.json"
    references = tmp_path / "references.txt"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolver",
            "--version",
            "2.0.0",
            "--source-revision",
            REVISION,
            "--output",
            str(output),
            "--references",
            str(references),
        ],
    )

    def fetcher(repository):
        if repository.endswith("/cpp-dev"):
            return registry(architectures=("amd64",)).__getitem__
        if repository.endswith("/cpp-inference"):
            return registry().__getitem__
        return {}.__getitem__

    monkeypatch.setattr(script, "public_fetcher", fetcher)
    with pytest.raises(KeyError):
        script.main()
    assert not output.exists()
    assert not references.exists()


def workflow():
    return yaml.load(
        (ROOT / ".github/workflows/release-docker-signatures.yml").read_text(
            encoding="utf-8"
        ),
        Loader=yaml.BaseLoader,
    )


def test_all_images_are_preflighted_before_signing():
    config = workflow()
    steps = config["jobs"]["sign"]["steps"]
    preflight = next(
        i
        for i, step in enumerate(steps)
        if "resolve_docker_release_images.py" in step.get("run", "")
    )
    signing = next(
        i for i, step in enumerate(steps) if "cosign sign" in step.get("run", "")
    )
    assert preflight < signing
    assert config["jobs"]["sign"]["permissions"]["id-token"] == "write"
    assert config["jobs"]["sign"]["permissions"]["packages"] == "write"
    assert not steps[preflight].get("continue-on-error")
    assert not steps[signing].get("continue-on-error")
    assert "--yes" in steps[signing]["run"]
    assert "--insecure" not in steps[signing]["run"]


@pytest.mark.parametrize(
    "reference,matching_source,success",
    [
        ("refs/tags/docker-signatures-v2.0.0", True, True),
        ("refs/heads/dev", True, False),
        ("refs/tags/docker-signatures-v2.0.0", False, False),
    ],
)
def test_only_the_immutable_signature_tag_can_sign(
    tmp_path, reference, matching_source, success
):
    step = next(
        step
        for step in workflow()["jobs"]["sign"]["steps"]
        if step.get("name") == "Validate immutable signing and build tags"
    )
    signer = "a" * 40
    tag_commit = signer if matching_source else "b" * 40
    git = (
        'case "$2" in '
        f"HEAD) echo {signer};; "
        f"refs/tags/docker-signatures-v2.0.0*) echo {tag_commit};; "
        f"refs/tags/docker-v2.0.0*) echo {REVISION};; "
        "*) exit 1;; esac"
    )
    result = shell(
        tmp_path,
        step["run"],
        stubs={"git": git},
        env={"RELEASE_VERSION": "2.0.0", "GITHUB_REF": reference},
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    if success:
        assert f"SOURCE_REVISION={REVISION}" in (tmp_path / "env").read_text(
            encoding="utf-8"
        )
