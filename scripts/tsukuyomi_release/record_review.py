"""Reflect an actual listening result without inventing quality approval."""

import argparse
import copy
import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path


FIELDS = ("reading", "similarity", "naturalness", "noise")
START = "<!-- listening-review:start -->"
END = "<!-- listening-review:end -->"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def record_review(workspace: Path, review: dict) -> None:
    """Validate the current inventory before updating only review metadata."""
    release = workspace / "bundle/releases/zs-v1"
    manifest = read_json(release / "manifest.json")
    entries = manifest["files"]
    if len({entry["path"] for entry in entries}) != len(entries):
        raise ValueError("duplicate manifest entry")
    for entry in entries:
        raw_path = release / entry["path"]
        path = raw_path.resolve()
        if not path.is_relative_to(release.resolve()) or raw_path.is_symlink():
            raise ValueError("manifest path escapes release")
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"manifest hash mismatch: {entry['path']}")
    expected = {
        entry["path"]: entry["sha256"]
        for entry in entries
        if entry["path"].startswith("samples/ja-")
    }
    if len(expected) != 3 or review.get("sample_sha256") != expected:
        raise ValueError(
            "review sample hashes do not match the three current Japanese WAVs"
        )
    if (
        review.get("reviewer") != "user"
        or review.get("release_decision") != "publish_experimental"
    ):
        raise ValueError("user listening result must permit experimental publication")
    if (
        not isinstance(review.get("user_message"), str)
        or not review["user_message"].strip()
    ):
        raise ValueError("actual user message is required")
    recorded = review.get("recorded_at")
    if not isinstance(recorded, str) or not recorded.strip():
        raise ValueError("recorded_at is required")
    try:
        stamp = datetime.fromisoformat(recorded)
    except ValueError as error:
        raise ValueError("recorded_at must be an ISO timestamp") from error
    if stamp.tzinfo is None:
        raise ValueError("recorded_at must include a timezone")
    assessments = review.get("assessments", {})
    if any(
        not isinstance(assessments.get(field), str) or not assessments[field].strip()
        for field in FIELDS
    ):
        raise ValueError(
            "reading, similarity, naturalness and noise assessments are required"
        )
    card = (release / "README.md").read_text(encoding="utf-8")
    if (
        card.count(START) != 1
        or card.count(END) != 1
        or card.index(START) > card.index(END)
    ):
        raise ValueError("model card needs exactly one listening-review block")
    labels = dict(
        zip(
            FIELDS, ("Reading", "Voice similarity", "Naturalness", "Noise"), strict=True
        )
    )
    lines = [
        "Human listening review is recorded for the three Japanese samples.",
        "The user permitted publication as an experimental baseline. This is not a",
        "claim of improved quality or approval across all languages and texts.",
        f"Recorded: {recorded}.",
    ]
    for field in FIELDS:
        # Indent user-provided text as a quote; do not promote it to card markup.
        lines.append(f"\n{labels[field]}:")
        lines.extend(f"> {line}" for line in assessments[field].splitlines())
    block = START + "\n" + "\n".join(lines) + "\n" + END
    card = card[: card.index(START)] + block + card[card.index(END) + len(END) :]
    verification = read_json(release / "verification.json")
    verification.update(
        human_review_status="recorded",
        human_review=copy.deepcopy(review),
        quality_approval=False,
    )
    if "consumer" in verification:
        verification["consumer"]["human_review_status"] = "recorded"
    if "voice_metrics" in verification:
        for field in FIELDS:
            verification["voice_metrics"][f"human_{field}_assessment"] = assessments[
                field
            ]
    changed = {
        "README.md": card.encode(),
        "verification.json": json_bytes(verification),
    }
    for entry in entries:
        if entry["path"] in changed:
            content = changed[entry["path"]]
            entry.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    manifest.update(human_review_status="recorded", quality_approval=False)
    changed["manifest.json"] = json_bytes(manifest)
    changed["SHA256SUMS"] = "".join(
        f"{entry['sha256']}  {entry['path']}\n" for entry in entries
    ).encode()
    # All checks above precede any write. A partial I/O failure is rejected by
    # the publisher's manifest/hash checks, and can be repaired from the backup.
    backup = Path(tempfile.mkdtemp(prefix="review-update-backup-", dir=workspace))
    for name in changed:
        (backup / name).write_bytes((release / name).read_bytes())
    for name, content in changed.items():
        temporary = release / (name + ".review-tmp")
        temporary.write_bytes(content)
        temporary.replace(release / name)
    (workspace / "human-review.json").write_bytes(json_bytes(review))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    record_review(args.workspace.resolve(), read_json(args.review))
    print("Listening record reflected; rerun publication dry-run before upload.")


if __name__ == "__main__":
    main()
