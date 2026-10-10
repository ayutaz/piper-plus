# Pre-trained Models

Available pre-trained piper-plus models, how to download them, and language-specific model details including Japanese TTS.

## Model Download

Pre-trained models for multilingual TTS and fine-tuning are available on Hugging Face.

**Zero-Shot + fine-tuning base (2026-10-10):**

[zs-v1 is publicly available without a gate](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1).
It packages the existing **v7 epoch32 experimental baseline**, including a 192-dim CAM++ encoder,
Zero-Shot FP16 ONNX, fine-tuning checkpoint, model-specific config, hashes and runnable examples.
Reference-conditioned generation was checked with PyPI `piper-plus==2.0.0`; short fine-tuning,
checkpoint save, export and reference-free generation were checked with GitHub `v2.0.0` source.
This is an interim model with known noise/voice-transfer limits and some unsupported historical phonemes.
It is not a newly quality-approved or latest/best model. See the [release record](../../design/zero-shot-base-zs-v1-release-2026-10-10.md)
and [published usage guide](https://huggingface.co/ayousanz/piper-plus-base/blob/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/README.md).
The legacy root files remain separate; use the config bundled with the selected generation.

**Inference Models (ready to use):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang (canonical) | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan voice, 6-language, FP16. **500 epochs (2026-03-16)**, fine-tuned from 6-language base with `freeze-dp` + `emb_lang` unify for voice consistency across all 6 languages. Actual HF file: `tsukuyomi-chan-6lang-fp16.onnx`. ONNX size 39,652,717 bytes (37.8 MiB). | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japanese 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 Japanese voice, 6-language, FP16. 50 epochs from 6-language base, 6,841 utterances. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

> **MB-iSTFT / 6lang-v2 variants (upcoming)**: `tsukuyomi-mb-istft-500epoch.onnx` (500 epoch MB-iSTFT FT、 2.21x faster CPU inference) と `tsukuyomi-6lang-v2-fixed.onnx` (v3→v4→v2 段階改善版) は学習完了済みですが、 HF への upload はまだ実施されていません。 現在 canonical な推論用 ONNX は `tsukuyomi-chan-6lang-fp16.onnx` のみです。 進捗は [Issue #590](https://github.com/ayutaz/piper-plus/issues/590) / follow-up model publish tracking 参照。

**Base Models (for fine-tuning):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| Legacy 6-Language Base (MB-iSTFT-VITS2) | JA/EN/ZH/ES/FR/PT | 571 | Retained root-era multilingual checkpoint (508,187 utterances, VITS + Prosody). **75 epochs scratch / `epoch=74-step=500034`**, MB-iSTFT + PQMF decoder (`upsample_rates=(4, 4)` × iSTFT(4) × PQMF(4) = 256x), language-balanced sampling, WavLM-disabled (V100 friendly). `num_symbols=173` / `num_languages=6` / `prosody_dim=16` / `gin_channels=512`. Root files remain `model.ckpt` + `config.json` for legacy fine-tuning; they do not provide the new CAM++ zero-shot path. | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

> **Decoder 世代**: HF root の `model.ckpt` は 2026-05-03 に HiFi-GAN 版から **MB-iSTFT-VITS2 版** (75 epoch scratch、 2.21x faster CPU inference、 [Issue #268](https://github.com/ayutaz/piper-plus/issues/268) / [PR #320](https://github.com/ayutaz/piper-plus/pull/320)) に差し替え済みです。 旧 HiFi-GAN 版の ckpt は配布されていません。 root の旧 run に対応する ONNX はこのガイドの公開推論モデルではありません。新しい公開ベースは下記 `releases/zs-v1` を使用してください。

> **旧rootとZero-Shot baseの区別**: 旧root checkpointには現研究の192次元話者projectionがありません。
> 旧decoder条件層の移行処理はv2.0.0のtraining sourceに実装されていますが、今回の公開検証は
> 新しい`releases/zs-v1`を対象にしています。旧rootのFT互換と、新しいZero-Shot baseの両用途検証を混同しないでください。

> **公開 zs-v1 の利用条件**: `releases/zs-v1/base.onnx` は v7 epoch32 の実験用
> Zero-Shot base です。推論時は 192 次元 CAM++ `speaker_embedding` と対応する
> `campplus.onnx` が必要です。通常の参照なし TTS API/Wyoming 音声として使うモデルではありません。
> `base.ckpt` を単一話者へ追加学習して export した ONNX では、参照なし生成を確認済みですが、
> これは機能確認であり品質承認ではありません。公開 bundle は revision
> `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1` に固定されています。

> **音素表の世代差**: 本 ckpt は `num_symbols=173` (6 言語時代の inventory) で学習されています。 現行の `get_phoneme_id_map("ja-en-zh-es-fr-pt")` は KO/SV を含む 8 言語統合マップ (185 symbol) を 返すので、 これを使って FT すると `model_g.enc_p.emb.weight` が 173 vs 185 で size mismatch に なります。 FT 時は `get_phoneme_id_map()` ではなく HF `config.json` の `phoneme_id_map` / `num_symbols` をそのまま使ってください (`get_phoneme_id_map` の docstring が案内している経路。 `notebooks/finetune.ipynb` は対応済み)。

**Zero-Shot TTS Models (PR #222, v7 multi-6lang scratch + Tsukuyomi FT):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| v7 Multi-6lang Zero-Shot (research) | JA/EN/ZH/ES/FR/PT | 571 + zero-shot | Research artifact: scratch-trained 32 epochs (V100 × 4, 12.5 days, 2026-05-08〜2026-05-20). CAM++ (192-dim) speaker embedding + Multi-scale FiLM + DINO self-distill. SECS (zero-shot) **0.6879** at epoch 32. Research repository remains private. | [HuggingFace (private)](https://huggingface.co/ayousanz/piper-plus-zero-shot-multi-6lang-v7) |
| Tsukuyomi Zero-Shot FT | JA/EN/ZH/ES/FR/PT | 1 (single-speaker FT) | Single-speaker fine-tune from v7 zero-shot base, 500 epochs (2026-05-21, 51 min on RTX 4070 Ti SUPER). Tsukuyomi-chan reproducibility SECS (CAM++) **0.7749**. ONNX 38.2 MB FP16. | [HuggingFace (private)](https://huggingface.co/ayousanz/piper-plus-zero-shot-tsukuyomi) |
| CAM++ Speaker Encoder | — | — | Apache-2.0 licensed CAM++ ONNX (ModelScope iic mirror, Voice Cloning 用 speaker embedding 抽出器、 192-dim L2 normalized). | [HuggingFace (private)](https://huggingface.co/ayousanz/campplus-onnx) |

> **Research storage**: the private/gated repositories above retain research artifacts. General users should download
> the ungated `piper-plus-base/releases/zs-v1` bundle at the pinned revision above, which includes `base.onnx`,
> `base.ckpt`, `config.json`, `base.onnx.json`, `campplus.onnx`, and their hashes. It needs no access to research storage.
> A new Tsukuyomi FT release from the same public base is the next stage and has not been published here.
> Historical SECS scores above are not a new quality approval. Research details: [`docs/design/multi-6lang-zero-shot-v7-training-results.md`](../../design/multi-6lang-zero-shot-v7-training-results.md).

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
- Phonemes: 173 symbols for these historical checkpoints. 現行コードのlive inventoryは185 symbol (`1.1`)ですが、同じ173という音素数でも研究artifactと前処理のID対応が異なる場合があります。実際の重みに対応する配布configを使用し、FT入力も音素名を介して対応を合わせてください。契約のinventory snapshotだけで既存HF checkpointの対応表と同一だと判定しないでください。
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
