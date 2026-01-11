# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🟡 現在の状態: WavLM Discriminator学習中（再開待ち）

**ブランチ**: `dev`

### 学習状況 (2026-01-11 更新)

| 項目 | 値 |
|------|-----|
| エポック | **150** / 200 (75%) |
| データセット | `dataset-moe-speech-20speakers-v2` |
| 発話数 | 60,164 |
| 話者数 | 20 |
| 新機能 | WavLM Discriminator (デフォルト有効) |
| 残りエポック | 50 |
| 残り時間 | 約22時間 |
| WandB | https://wandb.ai/yousan/piper-tts/runs/0eftq9nt |

### 中間評価結果 (150 epoch時点)

- **音割れ（クリッピング）発生**: WavLM Discriminatorにより高振幅音声が生成される傾向
- v2モデル（WavLMなし）では発生しない

### 音割れ解決プラン

| 優先度 | オプション | 内容 | 所要時間 |
|-------|-----------|------|---------|
| 1 | **A: 学習継続** | 200epochまで学習継続して改善を確認 | 約22時間 |
| 2 | B: c_wavlm調整 | c_wavlmを下げて再学習（0.5→0.2） | 約90時間 |

**現在のプラン**: まずAを試し、改善しない場合はBを実行

**オプションBの学習コマンド** (必要な場合):
```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --c-wavlm 0.2 \
  --default_root_dir /data/piper/output-moe-speech-20speakers-wavlm-c02
```

### 学習再開コマンド

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-wavlm \
  --resume_from_checkpoint /data/piper/output-moe-speech-20speakers-wavlm/lightning_logs/version_2/checkpoints/last.ckpt
```

### 学習中モデル

```
/data/piper/output-moe-speech-20speakers-wavlm/
├── lightning_logs/version_2/checkpoints/
│   ├── epoch=149-step=257700.ckpt  ← 最新
│   └── last.ckpt  ← リジューム用
├── moe-speech-20speakers-wavlm-150epoch.onnx  ← 中間テスト用
└── (学習完了後に最終ONNX変換予定)
```

### 学習完了後の手順

1. **ONNX変換**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-20speakers-wavlm/lightning_logs/version_2/checkpoints/last.ckpt \
  /data/piper/output-moe-speech-20speakers-wavlm/moe-speech-20speakers-wavlm-200epoch.onnx
```

2. **推論テスト**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-moe-speech-20speakers-wavlm/moe-speech-20speakers-wavlm-200epoch.onnx \
  --config /data/piper/dataset-moe-speech-20speakers-v2/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、今日は良い天気ですね。" \
  --speaker-id 0
```

3. **音割れ確認** - v2モデルと比較して改善されているか確認
   - 改善された場合: WavLMモデルを本番採用
   - 改善しない場合: オプションBを実行（c_wavlm=0.2で再学習）

### 完了済みモデル

```
/data/piper/output-moe-speech-20speakers-v2/
├── lightning_logs/version_0/checkpoints/
│   ├── epoch=199-step=206000.ckpt
│   └── last.ckpt
└── moe-speech-20speakers-v2.onnx  ← 本番用モデル (74MB)
```

### 推論テスト

**方法1: テキスト直接入力（推奨）**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-moe-speech-20speakers-v2/moe-speech-20speakers-v2.onnx \
  --config /data/piper/dataset-moe-speech-20speakers-v2/config.json \
  --output-dir /path/to/output \
  --text "こんにちは、今日は良い天気ですね。" \
  --speaker-id 0
```

**方法2: JSONL入力**
```bash
cat test.jsonl | CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-moe-speech-20speakers-v2/moe-speech-20speakers-v2.onnx \
  --output-dir /path/to/output
```

---

## 実装済み機能

### WavLM Discriminator ✅ NEW (2026-01-08)

Microsoft WavLMベースの知覚品質判別器。音質向上のためデフォルトで有効。

**期待効果:**
- MOS向上: +0.15-0.25
- 推論速度への影響: なし（学習時のみ使用）

**実装ファイル:**
- `src/python/piper_train/vits/models.py` - `WavLMDiscriminator`クラス
- `src/python/piper_train/vits/lightning.py` - 学習ループ統合

**注意:**
- WavLMは学習時のみ使用（推論グラフには含まれない）
- FP16 Mixed Precision対応済み（内部でfloat32変換）
- GPUメモリ追加: 約1-2GB/GPU

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

### SpeakerBalancedBatchSampler ✅

マルチスピーカーモデルのDuration Predictor崩壊問題を解決するカスタムバッチサンプラー。

```bash
--batch-size 32 --samples-per-speaker 4  # 8話者 × 4サンプル = 32
```

### FP16 Mixed Precision ✅

デフォルトで有効（`--precision 16-mixed`）。学習速度2-3倍向上、GPUメモリ約50%削減。

---

## 学習設定

### 推奨設定 (20話者、L4 GPU 16GB × 4、WavLM有効)

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-wavlm
```

**注意:** WavLMはデフォルトで有効。GPUメモリ増加のため`batch-size`を12に削減。

### 話者数別の推奨設定

| 話者数 | batch_size | samples_per_speaker | 実効バッチ | 備考 |
|-------|------------|---------------------|-----------|------|
| 5話者 | 20 | 4 | 20 | ✅ 検証済み |
| **20話者** | **20** | **2** | **40** | **✅ 検証済み** |

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
| 日本語音素化 | `src/python/piper_train/phonemize/japanese.py` |
| IDマップ | `src/python/piper_train/phonemize/jp_id_map.py` |
| トークンマッパー | `src/python/piper_train/phonemize/token_mapper.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |

### データセット

| 用途 | パス | 発話数 | 特徴 |
|------|------|--------|------|
| **20話者 v2** ✅最新 | `/data/piper/dataset-moe-speech-20speakers-v2/` | 60,164 | Issue #204, #207 対応 |
| 20話者 (従来版) | `/data/piper/dataset-moe-speech-20speakers/` | 60,164 | 旧トークン体系 |

### 学習済み/学習中モデル

| 用途 | パス | 状態 |
|------|------|------|
| **20話者 WavLM** | `/data/piper/output-moe-speech-20speakers-wavlm/` | 🟡 学習中 (75%) |
| 20話者 v2 (200epoch) | `/data/piper/output-moe-speech-20speakers-v2/moe-speech-20speakers-v2.onnx` | ✅ 完了 |
| つくよみちゃん | HuggingFace: `ayousanz/piper-plus-tsukuyomi-chan` | ✅ 完了 |

### 便利ツール

| ツール | パス | 用途 |
|--------|------|------|
| `add_prosody_features.py` | `/data/piper/add_prosody_features.py` | 既存データセットにprosody_features追加＋phoneme_ids再生成 |

**使用例**:
```bash
uv run python /data/piper/add_prosody_features.py \
  --input-dataset /data/piper/dataset-moe-speech-20speakers/dataset.jsonl \
  --output-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --workers 8
```

---

## 基本コマンド

### ONNX変換

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx
```

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
| PR #212 | WavLM Discriminator追加 | Open |
| PR #210 | Issue #204, #207 実装 | Open |
| Issue #204 | 疑問詞マーカーの拡張 | 実装完了 |
| Issue #207 | 文脈依存N phoneme variants | 実装完了 |
| Issue #198 | WavLM Discriminator | 実装完了 |
| PR #196 | A1/A2/A3 prosody機能 | Merged |
| PR #195 | FP16 Mixed Precision | Merged |
