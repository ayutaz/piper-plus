#!/usr/bin/env python3
"""Debug phoneme to ID conversion"""

import subprocess
import sys
import json
from pathlib import Path

# Add src/python_run to path
sys.path.insert(0, str(Path(__file__).parent / "src" / "python_run"))

from piper import PiperVoice

def debug_phoneme_conversion():
    # Model paths
    model_path = "/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx"
    config_path = "/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx.json"
    
    # Test text
    text = "こんにちは"
    
    print("=== Phoneme to ID Conversion Debug ===")
    print(f"Text: {text}")
    print()
    
    # Load model config
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Load Python voice
    voice = PiperVoice.load(model_path, config_path=config_path)
    
    # Get phonemes
    phonemes_list = voice.phonemize(text)
    phonemes = phonemes_list[0]
    
    print("Python phonemes:")
    for i, ph in enumerate(phonemes):
        if len(ph) == 1:
            unicode_val = ord(ph)
            if unicode_val >= 0xE000 and unicode_val <= 0xF8FF:
                # Find original
                from piper.voice import MULTI_CHAR_TO_PUA
                for orig, pua in MULTI_CHAR_TO_PUA.items():
                    if pua == ph:
                        print(f"  [{i}] '{orig}' (PUA U+{unicode_val:04X})")
                        break
            else:
                print(f"  [{i}] '{ph}' (U+{unicode_val:04X})")
    
    # Get phoneme IDs
    ids = voice.phonemes_to_ids(phonemes)
    print(f"\nPython IDs ({len(ids)}): {ids}")
    
    # Get C++ debug output
    print("\nC++ phoneme processing:")
    env = {"ESPEAK_DATA_PATH": "/Users/s19447/Desktop/tmp/piper/espeak-ng-data"}
    proc = subprocess.run(
        ["/Users/s19447/Desktop/tmp/piper/bin/piper", 
         "--model", model_path,
         "--output_file", "/dev/null",
         "--debug"],
        input=text.encode('utf-8'),
        capture_output=True,
        env={**subprocess.os.environ, **env}
    )
    
    # Parse debug output
    stderr = proc.stderr.decode('utf-8')
    for line in stderr.split('\n'):
        if "Phoneme sequence:" in line:
            print(f"  {line.strip()}")
        elif "Converting" in line and "phoneme(s) to ids:" in line:
            print(f"  {line.strip()}")
        elif "Converted" in line and "phoneme id(s):" in line:
            print(f"  {line.strip()}")
    
    # Compare specific phonemes
    print("\n=== Phoneme ID Mapping Check ===")
    test_phonemes = ["^", "k", "o", "N", "n", "i", "\ue00e", "ch", "$"]
    
    for ph in test_phonemes:
        if ph in config['phoneme_id_map']:
            id_val = config['phoneme_id_map'][ph][0]
            if ph == "\ue00e":
                print(f"  'ch' (U+E00E) -> ID {id_val}")
            else:
                print(f"  '{ph}' -> ID {id_val}")

if __name__ == "__main__":
    debug_phoneme_conversion()