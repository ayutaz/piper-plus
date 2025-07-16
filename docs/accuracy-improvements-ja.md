# Piper-Plus 精度向上実装ガイド

## 概要

本ドキュメントでは、piper-plusの音声合成品質を向上させるための改善実装について説明します。これらの改善は、モデルサイズを大幅に増加させることなく、MOS（Mean Opinion Score）を向上させることを目的としています。

## 実装状況凡例
- ✅ v1で実装済み
- ✅ v2で実装済み  
- ❌ 未実装

## 改善項目と期待される効果

| 改善項目 | 期待されるMOS向上 | 実装の複雑さ | ONNX互換性 | 実装状況 |
|---------|-----------------|------------|-----------|---------|
| gin_channels増加 | +0.04-0.06 | 低 | ✓ | ✅ v1 (PR #97) |
| F0予測器の追加 | +0.10 | 中 | ✓ | ✅ v1 (PR #98) |
| アクセント記号埋め込み | +0.05-0.08 | 低 | ✓ | ✅ v1 (PR #98) |
| HiFi-GAN EMA平均化 | +0.03-0.06 | 低 | ✓ | ✅ v1 (PR #98) |
| Multi-Resolution STFT | +0.08-0.12 | 中 | ✓ | ✅ v2 |
| アクセント強度レベル | +0.03-0.05 | 低 | ✓ | ✅ v2 |
| 質問文検出改善 | +0.02-0.03 | 低 | ✓ | ✅ v2 |
| データ拡張 | +0.05-0.10 | 中 | ✓ | ✅ v2 |
| Duration正則化 | +0.02-0.04 | 低 | ✓ | ✅ v2 |
| Transformer blocks | +0.06-0.08 | 中 | ✓ | ✅ v2 |
| WavLM Discriminator | +0.15-0.25 | 高 | ✓ | ❌ 未実装 |
| 日本語BERT埋め込み | +0.06-0.10 | 高 | △ | ❌ 未実装 |
| Conditional Flow Matching | +0.10-0.15 | 高 | ✓ | ❌ 未実装 |

## 実装済み機能の詳細

### 1. v1ブランチで実装済み

#### 1.1 gin_channels の増加 ✅
- **PR**: #97
- **効果**: 話者埋め込みサイズを増やし、話者の個性をより豊かに表現
- **実装**: 設定値の変更のみで対応可能

#### 1.2 F0予測器の追加 ✅
- **PR**: #98
- **ファイル**: `src/python/piper_train/vits/f0_predictor.py`
- **効果**: より自然なイントネーションとアクセントを実現
- **主要コンポーネント**:
  - FastSpeech2ベースのF0予測モジュール
  - 離散F0ビン（256個）による予測
  - プロソディ埋め込みの統合
  - 不確実性モデリング

#### 1.3 AccentProcessor ✅
- **PR**: #98
- **ファイル**: `src/python/piper_train/phonemize/accent_processor.py`
- **効果**: 詳細なアクセント制御
- **拡張アクセントマーク**:
  - `↑`: アクセント核の上昇
  - `↓`: アクセント核後の下降
  - `→`: 平坦なイントネーション
  - `⤴`: 句末の上昇
  - `⤵`: 句末の下降
  - `|`: 小句境界
  - `‖`: 大句境界

#### 1.4 EMA（指数移動平均） ✅
- **PR**: #98
- **ファイル**: `src/python/piper_train/vits/ema.py`
- **効果**: 学習の安定性向上とファインチューニング耐性
- **機能**:
  - 適応的減衰率
  - PyTorch Lightningコールバック統合
  - チェックポイント対応

### 2. v2ブランチで実装済み

#### 2.1 Multi-Resolution STFT Discriminator ✅
- **ファイル**: `src/python/piper_train/vits/stft_discriminator.py`
- **効果**: より詳細な音声特徴の識別
- **機能**:
  - 複数の時間-周波数解像度での識別
  - CombinedMultiDiscriminatorによる統合

#### 2.2 アクセント強度レベル ✅
- **ファイル**: `src/python/piper_train/phonemize/japanese_enhanced.py`
- **効果**: 繊細なアクセント表現
- **機能**:
  - 3段階の強度（弱/中/強）
  - [1/2/3, ]1/2/3 マーク体系

#### 2.3 質問文検出の改善 ✅
- **ファイル**: `src/python/piper_train/phonemize/japanese_enhanced.py`
- **効果**: 質問タイプに応じた適切なイントネーション
- **質問タイプ**:
  - Yes/No質問: `?`
  - WH質問: `?!`
  - 修辞疑問: `?.`
  - 付加疑問: `?~`

#### 2.4 データ拡張 ✅
- **ファイル**: `src/python/piper_train/vits/augmentation.py`
- **効果**: モデルの汎化性能向上
- **手法**:
  - SpecAugment
  - 速度変動（0.9-1.1x）
  - ピッチシフト（±2半音）
  - 音素ドロップアウト
  - MixUp

#### 2.5 Duration正則化 ✅
- **ファイル**: `src/python/piper_train/vits/losses.py`
- **効果**: 安定した音素長予測
- **機能**:
  - 分散ペナルティ
  - 平滑性ペナルティ
  - 音素別ペナルティ

#### 2.6 Transformer blocks ✅
- **ファイル**: `src/python/piper_train/vits/attentions.py`
- **効果**: 長期依存性のモデリング改善
- **既にVITSアーキテクチャに統合済み**

## 未実装の機能

### 1. WavLM Discriminator ❌
- **期待効果**: MOS +0.15-0.25（最大の改善）
- **概要**: 事前学習済みWavLMモデルを使用した識別器
- **実装時間**: 約2週間
- **利点**: 人間の知覚に近い音声品質評価

### 2. 日本語BERT埋め込み ❌
- **期待効果**: MOS +0.06-0.10
- **概要**: 文脈理解の強化
- **実装時間**: 約1.5週間
- **注意**: ONNXエクスポート時に工夫が必要

### 3. Conditional Flow Matching ❌
- **期待効果**: MOS +0.10-0.15
- **概要**: Matcha-TTS方式の最新フロー
- **実装時間**: 約3週間
- **利点**: 推論速度も2-3倍向上

## 累積効果

### 実装済み改善の合計効果
- **v1ブランチ**: MOS +0.20-0.30
- **v2ブランチ**: MOS +0.26-0.46
- **合計**: MOS +0.46-0.76

### 未実装を含めた潜在的な最大効果
- **全実装時**: MOS +0.77-1.26

## 使用方法

### v1機能の使用
```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --gin-channels 768 \
    --use-ema \
    --ema-decay 0.9995
```

### v2機能の使用
```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --use-stft-discriminator \
    --use-duration-regularization \
    --batch-size 32
```

## まとめ

piper-plusは既に多くの最新技術を実装しており、商用レベルに近い品質を実現しています。残る主要な改善点は：

1. **WavLM Discriminator**: 最も効果的だが実装に時間がかかる
2. **日本語BERT**: 日本語特有の文脈理解を強化
3. **Conditional Flow Matching**: 品質と速度の両方を改善

これらの実装により、人間の音声と区別がつかないレベルの合成音声を実現できる可能性があります。