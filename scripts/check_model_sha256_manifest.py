#!/usr/bin/env python3
"""Structural drift check for docs/spec/model-sha256-manifest.toml (M2 T-005).

The companion `scripts/verify_model_checksums.py` is a release-time tool
that computes an actual file's SHA256 and looks it up here. This script
runs in CI / pre-commit and gates the *structure* of the manifest itself:
that every entry is well-formed, that the placeholder sentinel is uniform,
and that the model inventory matches CLAUDE.md's "学習済みモデル" table.

Why split it out:
  * Most entries today carry `sha256 = "<computed-on-publish>"` placeholders
    because the hashes are filled in at publish time. A loader-vs-manifest
    diff (the original T-005 ambition) is therefore vacuous until the
    publish pipeline lands. This script enforces the *constraints we have
    now* so the manifest cannot silently rot before the publish gate.
  * The forward-compat schema_version loader pattern (mirroring
    check_loanword_consistency.py) is asserted so that a future
    schema_version=2 bump can add fields without breaking this gate.

Exit codes:
  0 -- structure is well-formed
  1 -- spec drift (model count, missing required keys, malformed placeholder)
  2 -- spec file missing / unreadable
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "docs" / "spec" / "model-sha256-manifest.toml"

# Mirrored from CLAUDE.md "学習済みモデル" table + speaker encoder.
# Adding / removing a model requires updating BOTH this list and the
# manifest in the same commit — that is exactly what this gate enforces.
EXPECTED_MODELS = {
    "multilingual-6lang-base",  # [Archived/v1.11]
    "multilingual-6lang-mb-istft",  # 現行 base
    "tsukuyomi-6lang-v2",  # [Archived/v1.11]
    "tsukuyomi-mb-istft",  # 現行 tsukuyomi
    "css10-ja-6lang",  # CSS10 JA 6lang
    "speaker-encoder-ecapa-tdnn",  # voice cloning
}

# Forward-compat: the loader MUST accept schema_version values up to and
# including this number without crashing. Bump in lockstep with the
# manifest. The mirror check (`schema_version > MAX_KNOWN`) lets a future
# bump appear without immediately failing this gate.
MAX_KNOWN_SCHEMA_VERSION = 2

REQUIRED_META_KEYS = (
    "spec_version",
    "canonical_source",
    "hash_algorithm",
    "hash_encoding",
    "update_policy",
    "forward_compat_policy",
)

REQUIRED_MODEL_KEYS = ("name", "description")
REQUIRED_ARTIFACT_KEYS = ("filename", "sha256")

PLACEHOLDER_SHA256 = "<computed-on-publish>"
SHA256_HEX_LEN = 64


def _silent_zero_log(*, models: int, artifacts: int) -> None:
    """Echo Collected line so a zero count is never invisible (NFR-5.3).

    The same defensive pattern used by check_action_sha_drift.py and
    verify_rekor_releases.py — fail loudly when the parser walked over an
    empty manifest. ::warning:: lifts the line into the GH Actions UI.
    """
    msg = f"Collected manifest entries (models={models}, artifacts={artifacts})"
    print(msg, file=sys.stderr)
    if models == 0 or artifacts == 0:
        print(
            "::warning::model-sha256-manifest is empty — paths filter mismatch?",
            file=sys.stderr,
        )


def _check_artifact(model_name: str, idx: int, artifact: dict) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_ARTIFACT_KEYS:
        if key not in artifact:
            errors.append(f"{model_name}.artifacts[{idx}] missing required key '{key}'")
    sha = artifact.get("sha256")
    if sha and sha != PLACEHOLDER_SHA256:
        if not (
            isinstance(sha, str)
            and len(sha) == SHA256_HEX_LEN
            and all(c in "0123456789abcdef" for c in sha)
        ):
            errors.append(
                f"{model_name}.artifacts[{idx}].sha256 is neither the "
                f"'{PLACEHOLDER_SHA256}' sentinel nor a 64-char lowercase "
                f"hex digest (got: {sha!r})"
            )
    return errors


def check_manifest(data: dict) -> list[str]:
    errors: list[str] = []

    meta = data.get("meta", {})
    for key in REQUIRED_META_KEYS:
        if key not in meta:
            errors.append(f"[meta] missing required key '{key}'")

    schema_version = meta.get("spec_version")
    if schema_version is None:
        errors.append("[meta].spec_version missing")
    else:
        try:
            major = int(str(schema_version).split(".", 1)[0])
        except ValueError:
            errors.append(f"[meta].spec_version not parseable: {schema_version!r}")
        else:
            if major > MAX_KNOWN_SCHEMA_VERSION:
                errors.append(
                    f"[meta].spec_version major={major} exceeds "
                    f"MAX_KNOWN_SCHEMA_VERSION={MAX_KNOWN_SCHEMA_VERSION}; "
                    "bump the constant in check_model_sha256_manifest.py "
                    "and add forward-compat handling for the new fields."
                )

    models = data.get("models", [])
    seen_names: set[str] = set()
    artifact_count = 0
    for i, model in enumerate(models):
        for key in REQUIRED_MODEL_KEYS:
            if key not in model:
                errors.append(f"[[models]][{i}] missing required key '{key}'")
        name = model.get("name")
        if name:
            if name in seen_names:
                errors.append(f"[[models]] duplicate name '{name}'")
            seen_names.add(name)
        artifacts = model.get("artifacts", [])
        if not artifacts:
            errors.append(f"[[models]] '{name}' has no [[models.artifacts]]")
        for j, artifact in enumerate(artifacts):
            artifact_count += 1
            errors.extend(_check_artifact(name or f"<idx-{i}>", j, artifact))

    missing = EXPECTED_MODELS - seen_names
    extra = seen_names - EXPECTED_MODELS
    if missing:
        errors.append(
            f"[[models]] missing expected entries: {sorted(missing)}. "
            "If you removed a model, also remove it from "
            "EXPECTED_MODELS in this script (CLAUDE.md mirror)."
        )
    if extra:
        errors.append(
            f"[[models]] unexpected entries: {sorted(extra)}. "
            "Add them to EXPECTED_MODELS in this script and to "
            "CLAUDE.md's 学習済みモデル table."
        )

    _silent_zero_log(models=len(seen_names), artifacts=artifact_count)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST,
        help="Path to model-sha256-manifest.toml (default: docs/spec/...)",
    )
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f"ERROR: manifest missing: {args.manifest}", file=sys.stderr)
        return 2

    try:
        data = tomllib.loads(args.manifest.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        print(f"ERROR: failed to parse {args.manifest}: {exc}", file=sys.stderr)
        return 2

    errors = check_manifest(data)
    if errors:
        print(
            f"model-sha256-manifest.toml drift ({len(errors)} issues):", file=sys.stderr
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("model-sha256-manifest.toml structure OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
