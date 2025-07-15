# Piper Documentation Structure

このディレクトリには、Piper TTSプロジェクトのドキュメントが整理されています。

## 📁 ディレクトリ構成

### unity/ - Unity実装関連
Unity Piper TTSプラグインの開発に関するドキュメント

- **current/** - 現在の進捗と状況
  - `phase1-progress.md` - Phase 1の進捗状況
  - `task-checklist.md` - タスクチェックリスト

- **planning/** - 計画と設計ドキュメント
  - `final-plan.md` - 最終実装計画
  - `sentis-architecture.md` - Sentis統合アーキテクチャ
  - `roadmap.md` - 実装ロードマップ
  - その他の計画ドキュメント

- **implementation/** - 実装ガイドと仕様
  - `phase1-guide.md` - Phase 1実装ガイド
  - `test-cases.md` - テストケース仕様
  - その他の実装ドキュメント

- **archive/** - 過去のドキュメント（参考用）

### piper-core/ - Piperコア実装関連
Piper本体の改善と実装に関するドキュメント

- **accuracy-improvements/** - 精度改善関連
- **implementation-guides/** - 実装ガイド
- **technical-docs/** - 技術仕様書

### setup/ - セットアップとインストール
環境構築とセットアップに関するドキュメント

- Windows、Linux、macOS向けセットアップガイド
- OpenJTalk関連のドキュメント
- 環境変数とトラブルシューティング

## 🚀 クイックスタート

### Unity開発者向け
1. [`UNITY-DOCS-INDEX.md`](UNITY-DOCS-INDEX.md) を参照してUnity関連ドキュメントの概要を把握
2. [`unity/current/phase1-progress.md`](unity/current/phase1-progress.md) で現在の進捗を確認
3. 実装に必要なドキュメントを参照

### Piperコア開発者向け
1. [`piper-core/implementation-guides/`](piper-core/implementation-guides/) の実装ガイドを確認
2. 必要に応じて精度改善や技術仕様のドキュメントを参照

## 📝 ドキュメント管理方針

- **最新情報**: `unity/current/` ディレクトリのドキュメントを最新に保つ
- **アーカイブ**: 古いドキュメントは `archive/` に移動（削除しない）
- **命名規則**: 新規ドキュメントは目的が分かりやすい名前を付ける
- **更新日時**: 重要なドキュメントには最終更新日を記載

## 🔗 主要ドキュメントへのリンク

- [Unity実装索引](UNITY-DOCS-INDEX.md)
- [Phase 1進捗](unity/current/phase1-progress.md)
- [Unity最終実装計画](unity/planning/final-plan.md)
- [Sentisアーキテクチャ](unity/planning/sentis-architecture.md)