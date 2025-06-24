#!/usr/bin/env python3
"""Generate same text with Python"""

import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src" / "python_run"))

from piper import PiperVoice

# Load voice
voice = PiperVoice.load(
    "/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx",
    config_path="/Users/s19447/Desktop/tmp/css10_ja_epoch1999.onnx.json"
)

# Generate audio
text = "ちょっと待ってください"
with wave.open("/Users/s19447/Desktop/tmp/chotto_python.wav", "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(voice.config.sample_rate)
    
    audio_bytes = bytes()
    for audio in voice.synthesize_stream_raw(text):
        audio_bytes += audio
    
    wav_file.writeframes(audio_bytes)

print(f"Generated: {text}")
phonemes = voice.phonemize(text)[0]
print(f"Phonemes: {' '.join(phonemes)}")