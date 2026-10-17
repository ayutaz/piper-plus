---
title: piper-plus Demo
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 6.26.0
app_file: app.py
python_version: "3.13"
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
- 🧪 **Zero-shot (experimental)**: Speak in the voice of an uploaded or recorded reference clip

## Supported Languages

| Code | Language | Script | Phonemizer | In demo model |
|------|----------|--------|------------|---------------|
| `ja` | Japanese | Hiragana/Katakana/Kanji | pyopenjtalk | ✅ |
| `en` | English | Latin | Bundled `g2p-en` 2.1.0 source | ✅ |
| `zh` | Chinese (Mandarin) | Simplified Chinese | pypinyin | ✅ |
| `ko` | Korean | Hangul | g2pk2 | ❌ (G2P only — model not trained yet) |
| `es` | Spanish | Latin | Rule-based | ✅ |
| `fr` | French | Latin | Rule-based | ✅ |
| `pt` | Portuguese | Latin | Rule-based | ✅ |
| `sv` | Swedish | Latin | Rule-based | ❌ (G2P only — model not trained yet) |

## Models

This demo uses a multilingual model trained on 6 languages with 571 speakers and 508,187 utterances:

- **Multilingual 6-lang (Medium)**: Supports Japanese, English, Chinese, Spanish, French, and Portuguese with a unified 173-symbol model

## Zero-shot (experimental)

The **Zero-shot (experimental)** tab synthesizes speech in the voice of a reference clip.

1. Choose the language and enter text.
2. Upload a reference clip or record one with the microphone (3-30 seconds; longer clips are cut to the first 30 seconds).
3. Click "Generate Speech".

- **Model**: the public [zs-v1 base](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) (revision-pinned, SHA256-verified, downloaded on first use) with the CAM++ speaker encoder (192-dim embedding).
- **Quality**: experimental and not approved; an unseen speaker is reproduced only partially.
- **Phonemes**: zs-v1 uses the older 173-symbol table. Text containing phonemes the model never learned (for example the Portuguese nasal vowel "ã" in "não" or the French "ɥ" in "nuit"), or letters outside the six languages (for example Hangul or Cyrillic), is rejected with an error instead of being silently dropped. Selecting a language loads a sample text that the model can speak.
- **Privacy and consent**: the reference clip is used only for the request and is not stored. Only use voices you have the speaker's consent to use.

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

```text
今日はgood morningですね  →  JA + EN mixed
```

## Technical Details

- **Framework**: ONNX Runtime (CPU inference)
- **Phonemization**:
  - Japanese: pyopenjtalk (OpenJTalk-based)
  - English: bundled `g2p-en` 2.1.0 source (Apache-2.0 + Tacotron MIT; no external `g2p-en` or `Distance` package)
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

# The app expects models/multilingual-test-medium.onnx and its .json config.
# The deployment workflow copies the checked-in test fixture before launch.
# If that fixture is absent locally, download_models.py creates a dummy model
# so the UI can start; that fallback is only a smoke test and is not a speech
# quality or model-inference demonstration.

# Run the app
python app.py
```

The model setup runs at application startup. Check the console for whether a
real fixture was found or a dummy fallback was created before evaluating audio.

## Credits

- Piper TTS by [Rhasspy](https://github.com/rhasspy/piper)
- Multilingual (6-language) enhancements by [ayutaz](https://github.com/ayutaz/piper-plus)
- Chinese phonemization: [pypinyin](https://github.com/mozillazg/python-pinyin) (MIT)
- Zero-shot base: [zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) (MIT); see its [NOTICE](https://huggingface.co/ayousanz/piper-plus-base/blob/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/NOTICE.md)
- Speaker encoder: CAM++ ([Apache-2.0](https://huggingface.co/ayousanz/piper-plus-base/blob/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/licenses/CAMPP-APACHE-2.0.txt))
- English G2P source: [g2p-en](https://github.com/Kyubyong/g2p) 2.1.0, bundled under a private namespace with Apache-2.0 and Tacotron MIT notices

## License

This project is licensed under the MIT License. See the original [Piper repository](https://github.com/rhasspy/piper) for more details.

---
_Last updated: 2026-10-17 - Experimental zero-shot tab (zs-v1)_
