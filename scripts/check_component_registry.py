"""Verify existing component releases without building or republishing them."""

import argparse
import json
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from prepare_release_draft import verify_crates, verify_nuget, version


def component_version(component):
    if component == "crates":
        return version(
            tomllib.loads(Path("src/rust/Cargo.toml").read_text(encoding="utf-8"))[
                "workspace"
            ]["package"]["version"]
        )
    versions = {
        ET.parse(f"src/csharp/{name}/{name}.csproj").findtext("PropertyGroup/Version")
        for name in ("PiperPlus.Core", "PiperPlus.Cli")
    }
    if len(versions) != 1:
        raise ValueError("CSharp component versions differ")
    return version(versions.pop())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("nuget", "crates"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    registry = args.directory / "registry"
    proof = args.directory / "proof"
    registry.mkdir(parents=True, exist_ok=False)
    proof.mkdir(parents=True, exist_ok=False)
    verify = verify_nuget if args.component == "nuget" else verify_crates
    records = verify(component_version(args.component), registry, proof)
    (proof / "manifest.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Verified {len(records)} existing {args.component} packages; no publication performed."
    )


if __name__ == "__main__":
    main()
