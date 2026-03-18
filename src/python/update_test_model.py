#!/usr/bin/env python3
"""
Updates the test model configuration to support unvoiced vowels.
"""

import json
import sys
from pathlib import Path

from jp_phoneme_map import get_phoneme_id_map


def update_model_config(json_path):
    """
    Updates a model JSON configuration to support unvoiced vowels.

    Args:
        json_path: Path to the model JSON file
    """
    json_path = Path(json_path)

    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        return False

    # Read existing config
    with open(json_path, encoding="utf-8") as f:
        config = json.load(f)

    # Get the new phoneme mapping
    new_phoneme_map = get_phoneme_id_map()

    # Convert to Piper format (each phoneme maps to a list containing one ID)
    new_phoneme_id_map = {}
    for phoneme, id_val in new_phoneme_map.items():
        new_phoneme_id_map[phoneme] = [id_val]

    # Backup original
    backup_path = json_path.with_suffix(".json.backup")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    print(f"Created backup: {backup_path}")

    # Update config
    old_num_symbols = config.get("num_symbols", 0)
    config["phoneme_id_map"] = new_phoneme_id_map
    config["num_symbols"] = len(new_phoneme_map)

    # Write updated config
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    print(f"Updated {json_path}")
    print(f"Number of symbols: {old_num_symbols} -> {config['num_symbols']}")

    # Show what was added
    print("\nAdded support for unvoiced vowels:")
    for vowel in ["A", "I", "U", "E", "O"]:
        if vowel in new_phoneme_id_map:
            print(f"  {vowel}: ID {new_phoneme_id_map[vowel][0]}")

    return True


def main():
    if len(sys.argv) < 2:
        # Default to test model
        test_model_path = (
            Path(__file__).parent.parent.parent
            / "test"
            / "models"
            / "multilingual-test-medium.onnx.json"
        )
        if test_model_path.exists():
            print(f"Updating test model: {test_model_path}")
            update_model_config(test_model_path)
        else:
            print("Usage: python update_test_model.py <model.json>")
            sys.exit(1)
    else:
        for json_path in sys.argv[1:]:
            update_model_config(json_path)


if __name__ == "__main__":
    main()
