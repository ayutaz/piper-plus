#!/usr/bin/env python3
"""Check phoneme details with Unicode values"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src" / "python_run"))

from piper import PiperVoice

# Load voice
voice = PiperVoice.load(
    "/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx",
    config_path="/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx.json"
)

# Test text
text = "ちょっと待ってください"
print(f"Text: {text}")

# Get phonemes
phonemes = voice.phonemize(text)[0]
print(f"\nPhonemes ({len(phonemes)} total):")

# Show each phoneme with its Unicode value
for i, ph in enumerate(phonemes):
    if len(ph) == 1:
        unicode_val = ord(ph)
        if unicode_val >= 0xE000 and unicode_val <= 0xF8FF:
            # PUA character
            print(f"  [{i:2d}] U+{unicode_val:04X} (PUA) - displays as '{ph}'")
            # Map back to original phoneme
            from piper.voice import MULTI_CHAR_TO_PUA
            for orig, pua in MULTI_CHAR_TO_PUA.items():
                if pua == ph:
                    print(f"       -> Original phoneme: '{orig}'")
                    break
        else:
            # Regular character
            print(f"  [{i:2d}] '{ph}' (U+{unicode_val:04X})")
    else:
        # Multi-character (shouldn't happen after fix)
        print(f"  [{i:2d}] '{ph}' (multi-char)")

# Expected phonemes for "ちょっと待ってください"
print("\nExpected phonemes:")
print("  ch o cl t o m a cl t e k u d a s a i")
print("  (where ch=U+E00E, cl=U+E005)")