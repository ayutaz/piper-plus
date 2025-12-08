# Piper TTS - プロジェクト概要

## プロジェクト説明

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

## 現在の作業状態（2025-12-08）

### ✅ 完了: 5話者マルチスピーカーTTS学習

5話者モデルの学習が完了しました（100/130/200エポック）。**100エポックが最も音質が良い**ことが判明しました（過学習の影響）。

### ✅ 完了: 20話者モデル200エポック学習

**学習完了時刻:** 2025-12-07 19:26
**総学習時間:** 約26時間52分（batch_size=5使用）
**最終チェックポイント:** `epoch=199-step=120400.ckpt` (889MB)
**チェックポイント総数:** 201個（epoch 0-199 + last.ckpt）

### ✅ 完了: ONNX変換・推論テスト

**ONNXモデル:** `/data/piper/output-moe-speech-20speakers/moe-speech-20speakers-200epochs.onnx` (74MB)
**推論音声:** `/home/jovyan/inference_200epoch_test/` (11ファイル)
**テスト話者:** 0, 5, 10, 19
**Real-time Factor:** 0.08-0.19（非常に高速）

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

### 20話者モデル学習（完了済み）
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

### フェーズ2: 20話者モデル（完了）
- [x] 20話者データセット作成（60,233発話、90.6時間）
- [x] 20話者データセットHuggingFaceアップロード
- [x] 20話者前処理完了
- [x] **20話者モデル200エポック学習完了**
- [x] **20話者ONNX変換完了（200エポック）**
- [x] **20話者推論テスト完了（11音声ファイル生成）**
- [ ] 20話者100エポックモデルテスト
- [ ] 100 vs 200エポック音質比較
- [ ] 20話者モデルHuggingFaceアップロード

### フェーズ3: データセット拡張（計画中）
- [x] moe-speechデータセット分析完了
  - 総話者数: 473人
  - 3時間以上話者: 41人（165時間）
- [ ] 41話者データセット作成
- [ ] 41話者モデル学習

---

## 次のステップ

### 推奨アクション（優先順位順）

1. **epoch=100モデルのテスト（推奨）**
   - 5話者モデルでは100エポックが最良だったため
   - `/data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=99-step=60200.ckpt`をONNX変換
   - 推論テストで音質を確認

2. **音質比較**
   - 100エポック vs 200エポックの音声を聴き比べ
   - 各話者の音質を評価
   - ベストモデルを決定

3. **HuggingFaceアップロード**
   - ベストモデル（おそらく100エポック）をアップロード
   - モデルカード作成
   - サンプル音声添付

4. **41話者データセット作成（オプション）**
   - 3時間以上の話者41人を選択
   - データセット作成・前処理
   - 学習実行（165時間、20話者の1.82倍）

### epoch=100テストコマンド

```bash
# ONNX変換
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-20speakers/lightning_logs/version_0/checkpoints/epoch=99-step=60200.ckpt \
  /data/piper/output-moe-speech-20speakers/moe-speech-20speakers-100epochs.onnx

# 推論テスト（話者0）
cat /tmp/test_speaker_0.jsonl | \
  CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model /data/piper/output-moe-speech-20speakers/moe-speech-20speakers-100epochs.onnx \
    --output-dir /home/jovyan/inference_100epoch_test/speaker_0
```

---

## トラブルシューティング

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
