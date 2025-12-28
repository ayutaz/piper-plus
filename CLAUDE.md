# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🟢 現在の状態: prosody_features 実装完了

**ブランチ**: `feature/prosody-a-values-utilization`

### 完了した実装

A1/A2/A3プロソディ値をモデル学習・推論で活用する機能を実装完了。

| コンポーネント | ファイル | 変更内容 |
|---------------|---------|---------|
| **Python モデル** | `models.py` | `prosody_proj` レイヤー追加、`forward()`/`infer()` 変更 |
| **Python 学習** | `lightning.py` | `--prosody-dim` 引数追加、学習時に prosody_features を渡す |
| **Python ONNX** | `export_onnx.py` | prosody_features 入力をエクスポート |
| **Python 推論** | `infer_onnx.py` | JSONL から prosody_features 読み込み |
| **C++ 抽出** | `openjtalk_wrapper.c` | Full-context label から A1/A2/A3 抽出 |
| **C++ 音素化** | `openjtalk_phonemize.cpp/hpp` | `phonemize_openjtalk_with_prosody()` 追加 |
| **C++ 推論** | `piper.cpp/hpp` | prosody テンソル追加、`textToAudio()` 対応 |

### 次のステップ

prosody_features 付きデータセットで学習開始：

```bash
NCCL_DEBUG=INFO NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-5speakers-prosody \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 32 --samples-per-speaker 4 \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --default_root_dir /data/piper/output-moe-speech-5speakers-prosody
```

---

## 実装済み機能

### prosody_features (A1/A2/A3) モデル統合 ✅ NEW

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
uv run python -m piper_train.preprocess --use-japanese-prosody ...
```

**後方互換性:** `--prosody-dim 0`（デフォルト）で従来通り動作

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
| `--prosody-dim` | prosody 投影次元 (0で無効) | 0 |

---

## 学習設定

### 推奨学習コマンド（マルチスピーカー + prosody）

```bash
NCCL_DEBUG=INFO NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-5speakers-prosody \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 32 --samples-per-speaker 4 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-5speakers-prosody
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
| 5話者 (prosody付き) ✅ | `/data/piper/dataset-moe-speech-5speakers-prosody/` |
| 5話者 (従来版) | `/data/piper/dataset-moe-speech-5speakers/` |
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

**prosody付きJSONLフォーマット:**
```json
{"phoneme_ids": [...], "speaker_id": 0, "prosody_features": [{"a1": -2, "a2": 1, "a3": 5}, ...]}
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
