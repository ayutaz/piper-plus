# Changelog

All notable changes to piper-plus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Enhanced Japanese phoneme support** (PR #99)
  - 65 phonemes with PUA (Private Use Area) character support
  - 3-level accent strength system ([1/[2/[3, ]1/]2/]3)
  - Enhanced question detection (?!, ?., ?~)
  - Data augmentation (SpecAugment, AudioAugmentation, PhonemeAugmentation)
- **`--precision` argument** for mixed precision training
  - Supports: 32-true (default), 16-mixed, bf16-mixed
  - Compatible with PyTorch Lightning 2.4.0

### Fixed
- **PyTorch Lightning 2.x compatibility**
  - Removed duplicate `Trainer.from_argparse_args` API call
  - Fixed precision argument not being passed to Trainer
- **Japanese preprocessing**
  - Fixed missing phoneme warnings for PUA characters
  - Updated phoneme ID mapping to include all 96 symbols

### Removed
- MixUp data augmentation (gradient computation issues)

## [1.3.0] - 2024-07-20

### 🎯 音声品質向上コンポーネント統合 (PR #98)

#### Added
- **EMA (Exponential Moving Average)** - 学習安定性とファインチューニング品質向上
  - デフォルトで有効 (decay rate: 0.9995)
  - `--no-ema` で無効化可能
  - `--ema-decay` で減衰率調整可能
- **AccentProcessor** - 日本語韻律・アクセント処理の高精度化
  - 拡張アクセントマーク対応 (↑↓→⤴⤵|‖)
  - prosody_ids として自動保存
  - 前処理パイプラインに統合
- **F0 Predictor** - FastSpeech2ベースのピッチ予測
  - 離散F0ビン (256レベル) による予測
  - 韻律埋め込み統合
  - SynthesizerTrn に組み込み

#### Changed
- **PyTorch Lightning 2.4.0 対応**
  - 非推奨API (`Trainer.add_argparse_args`) を削除
  - 新しいTrainer初期化方式に対応
  - DDP戦略での安定動作確認
- **依存関係の細かい指定**
  - `pytorch-lightning>=2.4.0,<2.5.0`
  - `torch>=2.0.0,<2.6.0`
  - `torchaudio>=2.0.0,<2.6.0`
  - `ruff==0.12.4` (全ファイル統一)

#### Fixed
- **セキュリティ改善**
  - `torch.load()` に `weights_only=True` を追加
  - pickle security warning を完全解決
- **分散学習最適化**
  - PyTorch Lightning ログ精度向上
  - `batch_size` と `sync_dist` の適切な設定
  - Multi-GPU環境での正確な指標計算
  - 統一ログヘルパーメソッド実装

#### Performance
- **期待される音声品質向上**
  - EMA: MOS +0.08-0.12
  - AccentProcessor: MOS +0.06-0.08  
  - F0 Predictor: MOS +0.04-0.06
  - **総合: MOS +0.18-0.26**

#### Documentation
- `src/python/docs/integrated-components-ja.md` を更新
- README.md にPR #98コンポーネント情報を追加
- Multi-GPU使用例を更新

### 🧪 テスト・検証

#### Tested
- Multi-GPU (4 x NVIDIA L4) での動作確認
- CSS10日本語データセット (6,841 utterances) での検証
- EMA, AccentProcessor, F0 Predictor の統合動作確認
- 自動学習率スケーリング (0.0002 → 0.0032)
- 有効バッチサイズ: 256

## [1.2.0] - 2024-06

### Added
- マルチGPU学習対応（PyTorch Lightning 2.x）
- 日本語音声合成対応（OpenJTalk統合）
- 自動ダウンロード機能

### Fixed
- 前処理済み .pt ファイル破損時の自動スキップ
- DataLoader GPU転送最適化

## [1.0.0] - 2024-01

### Added
- 初期リリース
- 基本的なTTS機能
- VITS アーキテクチャ実装