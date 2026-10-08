"""Verify public native packages and prepare a draft on a hosted CI runner."""

import argparse
import json
import re
import subprocess
import tarfile
import time
import tomllib
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from release_checksums import digest, verify


REPO = "ayutaz/piper-plus"


def version(value):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("invalid release version")
    return value


def native_assets():
    return {
        **{
            f"piper-plus-rs-cli-{target}.{extension}": "rust"
            for target, extension in (
                ("linux-x64", "tar.gz"),
                ("osx-arm64", "tar.gz"),
                ("win-x64", "zip"),
            )
        },
        **{
            f"piper-plus-cli-{target}.{extension}": "csharp"
            for target, extension in (
                ("linux-x64", "tar.gz"),
                ("linux-arm64", "tar.gz"),
                ("osx-x64", "tar.gz"),
                ("osx-arm64", "tar.gz"),
                ("win-x64", "zip"),
                ("win-arm64", "zip"),
            )
        },
    }


def expected_assets(value):
    version(value)
    shared = {
        f"libpiper_plus-android-{target}-v{value}.tar.gz"
        for target in ("arm64-v8a", "armeabi-v7a", "x86_64")
    }
    shared |= {
        f"libpiper_plus-ios-arm64-v{value}.tar.gz",
        f"libpiper_plus-ios-v{value}.xcframework.zip",
        f"libpiper_plus_g2p-apple-v{value}.xcframework.zip",
    }
    shared |= {
        f"piper-plus-shared-{target}.tar.gz" for target in ("linux-x64", "macos-arm64")
    }
    shared.add("piper-plus-shared-windows-x64.zip")
    cpp = {
        f"piper-plus-cpp-{target}.tar.gz"
        for target in ("linux-x64", "linux-arm64", "linux-armv7", "macos-arm64")
    }
    cpp.add("piper-plus-cpp-windows-x64.zip")
    return (
        set(native_assets())
        | shared
        | cpp
        | {"checksums-sha256.txt", "LICENSE_ATTRIBUTIONS.md", "MODEL_CARD.md"}
    )


def validate_root(release, value):
    if release.get("draft") is not True:
        raise ValueError("only a draft release may be updated")
    names = [asset["name"] for asset in release["assets"]]
    if len(names) != len(set(names)) or set(names) != expected_assets(value):
        raise ValueError("root release inventory does not match")


def check_download(path, descriptor):
    if path.stat().st_size != descriptor["size"] or descriptor.get(
        "digest"
    ) != "sha256:" + digest(path):
        raise ValueError(f"download differs from GitHub descriptor: {path.name}")


def validate_component(release, component):
    expected = {name for name, kind in native_assets().items() if kind == component}
    names = [asset["name"] for asset in release["assets"]]
    actual = set(names)
    allowed = expected | {name + ".cosign.bundle" for name in expected}
    if len(names) != len(actual) or not expected <= actual <= allowed:
        raise ValueError(f"component inventory mismatch: {component}")


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def release(tag):
    # Draft releases require an authenticated listing, not releases/tags/<tag>.
    values = json.loads(
        run(
            "gh",
            "api",
            f"repos/{REPO}/releases?per_page=100&verify_time={time.time_ns()}",
        )
    )
    matches = [item for item in values if item["tag_name"] == tag]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one release: {tag}")
    return matches[0]


def source(tag):
    return run("git", "rev-parse", f"refs/tags/{tag}^{{commit}}").strip()


def attest(path, tag, workflow, proof):
    sha = source(tag)
    result = run(
        "gh",
        "attestation",
        "verify",
        str(path),
        "--repo",
        REPO,
        "--source-ref",
        f"refs/tags/{tag}",
        "--source-digest",
        sha,
        "--signer-digest",
        sha,
        "--signer-workflow",
        f"{REPO}/.github/workflows/{workflow}",
        "--deny-self-hosted-runners",
        "--format",
        "json",
    )
    (proof / f"{path.name}.attestation.json").write_text(result, encoding="utf-8")
    return sha


def fetch(url, path):
    request = urllib.request.Request(
        url, headers={"User-Agent": "piper-plus-release-ci"}
    )
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        path.open("wb") as out,
    ):
        while chunk := response.read(1024 * 1024):
            out.write(chunk)


def verify_crates(rust, directory, proof):
    records = []
    for name in ("piper-plus-g2p", "piper-plus", "piper-plus-cli"):
        path = directory / f"{name}-{rust}.crate"
        metadata_path = proof / f"{name}.registry.json"
        fetch(f"https://crates.io/api/v1/crates/{name}/{rust}", metadata_path)
        metadata = json.loads(metadata_path.read_text())["version"]
        fetch(f"https://static.crates.io/crates/{name}/{path.name}", path)
        if (
            metadata["num"] != rust
            or metadata["yanked"]
            or digest(path) != metadata["checksum"]
        ):
            raise ValueError(f"crate metadata/checksum mismatch: {name}")
        tag = f"rust-v{rust}"
        with tarfile.open(path) as archive:
            vcs = archive.extractfile(f"{name}-{rust}/.cargo_vcs_info.json")
            if json.load(vcs)["git"]["sha1"] != source(tag):
                raise ValueError(f"crate source mismatch: {name}")
        sha = attest(path, tag, "release-rust.yml", proof)
        records.append({"name": path.name, "sha256": digest(path), "source": sha})
    return records


def verify_nuget(csharp, directory, proof):
    records = []
    for name in ("piperplus.core", "piperplus.cli"):
        path = directory / f"{name}.{csharp}.nupkg"
        fetch(
            f"https://api.nuget.org/v3-flatcontainer/{name}/{csharp}/{path.name}", path
        )
        tag = f"csharp-v{csharp}"
        with zipfile.ZipFile(path) as archive:
            nuspec = next(
                item for item in archive.namelist() if item.endswith(".nuspec")
            )
            document = ET.fromstring(archive.read(nuspec))
            for node in document.iter():
                node.tag = node.tag.split("}")[-1]
            metadata = document.find("metadata")
            if (
                metadata.findtext("version") != csharp
                or metadata.find("repository").get("commit") != source(tag)
                or metadata.findtext("license") != "MIT"
            ):
                raise ValueError(f"NuGet metadata mismatch: {name}")
        signature = run("dotnet", "nuget", "verify", "--all", str(path))
        (proof / f"{path.name}.signature.log").write_text(signature, encoding="utf-8")
        sha = attest(path, tag, "release-csharp.yml", proof)
        records.append({"name": path.name, "sha256": digest(path), "source": sha})
    return records


def verify_registry(rust, csharp, directory, proof):
    return verify_crates(rust, directory, proof) + verify_nuget(
        csharp, directory, proof
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root_tag = f"v{version(args.version)}"
    rust = version(
        tomllib.loads(Path("src/rust/Cargo.toml").read_text())["workspace"]["package"][
            "version"
        ]
    )
    csharp = version(
        ET.parse("src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj").findtext(
            "PropertyGroup/Version"
        )
    )
    directory = args.directory.resolve()
    payloads, proof, registry = (
        directory / name for name in ("payloads", "proof", "registry")
    )
    for item in (payloads, proof, registry):
        item.mkdir(parents=True, exist_ok=False)
    root = release(root_tag)
    validate_root(root, args.version)
    records = verify_registry(rust, csharp, registry, proof)
    components = {
        "rust": release(f"rust-v{rust}"),
        "csharp": release(f"csharp-v{csharp}"),
    }
    for component, value in components.items():
        validate_component(value, component)
    final = {}
    for old in root["assets"]:
        name = old["name"]
        if name == "checksums-sha256.txt":
            continue
        component = native_assets().get(name)
        selected = components[component] if component else root
        descriptor = next(
            asset for asset in selected["assets"] if asset["name"] == name
        )
        path = payloads / name
        run(
            "gh",
            "release",
            "download",
            selected["tag_name"],
            "--repo",
            REPO,
            "--pattern",
            name,
            "--dir",
            str(payloads),
        )
        check_download(path, descriptor)
        if component:
            attest(path, selected["tag_name"], f"release-{component}.yml", proof)
        elif name.startswith(("libpiper_plus", "piper-plus-shared-")):
            attest(path, root_tag, "release-shared-lib.yml", proof)
        final[name] = digest(path)
    manifest = "".join(f"{final[name]}  {name}\n" for name in sorted(final))
    checksum = payloads / "checksums-sha256.txt"
    checksum.write_text(manifest, encoding="utf-8", newline="\n")
    verify(payloads, manifest)
    subprocess.run(["sha256sum", "--check", checksum.name], cwd=payloads, check=True)
    # Recheck the draft and original asset hashes immediately before mutation.
    current = release(root_tag)
    validate_root(current, args.version)
    if {a["name"]: a["digest"] for a in current["assets"]} != {
        a["name"]: a["digest"] for a in root["assets"]
    }:
        raise ValueError("root draft changed during verification")
    run(
        "gh",
        "release",
        "upload",
        root_tag,
        "--repo",
        REPO,
        "--clobber",
        *(str(payloads / name) for name in sorted(native_assets())),
        str(checksum),
    )
    updated = release(root_tag)
    validate_root(updated, args.version)
    expected = {**final, checksum.name: digest(checksum)}
    for asset in updated["assets"]:
        if asset["digest"] != "sha256:" + expected[asset["name"]]:
            raise ValueError(f"uploaded asset mismatch: {asset['name']}")
    (proof / "verification.json").write_text(
        json.dumps(
            {
                "root_tag": root_tag,
                "draft": True,
                "assets": expected,
                "rust_tag": f"rust-v{rust}",
                "rust_source": source(f"rust-v{rust}"),
                "csharp_tag": f"csharp-v{csharp}",
                "csharp_source": source(f"csharp-v{csharp}"),
                "registry_packages": records,
                "gnu_sha256sum_verified": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Prepared {root_tag} draft: {len(final)} verified payloads; not published.")


if __name__ == "__main__":
    main()
