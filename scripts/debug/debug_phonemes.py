#!/usr/bin/env python3
"""Debug script to test OpenJTalk phoneme extraction"""

import json
import subprocess
import tempfile
import os

def test_openjtalk_phonemes(text):
    """Test OpenJTalk phoneme extraction using command line"""
    
    # Check for open_jtalk binary
    openjtalk_paths = [
        "./build/oj/bin/open_jtalk_phonemizer",
        "./build/oj/bin/open_jtalk",
        "open_jtalk_phonemizer",
        "open_jtalk"
    ]
    
    # Skip Windows executables on non-Windows platforms
    import platform
    if platform.system() == "Windows":
        openjtalk_paths.insert(0, "./test_windows_build/bin/open_jtalk.exe")
    
    openjtalk_bin = None
    for path in openjtalk_paths:
        if os.path.exists(path) or os.system(f"which {path} >/dev/null 2>&1") == 0:
            openjtalk_bin = path
            break
    
    if not openjtalk_bin:
        print("OpenJTalk binary not found")
        return
    
    print(f"Using OpenJTalk: {openjtalk_bin}")
    
    # Get dictionary path
    dict_path = os.path.expanduser("~/.local/share/piper/open_jtalk_dic_utf_8-1.11")
    if not os.path.exists(dict_path):
        print(f"Dictionary not found at {dict_path}")
        return
    
    # Create temp files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(text)
        input_file = f.name
    
    output_file = tempfile.mktemp(suffix='.txt')
    
    try:
        # Run OpenJTalk with trace output
        cmd = [openjtalk_bin, "-x", dict_path, "-ot", output_file, input_file]
        print(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"OpenJTalk failed: {result.stderr}")
            return
        
        # Read trace output
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                lines = f.readlines()
            
            print(f"\nTrace output ({len(lines)} lines):")
            phonemes = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Parse full-context label
                # Format: xx^xx-phoneme+xx=xx/A:...
                if '/' in line:
                    context = line.split('/')[0]
                    
                    # Find phoneme between - and +
                    if '-' in context and '+' in context:
                        parts = context.split('-')
                        if len(parts) >= 2:
                            phoneme_part = parts[1].split('+')[0]
                            phonemes.append(phoneme_part)
                            print(f"  Phoneme: '{phoneme_part}'")
            
            print(f"\nExtracted phonemes: {' '.join(phonemes)}")
            
            # Load model phoneme map
            model_path = "./test/models/ja_JP-test-medium.onnx.json"
            if os.path.exists(model_path):
                with open(model_path, 'r') as f:
                    model_data = json.load(f)
                
                phoneme_map = model_data.get('phoneme_id_map', {})
                print(f"\nModel has {len(phoneme_map)} phonemes")
                
                # Check which phonemes are missing
                missing = []
                for p in phonemes:
                    if p not in phoneme_map and p not in ['sil', 'pau']:
                        missing.append(p)
                
                if missing:
                    print(f"Missing phonemes in model: {missing}")
                    print("\nModel phonemes:")
                    for k in sorted(phoneme_map.keys()):
                        if len(k) == 1:
                            print(f"  '{k}'")
                else:
                    print("All phonemes found in model!")
    
    finally:
        # Cleanup
        if os.path.exists(input_file):
            os.unlink(input_file)
        if os.path.exists(output_file):
            os.unlink(output_file)


if __name__ == "__main__":
    test_texts = [
        "こんにちは",
        "テスト",
        "今日は良い天気です"
    ]
    
    for text in test_texts:
        print(f"\n{'='*60}")
        print(f"Testing: {text}")
        print('='*60)
        test_openjtalk_phonemes(text)