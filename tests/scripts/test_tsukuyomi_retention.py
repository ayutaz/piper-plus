"""Reject payload drift while allowing Hub-added LFS rules for this release."""

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.tsukuyomi_release import consumer


def git_blob(content):
    return hashlib.sha1(
        f"blob {len(content)}\0".encode() + content, usedforsecurity=False
    ).hexdigest()


@pytest.fixture
def retention(tmp_path, monkeypatch):
    old_attributes = b"*.onnx filter=lfs diff=lfs merge=lfs -text\n"
    sample = "releases/zs-v1/samples/ja-2-ft.wav"
    new_attributes = (
        old_attributes + f"{sample} filter=lfs diff=lfs merge=lfs -text\n".encode()
    )
    old = {
        "bytes": len(old_attributes),
        "blob_id": git_blob(old_attributes),
        "lfs_sha256": None,
    }
    before = {
        "target": {
            "revision": "before",
            "files": {
                ".gitattributes": old,
                "config.json": {"bytes": 10, "blob_id": "config", "lfs_sha256": None},
            },
        },
        "preserved_repositories": [],
    }
    receipt = {"files": [{"path": sample}]}
    (tmp_path / "publication-before-state.json").write_text(json.dumps(before))
    (tmp_path / "publication-receipt.json").write_text(json.dumps(receipt))
    target = {
        "private": False,
        "gated": False,
        "siblings": [
            {
                "rfilename": ".gitattributes",
                "size": len(new_attributes),
                "blobId": git_blob(new_attributes),
            },
            {"rfilename": "config.json", "size": 10, "blobId": "config"},
            {
                "rfilename": sample,
                "size": 123,
                "blobId": "sample",
                "lfs": {"sha256": "sample-sha"},
            },
        ],
    }
    contents = {"before": old_attributes, "after": new_attributes}
    requests = []

    def get(url, timeout):
        requests.append(url)
        revision = url.split("/resolve/")[1].split("/")[0]
        return SimpleNamespace(
            content=contents[revision],
            request=SimpleNamespace(headers={}),
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(consumer, "anonymous_metadata", lambda *args: target)
    monkeypatch.setattr(consumer, "HfApi", SimpleNamespace)
    return tmp_path, target, contents, SimpleNamespace(get=get), sample, requests


def test_hub_added_rule_preserves_existing_attributes_and_legacy_payloads(retention):
    workspace, _, _, session, sample, requests = retention
    result = consumer.verify_retention(session, "after", workspace)
    assert result["legacy_files_unchanged"] is True
    assert result["lfs_attributes_appended_for_release"] == [sample]
    assert len(requests) == 2
    assert all(url.endswith("/.gitattributes") for url in requests)


@pytest.mark.parametrize(
    "fault",
    [
        "old_rule_changed",
        "undeclared_file",
        "non_lfs_file",
        "other_attribute",
        "duplicate_rule",
        "wrong_blob",
        "legacy_payload",
        "legacy_missing",
    ],
)
def test_unexpected_repository_drift_is_rejected(retention, fault):
    workspace, target, contents, session, sample, _ = retention
    if fault == "old_rule_changed":
        contents["after"] = contents["after"].replace(b"*.onnx", b"*.bin")
    elif fault == "undeclared_file":
        contents["after"] = contents["after"].replace(
            sample.encode(), b"unreviewed.wav"
        )
    elif fault == "non_lfs_file":
        target["siblings"][2].pop("lfs")
    elif fault == "other_attribute":
        contents["after"] += b"* -diff\n"
    elif fault == "duplicate_rule":
        contents["after"] += contents["after"].splitlines(keepends=True)[-1]
    elif fault == "wrong_blob":
        target["siblings"][0]["blobId"] = "unexpected"
    elif fault == "legacy_payload":
        target["siblings"][1]["blobId"] = "changed"
    else:
        target["siblings"].pop(1)
    if fault != "wrong_blob":
        target["siblings"][0].update(
            size=len(contents["after"]), blobId=git_blob(contents["after"])
        )
    original = copy.deepcopy(target)
    with pytest.raises(ValueError):
        consumer.verify_retention(session, "after", workspace)
    assert target == original


def test_unchanged_attributes_need_no_content_download(retention):
    workspace, target, contents, session, _, requests = retention
    target["siblings"][0].update(
        size=len(contents["before"]), blobId=git_blob(contents["before"])
    )
    result = consumer.verify_retention(session, "after", workspace)
    assert result["lfs_attributes_appended_for_release"] == []
    assert requests == []
