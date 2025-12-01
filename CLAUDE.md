# Piper TTS - プロジェクト概要

## プロジェクト説明

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

## 現在の作業状態（2025-12-01）

### 進行中: 5話者マルチスピーカーTTS学習

moe-speech-plusデータセットから抽出した5話者で日本語マルチスピーカーTTSモデルを学習中。

**学習設定:**
```bash
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-5speakers \
  --accelerator gpu \
  --devices 4 \
  --strategy ddp_find_unused_parameters_true \
  --precision 16-mixed \
  --max_epochs 100 \
  --batch-size 10 \
  --checkpoint-epochs 5 \
  --quality medium \
  --base_lr 2e-4 \
  --auto_lr_scaling \
  --ema-decay 0.9995 \
  --num-workers 0 \
  --default_root_dir /data/piper/output-moe-speech-5speakers
```

**データセット情報:**
| 項目 | 値 |
|------|-----|
| 発話数 | 19,617 |
| 話者数 | 5 |
| 音素タイプ | OpenJTalk |
| 韻律特徴 | 有効（11シンボル） |
| キャッシュ | 39,234ファイル（24GB） |

**話者一覧:**
| Speaker ID | 発話数 | ID |
|------------|--------|-----|
| 940de876 | 4,675 | 0 |
| 2cf01874 | 4,632 | 1 |
| bbd90363 | 3,747 | 2 |
| 1a5a3db8 | 3,295 | 3 |
| 4e2f4ba6 | 3,268 | 4 |

## 重要な設定

### FP16 Mixed Precision（デフォルト有効）

`--precision 16-mixed`がデフォルトで有効。

**効果:**
- 学習速度: 2-3倍高速化
- GPUメモリ: 約50%削減
- 品質: 同等（損失計算はFP32で維持）

**選択肢:**
| オプション | 説明 |
|-----------|------|
| `16-mixed` | FP16混合精度（デフォルト） |
| `bf16-mixed` | BFloat16混合精度 |
| `32-true` | 完全FP32（デバッグ用） |

### V100 16GB OOM対策

```bash
# 環境変数（必須）
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# 推奨パラメータ
--batch-size 10          # V100 16GBでは10が安全
--num-workers 0          # cgroupメモリ制限対策
--precision 16-mixed     # メモリ50%削減
```

**GPU別推奨batch_size:**
| GPU | VRAM | batch_size |
|-----|------|------------|
| L4 24GB | 24GB | 16-20 |
| V100 16GB | 16GB | 8-12 |
| A100 40GB | 40GB | 20-24 |

## 重要なファイルパス

| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS実装 | `src/python/piper_train/vits/` |
| 前処理済データ | `/data/piper/dataset-moe-speech-5speakers/` |
| 学習出力 | `/data/piper/output-moe-speech-5speakers/` |
| 学習ログ | `/data/piper/training_5speakers.log` |
| マルチGPUガイド | `docs/guides/training/multi-gpu-training.md` |

## 学習後の評価手順

### 1. ONNX変換
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /data/piper/output-moe-speech-5speakers/lightning_logs/version_10/checkpoints/epoch=99-step=XXXX.ckpt \
  /data/piper/output-moe-speech-5speakers/moe-speech-5speakers.onnx
```

### 2. 推論テスト
```bash
echo "こんにちは、今日は良い天気ですね。" | \
  uv run python -m piper_train.infer \
  --model /data/piper/output-moe-speech-5speakers/moe-speech-5speakers.onnx \
  --speaker 0 \
  --output-file test_speaker0.wav
```

## 進捗確認コマンド

```bash
# 学習ログ確認
tail -f /data/piper/training_5speakers.log

# GPU使用状況
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv

# チェックポイント確認
ls -la /data/piper/output-moe-speech-5speakers/lightning_logs/*/checkpoints/
```

## 完了済みタスク

- [x] FP16 Mixed Precision対応（`--precision`引数追加、デフォルト`16-mixed`）
- [x] LJSpeech形式5話者データセット作成（19,617発話）
- [x] Piper前処理完了（OpenJTalk音素化）
- [x] HuggingFaceアップロード（`ayousanz/moe-speech-5speakers-ljspeech`）
- [ ] 5話者モデル学習（100エポック）- 進行中
- [ ] ONNX変換・推論テスト

## 関連リソース

- HuggingFace: `ayousanz/moe-speech-5speakers-ljspeech`
- ドキュメント: `docs/guides/training/multi-gpu-training.md`
