#!/usr/bin/env python3
"""Resolve every release image to a verified public digest before signing."""

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


IMAGES = (
    ("cpp-dev", False),
    ("cpp-inference", False),
    ("python-train", False),
    ("python-inference", False),
    ("python-inference", True),
    ("webui", False),
    ("wyoming", False),
)
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


def _descriptor(fetch, kind, descriptor):
    digest = descriptor["digest"]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError(f"Invalid SHA256 descriptor: {digest}")
    raw = fetch(f"/{kind}/{digest}")
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"SHA256 mismatch: {digest}")
    if len(raw) != descriptor["size"]:
        raise ValueError(f"Descriptor size mismatch: {digest}")
    return json.loads(raw)


def resolve_image(
    repository, reference, expected_revision, expected_architectures, fetch
):
    """Verify each runnable platform, then return the immutable root digest."""
    raw = fetch(f"/manifests/{reference}")
    root = json.loads(raw)
    configs = []
    if "manifests" in root:
        manifests = [
            manifest
            for manifest in root["manifests"]
            if manifest.get("platform", {}).get("os") == "linux"
        ]
        architectures = {manifest["platform"]["architecture"] for manifest in manifests}
        if architectures != expected_architectures or len(manifests) != len(
            architectures
        ):
            raise ValueError(
                f"Unexpected release architectures: {sorted(architectures)}"
            )
        for manifest in manifests:
            image = _descriptor(fetch, "manifests", manifest)
            config = _descriptor(fetch, "blobs", image["config"])
            if (config["os"], config["architecture"]) != (
                "linux",
                manifest["platform"]["architecture"],
            ):
                raise ValueError("Image config and index architectures differ")
            configs.append(config)
    else:
        config = _descriptor(fetch, "blobs", root["config"])
        architectures = {config["architecture"]} if config["os"] == "linux" else set()
        if architectures != expected_architectures:
            raise ValueError(
                f"Unexpected release architectures: {sorted(architectures)}"
            )
        configs.append(config)

    for config in configs:
        labels = config["config"].get("Labels", {})
        if labels.get("org.opencontainers.image.revision") != expected_revision:
            raise ValueError(f"Image revision mismatch for {repository}:{reference}")
        if labels.get("org.opencontainers.image.version") != reference:
            raise ValueError(f"Image version mismatch for {repository}:{reference}")

    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return {
        "image": f"ghcr.io/{repository}:{reference}",
        "reference": f"ghcr.io/{repository}@{digest}",
        "digest": digest,
        "source_revision": expected_revision,
        "version": reference,
        "architectures": sorted(architectures),
        "anonymous_registry_read": True,
    }


def public_fetcher(repository):
    """Obtain only an anonymous public pull token; never read account credentials."""
    headers = {"User-Agent": "piper-plus-release-verification"}
    query = urllib.parse.urlencode(
        {"service": "ghcr.io", "scope": f"repository:{repository}:pull"}
    )
    request = urllib.request.Request(f"https://ghcr.io/token?{query}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)["token"]

    def fetch(path):
        request = urllib.request.Request(
            f"https://ghcr.io/v2/{repository}{path}",
            headers={**headers, "Authorization": f"Bearer {token}", "Accept": ACCEPT},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    return fetch


def expected_architectures(name, cpu):
    if name in {"cpp-dev", "python-train"} or (name == "python-inference" and not cpu):
        return {"amd64"}
    return {"amd64", "arm64"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("version must be a numeric release version")
    if not re.fullmatch(r"[a-f0-9]{40}", args.source_revision):
        parser.error("source revision must be an immutable Git commit")

    images = []
    fetchers = {}
    for name, cpu in IMAGES:
        repository = f"ayutaz/piper-plus/{name}"
        if repository not in fetchers:
            fetchers[repository] = public_fetcher(repository)
        reference = args.version + ("-cpu" if cpu else "")
        architectures = expected_architectures(name, cpu)
        images.append(
            resolve_image(
                repository,
                reference,
                args.source_revision,
                architectures,
                fetchers[repository],
            )
        )

    # Both outputs are written only after ALL approved images have passed.
    args.output.write_text(json.dumps(images, indent=2) + "\n", encoding="utf-8")
    args.references.write_text(
        "".join(image["reference"] + "\n" for image in images), encoding="utf-8"
    )
    for image in images:
        print(image["reference"])


if __name__ == "__main__":
    main()
