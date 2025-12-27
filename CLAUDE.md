# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🔴 現在の作業: A1/A2/A3プロソディ値の活用実装

**ブランチ**: `feature/prosody-a-values-utilization`

### 背景

OpenJTalkから抽出されるA1/A2/A3値は現在、記号（`[`, `]`, `#`）挿入の判定にのみ使用され、**数値自体は廃棄されている**。

```python
# japanese.py:118-140 の現状
a1 = int(m_a1.group(1))  # アクセント核の有無 (0/1) → 廃棄
a2 = int(m_a2.group(1))  # モーラ位置 (1-based) → 廃棄
a3 = int(m_a3.group(1))  # 句内モーラ総数 → 廃棄
```

### A1/A2/A3の意味と活用方法

| フィールド | 意味 | 値の例 | 活用方法 |
|-----------|------|--------|---------|
| A1 | アクセント核からの相対位置 | -4, -3, ..., 0, 1, ... | アクセント位置の明示的特徴 |
| A2 | アクセント句内のモーラ位置 | 1, 2, 3, ... | 位置に応じた継続時間予測 |
| A3 | アクセント句内の総モーラ数 | 1-10+ | フレーズ長を考慮した生成 |

### Expected Benefits
- Duration Predictorの学習安定化
- 位置に応じた自然な継続時間生成
- アクセント制御の精度向上

### 実装ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/phonemize/japanese.py` | A1/A2/A3値を返却 |
| `src/python/piper_train/preprocess.py` | prosody_ids生成 |
| `src/python/piper_train/phonemize/jp_id_map.py` | IDマッピング追加 |

---

## 実装済み機能

### SpeakerBalancedBatchSampler

マルチスピーカーモデルのDuration Predictor崩壊問題を解決するカスタムバッチサンプラー。

```bash
--batch-size 32 --samples-per-speaker 4  # 8話者 × 4サンプル = 32
```

**実装ファイル:**
- `src/python/piper_train/vits/dataset.py` - SpeakerBalancedBatchSamplerクラス
- `src/python/piper_train/vits/lightning.py` - DataLoader統合
- `src/python/piper_train/__main__.py` - `--samples-per-speaker`引数

### FP16 Mixed Precision

デフォルトで有効（`--precision 16-mixed`）。学習速度2-3倍向上、GPUメモリ約50%削減。

### 学習率スケーリング制御

**推奨**: マルチスピーカーモデルでは自動スケーリングを無効化

```bash
--base_lr 2e-4 --disable_auto_lr_scaling
```

| 引数 | 説明 | デフォルト |
|------|------|---------|
| `--base_lr` | ベース学習率 | 2e-4 |
| `--disable_auto_lr_scaling` | 自動スケーリング無効 | False |

---

## 学習設定

### 推奨学習コマンド（マルチスピーカー）

```bash
NCCL_DEBUG=INFO NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 32 --samples-per-speaker 4 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /path/to/output
```

### NCCL環境変数（マルチGPU必須）

```bash
NCCL_DEBUG=INFO
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
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |

### データセット

| 用途 | パス |
|------|------|
| 5話者データセット | `/data/piper/dataset-moe-speech-5speakers/` |
| 20話者データセット | `/data/piper/dataset-moe-speech-20speakers/` |

### 学習済みモデル

| 用途 | パス |
|------|------|
| 5話者ONNX (100epoch) | `/data/piper/output-moe-speech-5speakers-4gpu-b5-resume/moe-speech-5speakers-100epochs.onnx` |

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
{"phoneme_ids": [1, 8, 5, 39, ...], "speaker_id": 0}
```

---

## トラブルシューティング

### 推論音声が「ピー」音になる

**原因**: Duration Predictorの学習失敗（フレーム長を極端に短く予測）

**対処法**:
1. `--samples-per-speaker 4` を使用
2. `--disable_auto_lr_scaling` を使用
3. 学習率を下げる（`--base_lr 1e-4`）

### 学習中のクラッシュ

- NCCL環境変数が正しく設定されているか確認
- GPUメモリ使用状況を`nvidia-smi`で確認
- batch_sizeを下げる

### ONNX変換エラー

- `CUDA_VISIBLE_DEVICES=""`でCPUモードを使用
- チェックポイントファイルが存在するか確認

---

## HuggingFaceリソース

| リソース | URL |
|----------|-----|
| 5話者モデル | `ayousanz/piper-plus-moe-speech-top-5speakers` |
| 5話者データセット | `ayousanz/moe-speech-5speakers-ljspeech` |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` |
| ベースモデル | `ayousanz/piper-plus-base` |
| つくよみちゃんモデル | `ayousanz/piper-plus-tsukuyomi-chan` |
