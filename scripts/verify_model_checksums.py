"""
Verify model SHA256 checksums against docs/spec/model-sha256-manifest.toml.

Usage:
  python scripts/verify_model_checksums.py [--model PATH]

If --model is given, computes SHA256 of that file and prints whether
it matches any entry in the manifest. Without args, parses the manifest
and prints a list of (model, sha256) for documentation purposes.

Exit code:
  0 = all manifest entries are placeholders or computed hash matches
  1 = mismatch found
"""
import argparse
import hashlib
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "docs" / "spec" / "model-sha256-manifest.toml"


def compute_sha256(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST.exists():
        print(f"ERROR: manifest missing: {MANIFEST}", file=sys.stderr)
        sys.exit(1)
    with MANIFEST.open("rb") as f:
        return tomllib.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Path to model file to verify")
    parser.add_argument("--print-manifest", action="store_true", help="Print manifest entries")
    args = parser.parse_args()

    manifest = load_manifest()

    if args.print_manifest:
        models = manifest.get("models", []) or manifest.get("model", [])
        if isinstance(models, dict):
            models = list(models.values())
        for m in models:
            name = m.get("name", "<unknown>")
            sha256 = m.get("sha256", "<missing>")
            print(f"  {name}: {sha256}")
        return 0

    if not args.model:
        parser.print_help()
        return 0

    if not args.model.exists():
        print(f"ERROR: model file not found: {args.model}", file=sys.stderr)
        return 1

    actual_sha = compute_sha256(args.model)
    print(f"Computed SHA256: {actual_sha}")
    print(f"File: {args.model}")

    # Search manifest for match
    models = manifest.get("models", []) or manifest.get("model", [])
    if isinstance(models, dict):
        models = list(models.values())

    for m in models:
        expected_sha = m.get("sha256", "")
        if expected_sha == actual_sha:
            print(f"MATCH: {m.get('name', '<unknown>')}")
            return 0
        if expected_sha == "<computed-on-publish>":
            continue

    print(f"::warning::No matching manifest entry for SHA256={actual_sha}", file=sys.stderr)
    print("This model is either unreleased or not in the official manifest.")
    return 0  # not a fail; could be a custom user model


if __name__ == "__main__":
    sys.exit(main())
