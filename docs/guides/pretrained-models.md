# Pre-trained Models

Available pre-trained piper-plus models, how to download them, and language-specific model details including Japanese TTS.

## Model Download

Pre-trained models for multilingual TTS and fine-tuning are available on Hugging Face.

**Inference Models (ready to use):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang-v2 | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan voice, 6-language, FP16. **500 epochs (2026-03-16)**, fine-tuned from 6-language base with `freeze-dp` + `emb_lang` unify for voice consistency across all 6 languages. ONNX size 75 MB. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| Tsukuyomi-chan MB-iSTFT | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan with MB-iSTFT decoder, 6-language. **500 epochs (2026-05-02)**, fine-tuned from 6-lang MB-iSTFT base. **2.21x faster CPU inference** (61.9 ms p50). | TBD |
| CSS10 Japanese 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 Japanese voice, 6-language, FP16. 50 epochs from 6-language base, 6,841 utterances. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Base Models (for fine-tuning):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| 6-Language Base | JA/EN/ZH/ES/FR/PT | 571 | Multilingual pre-trained (508,187 utterances, VITS + Prosody). **75 epochs / ~282K gradient steps (2026-03-16)**, language-balanced sampling, WavLM-disabled (V100 friendly). Checkpoint `epoch=74-step=504712.ckpt`. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |
| 6-lang MB-iSTFT Base | JA/EN/ZH/ES/FR/PT | 571 | Multilingual pre-trained with MB-iSTFT decoder. **75 epochs (2026-04-16)**, scratch-trained. **2.21x faster CPU inference** vs HiFi-GAN. Issue #268. | TBD |

**Tsukuyomi-chan model:**

**Windows (PowerShell):**

```powershell
mkdir models
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx" -OutFile models/tsukuyomi.onnx
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json" -OutFile models/config.json
```

**macOS / Linux:**

```bash
mkdir -p models
curl -L -o models/tsukuyomi.onnx https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx
curl -L -o models/config.json https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json
```

## 6-Language Base Model Features

- Architecture: VITS + Prosody Features
- Training data: 508,187 utterances (571 speakers across 6 languages)
- Languages: Japanese (20 speakers), English (310 speakers), Mandarin Chinese (142 speakers), Spanish (63 speakers), French (28 speakers), Portuguese (8 speakers)
- Language codes: ja=0, en=1, zh=2, es=3, fr=4, pt=5
- Sample rate: 22,050 Hz
- Phonemes: 173 symbols (unified multilingual phoneme inventory)
- Prosody Features: A1/A2/A3 prosody information (Japanese)
- Extended phonemes: Question markers, context-dependent "N" variants

> **Note:** piper-plus has custom architecture extensions (multilingual embeddings, Prosody A1/A2/A3, 173 symbols) that make it incompatible with upstream Piper checkpoints/ONNX models. Please use piper-plus specific models.

## Japanese TTS Specifics

High-quality Japanese speech synthesis with OpenJTalk integration. The dictionary (NAIST-JDIC) is automatically downloaded on first run. HTS voice files are not required (removed in PR #342).

**Environment Variables (optional):**

| Variable | Description |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk dictionary path (auto-downloads if not set) |
| `PIPER_AUTO_DOWNLOAD_DICT` | Set to `0` to disable auto-download |
| `PIPER_OFFLINE_MODE` | Set to `1` for offline mode |

See the Japanese Usage Guide and [Phoneme Mapping Reference](../api-reference/phoneme-mapping.md).

---

→ Back to [README](../../README_EN.md)
