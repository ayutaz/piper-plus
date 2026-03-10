# 音声品質向上機能ドキュメント

このドキュメントでは、piper-plusで利用可能な音声品質向上機能について説明します。

**更新日**: 2025年8月  
**対応バージョン**: piper-plus v1.4.0  
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

## 2. カスタム辞書機能

日本語の複合語や技術用語の発音精度を向上させるカスタム辞書機能です。

### 特徴

- 478エントリの日本語発音辞書を標準搭載
- 「音声」「合成」などの複合漢字語の正確な発音
- ユーザー独自の辞書追加も可能

### 辞書ファイルの場所

```
data/dictionaries/
├── user_custom_dict.json  # ユーザーカスタム辞書（478エントリ）
├── default_tech_dict.json  # 技術用語辞書
└── default_common_dict.json  # 一般用語辞書
```

### 使用方法

カスタム辞書は自動的に適用されます。追加のエントリが必要な場合は、`user_custom_dict.json`を編集してください。

## 3. データフローの概要

```
入力テキスト
    ↓
カスタム辞書適用（推論時）
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

## 4. 訓練時の推奨設定

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

## 5. トラブルシューティング

### EMA関連

- チェックポイントサイズが大きい場合: `--save-ema-weights-in-callback-state`をfalseに設定
- 学習初期の不安定性: `--ema-start-step`で開始ステップを調整

## 6. 今後の改善点

1. **EMA**: Discriminatorへの適用オプション
2. **カスタム辞書**: より多くの専門用語・方言対応
3. **プロソディ制御**: C++ランタイムを含む完全実装（Issue #159）