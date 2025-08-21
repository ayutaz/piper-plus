---
title: Piper TTS Demo
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: mit
---

# Piper TTS Demo

A web-based demo for [Piper TTS](https://github.com/ayutaz/piper-plus), featuring high-quality text-to-speech synthesis for Japanese and English.

## Features

- 🇯🇵 **Japanese TTS**: High-quality Japanese speech synthesis using OpenJTalk phonemization
- 🇺🇸 **English TTS**: Natural English speech synthesis
- 🚀 **Fast Inference**: ONNX Runtime for efficient CPU-based inference
- 🎛️ **Adjustable Parameters**: Control speech speed, expressiveness, and phoneme duration
- 🌐 **Web Interface**: Easy-to-use Gradio interface

## Models

This demo includes:
- **Japanese (Medium)**: CSS10-based Japanese model with natural intonation
- **English (Test)**: English model for demonstration

## Usage

1. Select a model from the dropdown
2. Enter your text in the input field
3. Adjust advanced settings if needed
4. Click "Generate Speech" to synthesize

## Technical Details

- **Framework**: ONNX Runtime (CPU inference)
- **Phonemization**: 
  - Japanese: pyopenjtalk
  - English: Character-based fallback
- **Audio**: 16-bit PCM WAV output

## Local Development

```bash
# Clone the repository
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus/huggingface-space

# Install requirements
pip install -r requirements.txt

# Run the app
python app.py
```

## Credits

- Piper TTS by [Rhasspy](https://github.com/rhasspy/piper)
- Japanese enhancements by [ayutaz](https://github.com/ayutaz/piper-plus)

## License

This project is licensed under the MIT License. See the original [Piper repository](https://github.com/rhasspy/piper) for more details.

---
_Last updated: 2025-01-21 - Upgraded to Gradio 5.0.0 for security fixes_