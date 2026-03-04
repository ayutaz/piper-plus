# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🚀 現在の状態: v4 学習完了 + つくよみちゃん v4 ファインチューニング完了

**ブランチ**: `feat/bilingual-phonemizer`

### 最新データセット: `dataset-bilingual-ja-en-v4`

| 項目 | 値 |
|------|-----|
| データセット | `dataset-bilingual-ja-en-v4` |
| 発話数 | **135,060** (JA=60,148 + EN=74,912) |
| 話者数 | 330 (JA 20話者 speaker_id 0-19 + EN 310話者 LibriTTS-R speaker_id 20-329) |
| 音声時間 | JA **~78h** + EN **~92h** = 計 **~170h** (JA:EN ≈ 46:54) |
| EN per-speaker | **平均17.8分** (min=180発話, median=222発話, max=515発話) |
| 言語数 | 2 (ja=0, en=1) |
| シンボル数 | 97 |
| 状態 | **学習完了 (2026-03-04)** — 150 epoch、epoch=149-step=269700.ckpt、~46時間 |

### v4 データセット作成の概要 (2026-02-28)

- **目的**: EN per-speaker データ密度を v3 の 6.4分 → 17.8分 (2.8倍) に改善。話者数を絞り、per-speaker 発話量を増やして speaker embedding の学習品質を向上
- **JA**: v3 の 60,148 発話をそのまま再利用 (`--ja-already-bilingual`)
- **EN**: LibriTTS-R (libritts-ljspeech-v4) から **180 発話以上**の話者のみ採用 (1,151 → 310 話者)
- **EN ソース**: `libritts-ljspeech-v4` — LibriTTS_R 全 149,683 ファイルを LJSpeech 形式に変換（v3 は 60K 件制限だった）
- **キャッシュ**: エネルギーVAD高速キャッシュ (energy VAD fast path, ~37.5 files/s)

### 前バージョン: `dataset-bilingual-ja-en-v3` (学習完了)

| 項目 | 値 |
|------|-----|
| データセット | `dataset-bilingual-ja-en-v3` |
| 発話数 | **115,795** (JA=60,148 + EN=55,647) |
| 話者数 | 848 (JA 20話者 + EN 828話者) |
| 音声時間 | JA **85.5h** + EN **88.5h** = 計 **174h** |
| 状態 | **学習完了 (2026-02-27)** — 350 epoch完了、epoch=349-step=202300.ckpt |

### 次のステップ (TODO)

1. ✅ **v2 学習完了**: 200 epoch、約4時間19分 (2026-02-24)
2. ✅ **v2 ONNX 変換**: `bilingual-ja-en-v2-200epoch.onnx` (74MB, EMA適用済み)
3. ✅ **v2 推論テスト**: JA / EN / 混合テキスト 全3テスト成功 (RTF 0.13〜0.21)
4. ✅ **v3 データセット作成**: 115,795発話 / 848話者 / 174h、整合性確認済み (2026-02-25)
5. ✅ **v3 学習開始**: 350 epoch / language-balanced-sampling (2026-02-25)
6. ✅ **v3 学習完了**: epoch=349-step=202300.ckpt (2026-02-27)
7. ✅ **つくよみちゃん v3ベースファインチューニング完了**: 500 epoch / 1GPU / lr=2e-5 (2026-02-28) — epoch=499-step=22000.ckpt
8. ✅ **v3 ONNX 変換**: `bilingual-ja-en-v3-350epoch.onnx` (76MB, EMA適用済み) — JA/EN/混合テスト成功 (RTF 0.10〜0.16) (2026-02-28)
9. ✅ **つくよみちゃん v3 ONNX 変換**: `tsukuyomi-v3-emb_lang_fixed.onnx` (emb_lang[1] EN初期化済み) — JA/EN/混合テスト成功 (2026-02-28)
10. ✅ **v4 データセット作成**: 135,060発話 / 330話者 / ~170h、EN per-speaker 17.8分 (v3比2.8倍) (2026-02-28)
11. ✅ **PR #218 CI修正**: ruff lint/format、coverage互換性、テスト graceful skip — 37/40 checks PASSED (2026-03-01)
12. ✅ **v4 学習完了**: 150 epoch / ~46時間 / language-balanced-sampling 自動有効化 (2026-03-04) — epoch=149-step=269700.ckpt
13. ✅ **v4 ONNX 変換**: `bilingual-ja-en-v4-150epoch.onnx` (75MB, EMA適用済み) — JA/EN/混合テスト成功 (2026-03-04)
14. ✅ **つくよみちゃん v4ベースファインチューニング完了**: 500 epoch / 1GPU / lr=2e-5 (2026-03-04) — epoch=499-step=22000.ckpt、チェックポイント変換方式（emb_g除去→emb_lang補正→resume_from_checkpoint）
15. ✅ **つくよみちゃん v4 ONNX 変換**: `tsukuyomi-v4.onnx` (74MB) — JA/EN/混合テスト成功 (2026-03-04)
16. ✅ **`--freeze-dp` オプション追加**: Duration Predictor 凍結フラグ実装 (2026-03-04) — ファインチューニング時の DP catastrophic forgetting 防止
17. ✅ **つくよみちゃん v4 freeze-dp 再FT完了**: 500 epoch / --freeze-dp / ~52分 (2026-03-04) — 音声長 1.11s→1.76s に改善（DP崩壊抑制確認済み）
18. **HuggingFace アップロード**: v4 バイリンガル + つくよみちゃん v4 をアップロード
19. **不要チェックポイント削除**: `output-bilingual-ja-en/lightning_logs/version_28/checkpoints/` に全200エポック分 (~176GB) が残存。`epoch=199` と `last.ckpt` 以外は削除してディスク節約可能

### v4 vs v3 vs v2 vs enhanced-fixed 比較

| 指標 | enhanced-fixed | v2 | v3 | **v4 (現在)** |
|------|----------------|-----|-----|--------------|
| EN 発話数 | 59,994 (1話者) | 3,177 (20話者) | 55,647 (828話者) | **74,912 (310話者)** |
| EN 総時間 | 75h (単一話者) | 6.5h | 88.5h | **~92h** |
| EN 話者あたり時間 | 75h | 20分 | 6.4分 (中央値) | **17.8分 (平均)** |
| JA:EN バッチ比 (補正後) | 1:1 | 1:1 | 1:1 | **1:1 (language-balanced-sampling 自動有効化)** |
| Fix A/B (言語条件) | ❌ | ✅ | ✅ 継承 | ✅ 継承 |
| 学習期間 | - | 4h19分 (200ep) | ~3日 (350ep) | **~46時間 (150ep)** |
| num_speakers | 21 | 40 | 848 | **330** |

**v4 の設計方針**: v3 は EN 828 話者で per-speaker 6.4分と薄かった。v4 は EN 180発話以上の話者のみ (310話者) に絞り、per-speaker 密度を **2.8倍** に改善。

**`--language-balanced-sampling` は自動有効化**: v4 は EN 310 話者 vs JA 20 話者 (比率 15.5:1 ≥ 閾値 3.0) のため、自動的に有効化される。明示指定も可能だが不要。

### 学習開始コマンド (v4 ← 学習完了)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en-v4 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 150 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --default_root_dir /data/piper/output-bilingual-ja-en-v4 \
  > /data/piper/training_v4.log 2>&1 &
```

**注意:** `--language-balanced-sampling` は話者数比 15.5:1 ≥ 3.0 閾値により自動有効化される（明示指定不要）。`--max_epochs 150` は v3 (350ep × ~578 batches) と同等の gradient steps を確保するために計算 (v4 は ~1,798 batches/epoch のため 150ep で十分)。`--checkpoint-epochs 5` でディスク節約。

### 学習開始コマンド (v3 ← 学習完了)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en-v3 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 350 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --language-balanced-sampling \
  --default_root_dir /data/piper/output-bilingual-ja-en-v3 \
  > /data/piper/training_v3.log 2>&1 &
```

**注意:** `--language-balanced-sampling` で JA:EN = 50:50 を強制。`--max_epochs 350` は EN 最小話者が phoneme フィルタ後に 16 発話まで減少するため、等価ステップ数を確保するため 200 ep → 350 ep に増やしている（200 ep × 552 batches ≒ 350 ep × 331 batches）。

### つくよみちゃん v3ベースモデルファインチューニング (2026-02-27 開始 → 2026-02-28 完了)

v3バイリンガルモデル (848話者, 350 epoch) をベースとして、つくよみちゃんデータ (100発話, ~11分) を転移学習。500 epoch完了。

**転移学習の仕組み:**
- v3の `emb_g` (speaker embedding: 848×512) → 新モデルは `num_speakers=1` なので `emb_g` なし
- `--resume_from_checkpoint` → `emb_g` キー不一致で strict=False フォールバック
- `emb_g` 以外のすべての重みが v3 から転移 (encoder / decoder / flow / dp / discriminator)
- `emb_lang` (language embedding: 2×512) はそのまま維持 → JA 言語条件づけを保持

**emb_lang[1] (EN) 初期化修正 (2026-02-28):**
- シングル話者 fine-tuning は JA データのみのため `emb_lang[1]` (EN) は学習されない
- fine-tuning 完了後に `emb_lang[1] = emb_lang[0].clone()` で JA 声質を EN conditioning の初期値にコピー
- 修正前: emb_lang[1] ノルム = 14.71 / 修正後: 17.07（JA と同一化）
- 修正済み ONNX: `tsukuyomi-v3-emb_lang_fixed.onnx`（EN 声質がつくよみちゃんに近似）

**データセット:** `/data/piper/dataset-tsukuyomi-finetune-v3/` (100発話, 1話者, 97シンボル)

**学習開始コマンド:**
```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-tsukuyomi-finetune-v3 \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --checkpoint-epochs 50 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --val-every-n-epochs 50 \
  --audio-log-epochs 50 \
  --resume_from_checkpoint \
    /data/piper/output-bilingual-ja-en-v3/lightning_logs/version_0/checkpoints/epoch=349-step=202300.ckpt \
  --default_root_dir /data/piper/output-tsukuyomi-finetune-v3 \
  > /data/piper/training_tsukuyomi_v3.log 2>&1 &
```

**設計根拠:**
| パラメータ | 値 | 理由 |
|-----------|-----|------|
| `--devices 1` | 1 GPU | 100発話でDDPはオーバーヘッド過多 |
| `--base_lr 2e-5` | v3の1/10 | catastrophic forgetting防止 |
| `--batch-size 4` | 4 | 100発話 / 4 = 25 batches/epoch |
| `--max_epochs 500` | 500 | 25×500=12,500 gradient steps |
| `--no-wavlm` | true | 小データで不要、速度優先 |

### つくよみちゃん v4ベースモデルファインチューニング (2026-03-04 完了)

v4バイリンガルモデル (330話者, 150 epoch) をベースとして、つくよみちゃんデータ (100発話, ~11分) を追加学習。500 epoch完了。

**v3との違い — チェックポイント変換方式:**
- v3 では `--resume_from_checkpoint` で直接ロード (strict=False フォールバック)
- v4 では**事前にチェックポイントを変換**してからロード:
  1. `emb_g` (330×512) を除去
  2. `emb_g` 全話者平均を `emb_lang` に加算 (conditioning 分布補正)
  3. `emb_lang[1]` (EN) は元の値 + emb_g_mean をそのまま保持（~~JA でコピー上書き~~ → EN conditioning 保持に変更）
  4. optimizer/scheduler/epoch/EMA state をリセット
  5. 変換後チェックポイント: `bilingual-ja-en-v4-150epoch-single-speaker.ckpt` (302MB)
- **推奨:** 今後は `--resume-from-multispeaker-checkpoint` を使用すれば変換不要（自動で上記処理 + freeze-dp 有効化）

**データセット:** `/data/piper/dataset-tsukuyomi-finetune-v3/` (100発話, 1話者, 97シンボル — v3と同じ)

**学習開始コマンド:**
```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-tsukuyomi-finetune-v3 \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --checkpoint-epochs 50 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --freeze-dp \
  --val-every-n-epochs 50 \
  --audio-log-epochs 50 \
  --resume_from_checkpoint \
    /data/piper/output-bilingual-ja-en-v4/bilingual-ja-en-v4-150epoch-single-speaker.ckpt \
  --default_root_dir /data/piper/output-tsukuyomi-finetune-v4 \
  > /data/piper/training_tsukuyomi_v4.log 2>&1 &
```

**注意:** `--freeze-dp` で Duration Predictor を凍結し、ファインチューニング時の DP catastrophic forgetting を防止。

**生成モデル:** `/data/piper/output-tsukuyomi-finetune-v4/tsukuyomi-v4.onnx` (74MB)

### つくよみちゃん v4 freeze-dp 再ファインチューニング (2026-03-04 完了)

`--freeze-dp` 付きで v4 ベースからつくよみちゃんを再ファインチューニング。Duration Predictor の catastrophic forgetting を防止。

**学習設定:** 上記コマンドと同一（`--freeze-dp` 追加のみ）。出力先: `output-tsukuyomi-finetune-v4-freeze-dp`

**結果 — DP 凍結の効果:**

| モデル | 音声長 (「こんにちは、つくよみちゃんです。」) | 備考 |
|--------|---------------------------------------------|------|
| v4 base (FT前, speaker_id=0) | 2.73s | マルチスピーカーベースライン |
| **freeze-dp (500ep)** | **1.76s** | DP 凍結で劣化を抑制 |
| no-freeze (500ep, 旧) | 1.11s | DP 崩壊で早送り |

- 凍結なし (1.11s) → 凍結あり (1.76s) で **59% 改善**
- ベースモデル (2.73s) との差はマルチ→シングル話者化による duration 分布の変化（DP 崩壊とは別要因）

**生成モデル:** `/data/piper/output-tsukuyomi-finetune-v4-freeze-dp/tsukuyomi-v4-freeze-dp.onnx`

**チェックポイント:** `output-tsukuyomi-finetune-v4-freeze-dp/lightning_logs/version_0/checkpoints/epoch=499-step=22000.ckpt`

### 学習開始コマンド (v2、参考)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --default_root_dir /data/piper/output-bilingual-ja-en-v2 \
  > /data/piper/training_v2.log 2>&1 &
```

### 推論テスト (v3 バイリンガルモデル)

**日本語 (speaker_id=0, JA話者):**
```bash
CUDA_VISIBLE_DEVICES="" .venv/bin/python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en-v3/bilingual-ja-en-v3-350epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-v3/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、今日は良い天気ですね。" \
  --language ja-en --speaker-id 0 --noise-scale 0.667
```

**英語 (speaker_id=20, EN話者の先頭):**
```bash
CUDA_VISIBLE_DEVICES="" .venv/bin/python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en-v3/bilingual-ja-en-v3-350epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-v3/config.json \
  --output-dir /home/jovyan \
  --text "Hello, how are you today?" \
  --language ja-en --speaker-id 20 --noise-scale 0.667
```

**混合テキスト (コードスイッチング):**
```bash
CUDA_VISIBLE_DEVICES="" .venv/bin/python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en-v3/bilingual-ja-en-v3-350epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-v3/config.json \
  --output-dir /home/jovyan \
  --text "今日はgood morningですね" \
  --language ja-en --speaker-id 0 --noise-scale 0.667
```

**つくよみちゃん v3 (emb_lang修正済み):**
```bash
CUDA_VISIBLE_DEVICES="" .venv/bin/python -m piper_train.infer_onnx \
  --model /data/piper/output-tsukuyomi-finetune-v3/tsukuyomi-v3-emb_lang_fixed.onnx \
  --config /data/piper/dataset-tsukuyomi-finetune-v3/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、つくよみちゃんです。" \
  --language ja-en --speaker-id 0 --noise-scale 0.667
```

### V100 FP32 / WavLM無効の経緯

**FP32切り替え (2026-02-11):** `--precision 16-mixed` 使用時、Generator の backward pass が29-40秒かかり全体速度が 0.03 it/s に低下。`--precision 32-true` で backward が 0.7-1.1s に改善、全体速度 **0.45 it/s** (15倍高速化)。FP32でもGPU peak 13.7GB/16GB で V100に収まる。

**WavLM無効化 (2026-02-11):** WavLM有効時の学習速度が極めて遅く、完了まで推定19日。`--no-wavlm` で短縮。事前学習フェーズでは `--no-wavlm` で十分。

### 完了済みモデル (JA-only)

```
/data/piper/output-moe-speech-20speakers-v2/
├── lightning_logs/version_0/checkpoints/
│   ├── epoch=199-step=206000.ckpt
│   └── last.ckpt
└── moe-speech-20speakers-v2.onnx  ← JA-only本番用モデル (74MB)
```

---

## 実装済み機能

### Duration Predictor 凍結 (--freeze-dp) ✅ NEW (2026-03-04)

ファインチューニング時に Duration Predictor (DP) の catastrophic forgetting を防止するオプション。

**問題:** マルチスピーカー→シングルスピーカー転移学習で optimizer state がリセットされると、Adam の momentum/variance が「冷えた」状態から DP が不安定に更新され、音声の再生速度が異常に速くなる。

**解決策:** `--freeze-dp` フラグで DP パラメータを凍結（`requires_grad=False`）し、optimizer から除外。decoder（声質）のみ学習可能にする。

| シナリオ | DP | Decoder/Encoder/Flow |
|---------|-----|---------------------|
| 通常学習 (デフォルト) | 学習される | 学習される |
| `--freeze-dp` 指定 | **凍結** | 学習される |
| `--resume-from-multispeaker-checkpoint` 使用時 | **自動凍結** | 学習される |

**CLIオプション:** `--freeze-dp` — Duration Predictor パラメータを凍結（デフォルト: 無効）。`--resume-from-multispeaker-checkpoint` 使用時は自動有効化。

**実装ファイル:**
- `src/python/piper_train/__main__.py` — `--freeze-dp` CLI引数追加
- `src/python/piper_train/vits/lightning.py` — `configure_optimizers()` で DP 凍結 + optimizer 除外

**テストファイル:**
- `src/python/tests/test_freeze_dp.py` — 5テスト（凍結確認、他パラメータ非凍結確認、optimizer 除外確認）

### 学習高速化 ✅ NEW (2026-02-19)

Validation頻度削減、DataLoader最適化、LRスケジューラ修正、DDP最適化により学習スループットを向上。

**変更内容:**

| 項目 | 変更前 | 変更後 | 効果 |
|------|--------|--------|------|
| Validation頻度 | 毎エポック | 5エポックごと (`--val-every-n-epochs 5`) | Validation overhead 80%削減 |
| Validation バッチ数 | 全データ | 50バッチ (`--limit-val-batches 50`) | Validation時間短縮 |
| DataLoader num_workers | 0 | 2 | データ読み込み並列化 |
| DataLoader pin_memory | 無効 | 有効（デフォルト） | GPU転送高速化 |
| LRスケジューラ | エポック終了時に未ステップ | `on_train_epoch_end` で手動ステップ | 学習率が正しく減衰 |
| DDP strategy | `static_graph=True`（誤設定） | `find_unused_parameters=True` + `gradient_as_bucket_view=True` | GAN交互学習の未使用パラメータを正しく処理 |
| `__getitem__` スレッドセーフ | `pop(idx)` でリスト変更 | インデックスアクセスのみ | マルチワーカー安全 |

**新規CLIオプション:**
- `--val-every-n-epochs N` — Validation実行頻度（デフォルト: 5）
- `--limit-val-batches N` — Validation時の最大バッチ数（デフォルト: 50）

**デフォルト変更:**
- `--num-workers`: 0 → 2（明示的に `--num-workers 0` で旧動作に戻せる）
- `pin_memory`: 無効 → 有効（`--no-pin-memory` で無効化可能）

**実装ファイル:**
- `src/python/piper_train/__main__.py` — 新CLI引数追加、num_workersデフォルト変更
- `src/python/piper_train/vits/lightning.py` — `on_train_epoch_end()` LRスケジューラ修正、DDP `find_unused_parameters=True`
- `src/python/piper_train/vits/dataset.py` — `__getitem__` スレッドセーフ修正

**テストファイル (24テスト、4ファイル):**
- `src/python/tests/test_model_config.py` — CLI引数デフォルト値テスト
- `src/python/tests/test_dataset_getitem.py` — `__getitem__` スレッドセーフテスト
- `src/python/tests/test_ddp_strategy.py` — DDP strategy設定テスト
- `src/python/tests/test_lr_scheduler.py` — LRスケジューラステップテスト

### バイリンガル (JA+EN) Phonemizer ✅ NEW (2026-02-02)

文内コードスイッチング対応のバイリンガル音素化。Unicode範囲で言語セグメントを自動検出し、各言語のPhonemizerに委譲。

**機能:**
- 統一phoneme_id_map (JA+EN ~110記号、ID衝突なし)
- Unicode範囲ベースの言語自動検出 (CJK→ja、Latin→en)
- 混合テキスト対応: 「今日はgood morningですね」→ JA+EN音素を正しい順序で出力
- BOS/EOS/パディングの統一処理

**実装ファイル:**
- `src/python/piper_train/phonemize/bilingual_id_map.py` — 統一phoneme_id_map生成
- `src/python/piper_train/phonemize/bilingual.py` — `BilingualPhonemizer` (言語検出+混合phonemize)
- `src/python/piper_train/phonemize/registry.py` — `ja-en` 登録
- `test/test_bilingual_phonemizer.py` — 18テスト

**推論コマンド:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-enhanced-fixed/config.json \
  --output-dir /home/jovyan \
  --text "今日はgood morningですね" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

### バイリンガル学習パイプライン (Phase B) ✅ NEW (2026-02-02)

日英混合データセットでの学習を可能にする学習パイプライン拡張。

**機能:**
- `language_id` フィールド: Dataset/Batch/preprocessに追加 (0=ja, 1=en)
- 言語embedding: `nn.Embedding(n_languages, gin_channels)` をSynthesizerTrnに追加
- speaker embedding + language embeddingを加算して全サブモジュールに注入
- config.jsonに`num_languages`, `language_id_map`フィールド追加
- ONNX export/推論に`lid`入力対応
- preprocess.pyに`--language ja-en`バイリンガルモード追加

**変更ファイル:**
- `vits/dataset.py` — Utterance, UtteranceTensors, Batchにlanguage_id追加
- `vits/models.py` — SynthesizerTrnにn_languages, emb_lang, _get_global_conditioning追加
- `vits/lightning.py` — VitsModelにnum_languages、training loopでlanguage_ids伝播
- `export_onnx.py` — lid入力のONNXエクスポート対応
- `infer_onnx.py` — lid入力の推論対応
- `__main__.py` — config.jsonからnum_languages読み込み
- `preprocess.py` — PhonemeType.BILINGUAL + phonemize_batch_bilingual追加

**学習コマンド例 (バイリンガル):**
```bash
# 1. 前処理
uv run python -m piper_train.preprocess \
  --input-dir /path/to/bilingual_dataset \
  --output-dir /path/to/output \
  --language ja-en --sample-rate 22050 --dataset-format ljspeech

# 2. 学習
uv run python -m piper_train \
  --dataset-dir /path/to/output \
  --prosody-dim 16 --accelerator gpu --devices 4 \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2
```

**Phase C 状況:** 旧データセット (73,148発話、EN比率18%) で200 epoch学習完了 (2026-02-14)。enhanced-fixedデータセット (120,142発話、EN比率50%) で再学習予定

### Phonemizer ABC + 言語レジストリ ✅ NEW (2026-02-01)

`Phonemizer` 抽象基底クラスと言語レジストリにより、if/elif分岐を解消。新言語追加が容易に。

**新言語追加手順:**
1. `Phonemizer` を継承したクラスを作成 (`phonemize`, `phonemize_with_prosody`, `get_phoneme_id_map` を実装)
2. 必要に応じて `post_process_ids` をオーバーライド (BOS/EOS等)
3. `registry.py` の `_auto_register()` に登録

**実装ファイル:**
- `src/python/piper_train/phonemize/base.py` — `Phonemizer` ABC, 共通 `ProsodyInfo`
- `src/python/piper_train/phonemize/registry.py` — 言語レジストリ
- `src/python/piper_train/phonemize/japanese.py` — `JapanesePhonemizer`
- `src/python/piper_train/phonemize/english.py` — `EnglishPhonemizer`
- `test/test_phonemizer_registry.py` — レジストリ・ABCテスト

**変更点:**
- `ProsodyInfo` を `base.py` に統一 (日本語/英語共通)
- `EnglishProsodyInfo` は `ProsodyInfo` のエイリアス (後方互換)
- `infer_onnx.py` の言語分岐をレジストリ経由に変更
- BOS/EOS/パディング処理を `EnglishPhonemizer.post_process_ids()` に移動

### GPL-free 英語G2P (g2p-en) ✅ NEW (2026-01-31)

g2p-en (Apache-2.0) を使用したespeak-ng互換の英語音素化。espeak-ng/piper-phonemize (GPL) なしで英語推論が可能。

**espeak-ng互換の処理:**
- ストレスマーカー (`ˈ`/`ˌ`) を母音の前に挿入
- 単語間スペース挿入、句読点は前の単語に付着
- 機能語 (are, you, the等) のストレス除去
- AA+R → ɑːɹ、ER0 → ɚ、ER1 → ɜː の文脈依存変換
- BOS (`^`) / EOS (`$`) + phoneme間パディング (`_`=ID 0)

**実装ファイル:**
- `src/python/piper_train/phonemize/english.py` — G2P変換
- `src/python/piper_train/infer_onnx.py` — BOS/EOS・パディング挿入
- `test/test_english_phonemizer.py` — 42テスト

**推論コマンド:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir /path/to/output \
  --text "Hello, how are you today?" \
  --language en
```

**espeak-ngとの完全一致:**
hello, the cat, car, information, bird（検証済み）

**既知の差異（G2Pエンジン由来）:**
- 疑問詞 (how) のストレス種類: g2p-en=ˈ vs espeak-ng=ˌ
- フラッピング: g2p-en=t vs espeak-ng=ɾ (letter等)
- 縮約形: g2p-en=分離 vs espeak-ng=結合 (I am等)

### WavLM Discriminator ✅ NEW (2026-01-08)

Microsoft WavLMベースの知覚品質判別器。デフォルトで有効だが、`--no-wavlm` で無効化可能。

**期待効果:**
- MOS向上: +0.15-0.25
- 推論速度への影響: なし（学習時のみ使用）

**CLIオプション:**
- `--no-wavlm` — WavLM Discriminatorを無効化（学習速度向上、バッチサイズ増加可能）
- `--wavlm-every-n-steps N` — WavLM lossをNステップごとに計算（デフォルト: 1）
- `--c-wavlm` — WavLM loss重み（デフォルト: 0.5）

**実装ファイル:**
- `src/python/piper_train/vits/models.py` - `WavLMDiscriminator`クラス
- `src/python/piper_train/vits/lightning.py` - 学習ループ統合
- `src/python/piper_train/__main__.py` - `--no-wavlm` フラグ

**注意:**
- WavLMは学習時のみ使用（推論グラフには含まれない）
- FP16 Mixed Precision対応済み（内部でfloat32変換）
- GPUメモリ追加: 約1-2GB/GPU
- DDP + `find_unused_parameters=True` 環境では `--wavlm-every-n-steps N` (N>1) にすると未使用パラメータ同期のオーバーヘッドで逆に遅くなる（~3x低下確認済み）。マルチGPUでは N=1 を推奨

### WandB Audio Logging ✅ NEW (2026-02-14)

Validation時に生成される音声サンプルをWandBに自動アップロード。

**機能:**
- 毎エポック2サンプルを WandB Table 形式でログ（メモリ最適化版）
- リッチメタデータ: テキスト、話者ID、言語ID、エポック、ステップ、合成パラメータ
- WandBダッシュボードでブラウザ再生可能
- バイリンガル（ja/en）、マルチスピーカー（21話者）対応
- Graceful fallback: WandB未設定時は音声ログスキップ（学習継続）

**使用方法:**
```bash
# WandB APIキー設定（必須）
export WANDB_API_KEY=your_key_here

# 学習開始（自動で音声ログ有効）
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en-enhanced-fixed \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --no-wavlm \
  --audio-log-epochs 1 \
  --default_root_dir /data/piper/output-bilingual-ja-en-enhanced-fixed
```

**WandB UI での確認:**
1. https://wandb.ai/yourusername/piper-tts にアクセス
2. Run を選択
3. "validation_audio_samples" テーブルを開く
4. 音声を再生、メタデータで絞り込み可能

**Table Schema:**
- text: 元テキスト
- speaker: 話者ID（"spk=0" 形式）
- language: 言語コード（"ja" または "en"）
- epoch: エポック番号
- step: グローバルステップ
- audio: 再生可能な音声ウィジェット

**実装ファイル:**
- `src/python/piper_train/vits/lightning.py` - `on_validation_epoch_end()` でWandB Table形式ログ、`_get_wandb_logger()` ヘルパーメソッド
- `src/python/piper_train/__main__.py` - WandbLogger設定（TensorBoardLoggerと併用）

**実装の詳細:**
- PyTorch Lightning 2.x系では、複数ロガーは `trainer.loggers`（複数形）で管理される
- `_get_wandb_logger()` が `trainer.loggers` をチェックしてWandBLoggerを取得
- Validation epoch終了時に2サンプルの音声を生成し、WandB Table形式でログ
- エラーハンドリング: WandB未設定時は音声ログをスキップ（学習は継続）

**メモリ最適化 (2026-02-14更新):**
- **Generator メモリリークバグを修正** (models.py:360) — `torch.zeros(1)` によるCPUスカラー生成を `xs = None` 初期化に変更、In-place演算 (`xs +=`) を非In-place (`xs = xs +`) に変更
- **サンプル数を5→2に削減** (`--num-test-examples 2`) — メモリ使用量60%削減
- **積極的GPUメモリクリーンアップ** — 各サンプル生成後に `torch.cuda.synchronize()` + `empty_cache()`
- **学習ステップ後にインスタンス変数をクリア** — `_y`, `_y_hat` を `None` に設定してメモリ解放
- **定期的メモリクリーンアップに同期追加** — 500イテレーションごとの `empty_cache()` 前に `synchronize()`

**パフォーマンス最適化:**
- 音声ログは `on_validation_epoch_end()` で実行（validation_stepをブロックしない）
- `torch.no_grad()` + 明示的なメモリクリーンアップで効率化
- `--audio-log-epochs N` フラグで頻度制御（デフォルト: 1）
  - 例: `--audio-log-epochs 5` で5エポックごとにログ
  - `--audio-log-epochs 0` で音声ログを完全に無効化
- `--num-test-examples N` でサンプル数を制御（デフォルト: 2）
  - 例: `--num-test-examples 1` で最小メモリ使用

**⚠️ DDP NCCL タイムアウトバグと現状 (2026-02-22)**

マルチGPU DDP 学習中に `on_validation_epoch_end()` の WandB audio logging が NCCL ALLREDUCE タイムアウト（30分）を引き起こすバグが確認された。

**症状:** validation 後の training step で全ランクが NCCL タイムアウトでクラッシュ

**根本原因:** `on_validation_epoch_end()` で rank 0 が WandB アップロード（同期 I/O）を実行している間に Lightning が ranks 1-3 を次の training step へ進め、rank 0 が ALLREDUCE に参加できなくなる

**実施済み修正 (2026-02-22):**
1. `on_validation_epoch_end()` を `is_global_zero` ブロックで囲む（early return を廃止）
2. 関数末尾に `torch.distributed.barrier()` を追加し、全ランクが同期してから次 epoch へ進むように変更

**v3 での運用実績 (350epoch 完了):**
- `--audio-log-epochs 5` で audio logging を有効化 (barrier fix 済みで安定運用確認)
- 新規学習でも `--audio-log-epochs 5` を推奨

**トラブルシューティング:**
- CUDAメモリエラーが発生する場合:
  1. `--audio-log-epochs 10` で頻度を下げる
  2. `--num-test-examples 1` でサンプル数をさらに削減
  3. `--audio-log-epochs 0` で完全無効化
- 学習速度を最優先する場合: `--audio-log-epochs 0` で無効化

### テキスト直接入力推論 ✅ NEW (2026-01-08)

`infer_onnx.py`に`--text`オプション追加。JSONLなしで日本語テキストから直接音声生成。

**使用方法:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir /path/to/output \
  --text "こんにちは" \
  --speaker-id 0
```

**追加引数:**
| 引数 | 説明 |
|------|------|
| `--text` | 日本語テキスト入力 |
| `--config` | config.jsonパス（phoneme_id_map必須） |
| `--speaker-id` | 話者ID（デフォルト: 0） |

### Issue #204: 疑問詞マーカーの拡張 ✅

日本語の疑問文の種類を区別するための新しいマーカーを追加。

| マーカー | Unicode | 用途 | 例 |
|----------|---------|------|-----|
| `?!` | 0xE016 | 強調疑問 | 本当?! 本当！？ |
| `?.` | 0xE017 | 平叙疑問 | そうなの?. |
| `?~` | 0xE018 | 確認疑問 | 行くよね?~ |

**実装ファイル:**
- `src/python/piper_train/phonemize/japanese.py` - `_get_question_type()` 関数

### Issue #207: 文脈依存「ん」(N) バリアント ✅ NEW

「ん」の発音が後続音によって変わることを反映。

| バリアント | Unicode | 条件 | 例 |
|-----------|---------|------|-----|
| `N_m` | 0xE019 | m/b/p の前（両唇音同化）| さんぽ |
| `N_n` | 0xE01A | n/t/d/ts/ch の前（歯茎音同化）| あんない |
| `N_ng` | 0xE01B | k/g の前（軟口蓋音同化）| ぎんこう |
| `N_uvular` | 0xE01C | 語末/母音の前（口蓋垂音）| ほん |

**実装ファイル:**
- `src/python/piper_train/phonemize/japanese.py` - `_apply_n_phoneme_rules()` 関数
- `src/python/piper_train/phonemize/jp_id_map.py` - 新トークン定義
- `src/python/piper_train/phonemize/token_mapper.py` - PUAマッピング

**音素変換例:**
```
さんぽ → s a N_m p o     (N → N_m: pの前)
あんない → a N_n n a i   (N → N_n: nの前)
ぎんこう → g i N_ng k o o (N → N_ng: kの前)
ほん → h o N_uvular      (N → N_uvular: 語末)
```

**期待効果:**
- MOS向上: +0.04-0.08
- 推論速度への影響: なし（前処理のみ）

### prosody_features (A1/A2/A3) モデル統合 ✅

OpenJTalkから抽出されるA1/A2/A3値をDuration Predictorの入力として活用。

**A1/A2/A3の意味:**

| フィールド | 意味 | 値の例 |
|-----------|------|--------|
| A1 | アクセント核からの相対位置 | -4, -3, ..., 0, 1, ... |
| A2 | アクセント句内のモーラ位置 | 1, 2, 3, ... |
| A3 | アクセント句内の総モーラ数 | 1-10+ |

**使用方法:**
```bash
# 学習時
uv run python -m piper_train --prosody-dim 16 ...

# 前処理時（prosody_features 付きデータセット作成）
uv run python /data/piper/add_prosody_features.py --input-dataset ... --output-dir ...
```

**デフォルト有効:** prosodyはデフォルトで有効（`--prosody-dim 16`）

### 言語グループ均等サンプリング (--language-balanced-sampling) ✅ NEW (2026-02-25, 自動有効化対応 2026-03-01)

EN 話者数 >> JA 話者数の場合（v4: 310 EN vs 20 JA、v3: 828 EN vs 20 JA）でも JA 品質を保護するバッチサンプリング拡張。

**問題:** v3/v4 では言語バランスなしで JA がバッチの数% しか学習されない（v2 は 50:50 で問題なし）。

**自動有効化 (2026-03-01):** `language_group_balance` パラメータが `None`（デフォルト）の場合、言語間の話者数比が **3:1 以上**で自動的に有効化される。CLI で `--language-balanced-sampling` を明示指定すると強制有効化。

| シナリオ | 動作 |
|---------|------|
| `--language-balanced-sampling` 指定 | 有効（強制） |
| 未指定 + 比率 >= 3:1 (例: 310:20) | **自動有効化** |
| 未指定 + 比率 < 3:1 (例: 50:30) | 無効 |
| 未指定 + 言語1つ | 無効 |

**実装:** `SpeakerBalancedBatchSampler` の `language_group_balance` パラメータを `bool | None` に変更。`None` の場合、`Counter(speaker_to_language.values())` で話者数比を計算し閾値 3.0 で自動判定。

```bash
--language-balanced-sampling  # 強制有効化（通常は自動判定で十分）
```

**CLIオプション:** `--language-balanced-sampling` — 強制有効化。未指定時は話者数比 >= 3:1 で自動有効化

**実装ファイル:**
- `src/python/piper_train/vits/dataset.py` — `SpeakerBalancedBatchSampler` に `language_group_balance: bool | None` 自動判定ロジック追加
- `src/python/piper_train/vits/lightning.py` — `train_dataloader()` で CLI 未指定時に `None` を伝播
- `src/python/piper_train/__main__.py` — `--language-balanced-sampling` ヘルプテキスト更新

### エネルギーVAD高速キャッシュ ✅ NEW (2026-02-25)

LibriTTS-R の音声キャッシュ処理を Silero ONNX VAD から numpy エネルギーVAD に置き換えて **25倍高速化**。

| 指標 | Silero ONNX (旧) | Energy VAD (新) |
|------|-----------------|----------------|
| 単体速度 | ~390ms/file | ~8ms/file |
| 並列スループット (16w) | 1.5 files/s | **37.5 files/s** |
| 45,647ファイル | ~530分 | **~20分** |

**根拠:** LibriTTS-R はほぼ無音なし（先頭オフセット平均 1ms）のため Silero VAD は不要。numpy vectorized RMS で 1793x 高速かつ 100% 一致。

**実装ファイル:**
- `src/python/piper_train/norm_audio/__init__.py` — `energy_vad_numpy()` + `cache_norm_audio_fast()` 追加
- `prepare_bilingual_dataset.py` — `_cache_audio_batch_worker_fast()` 追加、EN キャッシュを fast path (batch=50) に切り替え

### 転移学習の話者成分処理修正 ✅ NEW (2026-02-28)

マルチ→シングル話者転移の専用フラグ追加と、逆方向の cond 層削除バグ修正。

**修正1: `--resume_from_single_speaker_checkpoint` の cond 層削除バグ修正**

シングル→マルチ転移時に `dec.cond`, `dp.cond`, `enc.cond_layer` を誤って除外していた。
これらは `gin_channels=512` で形状が同一のため除外不要。全重みが転移されるよう修正。

**修正2: `--resume-from-multispeaker-checkpoint` フラグ追加**

マルチスピーカー → シングルスピーカー転移の専用 API。

```bash
.venv/bin/python -m piper_train \
  --dataset-dir /path/to/single_speaker_dataset \
  --resume-from-multispeaker-checkpoint /path/to/multispeaker.ckpt \
  ...
```

処理ステップ:
1. `strict=False` でロード（`emb_g` は自動スキップ）
2. `emb_g` の全話者平均を `emb_lang` に加算（conditioning 分布補正）
3. `emb_lang[1]` (EN) は元の値 + emb_g_mean 補正をそのまま保持（JA でコピー上書きしない）
4. `--freeze-dp` を自動有効化（DP catastrophic forgetting 防止）

**注意:** 以前は `emb_lang[1] = emb_lang[0].clone()` で JA→EN コピーしていたが、凍結された DP が EN conditioning を認識できず英語 duration が崩壊する問題があったため、元の EN embedding を保持する方式に変更。

**実装ファイル:**
- `src/python/piper_train/__main__.py` — `--resume-from-multispeaker-checkpoint` 追加、freeze-dp 自動有効化

### preprocess.py: piper_phonemize 条件付きインポート ✅ NEW (2026-02-27)

`preprocess.py` の `piper_phonemize` トップレベルインポートを `try/except` でラップし、
`--language ja-en` (bilingual) モードで `piper_phonemize` がインストールされていない環境でも動作するよう修正。

**問題:** `piper_phonemize` (GPL) は bilingual/Japanese モードでは不要だが、トップレベルインポートのため
モジュールが存在しないと `ModuleNotFoundError` で即時クラッシュしていた。

**修正ファイル:**
- `src/python/piper_train/preprocess.py` — `from piper_phonemize import ...` を `try/except ImportError` でラップ

### PR #218 CI修正 ✅ NEW (2026-03-01)

PR #218 の CI を全チェック PASSED にするための4コミット。37/40 checks PASSED、残り3件は ARM64/Docker (無関係)。

**修正内容:**

| 修正 | 内容 | 対象ファイル |
|------|------|-------------|
| coverage 互換性 | coverage 7.3.2 → 7.6.9 に更新 (numba 0.64.0 との互換性) | `src/python/requirements_test.txt` |
| ruff lint/format | E741 変数名リネーム、PLC0415 noqa、I001 import ソート、ruff format | 7ファイル + `prepare_bilingual_dataset.py` |
| テスト graceful skip | `pytorch_lightning` / `monotonic_align.core` 未インストール時に自動スキップ | `test_ddp_strategy.py`, `test_model_config.py` |
| monotonic_align guard | `piper_train.__main__` インポートを try/except でラップ | `test_ddp_strategy.py` |

**変更ファイル:**
- `src/python/requirements_test.txt` — coverage バージョン更新
- `src/python/tests/test_ddp_strategy.py` — `pytest.importorskip` + try/except guard 追加
- `src/python/tests/test_model_config.py` — `pytest.importorskip` 追加
- `src/python/piper_train/` 配下7ファイル — ruff lint/format 修正
- `prepare_bilingual_dataset.py` — ruff format 修正

### SpeakerBalancedBatchSampler ✅

マルチスピーカーモデルのDuration Predictor崩壊問題を解決するカスタムバッチサンプラー。

```bash
--batch-size 32 --samples-per-speaker 4  # 8話者 × 4サンプル = 32
```

### FP16 Mixed Precision ✅ (⚠️ V100非推奨)

`--precision 16-mixed` で有効化。**ただしV100ではGenerator backward passが29-40秒に低下する致命的な性能問題があるため、V100では `--precision 32-true` を使用すること。** A100/L4等の新しいGPUでは正常に動作する可能性がある。

---

## 学習設定

### 推奨設定 (20話者、V100 GPU 16GB × 4、WavLM無効)

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --no-wavlm \
  --default_root_dir /data/piper/output-moe-speech-20speakers-v2
```

**注意:** V100では `--precision 32-true` を使用すること（FP16-mixedはbackward passが極端に遅くなる）。WavLMはデフォルトで有効。`--no-wavlm` で無効化するとbatch-size 20が使用可能に。WavLM有効時は16GBでbatch-size 20でOOM発生するため batch-size 12 が必要。

### 話者数別の推奨設定

| 話者数 | batch_size | samples_per_speaker | 実効バッチ | 備考 |
|-------|------------|---------------------|-----------|------|
| 5話者 | 20 | 4 | 20 | ✅ 検証済み (WavLMなし) |
| **20話者** | **20** | **2** | **40** | **✅ WavLM無効時 (`--no-wavlm`)** |
| 20話者 | 12 | 2 | 24 | WavLM有効時 (L4 16GB OOM対策) |

### NCCL環境変数（マルチGPU必須）

```bash
NCCL_DEBUG=WARN
NCCL_P2P_DISABLE=1
NCCL_IB_DISABLE=1
```

---

## 重要なファイルパス

### ソースコード

| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS実装 | `src/python/piper_train/vits/` |
| Phonemizer ABC | `src/python/piper_train/phonemize/base.py` |
| 言語レジストリ | `src/python/piper_train/phonemize/registry.py` |
| 英語音素化 | `src/python/piper_train/phonemize/english.py` |
| 日本語音素化 | `src/python/piper_train/phonemize/japanese.py` |
| IDマップ | `src/python/piper_train/phonemize/jp_id_map.py` |
| トークンマッパー | `src/python/piper_train/phonemize/token_mapper.py` |
| ONNXエクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| バイリンガルPhonemizer | `src/python/piper_train/phonemize/bilingual.py` |
| バイリンガルIDマップ | `src/python/piper_train/phonemize/bilingual_id_map.py` |

### データセット

| 用途 | パス | 発話数 | 特徴 |
|------|------|--------|------|
| **バイリンガル JA+EN v4** 学習待ち | `/data/piper/dataset-bilingual-ja-en-v4/` | 135,060 | JA 60,148 (20話者) + EN 74,912 (LibriTTS-R 310話者)、330話者、97シンボル、~170h、EN per-speaker 17.8分 |
| **バイリンガル JA+EN v3** ✅学習完了 | `/data/piper/dataset-bilingual-ja-en-v3/` | 115,795 | JA 60,148 (20話者) + EN 55,647 (LibriTTS-R 828話者)、848話者、97シンボル、174h |
| **つくよみちゃん v3ベース finetune** ✅完了 | `/data/piper/dataset-tsukuyomi-finetune-v3/` | 100 | 1話者、97シンボル、bilingual(JA+EN) |
| バイリンガル JA+EN v2 (参考) | `/data/piper/dataset-bilingual-ja-en-v2/` | 63,325 | JA 60,148 (20話者) + EN 3,177 (LibriTTS-R 20話者)、40話者 |
| バイリンガル JA+EN enhanced-fixed (参考) | `/data/piper/dataset-bilingual-ja-en-enhanced-fixed/` | 120,142 | JA 60,148 + EN 59,994、21話者、97シンボル |
| 20話者 v2 (JA-only) 参照用 | `/data/piper/dataset-moe-speech-20speakers-v2/` | 60,164 | Issue #204, #207 対応 |

**LibriTTS-R ソースデータ:**

| 用途 | パス | ファイル数 | 特徴 |
|------|------|----------|------|
| v4 EN ソース | `/data/piper/libritts-r/libritts-ljspeech-v4/` | 149,683 | LibriTTS_R 全ファイル LJSpeech 変換、1,151 話者 |
| v3 EN ソース | `/data/piper/libritts-r/libritts-ljspeech/` | ~60,000 | LibriTTS_R 一部、60K 件制限 |
| LibriTTS_R raw | `/data/piper/libritts-r/LibriTTS_R/` | 149,694 | train-clean-100 + train-clean-360 |

### 学習済み/学習中モデル

| 用途 | パス | 状態 |
|------|------|------|
| **バイリンガル JA+EN v4** | `/data/piper/output-bilingual-ja-en-v4/bilingual-ja-en-v4-150epoch.onnx` | ✅ 150 epoch完了・ONNX変換済み (75MB, 2026-03-04) — EMA適用済み、JA/EN/混合テスト成功 |
| **つくよみちゃん v4 freeze-dp** | `/data/piper/output-tsukuyomi-finetune-v4-freeze-dp/tsukuyomi-v4-freeze-dp.onnx` | ✅ 500 epoch完了・ONNX変換済み (2026-03-04) — --freeze-dp で DP 凍結、音声長 1.11s→1.76s 改善 |
| つくよみちゃん v4ベース finetune (旧) | `/data/piper/output-tsukuyomi-finetune-v4/tsukuyomi-v4.onnx` | ✅ 500 epoch完了 (74MB, 2026-03-04) — DP 崩壊あり (freeze-dp なし) |
| **バイリンガル JA+EN v3** | `/data/piper/output-bilingual-ja-en-v3/bilingual-ja-en-v3-350epoch.onnx` | ✅ 350 epoch完了・ONNX変換済み (76MB, 2026-02-28) — EMA適用済み、JA/EN/混合テスト成功 |
| **つくよみちゃん v3ベース finetune** | `/data/piper/output-tsukuyomi-finetune-v3/tsukuyomi-v3-emb_lang_fixed.onnx` | ✅ 500 epoch完了・ONNX変換済み (2026-02-28) — emb_lang[1] EN初期化修正済み |
| バイリンガル JA+EN v2 | `/data/piper/output-bilingual-ja-en-v2/bilingual-ja-en-v2-200epoch.onnx` | ✅ 200 epoch完了 (74MB, 2026-02-24) — 40話者、EMA適用済み |
| バイリンガル JA+EN (旧データセット) | `/data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx` | ✅ 200 epoch完了 (74MB) — EN比率18%で英語不明瞭 |
| 20話者 v2 JA-only (200epoch) | `/data/piper/output-moe-speech-20speakers-v2/moe-speech-20speakers-v2.onnx` | ✅ 完了 |
| つくよみちゃん | HuggingFace: `ayousanz/piper-plus-tsukuyomi-chan` | ✅ 完了 |

### 便利ツール

| ツール | パス | 用途 |
|--------|------|------|
| `add_prosody_features.py` | `/data/piper/add_prosody_features.py` | 既存データセットにprosody_features追加＋phoneme_ids再生成 |
| `prepare_bilingual_dataset.py` | `/data/piper/prepare_bilingual_dataset.py` | JA+ENバイリンガルデータセット作成（JA padding修正済み） |
| `prepare_libritts_parallel.py` | `/data/piper/prepare_libritts_parallel.py` | LibriTTS-R → LJSpeech形式変換（並列処理） |

**使用例**:
```bash
# prosody_features追加
uv run python /data/piper/add_prosody_features.py \
  --input-dataset /data/piper/dataset-moe-speech-20speakers/dataset.jsonl \
  --output-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --workers 8

# v4 バイリンガルデータセット作成 (LibriTTS-R 310話者、180発話以上/話者、高密度)
# Step 1: LibriTTS-R 全データを LJSpeech 形式に変換
.venv/bin/python prepare_libritts_parallel.py \
  --input-dir /data/piper/libritts-r/LibriTTS_R \
  --output-dir /data/piper/libritts-r/libritts-ljspeech-v4 \
  --max-utterances 200000 --workers 16

# Step 2: バイリンガルデータセット作成
.venv/bin/python prepare_bilingual_dataset.py \
  --ja-dataset /data/piper/dataset-bilingual-ja-en-v3/dataset.jsonl \
  --ja-already-bilingual \
  --en-libritts /data/piper/libritts-r/libritts-ljspeech-v4 \
  --max-en-speakers 1200 \
  --min-en-utterances-per-speaker 180 \
  --output-dir /data/piper/dataset-bilingual-ja-en-v4 \
  --sample-rate 22050 \
  --workers 16 \
  > /data/piper/prepare_v4.log 2>&1

# v3 バイリンガルデータセット作成 (参考: LibriTTS-R 828話者、30発話以上/話者)
/data/piper/.venv/bin/python /data/piper/prepare_bilingual_dataset.py \
  --ja-dataset /data/piper/dataset-bilingual-ja-en-v2/dataset.jsonl \
  --ja-already-bilingual \
  --en-libritts /data/piper/libritts-r/libritts-ljspeech \
  --max-en-speakers 1133 \
  --min-en-utterances-per-speaker 30 \
  --output-dir /data/piper/dataset-bilingual-ja-en-v3 \
  --sample-rate 22050 \
  --workers 16 \
  > /data/piper/prepare_v3_fast.log 2>&1
```

---

## 基本コマンド

### ONNX変換

```bash
# 通常エクスポート（EMA + stochastic、デフォルト推奨）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx

# deterministic（デバッグ用）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-stochastic \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--no-stochastic` | - | deterministic エクスポート（デバッグ用） |
| EMA | 常時有効 | チェックポイントに EMA state があれば自動適用 |

### 推論テスト

```bash
cat /path/to/test.jsonl | \
  CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --output-dir /path/to/output
```

**JSONLフォーマット:**
```json
{"phoneme_ids": [1, 8, 5, 39, ...], "speaker_id": 0, "prosody_features": [{"a1": -2, "a2": 1, "a3": 5}, ...]}
```

---

## トラブルシューティング

### 推論音声が「ピー」音になる

**原因**: Duration Predictorの学習失敗

**対処法**:
1. `--samples-per-speaker` を使用
2. `--disable_auto_lr_scaling` を使用
3. 学習率を下げる（`--base_lr 1e-4`）

### GPUメモリ不足 (OOM)

**対処法**:
1. NCCL環境変数を設定
2. `batch_size` と `samples_per_speaker` を下げる
3. 異なるバッチサイズからのリジュームを避ける

### 学習速度が遅い

**対処法**:
1. ゾンビGPUプロセスを確認: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` でOSプロセスに対応しないPIDがないか確認。`kill -9` で終了したプロセスがGPUメモリを占有し続けることがある
2. `--max-phoneme-ids 400` で長いシーケンスを除外しメモリスパイクを防止
3. `MEMORY_CLEANUP_FREQUENCY` を調整（`lightning.py`、デフォルト: 500）
4. `--val-every-n-epochs 10` でValidation頻度を下げる（デフォルト: 5エポックごと）
5. `--limit-val-batches 20` でValidationバッチ数を削減（デフォルト: 50）

**注意**: WavLM有効時の学習速度は ~0.03 it/s と遅い (WavLM無効時の 3-5倍)。速度を優先する場合は `--no-wavlm` で無効化推奨。マルチGPU環境で `--wavlm-every-n-steps N` (N>1) は使用しないこと。`find_unused_parameters=True` との相互作用でWavLMパラメータ（~94M）の未使用同期が発生し、逆に~3x遅くなる

### GPU が認識されない (CUDA_ERROR_NO_DEVICE)

**症状**: `nvidia-smi` が `Failed to initialize NVML: Unknown Error`、`torch.cuda.is_available()` が `False`、`cuInit()` が 100 (CUDA_ERROR_NO_DEVICE) を返す。`/dev/nvidia*` は存在するが `open()` で `EPERM`。

**原因**: Kubernetes Pod のGPUリソース割り当てが切れている。コンテナの cgroup がGPUデバイスへのアクセスをブロックしている。

**対処法**: **Podを再起動する**。再起動後に以下を確認:
```bash
nvidia-smi
/data/piper/.venv/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

**経緯 (2026-02-21):** 学習完了 (02/14) 後にPodが再スケジュールされ、GPUリソースなしで起動した模様。`/dev/nvidia*` ファイルはホストノードからマウントされているが、NVIDIA device plugin によるGPU割り当てがないためアクセス拒否。

### ONNX変換エラー

- `CUDA_VISIBLE_DEVICES=""`でCPUモードを使用

---

## HuggingFaceリソース

| リソース | URL |
|----------|-----|
| つくよみちゃんモデル | `ayousanz/piper-plus-tsukuyomi-chan` |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` |
| ベースモデル | `ayousanz/piper-plus-base` |

---

## 関連PR/Issue

| PR/Issue | 内容 | 状態 |
|----------|------|------|
| PR #218 | CI修正 (ruff lint/format、coverage互換性、テスト graceful skip) | CI PASSED (37/40) |
| PR #212 | WavLM Discriminator追加 | Open |
| PR #210 | Issue #204, #207 実装 | Open |
| Issue #204 | 疑問詞マーカーの拡張 | 実装完了 |
| Issue #207 | 文脈依存N phoneme variants | 実装完了 |
| Issue #198 | WavLM Discriminator | 実装完了 |
| PR #196 | A1/A2/A3 prosody機能 | Merged |
| PR #195 | FP16 Mixed Precision | Merged |
