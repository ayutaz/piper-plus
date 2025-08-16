# 統合コンポーネントドキュメント

このドキュメントでは、Piper TTSトレーニングパイプラインに統合された主要コンポーネントについて説明します。

**更新日**: 2025年8月  
**対応バージョン**: piper-plus v1.3.0  
**PyTorch Lightning**: 2.4.0対応

## 1. EMA (Exponential Moving Average)

EMAは、モデルパラメータの指数移動平均を計算することで、学習の安定性と品質を向上させる手法です。
**✅ PR #98により統合完了。デフォルトで有効になっています。**

### 使用方法

```bash
# 通常の使用（EMAが自動的に有効）
python -m piper_train \
  --dataset-dir /path/to/dataset

# EMAの減衰率を変更する場合
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --ema-decay 0.999

# EMAを無効化する場合（推奨されません）
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --no-ema
```

### 主な利点

- HiFi-GANジェネレータの学習安定性向上
- ファインチューニング時の品質劣化防止
- 推論時のモデル品質向上

### 実装詳細

- `vits/ema.py`: EMAの実装とPyTorch Lightningコールバック
- デフォルトのdecay率: 0.9995
- HiFi-GANデコーダー部分にのみ適用

## 2. データフローの概要

```
入力テキスト
    ↓
phoneme_ids
    ↓
TextEncoder
    ↓
Duration Predictor
    ↓
Flow + Decoder
    ↓
音声出力
```

## 3. 訓練時の推奨設定

### 日本語モデルの場合

```bash
python -m piper_train \
  --dataset-dir /path/to/japanese/dataset \
  --ema-decay 0.9995 \
  --batch-size 64 \
  --validation-split 0.1 \
  --checkpoint-epochs 5 \
  --num-workers 80
```

### Multi-GPU環境の場合 (推奨)

```bash
python -m piper_train \
  --dataset-dir /path/to/japanese/dataset \
  --accelerator gpu \
  --devices 4 \
  --strategy ddp_find_unused_parameters_true \
  --batch-size 64 \
  --ema-decay 0.9995 \
  --num-workers 80
```

### ファインチューニングの場合

```bash
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --resume-from-checkpoint /path/to/checkpoint.ckpt \
  --use-ema \
  --ema-decay 0.9995 \
  --learning-rate 0.0001
```

## 4. トラブルシューティング

### EMA関連

- チェックポイントサイズが大きい場合: `--save-ema-weights-in-callback-state`をfalseに設定
- 学習初期の不安定性: `--ema-start-step`で開始ステップを調整

## 5. 今後の改善点

1. **EMA**: Discriminatorへの適用オプション
2. **プロソディ制御**: Issue #159で追跡中（C++ランタイムを含む完全実装）
3. **全体**: エンドツーエンドの音声制御インターフェース