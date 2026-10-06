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
