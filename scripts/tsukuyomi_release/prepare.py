"""Create a publication-ready copy, keeping every listening field pending."""

import argparse
import hashlib
import shutil
from pathlib import Path

from scripts.tsukuyomi_release.record_review import END, START, json_bytes, read_json


PENDING = """**Human review is pending; quality approval is
not claimed.** This release must not be published until the current listening
review has been recorded and the release decision has been made."""


def prepare(source, output):
    source = source.resolve()
    output = output.resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError(
            "output must be a fresh directory outside the source workspace"
        )
    source_release = source / "bundle/releases/zs-v1"
    manifest = read_json(source_release / "manifest.json")
    if manifest["human_review_status"] != "pending":
        raise ValueError("source must be the unreviewed candidate")
    for entry in manifest["files"]:
        path = source_release / entry["path"]
        if not path.resolve().is_relative_to(source_release) or path.is_symlink():
            raise ValueError("manifest path escapes source release")
        if (
            path.stat().st_size != entry["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
        ):
            raise ValueError(f"source hash mismatch: {entry['path']}")
    source_card = (source_release / "README.md").read_text(encoding="utf-8")
    if source_card.count(PENDING) != 1:
        raise ValueError("expected pending listening text is missing or repeated")
    output.mkdir(parents=True)
    shutil.copytree(source / "bundle", output / "bundle")
    for name in (
        "legacy-tsukuyomi-README.md",
        "candidate-audit.json",
        "checkpoint-load-results.json",
        "consumer-review-results.json",
        "voice-metrics.json",
    ):
        shutil.copyfile(source / name, output / name)
    release = output / "bundle/releases/zs-v1"
    card = source_card.replace(PENDING, START + "\n" + PENDING + "\n" + END)
    (release / "README.md").write_text(card, encoding="utf-8")
    for entry in manifest["files"]:
        if entry["path"] == "README.md":
            content = (release / "README.md").read_bytes()
            entry.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    (release / "manifest.json").write_bytes(json_bytes(manifest))
    (release / "SHA256SUMS").write_text(
        "".join(f"{e['sha256']}  {e['path']}\n" for e in manifest["files"]),
        encoding="utf-8",
    )
    template = {
        "reviewer": "user",
        "release_decision": "pending",
        "recorded_at": None,
        "user_message": None,
        "assessments": dict.fromkeys(("reading", "similarity", "naturalness", "noise")),
        "sample_sha256": {
            entry["path"]: entry["sha256"]
            for entry in manifest["files"]
            if entry["path"].startswith("samples/ja-")
        },
    }
    (output / "human-review-template.json").write_bytes(json_bytes(template))
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.source, args.output))


if __name__ == "__main__":
    main()
