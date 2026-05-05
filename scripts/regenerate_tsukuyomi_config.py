#!/usr/bin/env python3
"""Regenerate the distributed tsukuyomi config.json with PUA v2 keys.

This script fixes the v1.12.0 regression where ɔɪ/œ̃/ɐ̃ leaked as multi-codepoint
keys into the HuggingFace-distributed `tsukuyomi` config, breaking C++ inference
for Windows users.

Workflow:
  1. Download the current config.json from HuggingFace.
  2. Run update_phoneme_id_map() in strict mode to PUA-encode all keys.
     (Strict mode raises if any unmappable multi-codepoint key remains.)
  3. Write the new config.json locally for human inspection.
  4. (Manual) Push the corrected config to HuggingFace.

Usage:
  python scripts/regenerate_tsukuyomi_config.py [--repo ayousanz/piper-plus-tsukuyomi-chan] [--out tmp/]

Pre-flight check (CI-equivalent):
  python -m piper_train.update_model_config tmp/config.json --validate-only
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "ayousanz/piper-plus-tsukuyomi-chan"
HF_BASE = "https://huggingface.co/{repo}/resolve/main/{path}"


def download_config(repo: str) -> dict:
    url = HF_BASE.format(repo=repo, path="config.json")
    print(f"Downloading {url} ...")
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"HuggingFace model repo id (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "tmp",
        help="Output directory for regenerated config (default: tmp/)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Use a local config.json instead of downloading from HF",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    if args.source:
        print(f"Loading local config: {args.source}")
        config = json.loads(args.source.read_text(encoding="utf-8"))
    else:
        config = download_config(args.repo)

    # Sanity dump
    pid_map = config.get("phoneme_id_map", {})
    multi = [k for k in pid_map if len(k) > 1]
    print(f"Loaded config.json: {len(pid_map)} phoneme_id_map entries")
    print(f"Multi-codepoint keys before: {len(multi)} ({multi})")

    # Snapshot original
    original_path = args.out / "config.original.json"
    original_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved original to: {original_path}")

    # Apply PUA mapping in strict mode
    sys.path.insert(0, str(REPO_ROOT / "src/python"))
    sys.path.insert(0, str(REPO_ROOT / "src/python/g2p"))
    from piper_train.update_model_config import update_phoneme_id_map

    try:
        update_phoneme_id_map(config, strict=True)
    except Exception as e:
        print(f"\nERROR: strict-mode update failed: {e}", file=sys.stderr)
        print(
            "\nThis means the config has multi-codepoint keys with no PUA mapping. "
            "Add the missing entries to src/python/g2p/piper_plus_g2p/data/pua.json "
            "and synchronize all 6 runtime tables before retrying.",
            file=sys.stderr,
        )
        return 1

    # Verify post-condition
    pid_map_after = config["phoneme_id_map"]
    multi_after = [k for k in pid_map_after if len(k) > 1]
    if multi_after:
        print(
            f"\nERROR: post-update config still has multi-codepoint keys: {multi_after}",
            file=sys.stderr,
        )
        return 1

    # Write
    out_path = args.out / "config.json"
    out_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nRegenerated config saved to: {out_path}")
    print(f"All {len(pid_map_after)} keys are single-codepoint.")
    print()
    print("Next steps (manual):")
    print(f"  1. Review {out_path}")
    print("  2. huggingface-cli login")
    print(f"  3. huggingface-cli upload {args.repo} {out_path} config.json")
    print("  4. Bump version tag on the HF repo if desired.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
