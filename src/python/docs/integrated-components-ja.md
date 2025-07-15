# 統合コンポーネントドキュメント

このドキュメントでは、Piper TTSトレーニングパイプラインに統合された主要コンポーネントについて説明します。

## 1. EMA (Exponential Moving Average)

EMAは、モデルパラメータの指数移動平均を計算することで、学習の安定性と品質を向上させる手法です。

### 使用方法

```bash
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --use-ema \
  --ema-decay 0.999
```

### 主な利点

- HiFi-GANジェネレータの学習安定性向上
- ファインチューニング時の品質劣化防止
- 推論時のモデル品質向上

### 実装詳細

- `vits/ema.py`: EMAの実装とPyTorch Lightningコールバック
- デフォルトのdecay率: 0.999
- HiFi-GANデコーダー部分にのみ適用

## 2. AccentProcessor

日本語音声合成のためのアクセント・プロソディ処理コンポーネントです。

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
  --use-ema \
  --ema-decay 0.999 \
  --batch-size 16 \
  --validation-split 0.1 \
  --checkpoint-epochs 10
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