#!/usr/bin/env python3
"""
Update existing Piper model config.json to support PUA phoneme mapping
This allows existing models to work better with OpenJTalk without retraining
"""

import json
import sys
from pathlib import Path

# Import the mapping from token_mapper
from token_mapper import MULTI_CHAR_TO_PUA, get_phoneme_id_map

def update_config_file(config_path):
    """Update model config.json with PUA phoneme mappings"""
    
    # Read existing config
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Get current phoneme_id_map
    current_map = config.get('phoneme_id_map', {})
    
    # Find the next available ID
    max_id = 0
    for ids in current_map.values():
        if isinstance(ids, list) and ids:
            max_id = max(max_id, max(ids))
    
    next_id = max_id + 1
    
    # Add PUA mappings if not present
    added_count = 0
    for multi_char, pua_char in MULTI_CHAR_TO_PUA.items():
        if pua_char not in current_map:
            # Check if the individual characters exist and map to them
            if len(multi_char) == 2:
                char1, char2 = multi_char[0], multi_char[1]
                if char1 in current_map and char2 in current_map:
                    # Map PUA to both individual character IDs
                    id1 = current_map[char1][0] if current_map[char1] else next_id
                    id2 = current_map[char2][0] if current_map[char2] else next_id + 1
                    current_map[pua_char] = [id1, id2]
                    print(f"Added '{multi_char}' → {pua_char} → IDs {[id1, id2]}")
                else:
                    # Fallback: assign new ID
                    current_map[pua_char] = [next_id]
                    next_id += 1
                    print(f"Added '{multi_char}' → {pua_char} → ID {current_map[pua_char]}")
            else:
                # For other cases, assign new ID
                current_map[pua_char] = [next_id]
                next_id += 1
                print(f"Added '{multi_char}' → {pua_char} → ID {current_map[pua_char]}")
            
            added_count += 1
    
    if added_count > 0:
        # Update config
        config['phoneme_id_map'] = current_map
        
        # Create backup
        backup_path = Path(config_path).with_suffix('.json.bak')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # Write updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ Updated {config_path}")
        print(f"   Added {added_count} PUA phoneme mappings")
        print(f"   Backup saved to {backup_path}")
    else:
        print(f"\n✅ {config_path} already has all PUA mappings")

def main():
    if len(sys.argv) < 2:
        print("Usage: python update_model_config.py <config.json>")
        print("\nThis script updates existing model config files to support")
        print("multi-character phonemes through PUA mapping.")
        sys.exit(1)
    
    config_path = Path(sys.argv[1])
    if not config_path.exists():
        print(f"Error: {config_path} not found")
        sys.exit(1)
    
    update_config_file(config_path)

if __name__ == "__main__":
    main()