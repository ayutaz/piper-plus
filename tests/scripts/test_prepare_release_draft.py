"""A remote draft update must preserve inventory and reject unchecked bytes."""

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "prepare_release_draft", ROOT / "scripts/prepare_release_draft.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_root_inventory_covers_every_payload_and_manifest():
    names = module.expected_assets("2.0.0")
    assert len(names) == 26
    assert set(module.native_assets()) < names
    assert "LICENSE_ATTRIBUTIONS.md" in names
    assert "MODEL_CARD.md" in names
    assert "checksums-sha256.txt" in names


@pytest.mark.parametrize("version", ["../2.0.0", "2.0", "2.0.0;echo", ""])
def test_version_rejects_paths_and_commands(version):
    with pytest.raises(ValueError):
        module.expected_assets(version)


@pytest.mark.parametrize("draft", [False, None])
def test_public_release_is_never_mutated(draft):
    with pytest.raises(ValueError, match="draft"):
        module.validate_root({"draft": draft, "assets": []}, "2.0.0")


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "extra"])
def test_inventory_mismatch_is_rejected(corruption):
    assets = [{"name": name} for name in module.expected_assets("2.0.0")]
    if corruption == "missing":
        assets.pop()
    elif corruption == "duplicate":
        assets.append(assets[0])
    else:
        assets.append({"name": "unexpected.zip"})
    with pytest.raises(ValueError, match="inventory"):
        module.validate_root({"draft": True, "assets": assets}, "2.0.0")


def test_downloaded_payload_must_match_server_digest_and_size(tmp_path):
    path = tmp_path / "asset.zip"
    path.write_bytes(b"actual payload")
    descriptor = {
        "size": path.stat().st_size,
        "digest": "sha256:" + module.digest(path),
    }
    module.check_download(path, descriptor)
    path.write_bytes(b"tampered bytes")
    with pytest.raises(ValueError, match="download"):
        module.check_download(path, descriptor)


def test_missing_server_digest_is_not_accepted(tmp_path):
    path = tmp_path / "asset.zip"
    path.write_bytes(b"payload")
    with pytest.raises(ValueError, match="download"):
        module.check_download(path, {"size": 7, "digest": None})


def test_preparing_a_draft_after_component_signing_preserves_exact_payloads():
    names = {name for name, kind in module.native_assets().items() if kind == "rust"}
    assets = [{"name": name} for name in names | {n + ".cosign.bundle" for n in names}]
    module.validate_component({"assets": assets}, "rust")
    with pytest.raises(ValueError, match="inventory"):
        module.validate_component(
            {"assets": assets + [{"name": "untrusted.zip"}]}, "rust"
        )
    with pytest.raises(ValueError, match="inventory"):
        module.validate_component(
            {"assets": [{"name": n + ".cosign.bundle"} for n in names]}, "rust"
        )


@pytest.mark.parametrize(
    "corruption", [None, "source", "tag", "missing", "duplicate", "digest"]
)
def test_recovery_receipt_must_bind_exact_source_and_every_shared_asset(
    monkeypatch, corruption
):
    from check_shared_release_recovery import archives

    monkeypatch.setattr(module, "source", lambda tag: "a" * 40)
    records = [
        {
            "artifact_id": i + 1,
            "artifact_digest": "sha256:" + "c" * 64,
            "payload": output,
            "sha256": "b" * 64,
        }
        for i, (_, output) in enumerate(archives("v2.0.1").values())
    ]
    receipt = {
        "source": "a" * 40,
        "tag": "v2.0.1",
        "build_run": 71,
        "artifacts": records,
    }
    if corruption in ("source", "tag"):
        receipt[corruption] = "unrelated"
    elif corruption == "missing":
        records.pop()
    elif corruption == "duplicate":
        records[-1] = records[0]
    elif corruption == "digest":
        records[0]["sha256"] = "not-a-digest"
    if corruption:
        with pytest.raises(ValueError):
            module.validate_shared_receipt(receipt, "v2.0.1")
    else:
        result = module.validate_shared_receipt(receipt, "v2.0.1")
        assert len(result) == 9 and set(result.values()) == {"b" * 64}


def test_normal_shared_verification_still_requires_original_build_attestation(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(module, "attest", lambda *args: calls.append(args))
    module.verify_shared(tmp_path / "native.zip", "v2.0.1", tmp_path, None)
    assert calls == [
        (tmp_path / "native.zip", "v2.0.1", "release-shared-lib.yml", tmp_path)
    ]
    with pytest.raises(ValueError):
        module.verify_shared(tmp_path / "native.zip", "v2.0.1", tmp_path, {})


@pytest.mark.parametrize(
    "invocation",
    [
        "https://github.com/ayutaz/piper-plus/actions/runs/77/attempts/1",
        "https://github.com/ayutaz/piper-plus/actions/runs/78/attempts/1",
    ],
)
def test_recovery_signature_must_match_exact_workflow_invocation(invocation):
    verified = [
        {
            "verificationResult": {
                "statement": {
                    "predicate": {
                        "runDetails": {"metadata": {"invocationId": invocation}}
                    }
                }
            }
        }
    ]
    if "/runs/77/" in invocation:
        module.validate_recovery_invocation(verified, "77", 1)
    else:
        with pytest.raises(ValueError):
            module.validate_recovery_invocation(verified, "77", 1)


@pytest.mark.parametrize(
    "corruption", [None, "verifier", "signature", "invocation", "artifact", "build"]
)
def test_signed_recovery_chain_binds_verifier_invocation_build_and_artifact(
    tmp_path, monkeypatch, corruption
):
    import json
    import subprocess

    from check_shared_release_recovery import archives

    root_sha, verifier_sha = "a" * 40, "b" * 40
    monkeypatch.setattr(module, "source", lambda tag: root_sha)
    specs = archives("v2.0.1")
    records = [
        {
            "artifact_id": i + 1,
            "artifact_digest": "sha256:" + "c" * 64,
            "payload": output,
            "sha256": "d" * 64,
        }
        for i, (_, output) in enumerate(specs.values())
    ]
    receipt = {
        "source": root_sha,
        "tag": "v2.0.1",
        "build_run": 71,
        "artifacts": records,
    }
    descriptors = [
        {
            "id": i + 1,
            "name": name,
            "digest": "sha256:" + ("0" if corruption == "artifact" else "c") * 64,
            "expired": False,
        }
        for i, name in enumerate(specs)
    ]
    calls = []

    def run(*args):
        calls.append(args)
        if args[:2] == ("gh", "api"):
            route = args[2]
            if route.endswith("/77"):
                return json.dumps(
                    {
                        "head_sha": "0" * 40
                        if corruption == "verifier"
                        else verifier_sha,
                        "head_branch": "fix/recovery",
                        "event": "workflow_dispatch",
                        "path": ".github/workflows/release-verify.yml",
                        "status": "completed",
                        "conclusion": "success",
                        "run_attempt": 1,
                    }
                )
            if route.endswith("/71"):
                return json.dumps(
                    {
                        "head_sha": "0" * 40 if corruption == "build" else root_sha,
                        "head_branch": "v2.0.1",
                        "event": "push",
                        "path": ".github/workflows/release-shared-lib.yml",
                        "status": "completed",
                    }
                )
            if "/jobs?" in route:
                return json.dumps(
                    {
                        "jobs": [
                            {"name": "Build windows-x64", "conclusion": "success"},
                            {
                                "name": "Create Release",
                                "conclusion": "failure",
                                "steps": [
                                    {
                                        "name": "Generate checksums",
                                        "conclusion": "failure",
                                    }
                                ],
                            },
                        ]
                    }
                )
            if "/artifacts?" in route:
                return json.dumps({"artifacts": descriptors})
            pytest.fail(route)
        if args[:3] == ("gh", "run", "download"):
            (Path(args[-1]) / "shared-recovery-proof.json").write_text(
                json.dumps(receipt)
            )
            return ""
        if args[:3] == ("gh", "attestation", "verify"):
            assert "--source-ref" in args and "refs/heads/fix/recovery" in args
            assert args[args.index("--source-digest") + 1] == verifier_sha
            assert args[args.index("--signer-digest") + 1] == verifier_sha
            assert "--deny-self-hosted-runners" in args
            if corruption == "signature":
                raise subprocess.CalledProcessError(1, args)
            run_id = 78 if corruption == "invocation" else 77
            return json.dumps(
                [
                    {
                        "verificationResult": {
                            "statement": {
                                "predicate": {
                                    "runDetails": {
                                        "metadata": {
                                            "invocationId": f"https://github.com/ayutaz/piper-plus/actions/runs/{run_id}/attempts/1"
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            )
        pytest.fail(str(args))

    monkeypatch.setattr(module, "run", run)
    if corruption:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            module.shared_recovery("77", verifier_sha, "v2.0.1", tmp_path)
    else:
        result = module.shared_recovery("77", verifier_sha, "v2.0.1", tmp_path)
        assert len(result) == 9 and set(result.values()) == {"d" * 64}
        assert (tmp_path / "shared-recovery/attestation.json").is_file()
