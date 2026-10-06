"""Check NuGet's signed public copy against the actual build payload."""

import importlib.util
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def checker():
    spec = importlib.util.spec_from_file_location(
        "nuget_copy", ROOT / "scripts/check_nuget_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compare_packages


def package(path, signed=False, changed=False, extra=False, removed=False):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "PiperPlus.Core.nuspec",
            "<package><metadata><id>PiperPlus.Core</id><version>0.5.0</version></metadata></package>",
        )
        if not removed:
            archive.writestr(
                "lib/net8.0/PiperPlus.Core.dll", b"changed" if changed else b"built DLL"
            )
        archive.writestr("LICENSE.md", b"MIT fixture")
        if signed:
            archive.writestr(".signature.p7s", b"repository signature fixture")
        if extra:
            archive.writestr("unexpected.dll", b"extra DLL")
    return path


def test_repository_signature_addition_preserves_build_payload(tmp_path):
    checker()(
        package(tmp_path / "built.nupkg"),
        package(tmp_path / "public.nupkg", signed=True),
    )


@pytest.mark.parametrize("mutation", ["changed", "extra", "removed"])
def test_changed_public_payload_is_rejected(tmp_path, mutation):
    with pytest.raises(ValueError, match="payload"):
        checker()(
            package(tmp_path / "built.nupkg"),
            package(tmp_path / "public.nupkg", signed=True, **{mutation: True}),
        )


def test_public_package_must_have_repository_signature(tmp_path):
    with pytest.raises(ValueError, match="signature"):
        checker()(package(tmp_path / "built.nupkg"), package(tmp_path / "public.nupkg"))


def test_duplicate_members_cannot_hide_changed_payload(tmp_path):
    public = package(tmp_path / "public.nupkg", signed=True)
    with zipfile.ZipFile(public, "a") as archive:
        with pytest.warns(UserWarning):
            archive.writestr("lib/net8.0/PiperPlus.Core.dll", b"different")
    with pytest.raises(ValueError, match="duplicate"):
        checker()(package(tmp_path / "built.nupkg"), public)


def test_public_nuget_copy_is_verified_before_final_attestation():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/dev-create-release.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["publish_nuget"]["steps"]
    publish = next(
        i for i, step in enumerate(steps) if step.get("name") == "Publish to NuGet"
    )
    verify = next(
        i
        for i, step in enumerate(steps)
        if "check_nuget_package.py" in step.get("run", "")
    )
    attest = next(
        i
        for i, step in enumerate(steps)
        if step.get("with", {}).get("subject-path") == "published-nupkgs/*.nupkg"
    )
    assert publish < verify < attest
    assert "dotnet nuget verify" in steps[verify]["run"]


def test_nuget_download_allows_bounded_registry_propagation(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "nuget_download", ROOT / "scripts/check_nuget_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **kwargs: commands.append((command, kwargs)),
    )
    module.download_public_copy(
        package(tmp_path / "built.nupkg"), tmp_path / "public.nupkg"
    )
    command, kwargs = commands[0]
    assert kwargs["check"] is True
    assert "--retry-all-errors" in command  # Registry 404s must be retried too.
    assert int(command[command.index("--retry") + 1]) >= 120
    assert int(command[command.index("--retry-max-time") + 1]) == 1200
    assert int(command[command.index("--max-time") + 1]) <= 30
