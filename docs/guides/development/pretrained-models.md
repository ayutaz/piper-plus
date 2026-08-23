# Pre-trained Models

Available pre-trained piper-plus models, how to download them, and language-specific model details including Japanese TTS.

## Model Download

Pre-trained models for multilingual TTS and fine-tuning are available on Hugging Face.

**Inference Models (ready to use):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang (canonical) | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan voice, 6-language, FP16. **500 epochs (2026-03-16)**, fine-tuned from 6-language base with `freeze-dp` + `emb_lang` unify for voice consistency across all 6 languages. Actual HF file: `tsukuyomi-chan-6lang-fp16.onnx`. ONNX size 75 MB. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japanese 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 Japanese voice, 6-language, FP16. 50 epochs from 6-language base, 6,841 utterances. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

> **MB-iSTFT / 6lang-v2 variants (upcoming)**: `tsukuyomi-mb-istft-500epoch.onnx` (500 epoch MB-iSTFT FT、 2.21x faster CPU inference) と `tsukuyomi-6lang-v2-fixed.onnx` (v3→v4→v2 段階改善版) は学習完了済みですが、 HF への upload はまだ実施されていません。 現在 canonical な推論用 ONNX は `tsukuyomi-chan-6lang-fp16.onnx` のみです。 進捗は [Issue #590](https://github.com/ayutaz/piper-plus/issues/590) / follow-up model publish tracking 参照。

**Base Models (for fine-tuning):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| 6-Language Base (MB-iSTFT-VITS2) | JA/EN/ZH/ES/FR/PT | 571 | Multilingual pre-trained (508,187 utterances, VITS + Prosody). **75 epochs scratch / `epoch=74-step=500034`**, MB-iSTFT + PQMF decoder (`upsample_rates=(4, 4)` × iSTFT(4) × PQMF(4) = 256x), language-balanced sampling, WavLM-disabled (V100 friendly). `num_symbols=173` / `num_languages=6` / `prosody_dim=16` / `gin_channels=512`. Actual HF files: `model.ckpt` (302 MB, training checkpoint for FT) + `config.json`. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

> **Decoder 世代**: HF 上の `model.ckpt` は 2026-05-03 に HiFi-GAN 版から **MB-iSTFT-VITS2 版** (75 epoch scratch、 2.21x faster CPU inference、 [Issue #268](https://github.com/ayutaz/piper-plus/issues/268) / [PR #320](https://github.com/ayutaz/piper-plus/pull/320)) に差し替え済みです。 旧 HiFi-GAN 版の ckpt は配布されていません。 同じ学習 run の推論用 ONNX (`multilingual-6lang-mb-istft-scratch-75epoch.onnx`) の upload は [Issue #590](https://github.com/ayutaz/piper-plus/issues/590) follow-up にて予定。

> ⚠️ **v2.0 (`dev`) では読み込めません**: Zero-Shot TTS ([PR #579](https://github.com/ayutaz/piper-plus/pull/579)) が `MBiSTFTGenerator.cond` を Multi-scale FiLM 化して出力チャネルを 2 倍にしたため、 この ckpt は `model_g.dec.cond` で size mismatch (256 vs 512) になります ([Issue #616](https://github.com/ayutaz/piper-plus/issues/616))。 現時点で FT / ONNX エクスポートに使う場合は互換タグ **`v1.13.0`** を checkout してください (`git clone --branch v1.13.0 https://github.com/ayutaz/piper-plus.git`)。 v2.0 対応の新しい base ckpt は次回リリースで公開予定です。

> **音素表の世代差**: 本 ckpt は `num_symbols=173` (6 言語時代の inventory) で学習されています。 現行の `get_phoneme_id_map("ja-en-zh-es-fr-pt")` は KO/SV を含む 8 言語統合マップ (185 symbol) を 返すので、 これを使って FT すると `model_g.enc_p.emb.weight` が 173 vs 185 で size mismatch に なります。 FT 時は `get_phoneme_id_map()` ではなく HF `config.json` の `phoneme_id_map` / `num_symbols` をそのまま使ってください (`get_phoneme_id_map` の docstring が案内している経路。 `notebooks/finetune.ipynb` は対応済み)。

**Zero-Shot TTS Models (PR #222, v7 multi-6lang scratch + Tsukuyomi FT):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| v7 Multi-6lang Zero-Shot | JA/EN/ZH/ES/FR/PT | 571 + zero-shot | Zero-shot TTS base, scratch-trained 32 epochs (V100 × 4, 12.5 days, 2026-05-08〜2026-05-20). CAM++ ECAPA-TDNN (192-dim) speaker embedding + Multi-scale FiLM + DINO self-distill. SECS (zero-shot) **0.6879** at epoch 32. ONNX 38.9 MB FP16. | [HuggingFace (private)](https://huggingface.co/ayousanz/piper-plus-zero-shot-multi-6lang-v7) |
| Tsukuyomi Zero-Shot FT | JA/EN/ZH/ES/FR/PT | 1 (single-speaker FT) | Single-speaker fine-tune from v7 zero-shot base, 500 epochs (2026-05-21, 51 min on RTX 4070 Ti SUPER). Tsukuyomi-chan reproducibility SECS (CAM++) **0.7749**. ONNX 38.2 MB FP16. | [HuggingFace (private)](https://huggingface.co/ayousanz/piper-plus-zero-shot-tsukuyomi) |
| CAM++ Speaker Encoder | — | — | Apache-2.0 licensed CAM++ ECAPA-TDNN ONNX (ModelScope iic mirror, Voice Cloning 用 speaker embedding 抽出器、 192-dim L2 normalized). | [HuggingFace (private)](https://huggingface.co/ayousanz/campplus-onnx) |

> **Note**: zero-shot model repos are currently **private** during license review. Public listing planned post-v2.0.0 GA. Research details and training reproducibility: [`docs/design/multi-6lang-zero-shot-v7-training-results.md`](../../design/multi-6lang-zero-shot-v7-training-results.md), environment handoff: [`docs/handoff/zero-shot-tts-handoff-2026-06-20.md`](../../handoff/zero-shot-tts-handoff-2026-06-20.md).

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
- Phonemes: 173 symbols (`symbol_set_version` 1.0 — the inventory the published models were trained on). 現行コードの live inventory は 185 symbol (`1.1`、 KO/SV 追加分を含む) で、 先頭 173 は 1.0 と byte 一致する append-only 拡張。 契約と検証: [`docs/spec/phoneme-set-version.toml`](../../spec/phoneme-set-version.toml)
- Prosody Features: A1/A2/A3 prosody information (Japanese)
- Extended phonemes: Question markers, context-dependent "N" variants

> **Note:** piper-plus has custom architecture extensions (multilingual embeddings, Prosody A1/A2/A3, 173 symbols) that make it incompatible with upstream Piper checkpoints/ONNX models. Please use piper-plus specific models.

## Japanese TTS Specifics

High-quality Japanese speech synthesis with OpenJTalk integration. The dictionary (NAIST-JDIC) is automatically downloaded on first run. HTS voice files are not required (removed in PR #342).

**Environment Variables (optional):**

| Variable | Description |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk dictionary path (auto-downloads if not set) |
| `PIPER_PLUS_AUTO_DOWNLOAD_DICT` | Set to `0` to disable auto-download |
| `PIPER_PLUS_OFFLINE_MODE` | Set to `1` for offline mode |

See the Japanese Usage Guide and [Phoneme Mapping Reference](../../api-reference/phoneme-mapping.md).

---

→ Back to [README](../../../README_EN.md)
