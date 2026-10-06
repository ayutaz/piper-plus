"""Verify anonymous release downloads and every keyless signature in CI."""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from prepare_release_draft import (
    REPO,
    check_download,
    expected_assets,
    native_assets,
    source,
)
from release_checksums import digest


def expected_payloads(tag):
    match = re.fullmatch(r"(v|rust-v|csharp-v)([0-9]+\.[0-9]+\.[0-9]+)", tag)
    if not match:
        raise ValueError("unsupported public release tag")
    if match[1] == "v":
        return expected_assets(match[2])
    component = match[1].removesuffix("-v")
    return {name for name, kind in native_assets().items() if kind == component}


def validate_public(release, tag):
    if release.get("draft") is not False:
        raise ValueError("release is not public")
    payloads = expected_payloads(tag)
    expected = payloads | {name + ".cosign.bundle" for name in payloads}
    names = [asset["name"] for asset in release["assets"]]
    if len(names) != len(set(names)) or set(names) != expected:
        raise ValueError("public release inventory or signatures are incomplete")


def run(*args):
    try:
        return subprocess.run(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout
    except subprocess.CalledProcessError as error:
        print(error.output, file=sys.stderr)
        raise


def verify_signature(path, bundle, tag, sha):
    return run(
        "cosign",
        "verify-blob",
        "--bundle",
        str(bundle),
        "--certificate-identity",
        f"https://github.com/{REPO}/.github/workflows/cosign-release-artifacts.yml@refs/tags/{tag}",
        "--certificate-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "--certificate-github-workflow-sha",
        sha,
        "--certificate-github-workflow-repository",
        REPO,
        "--certificate-github-workflow-ref",
        f"refs/tags/{tag}",
        str(path),
    )


def anonymous_download(url, path):
    # Deliberately no GitHub token: this verifies the actual public access path.
    request = urllib.request.Request(
        url, headers={"User-Agent": "piper-plus-public-verify"}
    )
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        path.open("wb") as out,
    ):
        while chunk := response.read(1024 * 1024):
            out.write(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    payloads = expected_payloads(args.tag)
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    metadata_path = directory / "release.json"
    anonymous_download(
        f"https://api.github.com/repos/{REPO}/releases/tags/{args.tag}?verify_time={time.time_ns()}",
        metadata_path,
    )
    release = json.loads(metadata_path.read_text(encoding="utf-8"))
    if release["tag_name"] != args.tag:
        raise ValueError("public tag mismatch")
    validate_public(release, args.tag)
    assets = {asset["name"]: asset for asset in release["assets"]}
    sha = source(args.tag)
    records = {}
    for name in sorted(payloads):
        for item in (name, name + ".cosign.bundle"):
            asset = assets[item]
            expected_url = (
                f"https://github.com/{REPO}/releases/download/{args.tag}/{item}"
            )
            if asset["browser_download_url"] != expected_url:
                raise ValueError(f"unexpected public asset URL: {item}")
            path = directory / item
            anonymous_download(expected_url, path)
            check_download(path, asset)
        result = verify_signature(
            directory / name, directory / (name + ".cosign.bundle"), args.tag, sha
        )
        (directory / (name + ".verify.log")).write_text(result, encoding="utf-8")
        records[name] = {"sha256": digest(directory / name), "signature_verified": True}
        print(f"Verified public payload and pinned signature: {name}", flush=True)
    (directory / "verification.json").write_text(
        json.dumps(
            {
                "tag": args.tag,
                "release_id": release["id"],
                "signer_commit": sha,
                "anonymous_downloads_verified": True,
                "rekor_verification_enabled": True,
                "payloads": records,
                "verified_signatures": len(records),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
