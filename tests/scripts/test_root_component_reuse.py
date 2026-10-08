"""Root releases must verify immutable component packages without republishing."""

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "component_registry", ROOT / "scripts/prepare_release_draft.py"
)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


@pytest.mark.parametrize(
    "corruption", [None, "source", "version", "license", "signature", "attestation"]
)
def test_existing_nuget_is_checked_against_its_component_tag(
    tmp_path, monkeypatch, corruption
):
    sha = "a" * 40
    calls = []
    proof = tmp_path / "proof"
    proof.mkdir()
    monkeypatch.setattr(
        registry,
        "source",
        lambda tag: sha if tag == "csharp-v0.5.1" else pytest.fail(tag),
    )

    def fetch(url, path):
        version = "0.5.2" if corruption == "version" else "0.5.1"
        commit = "b" * 40 if corruption == "source" else sha
        license = "GPL-3.0" if corruption == "license" else "MIT"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "package.nuspec",
                f'<package><metadata><version>{version}</version><license>{license}</license><repository commit="{commit}"/></metadata></package>',
            )
            archive.writestr(".signature.p7s", b"repository-signature")

    def run(*args):
        calls.append(args)
        if args[0] == "dotnet" and corruption == "signature":
            raise subprocess.CalledProcessError(1, args)
        if args[0] == "gh" and corruption == "attestation":
            raise subprocess.CalledProcessError(1, args)
        return "[]"

    monkeypatch.setattr(registry, "fetch", fetch)
    monkeypatch.setattr(registry, "run", run)
    if corruption:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            registry.verify_nuget("0.5.1", tmp_path, proof)
    else:
        records = registry.verify_nuget("0.5.1", tmp_path, proof)
        assert len(records) == 2
        assert all(record["source"] == sha for record in records)
        assert (
            sum(
                command[:4] == ("dotnet", "nuget", "verify", "--all")
                for command in calls
            )
            == 2
        )
        attestations = [command for command in calls if command[0] == "gh"]
        assert len(attestations) == 2
        assert all(
            "refs/tags/csharp-v0.5.1" in command and sha in command
            for command in attestations
        )
        assert not any("publish" in command or "push" in command for command in calls)


def test_root_release_only_verifies_existing_component_packages():
    workflow = yaml.load(
        (ROOT / ".github/workflows/dev-create-release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    for job_name, component in [
        ("publish_nuget", "nuget"),
        ("publish_crates", "crates"),
    ]:
        job = workflow["jobs"][job_name]
        scripts = "\n".join(step.get("run", "") for step in job["steps"])
        assert f"--component {component}" in scripts
        assert "check_component_registry.py" in scripts
        assert "dotnet pack" not in scripts and "dotnet nuget push" not in scripts
        assert "cargo publish" not in scripts and "cargo package" not in scripts
        assert "secrets." not in json.dumps(job)
        assert job["permissions"]["attestations"] == "read"
        assert job["steps"][0]["with"]["fetch-depth"] == "0"


@pytest.mark.parametrize("component", ["nuget", "crates"])
@pytest.mark.parametrize("failure", [False, True])
def test_registry_entrypoint_propagates_failure_and_preserves_proof(
    tmp_path, monkeypatch, component, failure
):
    spec = importlib.util.spec_from_file_location(
        "verify_components", ROOT / "scripts/check_component_registry.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    output = tmp_path / "verification"
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_components", "--component", component, "--directory", str(output)],
    )
    monkeypatch.setattr(cli, "component_version", lambda name: "0.5.1")
    records = [{"name": "original-package", "sha256": "a" * 64, "source": "b" * 40}]

    def verify(version, registry, proof):
        assert version == "0.5.1" and registry.is_dir() and proof.is_dir()
        if failure:
            raise ValueError("Published package provenance mismatch")
        return records

    monkeypatch.setattr(
        cli, "verify_nuget" if component == "nuget" else "verify_crates", verify
    )
    if failure:
        with pytest.raises(ValueError, match="provenance mismatch"):
            cli.main()
        assert not (output / "proof/manifest.json").exists()
    else:
        cli.main()
        assert json.loads((output / "proof/manifest.json").read_text()) == records


def test_mismatched_csharp_versions_are_rejected_before_download(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "component_versions", ROOT / "scripts/check_component_registry.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    for name, version in [("PiperPlus.Core", "0.5.1"), ("PiperPlus.Cli", "0.5.2")]:
        path = tmp_path / f"src/csharp/{name}/{name}.csproj"
        path.parent.mkdir(parents=True)
        path.write_text(
            f"<Project><PropertyGroup><Version>{version}</Version></PropertyGroup></Project>"
        )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="versions differ"):
        cli.component_version("nuget")
