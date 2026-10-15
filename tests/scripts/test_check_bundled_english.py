"""The reviewed large-file exemption must not admit changed model/code bytes."""

import json
import shutil

import pytest

from scripts import check_bundled_english as gate


@pytest.fixture
def copy(tmp_path):
    for relative in gate.TARGETS:
        shutil.copytree(
            gate.ROOT / relative,
            tmp_path / relative,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    return tmp_path


def test_real_bundle():
    gate.check()


def test_changed_model_is_rejected(copy):
    (copy / gate.TARGETS[0] / "checkpoint20.npz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="asset changed"):
        gate.check(copy)


def test_rewriting_both_manifests_cannot_approve_changed_code(copy):
    for relative in gate.TARGETS:
        target = copy / relative
        (target / "g2p.py").write_bytes(b"changed code")
        manifest = json.loads((target / "provenance.json").read_text())
        manifest["files"]["g2p.py"] = gate.digest(b"changed code")
        (target / "provenance.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="provenance"):
        gate.check(copy)


def test_additional_file_in_both_bundles_is_rejected(copy):
    for relative in gate.TARGETS:
        (copy / relative / "unexpected.py").write_text("# GPL-3.0-only\n")
    with pytest.raises(ValueError, match="Unexpected bundled files"):
        gate.check(copy)


def test_changed_upstream_identity_in_both_manifests_is_rejected(copy):
    for relative in gate.TARGETS:
        target = copy / relative / "provenance.json"
        manifest = json.loads(target.read_text())
        manifest["version"] = "unreviewed"
        target.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="provenance"):
        gate.check(copy)


def test_missing_attribution_is_rejected(copy):
    (copy / gate.TARGETS[0] / "NOTICE.txt").write_text("incorrect notice")
    with pytest.raises(ValueError, match="attribution"):
        gate.check(copy)


def test_import_rejects_untrusted_archive_before_writing(tmp_path):
    archive = tmp_path / "fake.whl"
    archive.write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="Untrusted"):
        gate.import_wheel(archive)
