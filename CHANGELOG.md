# Changelog

All notable changes to piper-plus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2025-09-02

### 🚀 Major Features

#### Added
- **マルチスピーカー → 単一話者モデル変換** (#170)
  - マルチスピーカーモデルから特定話者を抽出
  - 単一話者モデルとしてエクスポート可能
  - メモリ使用量の最適化

- **Hugging Face Spaces対応** (#168)
  - 実際のモデルファイルのアップロード機能
  - Web UIでのモデルデプロイメント
  - GitHub Pages対応の改善

- **ストリーミングTTS** (#151)
  - Raw phonemesモードでのストリーミング対応
  - リアルタイム音声合成の遅延削減
  - バッファリング最適化

- **カスタム辞書機能の大幅拡張** (#143, #149)
  - 拡張辞書フォーマット対応
  - ユーザー定義辞書の優先度制御
  - 音素マッピングの改善

### 🔧 Improvements

#### Changed
- **メモリ管理最適化** (#166, #164)
  - マルチスピーカーモデル学習時のメモリ効率改善
  - num_workers自動調整機能の削除（共有メモリ問題対応）
  - GPUメモリフラグメンテーション対策

- **日本語TTS改善** (#167, #160)
  - GitHub PagesでのWebデモ日本語モデル読み込み修正
  - カスタム辞書機能の有効化による発音改善
  - OpenJTalk統合の最適化

#### Fixed
- NumPy 2.x互換性対応 (#163)
- GitHub Actionsリリースワークフロー修正 (#162)
- Docker環境でのテスト改善 (#147)
- WebAssembly版の各種修正 (#136, #144)

### 📚 Documentation

#### Added
- Unity統合プラグイン「uPiper」情報追加 (#154)
- 英語版README作成
- WebAssembly対応ドキュメント (#150)
- ドキュメント構造の大規模再編成 (#133, #150)

### 🎯 Performance
- **音素タイミング情報出力** (#128)
  - リップシンク用タイミング情報
  - フレーム単位の音素境界情報

- **GPU最適化** (#124)
  - device_id選択機能
  - マルチGPU環境での安定性向上

### 🧪 Developer Experience

#### Added
- WebUI実装 (#131)
- Docker環境とCI/CDパイプライン構築 (#129)
- Hugging Face Spaces自動デプロイ (#134)
- GitHubスポンサーボタン追加 (#148)

#### Changed
- piper-plusブランディング更新 (#161)
- プロジェクト構造のクリーンアップ
- CSS10日本語データセット対応強化 (#117)

## [1.3.0] - 2025-07-21

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