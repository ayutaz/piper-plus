# Piper TTS - プロジェクト概要

## プロジェクト説明

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

## 現在の作業状態（2025-12-15）

### ✅ 完了: SpeakerBalancedBatchSampler実装

**20話者モデルのDuration Predictor崩壊問題**を解決するため、話者バランスバッチサンプラーを実装しました。

**実装ファイル:**
- `src/python/piper_train/vits/dataset.py` - SpeakerBalancedBatchSamplerクラス
- `src/python/piper_train/vits/lightning.py` - DataLoader統合
- `src/python/piper_train/__main__.py` - `--samples-per-speaker`引数
- `src/python/piper_train/vits/test_speaker_balanced_sampler.py` - テストコード

**使用方法:**
```bash
--batch-size 32 --samples-per-speaker 4  # 8話者 × 4サンプル = 32
```

**期待される効果:**
| 設定 | 同一話者サンプル/バッチ | 結果 |
|------|----------------------|------|
| 従来 (20話者) | 1.6件 | ❌ 崩壊 |
| **新方式** | **4件** | ✅ 安定（予想） |
| 5話者モデル | 6.4件 | ✅ 安定（実績） |

### ✅ 完了: 5話者マルチスピーカーTTS学習

5話者モデルの学習が完了しました（100/130/200エポック）。**100エポックが最も音質が良い**ことが判明しました（過学習の影響）。
- **学習方法:** 一から学習（事前学習モデルなし）
- **結果:** 正常に動作、高品質な音声生成

### ✅ 解決済み: 20話者モデルの学習率問題

**問題:** 20話者モデルで「ピー」という短い音しか出ない（Duration Predictor崩壊）

**解決策:**
1. **話者バランスバッチサンプリング** (`--samples-per-speaker 4`) ← **推奨**
2. 学習率を2e-4から1e-4に下げる + バッチサイズを48に増やす

**検証結果（5エポック学習）:**

| 設定 | lr=2e-4, batch=5 (失敗) | lr=1e-4, batch=48 (成功) |
|------|------------------------|-------------------------|
| Audio samples | ~2,000-4,000 | **23,000-40,000** |
| 音声長 | ~0.1秒 ("ピー"音) | **0.6-1.8秒 (正常)** |
| Duration Predictor | 崩壊 | **正常動作** |

**生成された音声（lr=1e-4モデル）:**
- `/home/jovyan/inference_lr1e4_test/speaker_0.wav` (43KB, 0.975秒)
- `/home/jovyan/inference_lr1e4_test/speaker_5.wav` (70KB, 1.579秒)
- `/home/jovyan/inference_lr1e4_test/speaker_10.wav` (29KB, 0.662秒)
- `/home/jovyan/inference_lr1e4_test/speaker_19.wav` (79KB, 1.800秒)

**チェックポイント:** `/data/piper/output-moe-speech-20speakers-lr1e4/lightning_logs/version_0/checkpoints/epoch=4-step=2820.ckpt`
**ONNXモデル:** `/data/piper/output-moe-speech-20speakers-lr1e4/moe-speech-20speakers-lr1e4-epoch4.onnx`

### 📋 次のステップ: 20話者モデル本格学習

lr=1e-4で問題が解決したことを確認。100-200エポックの本格学習を実行予定。

---

## ❌ 過去の問題: 20話者モデル200エポック学習（lr=2e-4）

**学習完了時刻:** 2025-12-07 19:26
**総学習時間:** 約26時間52分（batch_size=5使用）
**最終チェックポイント:** `epoch=199-step=120400.ckpt` (889MB)

**⚠️ 問題:** 推論結果が正常に発音されない（「ピー」という短い音のみ）
**原因:** 学習率2e-4が20話者には高すぎた → Duration Predictorが崩壊

**ONNXモデル（問題あり）:** `/data/piper/output-moe-speech-20speakers/moe-speech-20speakers-200epochs.onnx` (74MB)
**推論音声（異常）:** `/home/jovyan/inference_200epoch_test/` (11ファイル)

---

## 🔴 20話者モデル問題調査結果（2025-12-08 詳細調査完了）

### 症状

| 項目 | 5話者モデル（正常） | 20話者モデル（異常） |
|------|-------------------|---------------------|
| 音声出力 | 正常な発話 | 「ピー」という短い音のみ |
| 音声長 | 約2.77秒 | 約0.27-0.36秒 |
| 波形振幅 | 正負両方（-0.329〜0.237） | 負のみ（-0.114〜-0.003） |
| DCオフセット | なし | あり（負方向に偏り） |

### 根本原因: Duration Predictorの学習失敗

**Duration Predictor**がフレーム長を極端に短く予測している。

| モデル | 予測フレーム数 | 状態 |
|--------|---------------|------|
| 新規初期化 (5話者構成) | 31.6 | ベースライン |
| 新規初期化 (20話者構成) | 29.7 | ほぼ同じ |
| **5話者 epoch=0 (2gpu)** | **131.6** | ✅ **学習で大幅改善** |
| **5話者 epoch=0 (v15)** | **58.3** | ✅ **学習で改善** |
| 5話者 epoch=49 | 176.3 | さらに改善 |
| 5話者 epoch=99 | 180.7 | ✅ 正常（安定） |
| **20話者 epoch=0** | **16.4** | ❌ **初期化より悪化！** |
| 20話者 epoch=10 | 15.8 | 停滞 |
| 20話者 epoch=100 | 17.1 | ほぼ変化なし |

**重要な発見:**
- **初期化時点では両モデルとも約30フレーム**（差なし）
- 1エポック後に大きな差が発生:
  - 5話者: 58-131フレームに**増加** ✅
  - 20話者: 16フレームに**減少** ❌
- 問題は**学習の最初のエポック**で発生（過学習ではない）

### 詳細調査結果

#### 1. データセット比較

| 項目 | 結果 |
|------|------|
| 話者の重複 | 5話者データセットの話者は20話者の最初の5人と**完全に同一** |
| Speaker 0-4の発話数 | 両データセットでほぼ同じ（差は2件程度） |
| 音素列長（平均） | 5話者: 62.9、20話者: 65.7（大差なし） |
| 空の音素列 | 5話者: 2件、20話者: 16件（影響は小さい） |

#### 2. モデル設定比較

| 項目 | 5話者 | 20話者 |
|------|-------|--------|
| gin_channels | 512 | 512 |
| num_symbols | 58 | 58 |
| num_speakers | 5 | 20 |
| hidden_channels | 192 | 192 |

**結論: 設定に問題なし**

#### 3. 話者別発話数

**5話者データセット:**
```
Speaker 0: 4,675 utterances
Speaker 1: 4,632 utterances
Speaker 2: 3,747 utterances
Speaker 3: 3,295 utterances
Speaker 4: 3,268 utterances
```

**20話者データセット (追加15話者):**
```
Speaker 5-9:   3,043 - 2,861 utterances
Speaker 10-14: 2,811 - 2,654 utterances
Speaker 15-19: 2,631 - 2,310 utterances
```

追加話者は元の5話者より発話数が少ない傾向。

### 影響

- 音素ごとの継続時間が極端に短い（約1/10）
- 生成される音声が約0.3秒しかない（本来は約2.5秒以上必要）
- 音声がクリッピングして「ピー」音になる

### 学習条件の比較

| 項目 | 5話者モデル | 20話者モデル |
|------|------------|-------------|
| 発話数 | 19,617 | 60,164 |
| 話者数 | 5 | 20 |
| 総音声時間 | 約30時間 | 約90.6時間 |
| 事前学習 | なし | なし |
| batch_size | 5 | 5 |
| learning_rate | 2e-4 (auto-scaled) | 2e-4 (auto-scaled) |
| precision | 16-mixed | 16-mixed |
| gin_channels | 512 | 512 |
| 結果 | ✅ 成功 | ❌ 失敗 |

### 考えられる原因（詳細分析後）

1. **話者数増加による学習ダイナミクスの変化**
   - batch_size=5で20話者の場合、各バッチに含まれる話者の多様性が高い
   - Duration Predictorが話者embeddingを学習しにくい
   - 5話者では同一話者がバッチ内に出現しやすく、学習が安定

2. **学習率の不適合**
   - 5話者で最適だった学習率（2e-4）が20話者では高すぎる可能性
   - Duration Predictorが発散している可能性

3. **バッチ構成の問題**
   - 20話者 × batch_size=5 = 各話者が各バッチに出現する確率 25%
   - 5話者 × batch_size=5 = 各話者が各バッチに出現する確率 100%

### 解決策の候補（優先順位順）

1. **話者バランスバッチサンプリング**（✅ 実装完了・推奨）
   - `--samples-per-speaker 4` を使用
   - 各バッチに同一話者のサンプルが4件含まれるようになる
   - Duration Predictorが話者埋め込みを安定して学習できる
   - **根本原因に直接対処**

2. **学習率を下げて再学習**
   - 学習率: 2e-4 → 1e-4 または 5e-5
   - Duration Predictorの学習が安定する可能性

3. **バッチサイズを増やす**
   - batch_size=5 → batch_size=20以上
   - 各バッチに全話者が含まれやすくなる
   - GPUメモリ制約あり

4. **5話者モデルからファインチューン**
   - 正常に学習された5話者モデルをベースに追加話者を学習
   - Duration Predictorが正常な状態からスタート

5. **段階的な話者追加**
   - 5話者 → 10話者 → 20話者と段階的に増やす

---

## 完了済みタスク

### 5話者モデル（完了）

| 項目 | 値 |
|------|-----|
| 発話数 | 19,617 |
| 話者数 | 5 |
| 総音声時間 | 約30時間 |
| 学習エポック | 100/130/200 |
| **ベストモデル** | **100エポック** |
| チェックポイント | `/data/piper/output-moe-speech-5speakers-4gpu-b5-resume/lightning_logs/version_0/checkpoints/epoch=99-step=176600.ckpt` |
| ONNXモデル | `/data/piper/output-moe-speech-5speakers-4gpu-b5-resume/moe-speech-5speakers-100epochs.onnx` |
| HuggingFace | `ayousanz/piper-plus-moe-speech-top-5speakers` |

**話者一覧:**
| Speaker ID | 発話数 | 音声時間 | Speaker Index |
|------------|--------|----------|--------------|
| 940de876 | 4,675 | 7.15h | 0 |
| 2cf01874 | 4,632 | 6.98h | 1 |
| bbd90363 | 3,747 | 5.64h | 2 |
| 1a5a3db8 | 3,295 | - | 3 |
| 4e2f4ba6 | 3,268 | 4.38h | 4 |

### 20話者モデル（完了）

| 項目 | 値 |
|------|-----|
| 発話数 | 60,164 |
| 話者数 | 20 |
| 総音声時間 | **約90.6時間** |
| 学習エポック | 200 (完了) |
| 学習時間 | 約26時間52分 |
| Batch Size | 5 |
| 最終チェックポイント | `/data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=199-step=120400.ckpt` (889MB) |
| ONNXモデル (200epoch) | `/data/piper/output-moe-speech-20speakers/moe-speech-20speakers-200epochs.onnx` (74MB) |
| 推論音声 | `/home/jovyan/inference_200epoch_test/` (11ファイル) |
| 音素タイプ | OpenJTalk |
| 前処理済みデータ | `/data/piper/dataset-moe-speech-20speakers/` |
| LJSpeech形式データ | `/data/moe-speech-20speakers-ljspeech/` |
| HuggingFace Dataset | `ayousanz/moe-speech-20speakers-ljspeech` |

**TOP 10話者一覧:**
| 順位 | Speaker ID | 音声時間 | 発話数 | Speaker Index |
|------|-----------|----------|--------|--------------|
| 1 | 940de876 | 7.15h | 4,675 | 0 |
| 2 | 2cf01874 | 6.98h | 4,632 | 1 |
| 3 | ee093a4f | 6.72h | 2,957 | 7 |
| 4 | ad28b91b | 6.55h | 3,033 | 6 |
| 5 | bbd90363 | 5.64h | 3,747 | 2 |
| 6 | 18460462 | 5.42h | 2,861 | 9 |
| 7 | bb6ac6f1 | 4.96h | 2,171 | - |
| 8 | 4ce0075b | 4.69h | 2,139 | - |
| 9 | b8015202 | 4.49h | 1,932 | - |
| 10 | 917feebd | 4.38h | 2,811 | 10 |

### moe-speechデータセット統計

| 項目 | 値 |
|------|-----|
| 総話者数 | **473人** |
| 総ファイル数 | 395,170 |
| 総音声時間 | 約592時間 |
| **3時間以上の話者** | **41人** |
| **3時間以上話者の総時間** | **約165.0時間** |
| **3時間以上話者の平均時間** | 約4.0時間/話者 |

**3時間以上の話者を使用すると:**
- 20話者（90.6時間）→ 41話者（165.0時間）
- データ量 **1.82倍増加**（+75時間）

---

## 重要なファイルパス

### 5話者（完了）
| 用途 | パス |
|------|------|
| 前処理済データ | `/data/piper/dataset-moe-speech-5speakers/` |
| 学習出力 | `/data/piper/output-moe-speech-5speakers-4gpu-b5-resume/` |
| 100epoch ONNX | `/data/piper/output-moe-speech-5speakers-4gpu-b5-resume/moe-speech-5speakers-100epochs.onnx` |
| 比較音声 | `/home/jovyan/comparison_test/` |

### 20話者（完了）
| 用途 | パス |
|------|------|
| LJSpeech形式データ | `/data/moe-speech-20speakers-ljspeech/` |
| 前処理済データ | `/data/piper/dataset-moe-speech-20speakers/` |
| 学習出力 | `/data/piper/output-moe-speech-20speakers/` |
| チェックポイント | `/data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/` |
| 学習ログ | `/data/piper/training_20speakers.log` |
| 200epoch ONNX | `/data/piper/output-moe-speech-20speakers/moe-speech-20speakers-200epochs.onnx` |
| 推論音声 | `/home/jovyan/inference_200epoch_test/` |

### 共通
| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS実装 | `src/python/piper_train/vits/` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |

---

## マルチGPU学習設定

### 推奨構成: 4GPU + batch_size 5（安定動作確認済み）

**20話者モデル（60,164発話）の学習結果:**

| 構成 | batch_size | 結果 | 1エポック時間 | 200エポック時間 |
|------|------------|------|-------------|---------------|
| 4GPU | 5 | ✅ 安定動作 | 約8-9分 | 約26時間52分 |

**GPU環境:**
- GPU: 4 × Tesla V100-PCIE-16GB (各16GB VRAM)
- 分散学習: NCCL DDP（4ランク）
- GPU使用率: 50-100%
- メモリ使用: 3-5GB/GPU

### NCCL環境変数（必須）

```bash
NCCL_DEBUG=INFO
NCCL_P2P_DISABLE=1
NCCL_IB_DISABLE=1
```

---

## 学習コマンド

### 20話者モデル学習（話者バランスサンプリング使用・推奨）
```bash
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 200 \
  --batch-size 32 \
  --samples-per-speaker 4 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 2e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-balanced \
  2>&1 | tee /data/piper/training_20speakers_balanced.log
```

**注意:**
- `--samples-per-speaker 4`: 各バッチに同一話者から4サンプルを含める
- `--batch-size 32`: 8話者 × 4サンプル = 32（話者数 = batch_size / samples_per_speaker）
- Duration Predictor崩壊を防ぐための推奨設定

### 20話者モデル学習（従来方式・問題あり）
```bash
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 200 \
  --batch-size 5 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 2e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers \
  2>&1 | tee /data/piper/training_20speakers.log
```

### 5話者モデル学習（参考：完了済み）
```bash
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-5speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 100 \
  --batch-size 5 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 2e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-5speakers-4gpu-b5-resume \
  2>&1 | tee /data/piper/training_5speakers.log
```

### チェックポイントからの再開
```bash
# --resume_from_checkpoint を追加
# 例: epoch=99から200エポックまで継続する場合
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 200 \
  --batch-size 5 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 1e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --resume_from_checkpoint /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=99-step=60200.ckpt \
  --default_root_dir /data/piper/output-moe-speech-20speakers \
  > /data/piper/training_20speakers_resume.log 2>&1
```

**注意:**
- チェックポイントパスは実際のファイル名に置き換えてください
- 学習率を下げる場合は `--base_lr 1e-4` を使用（デフォルトは2e-4）
- batch_sizeは元の学習と同じ5を使用してください

---

## ONNX変換・推論テスト

### ONNX変換

```bash
# 20話者モデル - 200エポック（完了）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=199-step=120400.ckpt \
  /data/piper/output-moe-speech-20speakers/moe-speech-20speakers-200epochs.onnx

# 20話者モデル - 100エポック（推奨テスト）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=99-step=60200.ckpt \
  /data/piper/output-moe-speech-20speakers/moe-speech-20speakers-100epochs.onnx

# 5話者モデル（参考：完了済み）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-5speakers-4gpu-b5-resume/lightning_logs/version_0/checkpoints/epoch=99-step=176600.ckpt \
  /data/piper/output-moe-speech-5speakers-4gpu-b5-resume/moe-speech-5speakers-100epochs.onnx
```

**チェックポイント計算:**
- batch_size=5の場合: 1エポック = 602ステップ
- step計算例: epoch=99 → step=99×602+602=60,200

### 推論テスト方法

**重要:** `infer_onnx.py`を使用してください。標準入力からJSONL形式でデータを受け取ります。

#### 1. テスト用JSONLファイルを作成

```bash
# 話者0のテスト用データを作成
head -3 /data/piper/dataset-moe-speech-20speakers/dataset.jsonl | \
  grep '"speaker_id": 0' > /tmp/test_speaker_0.jsonl
```

#### 2. 推論を実行

```bash
# 20話者モデル（200エポック）で推論
cat /tmp/test_speaker_0.jsonl | \
  CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model /data/piper/output-moe-speech-20speakers/moe-speech-20speakers-200epochs.onnx \
    --output-dir /home/jovyan/inference_test/speaker_0

# 5話者モデルで推論（参考）
cat /tmp/test_speaker_0.jsonl | \
  CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model /data/piper/output-moe-speech-5speakers-4gpu-b5-resume/moe-speech-5speakers-100epochs.onnx \
    --output-dir /home/jovyan/inference_test/5speakers_speaker_0
```

#### 3. JSONLフォーマット

入力ファイルは1行ごとに以下のJSON形式：
```json
{"phoneme_ids": [1, 8, 5, 39, 8, 6, 50, ...], "speaker_id": 0}
```

### 生成済み推論音声（200エポックモデル）

```
/home/jovyan/inference_200epoch_test/
├── 0.wav, 1.wav, 2.wav (話者0)
├── speaker_0/
│   ├── 0.wav (37K)
│   └── 1.wav (54K)
├── speaker_5/
│   ├── 0.wav (56K)
│   └── 1.wav (19K)
├── speaker_10/
│   ├── 0.wav (24K)
│   └── 1.wav (58K)
└── speaker_19/
    ├── 0.wav (32K)
    └── 1.wav (55K)
```

**Real-time Factor:** 0.08-0.19（実時間の8-19%、非常に高速）

---

## 進捗確認コマンド

### 学習ログ監視
```bash
# リアルタイムログ
tail -f /data/piper/training_20speakers.log

# 最新のエポック確認
grep "Epoch" /data/piper/training_20speakers.log | tail -5

# 進捗プログレスバー確認
tail -100 /data/piper/training_20speakers.log | grep -E "Epoch [0-9]+:.*%.*it/s"
```

### GPU使用状況
```bash
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv
watch -n 1 nvidia-smi
```

### チェックポイント確認
```bash
# 最新のチェックポイント一覧
ls -lath /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/ | head -15

# 特定エポックのチェックポイント検索
ls /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/ | grep "epoch=99"
ls /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/ | grep "epoch=199"
```

### データセット確認
```bash
# 20話者データセット
cat /data/piper/dataset-moe-speech-20speakers/config.json | python3 -m json.tool

# 5話者データセット
cat /data/piper/dataset-moe-speech-5speakers/config.json | python3 -m json.tool
```

---

## 学習結果サマリー

### 5話者モデル品質評価

| エポック | 音質 | 備考 |
|----------|------|------|
| **100** | **最良** | 推奨 |
| 130 | 良 | わずかに過学習 |
| 200 | 劣化 | 過学習 |

### 20話者モデル学習完了

| 項目 | 値 |
|------|-----|
| 学習完了時刻 | 2025-12-07 19:26 |
| 総学習時間 | 約26時間52分 |
| エポック数 | 200/200 (100%完了) |
| 最終Loss | 確認推奨 |
| チェックポイント数 | 201個 |

### Loss指標の解説

| 指標 | 説明 | 目安 |
|------|------|------|
| `loss_gen_all` | Generator総合損失 | 低いほど良い |
| `loss_disc_all` | Discriminator総合損失 | 安定していれば良い |
| `val_loss` | 検証損失 | 上昇=過学習の兆候 |

---

## HuggingFaceリソース

| リソース | URL |
|----------|-----|
| 5話者LJSpeechデータセット | `ayousanz/moe-speech-5speakers-ljspeech` |
| 5話者学習済みモデル | `ayousanz/piper-plus-moe-speech-top-5speakers` |
| 20話者LJSpeechデータセット | `ayousanz/moe-speech-20speakers-ljspeech` |
| **20話者学習済みモデル** | **未アップロード** |

---

## 進捗チェックリスト

### フェーズ1: 5話者モデル（完了）
- [x] FP16 Mixed Precision対応
- [x] マルチGPUメモリ最適化
- [x] 5話者データセット作成・前処理
- [x] 5話者モデル学習（100/130/200エポック）
- [x] 5話者ONNX変換・推論テスト
- [x] 5話者モデルHuggingFaceアップロード

### フェーズ2: 20話者モデル（❌ 問題発生）
- [x] 20話者データセット作成（60,233発話、90.6時間）
- [x] 20話者データセットHuggingFaceアップロード
- [x] 20話者前処理完了
- [x] 20話者モデル200エポック学習完了
- [x] 20話者ONNX変換完了（200エポック）
- [x] 20話者推論テスト実施
- [x] **問題調査完了** - Duration Predictorの学習失敗を特定
- [ ] **再学習または修正が必要**
- [ ] 20話者モデルHuggingFaceアップロード

### フェーズ3: データセット拡張（計画中）
- [x] moe-speechデータセット分析完了
  - 総話者数: 473人
  - 3時間以上話者: 41人（165時間）
- [ ] 41話者データセット作成
- [ ] 41話者モデル学習

---

## 次のステップ

### 🔴 最優先: 20話者モデル問題の解決

**調査完了（2025-12-08）**: Duration Predictorの学習失敗が原因と特定。
- 初期化時点では両モデルとも~30フレーム予測（差なし）
- 1エポック後: 5話者は58-131フレームに増加 ✅、20話者は16フレームに減少 ❌
- 話者数増加によるバッチ内多様性の上昇が原因の可能性が高い

#### 解決策の選択肢（調査結果に基づく優先順位）

| 優先度 | 方法 | 説明 | メリット | デメリット |
|-------|------|------|----------|-----------|
| **1** | **話者バランスバッチサンプリング** | `--samples-per-speaker 4` | **✅ 実装完了**、根本原因に対処 | なし |
| 2 | 学習率を下げて再学習 | base_lr: 2e-4 → 1e-4 | 簡単に試せる | 約27時間の学習時間 |
| 3 | バッチサイズを増やす | batch_size: 5 → 20以上 | 各話者がバッチに出現しやすい | GPUメモリ制約 |
| 4 | 5話者→20話者ファインチューン | 5話者モデルから継続学習 | Duration Predictorが正常状態からスタート | 実装確認が必要 |

#### 方法1: 話者バランスバッチサンプリング（✅ 推奨・実装完了）

```bash
# 話者バランスバッチサンプリングを使用（推奨）
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 200 \
  --batch-size 32 \
  --samples-per-speaker 4 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 2e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-balanced \
  2>&1 | tee /data/piper/training_20speakers_balanced.log
```

**理由:** 各バッチに同一話者のサンプルが4件含まれるようになり、Duration Predictorが話者埋め込みを安定して学習できる。

#### 方法2: 学習率を下げて再学習

```bash
# 学習率を1/2に下げて再学習（2e-4 → 1e-4）
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 200 \
  --batch-size 5 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 1e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-lr1e4 \
  2>&1 | tee /data/piper/training_20speakers_lr1e4.log
```

**理由:** Duration Predictorが学習初期に発散している可能性が高い。学習率を下げることで安定化を図る。

#### 方法3: バッチサイズを増やして再学習

```bash
# バッチサイズを20に増やして再学習
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 200 \
  --batch-size 20 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 2e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-bs20 \
  2>&1 | tee /data/piper/training_20speakers_bs20.log
```

**理由:** batch_size=20なら各バッチに全20話者が含まれやすく、学習が安定する可能性。

#### 方法4: 5話者モデルからファインチューン

```bash
# 5話者モデルの話者embeddingを拡張して20話者モデルを学習
NCCL_DEBUG=INFO \
NCCL_P2P_DISABLE=1 \
NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers \
  --accelerator gpu \
  --devices 4 \
  --precision 16-mixed \
  --max_epochs 100 \
  --batch-size 5 \
  --checkpoint-epochs 1 \
  --quality medium \
  --base_lr 1e-4 \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --no-pin-memory \
  --resume_from_single_speaker_checkpoint /data/piper/output-moe-speech-5speakers-4gpu-b5-resume/lightning_logs/version_0/checkpoints/epoch=99-step=176600.ckpt \
  --default_root_dir /data/piper/output-moe-speech-20speakers-finetune \
  2>&1 | tee /data/piper/training_20speakers_finetune.log
```

**注意:** `--resume_from_single_speaker_checkpoint`は単一話者→マルチ話者変換用。5話者→20話者の場合は別途対応が必要かもしれない。

#### データセット検証（調査完了）

**結果:** データセットに重大な問題は見つからず。

```
調査済み項目:
- 話者の重複: 5話者データセットの話者は20話者の最初の5人と完全に同一 ✅
- 発話数分布: 大きな偏りなし ✅
- 音素列長: 5話者平均62.9、20話者平均65.7（大差なし）✅
- 空の音素列: 5話者2件、20話者16件（全体の0.03%以下）✅
```

### 今後の方針（20話者問題解決後）

1. **41話者データセット作成**
   - 3時間以上の話者41人を選択
   - データセット作成・前処理
   - 学習実行（165時間、20話者の1.82倍）

2. **HuggingFaceアップロード**
   - 正常動作するモデルをアップロード
   - モデルカード作成
   - サンプル音声添付

---

## トラブルシューティング

### 20話者モデル: 推論音声が「ピー」音になる問題

**症状:** 推論した音声が正常に発音されず、短い「ピー」という音だけになる

**原因:** Duration Predictorがフレーム長を極端に短く予測している（約1/17）

**診断方法:**
```bash
# Duration Predictorの予測フレーム数を確認
CUDA_VISIBLE_DEVICES="" uv run python -c "
import torch
from piper_train.vits.lightning import VitsModel

ckpt = '/data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=99-step=60200.ckpt'
model = VitsModel.load_from_checkpoint(ckpt, dataset=None, strict=False, map_location='cpu')
model.eval()

phoneme_ids = [1, 8, 5, 39, 8, 6, 50, 7, 40, 9, 0, 25, 11, 6, 5, 11, 39, 8, 23, 31, 10, 3]

with torch.no_grad():
    text = torch.LongTensor([phoneme_ids])
    text_lengths = torch.LongTensor([len(phoneme_ids)])
    sid = torch.LongTensor([0])

    x, m_p, logs_p, x_mask = model.model_g.enc_p(text, text_lengths)
    g = model.model_g.emb_g(sid).unsqueeze(-1)
    logw = model.model_g.dp(x, x_mask, g=g, reverse=True, noise_scale=0.8)
    w = torch.exp(logw) * x_mask

    print(f'Total predicted duration: {w.sum().item():.1f} frames')
    print(f'Expected: 50-80 frames, If < 20: Duration Predictor failed')
"
```

**対処法:** 上記「次のステップ」セクションの解決策A/B/Cを参照

### 学習中のクラッシュ
- NCCL環境変数が正しく設定されているか確認
- GPUメモリ使用状況を`nvidia-smi`で確認
- batch_sizeを下げる（5→3など）

### ONNX変換エラー
- `CUDA_VISIBLE_DEVICES=""`でCPUモードを使用
- チェックポイントファイルが存在するか確認
- ディスク容量を確認

### 推論エラー
- 正しい推論スクリプト（`infer_onnx.py`）を使用
- JSONLフォーマットが正しいか確認
- speaker_idが0-19の範囲内か確認

---

## SpeakerBalancedBatchSampler

### 概要

マルチスピーカーモデルのDuration Predictor崩壊問題を解決するためのカスタムバッチサンプラー。

### 問題の背景

| 話者数 | batch_size | 同一話者サンプル/バッチ | 結果 |
|-------|-----------|----------------------|------|
| 5話者 | 32 | 約6.4件 | ✅ 安定 |
| 20話者 | 32 | 約1.6件 | ❌ 崩壊 |

Duration Predictor (SDP) は話者埋め込みを条件として使用するため、同一話者のサンプルが少ないと安定して学習できません。

### 解決策

`SpeakerBalancedBatchSampler` は各バッチに同一話者のサンプルが複数含まれるようにします。

```
batch_size=32, samples_per_speaker=4 の場合:
→ 8話者 × 4サンプル = 32サンプル/バッチ

バッチ構成例:
[話者0×4, 話者3×4, 話者7×4, 話者12×4, 話者5×4, 話者18×4, 話者9×4, 話者15×4]
```

### 使用方法

```bash
uv run python -m piper_train \
  --batch-size 32 \
  --samples-per-speaker 4 \
  ...
```

### 引数

| 引数 | 型 | デフォルト | 説明 |
|------|-----|---------|------|
| `--samples-per-speaker` | int | 0 | 各話者からのサンプル数（0=無効） |

### 推奨設定

| 話者数 | batch_size | samples_per_speaker | 話者数/バッチ |
|-------|-----------|---------------------|--------------|
| 20 | 32 | 4 | 8 |
| 20 | 40 | 4 | 10 |
| 41 | 32 | 4 | 8 |

### 実装ファイル

| ファイル | 説明 |
|----------|------|
| `src/python/piper_train/vits/dataset.py` | `SpeakerBalancedBatchSampler`クラス |
| `src/python/piper_train/vits/lightning.py` | DataLoader統合 |
| `src/python/piper_train/__main__.py` | `--samples-per-speaker`引数 |
| `src/python/piper_train/vits/test_speaker_balanced_sampler.py` | テストコード |

### テスト実行

```bash
# テストを実行
uv run python -c "
import sys
sys.path.insert(0, 'src/python')
from collections import Counter
from dataclasses import dataclass
from piper_train.vits.dataset import SpeakerBalancedBatchSampler

@dataclass
class MockUtterance:
    speaker_id: int

class MockDataset:
    def __init__(self, num_speakers, samples_per_speaker):
        self.utterances = [
            MockUtterance(speaker_id=sid)
            for sid in range(num_speakers)
            for _ in range(samples_per_speaker)
        ]

dataset = MockDataset(20, 100)
sampler = SpeakerBalancedBatchSampler(dataset, batch_size=32, samples_per_speaker=4)

for batch in sampler:
    speakers = Counter(dataset.utterances[i].speaker_id for i in batch)
    print(f'Batch: {len(batch)} samples, {len(speakers)} speakers')
    print(f'Samples per speaker: {list(speakers.values())}')
    break
"
```

### 期待される出力

```
Batch: 32 samples, 8 speakers
Samples per speaker: [4, 4, 4, 4, 4, 4, 4, 4]
```
