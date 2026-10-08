"""Recover verified archives from a tag build into an unpublished draft."""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path


REPO = "ayutaz/piper-plus"


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def api(path):
    return json.loads(command("gh", "api", f"repos/{REPO}/{path}"))


def validate_run(run, sha, tag):
    expected = {
        "head_sha": sha,
        "head_branch": tag,
        "event": "push",
        "path": ".github/workflows/release-shared-lib.yml",
        "status": "completed",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Recovery requires the completed shared-library build at the exact release tag"
        )


def validate_jobs(jobs):
    if not jobs:
        raise ValueError("Build jobs are missing")
    for job in jobs:
        if job.get("conclusion") == "success":
            continue
        failures = [
            step["name"]
            for step in job.get("steps", [])
            if step.get("conclusion") == "failure"
        ]
        if (
            job.get("name") != "Create Release"
            or job.get("conclusion") != "failure"
            or failures != ["Generate checksums"]
        ):
            raise ValueError(
                "Recovery refuses an unsuccessful build or a different publication failure"
            )


def artifact_payload(path, expected_digest, member):
    with path.open("rb") as stream:
        actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_digest:
        raise ValueError("Original artifact digest mismatch")
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != [member]:
            raise ValueError("Artifact must contain exactly the expected archive")
        return archive.read(member)


def archives(tag):
    items = {}
    for target, extension in [
        ("linux-x64", "tar.gz"),
        ("macos-arm64", "tar.gz"),
        ("windows-x64", "zip"),
    ]:
        name = f"piper-plus-shared-{target}"
        items[name] = (f"{name}.{extension}", f"{name}.{extension}")
    for target in ("arm64-v8a", "armeabi-v7a", "x86_64"):
        name = f"libpiper_plus-android-{target}"
        items[name] = (f"{name}.tar.gz", f"{name}-{tag}.tar.gz")
    items.update(
        {
            "libpiper_plus-ios-arm64": (
                "libpiper_plus-ios-arm64.tar.gz",
                f"libpiper_plus-ios-arm64-{tag}.tar.gz",
            ),
            "libpiper_plus-ios-xcframework": (
                "libpiper_plus-ios.xcframework.zip",
                f"libpiper_plus-ios-{tag}.xcframework.zip",
            ),
            "libpiper_plus_g2p-apple-xcframework": (
                "libpiper_plus_g2p-apple.xcframework.zip",
                f"libpiper_plus_g2p-apple-{tag}.xcframework.zip",
            ),
        }
    )
    return items


def verify_swift(directory, tag, manifest):
    for variable, checksum, filename in [
        ("version", "checksum", f"libpiper_plus-ios-{tag}.xcframework.zip"),
        ("g2pVersion", "g2pChecksum", f"libpiper_plus_g2p-apple-{tag}.xcframework.zip"),
    ]:
        declared_version = re.search(
            rf'^let {variable} = "([^"]+)"', manifest, re.MULTILINE
        )
        declared = re.search(
            rf'^let {checksum} = "([a-f0-9]{{64}})"', manifest, re.MULTILINE
        )
        with (directory / filename).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            not declared_version
            or declared_version[1] != tag[1:]
            or not declared
            or declared[1] != actual
        ):
            raise ValueError(
                f"SwiftPM manifest mismatch: {filename}; refusing publication"
            )


def validate_draft(release, tag):
    specs = archives(tag)
    outputs = {output for _, output in specs.values()} | {
        "MODEL_CARD.md",
        "LICENSE_ATTRIBUTIONS.md",
        "checksums-sha256.txt",
    }
    if release.get("isDraft") is not True or outputs & {
        item["name"] for item in release["assets"]
    }:
        raise ValueError(
            "Recovery requires a draft without existing shared payloads or manifests"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version) or args.run_id <= 0:
        raise ValueError("Invalid recovery version/run")
    tag = f"v{args.version}"
    sha = command("git", "rev-parse", f"refs/tags/{tag}^{{commit}}").strip()
    if command("git", "rev-parse", "HEAD").strip() != sha:
        raise ValueError("Checkout does not match release tag")
    validate_run(api(f"actions/runs/{args.run_id}"), sha, tag)
    validate_jobs(api(f"actions/runs/{args.run_id}/jobs?per_page=100")["jobs"])
    release = json.loads(
        command(
            "gh", "release", "view", tag, "--repo", REPO, "--json", "isDraft,assets"
        )
    )
    validate_draft(release, tag)
    specs = archives(tag)
    descriptors = api(f"actions/runs/{args.run_id}/artifacts?per_page=100")["artifacts"]
    selected = [item for item in descriptors if item["name"] in specs]
    if len(selected) != len(specs) or {item["name"] for item in selected} != set(specs):
        raise ValueError("Missing or duplicate original artifacts")
    args.directory.mkdir(parents=True, exist_ok=False)
    proof = []
    for descriptor in selected:
        if descriptor["expired"] or not descriptor.get("digest", "").startswith(
            "sha256:"
        ):
            raise ValueError("Artifact expired or digest unavailable")
        original, output = specs[descriptor["name"]]
        container = args.directory.parent / f"artifact-{descriptor['id']}.zip"
        with container.open("wb") as stream:
            subprocess.run(
                ["gh", "api", f"repos/{REPO}/actions/artifacts/{descriptor['id']}/zip"],
                stdout=stream,
                check=True,
            )
        data = artifact_payload(container, descriptor["digest"], original)
        (args.directory / output).write_bytes(data)
        proof.append(
            {
                "artifact_id": descriptor["id"],
                "artifact_digest": descriptor["digest"],
                "payload": output,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    verify_swift(args.directory, tag, Path("Package.swift").read_text(encoding="utf-8"))
    receipt = {"source": sha, "tag": tag, "build_run": args.run_id, "artifacts": proof}
    (args.directory.parent / "shared-recovery-proof.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Recovered {len(proof)} archives from {sha}; SwiftPM checksums match; not yet uploaded."
    )


if __name__ == "__main__":
    main()
