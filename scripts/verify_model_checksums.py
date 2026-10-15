"""
Verify model SHA256 checksums against docs/spec/model-sha256-manifest.toml.

Usage:
  python scripts/verify_model_checksums.py [--model PATH]

Select an official artifact by --name and filename (or --artifact). Hash and
size mismatches fail. Unknown files require --allow-custom; an official
mismatch can never be bypassed by that switch. --print-manifest lists the
nested artifact inventory without downloading model bytes.

Exit code: 0 = verified (or explicitly allowed custom), 1 = not verified.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Path to model file to verify")
    parser.add_argument(
        "--name", help="Official model name (disambiguates shared filenames)"
    )
    parser.add_argument("--artifact", help="Exact filename from models.artifacts")
    parser.add_argument(
        "--allow-custom",
        action="store_true",
        help="Allow an unknown custom file, never an official mismatch",
    )
    parser.add_argument(
        "--print-manifest", action="store_true", help="Print manifest entries"
    )
    args = parser.parse_args(argv)

    manifest = load_manifest()

    if args.print_manifest:
        models = manifest.get("models", []) or manifest.get("model", [])
        if isinstance(models, dict):
            models = list(models.values())
        for m in models:
            name = m.get("name", "<unknown>")
            for artifact in m.get("artifacts", []):
                print(
                    f"  {name}/{artifact['filename']}: {artifact.get('sha256', '<missing>')}"
                )
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

    candidates = [
        (m, artifact)
        for m in models
        if not args.name or m.get("name") == args.name
        for artifact in m.get("artifacts", [])
        if artifact.get("filename") == args.artifact
        or (
            not args.artifact
            and Path(artifact.get("filename", "")).name == args.model.name
        )
    ]
    for model, artifact in candidates:
        if (
            artifact.get("sha256") == actual_sha
            and artifact.get("bytes") == args.model.stat().st_size
        ):
            print(f"MATCH: {model['name']}/{artifact['filename']}")
            return 0
    if not candidates and not args.name and not args.artifact and args.allow_custom:
        print(
            "::warning::Unknown custom artifact; not verified against the official manifest",
            file=sys.stderr,
        )
        return 0
    print("ERROR: official artifact not found or SHA256/size mismatch", file=sys.stderr)
    for model, artifact in candidates:
        print(
            f"Expected {model['name']}/{artifact['filename']}: {artifact.get('sha256')} ({artifact.get('bytes')} bytes)",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
