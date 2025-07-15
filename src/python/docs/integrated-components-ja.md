# 統合コンポーネントドキュメント

このドキュメントでは、Piper TTSトレーニングパイプラインに統合された主要コンポーネントについて説明します。

**更新日**: 2024年7月 (PR #98統合版)  
**対応バージョン**: piper-plus v1.3.0  
**PyTorch Lightning**: 2.4.0対応

## 1. EMA (Exponential Moving Average)

EMAは、モデルパラメータの指数移動平均を計算することで、学習の安定性と品質を向上させる手法です。
**✅ PR #98により統合完了。デフォルトで有効になっています。**

### 使用方法

```bash
<<<<<<< HEAD
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
=======
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --use-ema \
  --ema-decay 0.999
>>>>>>> d0e1cb2 (feat: Integrate EMA, AccentProcessor, and F0 Predictor into training pipeline)
```

### 主な利点

- HiFi-GANジェネレータの学習安定性向上
- ファインチューニング時の品質劣化防止
- 推論時のモデル品質向上

### 実装詳細

- `vits/ema.py`: EMAの実装とPyTorch Lightningコールバック
<<<<<<< HEAD
- デフォルトのdecay率: 0.9995
=======
- デフォルトのdecay率: 0.999
>>>>>>> d0e1cb2 (feat: Integrate EMA, AccentProcessor, and F0 Predictor into training pipeline)
- HiFi-GANデコーダー部分にのみ適用

## 2. AccentProcessor

日本語音声合成のためのアクセント・プロソディ処理コンポーネントです。
<<<<<<< HEAD
**✅ PR #98により統合完了。前処理パイプラインに組み込み済み。**
=======
>>>>>>> d0e1cb2 (feat: Integrate EMA, AccentProcessor, and F0 Predictor into training pipeline)

### 機能

- 日本語テキストからアクセント情報を抽出
- プロソディIDの生成と管理
- 高低アクセントパターンの分析

### 使用される場面

- 前処理時 (`preprocess.py`): テキストからプロソディ情報を抽出
- データセット作成時: `prosody_ids`フィールドとして保存

### データ形式

```json
{
  "text": "こんにちは",
  "phoneme_ids": [1, 2, 3, ...],
  "prosody_ids": [0, 1, 0, ...],
  "audio_norm_path": "path/to/audio.pt",
  "audio_spec_path": "path/to/spec.pt"
}
```

## 3. F0 Predictor

基本周波数（F0）予測モジュールで、より自然な音声合成を実現します。
<<<<<<< HEAD
**✅ PR #98により統合完了。SynthesizerTrnに組み込み済み。**
=======
>>>>>>> d0e1cb2 (feat: Integrate EMA, AccentProcessor, and F0 Predictor into training pipeline)

### アーキテクチャ

- Multi-head attentionベースの設計
- テキスト特徴量から直接F0を予測
- スピーカー埋め込みに対応（マルチスピーカーモデル）

### 統合箇所

- `vits/models.py`: SynthesizerTrnクラスに統合
- Duration Predictorの後に配置
- 学習時に自動的に使用される

### パラメータ

- `hidden_channels`: 隠れ層のチャンネル数
- `filter_channels`: フィルターチャンネル数（デフォルト: 256）
- `n_heads`: アテンションヘッド数
- `kernel_size`: 畳み込みカーネルサイズ（デフォルト: 3）
- `p_dropout`: ドロップアウト率

## 4. データフローの概要

```
入力テキスト
    ↓
AccentProcessor（前処理時）
    ↓
phoneme_ids + prosody_ids
    ↓
TextEncoder
    ↓
Duration Predictor
    ↓
F0 Predictor（NEW）
    ↓
Flow + Decoder
    ↓
音声出力
```

## 5. 訓練時の推奨設定

### 日本語モデルの場合

```bash
python -m piper_train \
  --dataset-dir /path/to/japanese/dataset \
<<<<<<< HEAD
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
=======
  --use-ema \
  --ema-decay 0.999 \
  --batch-size 16 \
  --validation-split 0.1 \
  --checkpoint-epochs 10
>>>>>>> d0e1cb2 (feat: Integrate EMA, AccentProcessor, and F0 Predictor into training pipeline)
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

## 6. トラブルシューティング

### EMA関連

- チェックポイントサイズが大きい場合: `--save-ema-weights-in-callback-state`をfalseに設定
- 学習初期の不安定性: `--ema-start-step`で開始ステップを調整

### プロソディ関連

- アクセント情報が正しく抽出されない: 入力テキストの正規化を確認
- プロソディIDが欠落: `preprocess.py`のログを確認

### F0予測関連

- 音程が不自然: `--f0-loss-weight`で損失の重みを調整
- 学習が収束しない: 学習率を下げて試す

## 7. 今後の改善点

1. **EMA**: Discriminatorへの適用オプション
2. **AccentProcessor**: より詳細なプロソディ特徴の抽出
3. **F0 Predictor**: ピッチレンジの制御機能
4. **全体**: エンドツーエンドのプロソディ制御インターフェース