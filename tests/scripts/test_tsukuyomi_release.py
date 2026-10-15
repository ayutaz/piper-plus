"""Check that listening records cannot silently approve or change a release."""

import hashlib
import json

import pytest

from scripts.tsukuyomi_release.record_review import record_review


def test_missing_listening_record_stops_before_any_hf_client(release):
    from scripts.tsukuyomi_release import publish_bundle

    workspace, _, _ = release
    with pytest.raises(ValueError, match="Actual human listening"):
        publish_bundle.human_gate({"human_review_status": "pending"}, workspace)


@pytest.mark.parametrize("fault", ["stale", "private", "gated", "already_published"])
def test_hf_parent_and_visibility_drift_are_rejected(fault):
    from types import SimpleNamespace

    from scripts.tsukuyomi_release.publish_bundle import PARENT, guard_parent

    before = SimpleNamespace(sha=PARENT, private=False, gated=False, siblings=[])
    if fault == "stale":
        before.sha = "changed"
    elif fault == "private":
        before.private = True
    elif fault == "gated":
        before.gated = "manual"
    else:
        before.siblings = [SimpleNamespace(rfilename="releases/zs-v1/tsukuyomi.onnx")]
    with pytest.raises(ValueError):
        guard_parent(before)


def test_changed_baseline_is_rejected_without_overwriting_receipt(tmp_path):
    from scripts.tsukuyomi_release.publish_bundle import preserve_snapshot

    path = tmp_path / "publication-before-state.json"
    preserve_snapshot(path, {"target": "reviewed baseline"})
    original = path.read_bytes()
    with pytest.raises(ValueError, match="baseline changed"):
        preserve_snapshot(path, {"target": "changed baseline"})
    assert path.read_bytes() == original


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def release(tmp_path):
    path = tmp_path / "bundle/releases/zs-v1"
    path.mkdir(parents=True)
    for name in ("tsukuyomi.onnx", "tsukuyomi.ckpt", "config.json"):
        (path / name).write_bytes(b"immutable model payload")
    write_json(
        path / "verification.json",
        {"human_review_status": "pending", "quality_approval": False},
    )
    (path / "README.md").write_text(
        "Model card\n<!-- listening-review:start -->\nHuman review is pending.\n<!-- listening-review:end -->\n",
        encoding="utf-8",
    )
    (path / "samples").mkdir()
    for name in ("ja-1", "ja-2", "ja-3"):
        (path / "samples" / f"{name}-ft.wav").write_bytes(name.encode())
    entries = [
        {
            "path": p.relative_to(path).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(path.rglob("*"))
        if p.is_file()
    ]
    write_json(
        path / "manifest.json",
        {"human_review_status": "pending", "quality_approval": False, "files": entries},
    )
    (path / "SHA256SUMS").write_text(
        "".join(f"{e['sha256']}  {e['path']}\n" for e in entries), encoding="utf-8"
    )
    review = {
        "reviewer": "user",
        "user_message": "Test-only fixture; no actual listening approval.",
        "recorded_at": "2026-10-12T00:00:00+00:00",
        "release_decision": "publish_experimental",
        "assessments": dict.fromkeys(
            ("reading", "similarity", "naturalness", "noise"), "test assessment"
        ),
        "sample_sha256": {
            e["path"]: e["sha256"] for e in entries if e["path"].startswith("samples/")
        },
    }
    return tmp_path, path, review


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_review_updates_all_metadata_and_hashes_without_changing_weights(release):
    workspace, path, review = release
    payloads = {
        name: (path / name).read_bytes()
        for name in ("tsukuyomi.onnx", "tsukuyomi.ckpt", "config.json")
    }
    record_review(workspace, review)
    verification = json.loads((path / "verification.json").read_text())
    manifest = json.loads((path / "manifest.json").read_text())
    assert verification["human_review"] == review
    assert (
        verification["human_review_status"]
        == manifest["human_review_status"]
        == "recorded"
    )
    assert verification["quality_approval"] is manifest["quality_approval"] is False
    assert "Human review is pending" not in (path / "README.md").read_text()
    assert "test assessment" in (path / "README.md").read_text()
    for entry in manifest["files"]:
        assert (
            entry["sha256"]
            == hashlib.sha256((path / entry["path"]).read_bytes()).hexdigest()
        )
        assert entry["bytes"] == (path / entry["path"]).stat().st_size
    for name, expected in payloads.items():
        assert (path / name).read_bytes() == expected
    assert json.loads((workspace / "human-review.json").read_text()) == review


@pytest.mark.parametrize(
    "fault",
    ["missing_assessment", "wrong_sample", "rejected", "unrecorded", "missing_message"],
)
def test_invalid_review_makes_no_changes(release, fault):
    workspace, _, review = release
    if fault == "missing_assessment":
        review["assessments"].pop("noise")
    elif fault == "wrong_sample":
        review["sample_sha256"]["samples/ja-1-ft.wav"] = "0" * 64
    elif fault == "rejected":
        review["release_decision"] = "revise"
    elif fault == "unrecorded":
        review["recorded_at"] = ""
    else:
        review["user_message"] = ""
    before = snapshot(workspace)
    with pytest.raises(ValueError):
        record_review(workspace, review)
    assert snapshot(workspace) == before


def test_payload_drift_is_rejected_before_rehashing(release):
    workspace, path, review = release
    (path / "tsukuyomi.onnx").write_bytes(b"changed after review")
    before = snapshot(workspace)
    with pytest.raises(ValueError, match="hash"):
        record_review(workspace, review)
    assert snapshot(workspace) == before
