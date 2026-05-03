---
title: piper-plus Demo
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 6.9.0
app_file: app.py
pinned: false
license: mit
---

# piper-plus Demo

A web-based demo for [piper-plus](https://github.com/ayutaz/piper-plus), featuring high-quality text-to-speech synthesis. The code supports 8 languages (Japanese, English, Chinese, Korean, Spanish, French, Portuguese, Swedish); the current demo model covers 6 languages (Korean and Swedish models not yet trained).

## Features

- 🇯🇵 **Japanese TTS**: High-quality Japanese speech synthesis using OpenJTalk phonemization
- 🇺🇸 **English TTS**: Natural English speech synthesis
- 🇨🇳 **Chinese TTS**: Mandarin Chinese speech synthesis using pypinyin
- 🇪🇸 **Spanish TTS**: Spanish speech synthesis with rule-based phonemization
- 🇫🇷 **French TTS**: French speech synthesis with rule-based phonemization
- 🇵🇹 **Portuguese TTS**: Portuguese speech synthesis with rule-based phonemization
- 🚀 **Fast Inference**: ONNX Runtime for efficient CPU-based inference
- 🎛️ **Adjustable Parameters**: Control speech speed, expressiveness, and phoneme duration
- 🌐 **Web Interface**: Easy-to-use Gradio interface

## Supported Languages

| Code | Language | Script | Phonemizer | In demo model |
|------|----------|--------|------------|---------------|
| `ja` | Japanese | Hiragana/Katakana/Kanji | pyopenjtalk | ✅ |
| `en` | English | Latin | g2p-en | ✅ |
| `zh` | Chinese (Mandarin) | Simplified Chinese | pypinyin | ✅ |
| `ko` | Korean | Hangul | g2pk2 | ❌ (G2P only — model not trained yet) |
| `es` | Spanish | Latin | Rule-based | ✅ |
| `fr` | French | Latin | Rule-based | ✅ |
| `pt` | Portuguese | Latin | Rule-based | ✅ |
| `sv` | Swedish | Latin | Rule-based | ❌ (G2P only — model not trained yet) |

## Models

This demo uses a multilingual model trained on 6 languages with 571 speakers and 508,187 utterances:
- **Multilingual 6-lang (Medium)**: Supports Japanese, English, Chinese, Spanish, French, and Portuguese with a unified 173-symbol model

## Usage

1. Select a model from the dropdown
2. Select the language of your input text
3. Enter your text in the input field (see sample texts below)
4. Adjust advanced settings if needed
5. Click "Generate Speech" to synthesize

### Sample Texts by Language

| Language | Sample Text |
|----------|-------------|
| Japanese (`ja`) | こんにちは、今日は良い天気ですね。 |
| English (`en`) | Hello, how are you today? |
| Chinese (`zh`) | 你好，今天天气很好。 |
| Spanish (`es`) | Hola, como estas hoy? |
| French (`fr`) | Bonjour, comment allez-vous? |
| Portuguese (`pt`) | Ola, como voce esta hoje? |

### Code-Switching (Mixed Language)

The multilingual model supports code-switching within a single utterance. The language detector automatically identifies language segments:

```
今日はgood morningですね  →  JA + EN mixed
```

## Technical Details

- **Framework**: ONNX Runtime (CPU inference)
- **Phonemization**:
  - Japanese: pyopenjtalk (OpenJTalk-based)
  - English: g2p-en (Apache-2.0, espeak-ng compatible)
  - Chinese: pypinyin (MIT)
  - Spanish / French / Portuguese: Rule-based (no external dependency)
- **Language Detection**: Unicode range-based automatic detection
- **Audio**: 16-bit PCM WAV output
- **Model Architecture**: VITS with language embedding (`emb_lang`), 173 phoneme symbols, 6 language IDs

## Local Development

```bash
# Clone the repository
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus/huggingface-space

# Install requirements
uv pip install -r requirements.txt

# Run the app
python app.py
```

## Credits

- Piper TTS by [Rhasspy](https://github.com/rhasspy/piper)
- Multilingual (6-language) enhancements by [ayutaz](https://github.com/ayutaz/piper-plus)
- Chinese phonemization: [pypinyin](https://github.com/mozillazg/python-pinyin) (MIT)
- English G2P: [g2p-en](https://github.com/Kyubyong/g2p) (Apache-2.0)

## License

This project is licensed under the MIT License. See the original [Piper repository](https://github.com/rhasspy/piper) for more details.

---
_Last updated: 2026-03-18 - 6-language multilingual support (ja/en/zh/es/fr/pt)_
