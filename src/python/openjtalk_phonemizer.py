#!/usr/bin/env python3
"""
OpenJTalk phonemizer for Python.
This module provides Python interface for OpenJTalk phonemization.
"""

import subprocess
import tempfile
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from jp_phoneme_map import PHONEME_TO_PUA, get_phoneme_id_map

def ensure_openjtalk_dictionary():
    """Ensure OpenJTalk dictionary is available."""
    dict_path = Path.home() / ".local" / "share" / "piper" / "open_jtalk_dic_utf_8-1.11"
    
    if not dict_path.exists():
        print("OpenJTalk dictionary not found. Please install it first.")
        return None
    
    return str(dict_path)

def find_openjtalk_binary():
    """Find OpenJTalk or open_jtalk_phonemizer binary."""
    # Prefer phonemizer version
    candidates = [
        "open_jtalk_phonemizer",
        "open_jtalk",
        "./build/oj/bin/open_jtalk_phonemizer",
        "./build/oj/bin/open_jtalk",
        "/usr/local/bin/open_jtalk_phonemizer",
        "/usr/local/bin/open_jtalk",
        "/usr/bin/open_jtalk",
    ]
    
    if sys.platform == "win32":
        candidates = [c + ".exe" if not c.endswith(".exe") else c for c in candidates]
    
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
        # Try which command
        try:
            result = subprocess.run(["which", candidate], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except:
            pass
    
    return None

def phonemize_openjtalk(text: str, preserve_unvoiced: bool = True) -> List[List[str]]:
    """
    Phonemize Japanese text using OpenJTalk.
    
    Args:
        text: Japanese text to phonemize
        preserve_unvoiced: If True, keep uppercase vowels for unvoiced vowels
        
    Returns:
        List of sentences, each containing a list of phonemes
    """
    # Find OpenJTalk binary
    openjtalk_bin = find_openjtalk_binary()
    if not openjtalk_bin:
        raise RuntimeError("OpenJTalk binary not found")
    
    # Get dictionary path
    dict_path = ensure_openjtalk_dictionary()
    if not dict_path:
        raise RuntimeError("OpenJTalk dictionary not found")
    
    # Create temporary files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(text)
        input_file = f.name
    
    output_file = tempfile.mktemp(suffix='.txt')
    
    try:
        # Run OpenJTalk
        cmd = [openjtalk_bin, "-x", dict_path, "-ot", output_file, input_file]
        
        # For phonemizer version, we don't need voice
        is_phonemizer = "phonemizer" in openjtalk_bin
        if not is_phonemizer:
            # Regular open_jtalk needs a voice file or /dev/null output
            cmd.extend(["-ow", "/dev/null" if sys.platform != "win32" else "NUL"])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"OpenJTalk failed: {result.stderr}")
        
        # Parse trace output
        phonemes_list = []
        current_sentence = []
        
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                for line in f:
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
                                
                                # Handle special phonemes
                                if phoneme_part == 'sil':
                                    # Sentence boundary
                                    if current_sentence:
                                        phonemes_list.append(current_sentence)
                                        current_sentence = []
                                elif phoneme_part == 'pau':
                                    # Pause within sentence
                                    current_sentence.append('_')
                                else:
                                    # Regular phoneme
                                    if not preserve_unvoiced and len(phoneme_part) == 1:
                                        # Convert uppercase vowels to lowercase
                                        if phoneme_part in 'AIUEO':
                                            phoneme_part = phoneme_part.lower()
                                    
                                    # Convert multi-character phonemes to PUA if needed
                                    if phoneme_part in PHONEME_TO_PUA:
                                        current_sentence.append(PHONEME_TO_PUA[phoneme_part])
                                    else:
                                        current_sentence.append(phoneme_part)
        
        # Add remaining phonemes
        if current_sentence:
            phonemes_list.append(current_sentence)
        
        return phonemes_list
        
    finally:
        # Cleanup
        if os.path.exists(input_file):
            os.unlink(input_file)
        if os.path.exists(output_file):
            os.unlink(output_file)

def phonemes_to_ids(phonemes: List[str], phoneme_id_map: Optional[Dict[str, int]] = None) -> List[int]:
    """
    Convert phonemes to IDs.
    
    Args:
        phonemes: List of phoneme strings
        phoneme_id_map: Optional custom phoneme to ID mapping
        
    Returns:
        List of phoneme IDs
    """
    if phoneme_id_map is None:
        phoneme_id_map = get_phoneme_id_map()
    
    ids = []
    for phoneme in phonemes:
        if phoneme in phoneme_id_map:
            ids.append(phoneme_id_map[phoneme])
        else:
            print(f"Warning: Unknown phoneme '{phoneme}', using silence")
            ids.append(0)  # Silence
    
    return ids

def test_phonemization():
    """Test phonemization with various Japanese texts."""
    test_texts = [
        ("こんにちは", "Basic greeting"),
        ("今日は良い天気です", "Statement with unvoiced vowels"),
        ("これはテストです", "Test with です"),
        ("私は学生です", "I am a student"),
        ("ありがとうございます", "Thank you (polite)"),
    ]
    
    print("Testing OpenJTalk phonemization")
    print("=" * 60)
    
    for text, description in test_texts:
        print(f"\nText: {text}")
        print(f"Description: {description}")
        
        try:
            phonemes_list = phonemize_openjtalk(text, preserve_unvoiced=True)
            
            for i, phonemes in enumerate(phonemes_list):
                print(f"  Sentence {i+1}: {' '.join(phonemes)}")
                
                # Show unvoiced vowels
                unvoiced = [p for p in phonemes if p in 'AIUEO']
                if unvoiced:
                    print(f"    Unvoiced vowels: {unvoiced}")
                
                # Convert to IDs
                ids = phonemes_to_ids(phonemes)
                print(f"    IDs: {ids[:10]}..." if len(ids) > 10 else f"    IDs: {ids}")
                
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    test_phonemization()