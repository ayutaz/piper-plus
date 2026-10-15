"""Prepare a pinned upload; --apply requires a recorded human listening result."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests
from huggingface_hub import CommitOperationAdd, HfApi, ModelCard


sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2] / "output/public-tsukuyomi-release-20261010"
DEFAULT_WORKSPACE = ROOT
REPO = "ayousanz/piper-plus-tsukuyomi-chan"
PARENT = "36b59c825c36bd386b8960cf3f604382f52f2a87"
BASE_REVISION = "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1"
ALLOWED = {
    "README.md",
    "NOTICE.md",
    "config.json",
    "tsukuyomi.ckpt",
    "tsukuyomi.onnx",
    "tsukuyomi.onnx.json",
    "training_recipe.json",
    "provenance.json",
    "verification.json",
    "examples/synthesize.py",
    "licenses/MIT.txt",
    *[
        f"samples/{name}-ft.wav"
        for name in ["ja-1", "ja-2", "ja-3", "en", "zh", "es", "fr", "pt"]
    ],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def metadata(info):
    return {
        "repo": info.id,
        "revision": info.sha,
        "private": info.private,
        "gated": info.gated,
        "files": {
            file.rfilename: {
                "bytes": file.size,
                "blob_id": file.blob_id,
                "lfs_sha256": file.lfs.sha256 if file.lfs else None,
            }
            for file in info.siblings
        },
    }


def prepare_root_readme(workspace=ROOT):
    bundle = workspace / "bundle"
    release = bundle / "releases/zs-v1"
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        f"https://huggingface.co/{REPO}/resolve/{PARENT}/README.md", timeout=30
    )
    response.raise_for_status()
    require(
        "Authorization" not in response.request.headers,
        "root README must be downloaded anonymously",
    )
    original = response.content.decode("utf-8")
    (workspace / "legacy-tsukuyomi-README.md").write_text(original, encoding="utf-8")
    require(original.startswith("---\n"), "legacy model card frontmatter missing")
    split = original.index("\n---", 4) + len("\n---")
    status = read_json(release / "verification.json")["human_review_status"]
    intro = f"\n\n## Public-base fine-tune: zs-v1\n\nThe [zs-v1 release](releases/zs-v1/README.md) is the existing 500 epoch\nTsukuyomi-chan fine-tune from the same v7 epoch32 generation as\n[the public base](https://huggingface.co/ayousanz/piper-plus-base/tree/{BASE_REVISION}/releases/zs-v1).\nUse its ONNX and config together. This fixed voice requires no reference WAV\nor speaker encoder. The release includes a fine-tuning checkpoint, exact\nhashes, synthetic samples, credits and observed training provenance.\n\nIt is an experimental baseline. Listening review status: **{status}**.\nFresh three-text CAM++ mean SECS was 0.6617 (FT), 0.6538 (legacy) and 0.6956\n(public-base Zero-Shot); these results do not establish improved voice quality.\nSee the release card and verification record for the review scope and limits.\n\nThe original root model files, configuration, samples and description below\nremain available for existing consumers and package aliases. Downloading\nthrough an older package alias still selects those original files.\n\n## Original root release\n"
    (bundle / "README.md").write_text(
        original[:split] + intro + original[split:], encoding="utf-8"
    )
    ModelCard.load(bundle / "README.md").validate()


def validate(workspace=ROOT):
    release = workspace / "bundle/releases/zs-v1"
    manifest = read_json(release / "manifest.json")
    entries = manifest["files"]
    require(
        len(entries) == len(ALLOWED)
        and {entry["path"] for entry in entries} == ALLOWED,
        "unexpected manifest inventory",
    )
    actual = {
        path.relative_to(release).as_posix()
        for path in release.rglob("*")
        if path.is_file()
    }
    require(
        actual == ALLOWED | {"manifest.json", "SHA256SUMS"},
        "unexpected release file inventory",
    )
    for entry in entries:
        path = release / entry["path"]
        require(
            path.resolve().is_relative_to(release.resolve())
            and (not path.is_symlink()),
            "release path escape",
        )
        require(
            path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"],
            f"artifact hash mismatch: {entry['path']}",
        )
    sums = (release / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    require(len(sums) == len(entries), "SHA256SUMS count mismatch")
    require(
        dict(line.split("  ", 1)[::-1] for line in sums)
        == {entry["path"]: entry["sha256"] for entry in entries},
        "SHA256SUMS inventory mismatch",
    )
    require(
        (release / "config.json").read_bytes()
        == (release / "tsukuyomi.onnx.json").read_bytes(),
        "config pair mismatch",
    )
    require(
        digest(release / "tsukuyomi.onnx")
        == "5fcef335c2bd69a4d2b5512e46d971427a653bf252097e2fb73618e7a584f331",
        "ONNX changed from checked source",
    )
    require(
        digest(release / "tsukuyomi.ckpt")
        == "7d6a15c4cd9a3c208f71ddf604efb462a023dfc348e266fa5be018f3d9ddba82",
        "checkpoint changed from checked source",
    )
    verification = read_json(release / "verification.json")
    require(
        manifest["human_review_status"] == verification["human_review_status"],
        "review status mismatch",
    )
    require(
        manifest["quality_approval"] is False
        and verification["quality_approval"] is False,
        "experimental release must not claim universal quality approval",
    )
    card = ModelCard.load(release / "README.md")
    require(
        card.data.license == "other"
        and card.data.base_model == "ayousanz/piper-plus-base",
        "card license/base mismatch",
    )
    card.validate()
    return verification


def human_gate(verification, workspace=ROOT):
    release = workspace / "bundle/releases/zs-v1"
    require(
        (workspace / "human-review.json").is_file(),
        "Actual human listening result is required before publication",
    )
    review = read_json(workspace / "human-review.json")
    require(
        review["release_decision"] == "publish_experimental"
        and review["reviewer"] == "user",
        "human release decision missing",
    )
    require(
        review["user_message"] and review["recorded_at"],
        "actual user result and timestamp missing",
    )
    require(
        review["sample_sha256"]
        == {
            entry["path"]: entry["sha256"]
            for entry in read_json(release / "manifest.json")["files"]
            if entry["path"].startswith("samples/ja-")
        },
        "listened sample hashes do not match release",
    )
    for field in ["reading", "similarity", "naturalness", "noise"]:
        require(
            isinstance(review["assessments"][field], str)
            and review["assessments"][field].strip(),
            f"{field} assessment missing",
        )
    require(
        verification["human_review_status"] == "recorded",
        "release review status is still pending",
    )
    require(verification["human_review"] == review, "release listening record mismatch")
    require(
        "Human review is pending"
        not in (release / "README.md").read_text(encoding="utf-8"),
        "model card still says pending",
    )


def guard_parent(before):
    require(
        before.sha == PARENT and before.private is False and (before.gated is False),
        "HF parent or visibility changed; inspect before publishing",
    )
    require(
        not any(
            file.rfilename.startswith("releases/zs-v1/") for file in before.siblings
        ),
        "zs-v1 already exists",
    )


def preserve_snapshot(path, snapshot):
    if path.exists():
        require(
            read_json(path) == snapshot,
            "HF baseline changed since preparation; inspect before publishing",
        )
    else:
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    bundle = workspace / "bundle"
    verification = validate(workspace)
    if args.apply:
        human_gate(verification, workspace)
    prepare_root_readme(workspace)
    names = ["README.md"] + [
        f"releases/zs-v1/{name}"
        for name in sorted(ALLOWED | {"manifest.json", "SHA256SUMS"})
    ]
    require(
        {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file()
        }
        == set(names),
        "bundle inventory mismatch",
    )
    api = HfApi()
    require(api.whoami()["name"] == "ayousanz", "HF account mismatch")
    before = api.model_info(REPO, files_metadata=True)
    guard_parent(before)
    preserved_names = [
        "ayousanz/piper-plus-base",
        "ayousanz/piper-plus-zero-shot-tsukuyomi",
        "ayousanz/piper-plus-zero-shot-multi-6lang-v7",
        "ayousanz/piper-plus-zero-shot-multi-7lang-v8",
        "ayousanz/campplus-onnx",
    ]
    preserved = [
        metadata(api.model_info(repo, files_metadata=True)) for repo in preserved_names
    ]
    require(
        next(item for item in preserved if item["repo"] == "ayousanz/piper-plus-base")[
            "revision"
        ]
        == BASE_REVISION,
        "public base revision changed",
    )
    base = next(
        item for item in preserved if item["repo"] == "ayousanz/piper-plus-base"
    )
    require(
        base["private"] is False and base["gated"] is False,
        "public base visibility changed",
    )
    snapshot = {"target": metadata(before), "preserved_repositories": preserved}
    preserve_snapshot(workspace / "publication-before-state.json", snapshot)
    files = [
        {
            "path": name,
            "bytes": (bundle / name).stat().st_size,
            "sha256": digest(bundle / name),
        }
        for name in names
    ]
    summary = {
        "repo": REPO,
        "parent": PARENT,
        "apply": args.apply,
        "human_review_status": verification["human_review_status"],
        "files": files,
        "total_bytes": sum(file["bytes"] for file in files),
    }
    (workspace / "upload-dry-run.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "repo": REPO,
                "files": len(files),
                "bytes": summary["total_bytes"],
                "human_review_status": verification["human_review_status"],
                "apply": args.apply,
            }
        ),
        flush=True,
    )
    if args.apply:
        for file in files:
            require(
                digest(bundle / file["path"]) == file["sha256"],
                "file changed during publication preflight",
            )
        result = api.create_commit(
            repo_id=REPO,
            operations=[
                CommitOperationAdd(
                    path_in_repo=name, path_or_fileobj=str(bundle / name)
                )
                for name in names
            ],
            commit_message="Publish zs-v1 Tsukuyomi fine-tune from the public base",
            commit_description="Add the checked experimental 500 epoch fine-tune, matching configs, weights-only checkpoint, provenance, listening review, synthetic samples and usage terms. Preserve the legacy root model and research repositories.",
            parent_commit=PARENT,
        )
        receipt = {**summary, "commit": result.oid, "url": result.commit_url}
        (workspace / "publication-receipt.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        print(json.dumps({"commit": result.oid, "url": result.commit_url}), flush=True)


if __name__ == "__main__":
    main()
