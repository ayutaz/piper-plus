#!/usr/bin/env python3
"""
Update existing Piper model configurations to use PUA phoneme mappings.

This script modifies model JSON configuration files to replace multi-character
phonemes with their corresponding Private Use Area (PUA) single-character
representations, ensuring compatibility between Python training and C++ inference.
"""

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING, TOKEN2CHAR


class UnmappedMultiCodepointKeyError(ValueError):
    """Raised when phoneme_id_map contains a multi-codepoint key with no PUA entry.

    This is the situation that broke C++ inference for Windows users in
    v1.12.0 (ɔɪ/œ̃/ɐ̃ leak). Failing fast here prevents unrunnable configs
    from being shipped to HuggingFace.
    """


def update_phoneme_id_map(config: dict[str, Any], *, strict: bool = True) -> bool:
    """
    Update the phoneme_id_map in a model configuration to use PUA characters.

    Args:
        config: The model configuration dictionary
        strict: If True (default), raise on multi-codepoint keys that have
            no PUA mapping. If False, leave them unchanged (legacy behaviour).

    Returns:
        bool: True if any changes were made, False otherwise

    Raises:
        UnmappedMultiCodepointKeyError: in strict mode, if any key is a
            multi-codepoint string not registered in FIXED_PUA_MAPPING.
    """
    if "phoneme_id_map" not in config:
        print("Warning: No phoneme_id_map found in configuration")
        return False

    phoneme_id_map = config["phoneme_id_map"]
    new_phoneme_id_map = {}
    changes_made = False
    unmapped_multi: list[str] = []

    # Process each phoneme in the map
    for phoneme, ids in phoneme_id_map.items():
        # Check if this is a multi-character phoneme that needs PUA mapping
        if phoneme in FIXED_PUA_MAPPING:
            # Replace with PUA character
            pua_char = TOKEN2CHAR[phoneme]
            new_phoneme_id_map[pua_char] = ids
            changes_made = True
            print(f"  Mapped: '{phoneme}' -> U+{ord(pua_char):04X} ('{pua_char}')")
        else:
            if len(phoneme) > 1:
                # Multi-codepoint key with no PUA mapping — this is the bug class
                unmapped_multi.append(phoneme)
            # Keep single-character phonemes as-is
            new_phoneme_id_map[phoneme] = ids

    if unmapped_multi:
        details = ", ".join(
            f"{p!r} (codepoints: {'+'.join(f'U+{ord(c):04X}' for c in p)})"
            for p in unmapped_multi
        )
        msg = (
            f"phoneme_id_map contains {len(unmapped_multi)} multi-codepoint key(s) "
            f"with no PUA mapping: {details}. "
            "Add them to src/python/g2p/piper_plus_g2p/data/pua.json and run "
            "scripts/check_pua_consistency.py before shipping the config. "
            "See docs/spec/pua-contract.toml."
        )
        if strict:
            raise UnmappedMultiCodepointKeyError(msg)
        print(f"WARNING: {msg}")

    # Replace the phoneme_id_map
    config["phoneme_id_map"] = new_phoneme_id_map

    return changes_made


def validate_phoneme_id_map(config: dict[str, Any]) -> list[str]:
    """Return a list of multi-codepoint keys (empty if config is valid).

    Used by ``--validate-only`` to pre-flight-check a config before HF push.
    """
    pid_map = config.get("phoneme_id_map", {})
    return [k for k in pid_map if len(k) > 1]


def process_model_config(
    config_path: Path, backup: bool = True, *, strict: bool = True
) -> None:
    """
    Process a single model configuration file.

    Args:
        config_path: Path to the JSON configuration file
        backup: Whether to create a backup of the original file
    """
    print(f"\nProcessing: {config_path}")

    # Read the configuration
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading {config_path}: {e}")
        return

    # NOTE: previously this skipped non-Japanese configs. Removed in PUA v2 because
    # multilingual configs (e.g. tsukuyomi 6lang) also need PUA normalization
    # for English/French/Portuguese multi-codepoint phonemes (ɔɪ, œ̃, ɐ̃).
    # See docs/spec/pua-contract.toml.

    # Create backup if requested
    if backup:
        backup_path = config_path.with_suffix(".json.bak")
        shutil.copy2(config_path, backup_path)
        print(f"  Created backup: {backup_path}")

    # Update the phoneme mappings
    if update_phoneme_id_map(config, strict=strict):
        # Write the updated configuration
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print("  Configuration updated successfully")
    else:
        print("  No changes needed")


def main():
    parser = argparse.ArgumentParser(
        description="Update Piper model configurations to use PUA phoneme mappings"
    )
    parser.add_argument(
        "configs",
        nargs="+",
        type=Path,
        help="Path(s) to model configuration JSON files",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Don't create backup files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only check that all phoneme_id_map keys are single-codepoint; "
        "exit non-zero if any multi-codepoint key exists. C++ runtime "
        "rejects multi-codepoint keys regardless of PUA mapping presence.",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Legacy mode: do not raise on multi-codepoint keys without PUA "
        "mapping (only warns). Not recommended for release pipelines.",
    )

    args = parser.parse_args()

    if args.validate_only:
        any_invalid = False
        for config_path in args.configs:
            if not config_path.exists() or config_path.suffix != ".json":
                continue
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            bad = validate_phoneme_id_map(config)
            if bad:
                any_invalid = True
                print(
                    f"FAIL: {config_path} has {len(bad)} multi-codepoint key(s): {bad}"
                )
            else:
                print(f"OK:   {config_path} (all keys are single-codepoint)")
        return 1 if any_invalid else 0

    print("PUA Phoneme Mapping Update Tool")
    print("=" * 40)
    print("\nFixed PUA mappings:")
    for phoneme, codepoint in sorted(FIXED_PUA_MAPPING.items()):
        print(f"  {phoneme:3s} -> U+{codepoint:04X}")

    # Process each configuration file
    for config_path in args.configs:
        if not config_path.exists():
            print(f"\nError: {config_path} does not exist")
            continue

        if not config_path.suffix == ".json":
            print(f"\nWarning: {config_path} is not a JSON file, skipping")
            continue

        if args.dry_run:
            print(f"\n[DRY RUN] Would process: {config_path}")
            # Just show what would be done
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            phoneme_id_map = config.get("phoneme_id_map", {})
            for phoneme in phoneme_id_map:
                if phoneme in FIXED_PUA_MAPPING:
                    pua_char = TOKEN2CHAR[phoneme]
                    print(f"  Would map: '{phoneme}' -> U+{ord(pua_char):04X}")
        else:
            process_model_config(
                config_path,
                backup=not args.no_backup,
                strict=not args.no_strict,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
