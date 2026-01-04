# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🟡 現在の状態: 20話者 Prosody モデル学習中

**ブランチ**: `feature/prosody-a-values-utilization`

### 学習進捗 (2024-12-30 更新) - 環境切り替えのため一時停止

| 項目 | 値 |
|------|-----|
| 停止時エポック | **57** / 200 |
| 進捗率 | **28.5%** |
| 残りエポック | 143 |
| 速度 | ~0.79-0.82 it/s (520 steps/epoch) |
| GPUメモリ | ~3.3GB / 16GB (L4 × 4) |
| wandb | https://wandb.ai/yousan/piper-tts/runs/knr0xuab |

### 再開方法

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-prosody \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-prosody \
  --resume-from-checkpoint /data/piper/output-moe-speech-20speakers-prosody/lightning_logs/version_1/checkpoints/last.ckpt
```

**チェックポイント位置**: `/data/piper/output-moe-speech-20speakers-prosody/lightning_logs/version_1/checkpoints/`
- `last.ckpt` (最新 = epoch 57)
- `epoch=57-step=60320.ckpt` (epoch 57完了時点)
- 全58個のチェックポイント保存済み (epoch 0-57)

### 学習設定

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-prosody \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-20speakers-prosody
```

**注意**: 当初 `--batch-size 40` で開始したがOOMで失敗。`--batch-size 20` に変更して安定。

### 学習完了後の次ステップ

1. **ONNX変換**:
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-20speakers-prosody/lightning_logs/version_1/checkpoints/epoch=199-step=XXXXX.ckpt \
  /data/piper/output-moe-speech-20speakers-prosody/moe-speech-20speakers-prosody.onnx
```

2. **推論テスト**:
```bash
cat test.jsonl | CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-moe-speech-20speakers-prosody/moe-speech-20speakers-prosody.onnx \
  --output-dir /data/piper/inference-test-20speakers-prosody \
  --noise-scale 0.3 --noise-scale-w 0.5
```

---

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
# 日本語(openjtalk)では prosody_features がデフォルトで抽出される
uv run python -m piper_train.preprocess --language ja --phoneme-type openjtalk ...

# 高速版: 既存データセットに prosody_features を追加
uv run python /data/piper/add_prosody_features.py --input-dataset ... --output-dir ...
```

**デフォルト有効:** prosodyはデフォルトで有効（`--prosody-dim 16`）

**🔧 2026-01-03 修正: prosody_features データ型をint64に統一（commit 812016a）**

**問題:** commit 3340825でfloat32に変更後、ONNX推論で不自然な音声が生成される

**根本原因:**
- **float32入力**: `.float()`がno-opとなり、ONNXグラフにCastノードが含まれない/最適化される
- **int64入力**: `.float()`が明示的なCastノードを生成し、正しい動作
- グラフ構造の違いがDuration Predictorの数値計算に影響
- A1/A2/A3は本来整数値なので、**int64が意味論的に正しい型**

**models.py Line 654 の `.float()` 呼び出しが重要:**
```python
prosody_proj = self.prosody_proj(prosody_features.float())
```
- **int64でexport**: `[int64 input] → [Cast to float32] → [Linear layer]` (正常)
- **float32でexport**: `[float32 input] → [Linear layer]` (Castがno-op、異常)

**修正内容（commit 812016a）:**
1. `export_onnx.py`: prosody_features を `torch.long` (int64) でエクスポート
2. `infer_onnx.py`: prosody_features を `np.int64` で渡す
3. `test_pytorch_onnx_parity.py`: テストをint64に更新
4. `piper.cpp`: C++推論をint64に統一
5. `conftest.py`: テストfixtureをint64に更新

**検証結果:**
- 長文3種類（10-14秒）でテスト
- PyTorch推論: 625KB/607KB/544KB（全て自然 ✅）
- ONNX float32: 563KB/548KB/565KB（全て不自然 ❌）
- ONNX int64（修正後）: 615KB/621KB/585KB（PyTorchと同等 ✅）
- ユーザー評価: "PyTorchは全て問題なし、int64も問題ないです"
- テスト結果: 7 passed ✅

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
| `--prosody-dim` | prosody 投影次元 | 16 |

---

## 学習設定

### バッチサイズ設定ガイド (L4 GPU 16GB × 4)

SpeakerBalancedBatchSamplerを使用する場合、実効バッチサイズは以下で計算:

```
実効バッチ = min(話者数, batch_size ÷ samples_per_speaker) × samples_per_speaker
```

#### 検証済み設定 (5話者、prosody_dim=16、L4 16GB×4)

| batch_size | samples_per_speaker | 実効バッチ | GPUメモリ | 状態 |
|------------|---------------------|-----------|----------|------|
| 80 | 16 | 80 | ~100% | ❌ OOM |
| 60 | 12 | 60 | ~100% | ❌ OOM |
| 50 | 10 | 50 | ~95% | ❌ 不安定（学習中OOM） |
| 40 | 8 | 40 | ~80% | ❌ 学習中OOM |
| 30 | 6 | 30 | ~55% | ❌ 学習中OOM（長い音声で発生） |
| **20** | **4** | **20** | **~35%** | **✅ 安定** |

#### 推奨設定

**新規学習**: `--batch-size 20 --samples-per-speaker 4`
```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-5speakers-prosody-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 4 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-moe-speech-5speakers-prosody-v2
```

**注意事項**:
- 長い音声サンプルが含まれるデータセットではメモリ使用量が大きく変動
- バッチ30以上は長い音声で突発的にOOMが発生する可能性あり
- 異なるバッチサイズからのリジュームはOOMを引き起こす可能性あり

#### 話者数別の推奨設定 (安定優先)

| 話者数 | batch_size | samples_per_speaker | 実効バッチ | 備考 |
|-------|------------|---------------------|-----------|------|
| 5話者 | 20 | 4 | 20 | ✅ 検証済み |
| 8話者 | 32 | 4 | 32 | 推定 |
| 10話者 | 40 | 4 | 40 | 推定 |
| **20話者** | **20** | **2** | **40** | **✅ 検証済み (batch_size 40はOOM)** |

**20話者での検証結果 (2024-12-29)**:
- `batch_size=40, samples_per_speaker=2` → OOM発生
- `batch_size=20, samples_per_speaker=2` → ✅ 安定 (~3.3GB/16GB)

※ 長い音声が多いデータセットでは実効バッチを下げることを推奨

### NCCL環境変数（マルチGPU必須）

```bash
NCCL_DEBUG=WARN  # INFO だとログが多すぎる
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

| 用途 | パス | 発話数 |
|------|------|--------|
| **20話者 (prosody付き)** 🔥学習中 | `/data/piper/dataset-moe-speech-20speakers-prosody/` | 60,164 |
| 20話者 (従来版) | `/data/piper/dataset-moe-speech-20speakers/` | 60,164 |
| 5話者 (prosody付き) | `/data/piper/dataset-moe-speech-5speakers-prosody/` | - |
| 5話者 (従来版) | `/data/piper/dataset-moe-speech-5speakers/` | - |

### 学習済みモデル

| 用途 | パス | 状態 |
|------|------|------|
| **20話者prosody (200epoch)** | `/data/piper/output-moe-speech-20speakers-prosody/` | 🔥 学習中 (Epoch 24/200) |
| 5話者ONNX (100epoch) | `/data/piper/output-moe-speech-5speakers-4gpu-b5-resume/moe-speech-5speakers-100epochs.onnx` | ✅ 完了 |

### 便利ツール

| ツール | パス | 用途 |
|--------|------|------|
| `add_prosody_features.py` | `/data/piper/add_prosody_features.py` | 既存データセットにprosody_features追加（高速） |

**使用例**:
```bash
uv run python /data/piper/add_prosody_features.py \
  --input-dataset /data/piper/dataset-moe-speech-20speakers/dataset.jsonl \
  --output-dir /data/piper/dataset-moe-speech-20speakers-prosody \
  --workers 8
```

- 音声処理をスキップし、phonemize_japanese_with_prosodyのみ実行
- 60,164発話を約6秒で処理（通常の前処理は数時間）
- cacheディレクトリを自動シンボリックリンク

---

## 学習モニタリング

### 現在の学習を確認

```bash
# バックグラウンドタスクの出力確認
tail -50 /tmp/claude/-data-piper/tasks/b36635c.output

# GPUメモリ確認
nvidia-smi

# wandbでリアルタイム確認
# https://wandb.ai/yousan/piper-tts/runs/knr0xuab
```

### チェックポイント確認

```bash
ls -la /data/piper/output-moe-speech-20speakers-prosody/lightning_logs/version_1/checkpoints/
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

### 学習中のクラッシュ (SIGSEGV)

**原因**: `monotonic_align.maximum_path` が大きな行列でスタックオーバーフロー

**対処法**: PR #196 で修正済み。大きなバッチ/長い音声はチャンク処理で自動分割。

**修正ファイル**: `src/python/piper_train/vits/monotonic_align/__init__.py`

```python
# 行列サイズ閾値: 500,000 (約700x700) 以上で1サンプルずつ処理
_LARGE_MATRIX_THRESHOLD = 500000
```

### GPUメモリ不足 (OOM)

**対処法**:
1. NCCL環境変数が正しく設定されているか確認
2. GPUメモリ使用状況を`nvidia-smi`で確認
3. `batch_size` と `samples_per_speaker` を下げる
4. 異なるバッチサイズからのリジュームを避ける（新規開始推奨）

### ONNX変換エラー

- `CUDA_VISIBLE_DEVICES=""`でCPUモードを使用
- チェックポイントファイルが存在するか確認

### SpeakerBalancedBatchSampler で 0 steps/epoch

**原因**: 話者数が `batch_size ÷ samples_per_speaker` より少ない場合に発生

**対処法**: PR #196 で修正済み。話者数に応じて自動調整。

```python
# 修正後: 話者数が少なくても正常にバッチ生成
speakers_per_batch = min(calculated, len(speakers))
```

---

## HuggingFaceリソース

| リソース | URL |
|----------|-----|
| 5話者モデル | `ayousanz/piper-plus-moe-speech-top-5speakers` |
| 5話者データセット | `ayousanz/moe-speech-5speakers-ljspeech` |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` |
| ベースモデル | `ayousanz/piper-plus-base` |
| つくよみちゃんモデル | `ayousanz/piper-plus-tsukuyomi-chan` |
