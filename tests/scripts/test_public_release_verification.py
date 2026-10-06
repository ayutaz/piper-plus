"""Public verification rejects incomplete signatures and an unexpected signer."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "verify_public_release", ROOT / "scripts/verify_public_release.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    ("tag", "count"), [("v2.0.0", 26), ("rust-v0.5.2", 3), ("csharp-v0.5.1", 6)]
)
def test_inventory_requires_a_bundle_for_every_expected_payload(tag, count):
    names = module.expected_payloads(tag)
    assert len(names) == count
    assets = [{"name": name} for name in names]
    with pytest.raises(ValueError, match="inventory"):
        module.validate_public({"draft": False, "assets": assets}, tag)
    assets += [{"name": name + ".cosign.bundle"} for name in names]
    module.validate_public({"draft": False, "assets": assets}, tag)


@pytest.mark.parametrize("tag", ["../v2.0.0", "v2.0", "npm-v0.8.0", "v2.0.0;echo"])
def test_unsupported_tags_are_rejected(tag):
    with pytest.raises(ValueError):
        module.expected_payloads(tag)


@pytest.mark.parametrize("draft", [True, None])
def test_a_draft_cannot_be_reported_as_public(draft):
    with pytest.raises(ValueError, match="public"):
        module.validate_public({"draft": draft, "assets": []}, "v2.0.0")


def test_extra_and_duplicate_assets_fail_the_inventory_gate():
    names = module.expected_payloads("rust-v0.5.2")
    assets = [{"name": name} for name in names | {n + ".cosign.bundle" for n in names}]
    for extra in (assets[0], {"name": "unexpected.zip"}):
        with pytest.raises(ValueError, match="inventory"):
            module.validate_public(
                {"draft": False, "assets": assets + [extra]}, "rust-v0.5.2"
            )


def test_signer_is_bound_to_exact_workflow_tag_commit_and_issuer(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(
        module, "run", lambda *args: commands.append(args) or "Verified OK"
    )
    module.verify_signature(tmp_path / "asset", tmp_path / "bundle", "v2.0.0", "a" * 40)
    command = commands[0]
    assert command[command.index("--certificate-identity") + 1] == (
        "https://github.com/ayutaz/piper-plus/.github/workflows/"
        "cosign-release-artifacts.yml@refs/tags/v2.0.0"
    )
    assert command[command.index("--certificate-github-workflow-sha") + 1] == "a" * 40
    assert (
        command[command.index("--certificate-oidc-issuer") + 1]
        == "https://token.actions.githubusercontent.com"
    )
    assert "--offline" not in command


def test_crypto_verification_failure_is_not_downgraded_to_a_warning(
    monkeypatch, tmp_path
):
    def fail(*args):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(module, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        module.verify_signature(
            tmp_path / "asset", tmp_path / "bundle", "v2.0.0", "a" * 40
        )
