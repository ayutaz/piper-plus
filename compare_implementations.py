#!/usr/bin/env python3
"""Compare C++ and Python implementations"""

import subprocess
import sys
from pathlib import Path

# Add src/python_run to path
sys.path.insert(0, str(Path(__file__).parent / "src" / "python_run"))

from piper import PiperVoice

def test_comparison():
    # Model path
    model_path = "/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx"
    config_path = "/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx.json"
    
    # Test texts
    test_texts = [
        "こんにちは、世界",
        "おはようございます",
        "ありがとうございました",
        "日本語の音声合成です",
    ]
    
    print("=== Comparing C++ and Python implementations ===\n")
    
    # Load Python voice
    voice = PiperVoice.load(model_path, config_path=config_path)
    
    for text in test_texts:
        print(f"Text: {text}")
        
        # Python phonemization
        phonemes_list = voice.phonemize(text)
        python_phonemes = phonemes_list[0] if phonemes_list else []
        print(f"Python: {' '.join(python_phonemes)}")
        
        # C++ phonemization (via debug output)
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
        
        # Extract phonemes from debug output
        for line in proc.stderr.decode('utf-8').split('\n'):
            if "Converting" in line and "phoneme(s) to ids:" in line:
                # Extract phoneme string
                start = line.find("ids: ") + 5
                if start > 4:
                    cpp_phonemes = line[start:].strip()
                    print(f"C++:    {cpp_phonemes}")
                    break
        
        print()

if __name__ == "__main__":
    test_comparison()