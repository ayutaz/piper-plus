# Unity実装ドキュメント索引

このドキュメントは、Unity Piper TTS実装に関する一般的なドキュメントの整理と索引です。

**注意**: uPiper固有の実装詳細（進捗管理、完了報告書など）は[uPiperリポジトリ](https://github.com/ayutaz/uPiper/tree/main/docs)に移動しました。詳細は[MOVED_TO_UPIPER.md](./MOVED_TO_UPIPER.md)を参照してください。

## 📁 ドキュメント構成

### 1. 🎯 現在の実装状況
- 進捗管理ドキュメントは[uPiper/docs/progress/](https://github.com/ayutaz/uPiper/tree/main/docs/progress)に移動しました

### 2. 📋 計画・設計ドキュメント

#### 2.1 最終確定版
- [`unity-piper-tts-final-plan.md`](unity-piper-tts-final-plan.md) - **最終実装計画**（確定版）
- [`unity-piper-tts-sentis-architecture.md`](unity-piper-tts-sentis-architecture.md) - **Sentis統合アーキテクチャ**

#### 2.2 開発計画
- [`unity-implementation-roadmap.md`](unity-implementation-roadmap.md) - 実装ロードマップ
- [`unity-piper-tts-development-plan.md`](unity-piper-tts-development-plan.md) - 詳細開発計画
- [`unity-piper-tts-revised-priorities.md`](unity-piper-tts-revised-priorities.md) - 優先順位（改訂版）

### 3. 🔧 実装ガイド

#### 3.1 Phase別実装ガイド
- [`phase1-implementation-guide-ja.md`](phase1-implementation-guide-ja.md) - Phase 1実装ガイド
- [`phase1-kickoff.md`](phase1-kickoff.md) - Phase 1キックオフ資料

#### 3.2 技術仕様
- [`unity-piper-tts-test-cases.md`](unity-piper-tts-test-cases.md) - テストケース仕様
- [`unity-plugin-investigation-ja.md`](unity-plugin-investigation-ja.md) - プラグイン調査報告

### 4. 📚 参考資料
- [`unity-piper-tts-integration-summary.md`](unity-piper-tts-integration-summary.md) - 統合サマリー
- [`unity-piper-tts-development-confirmation.md`](unity-piper-tts-development-confirmation.md) - 開発確認事項
- [`unity-piper-tts-document-review.md`](unity-piper-tts-document-review.md) - ドキュメントレビュー

## 🗂️ 推奨ディレクトリ構造（将来的な整理案）

```
docs/
├── unity/                          # Unity関連ドキュメント
│   ├── current/                    # 現在の状況
│   │   ├── phase1-progress.md
│   │   └── task-checklist.md
│   ├── planning/                   # 計画・設計
│   │   ├── final-plan.md
│   │   ├── sentis-architecture.md
│   │   └── roadmap.md
│   ├── implementation/             # 実装ガイド
│   │   ├── phase1-guide.md
│   │   └── test-cases.md
│   └── archive/                    # 過去のドキュメント
│       └── development-confirmation.md
├── piper-core/                     # Piperコア関連
│   ├── accuracy-improvements/
│   ├── implementation-guides/
│   └── technical-docs/
└── setup/                          # セットアップ関連
    ├── windows-setup.md
    ├── openjtalk-*.md
    └── environment-variables.md
```

## 📝 ドキュメント利用ガイド

### 新規開発者向け
1. まず [`unity-piper-tts-final-plan.md`](unity-piper-tts-final-plan.md) を読んで全体像を把握
2. [`phase1-progress.md`](phase1-progress.md) で現在の進捗を確認
3. [`unity-task-checklist.md`](unity-task-checklist.md) で残タスクを確認

### 実装担当者向け
1. [`unity-piper-tts-sentis-architecture.md`](unity-piper-tts-sentis-architecture.md) でアーキテクチャを理解
2. 該当するPhaseの実装ガイドを参照
3. [`unity-piper-tts-test-cases.md`](unity-piper-tts-test-cases.md) でテスト要件を確認

### プロジェクト管理者向け
1. [`phase1-progress.md`](phase1-progress.md) で進捗管理
2. [`unity-task-checklist.md`](unity-task-checklist.md) でタスク管理
3. 各種計画ドキュメントで全体計画を把握

## ⚠️ 注意事項

- 最新の情報は常に [`phase1-progress.md`](phase1-progress.md) を参照
- 技術的な質問は [`unity-piper-tts-sentis-architecture.md`](unity-piper-tts-sentis-architecture.md) を確認
- 実装前に必ず最新のタスクリストを確認すること