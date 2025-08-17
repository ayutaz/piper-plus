# WebAssembly OpenJTalkアプローチ

## 概要

このディレクトリは、piper-plusのWebAssembly実装に関する技術文書を含んでいます。PR #118でのMeCab単独実装の失敗を踏まえ、`wasm_open_jtalk`のアプローチ（OpenJTalk全体の移植）を採用した新しい実装方針について記載しています。

## ドキュメント構成

### 📊 [技術調査報告書](technical-investigation.md)
- wasm_open_jtalkの詳細分析
- PR #118の失敗原因分析
- ブラウザ対応の技術的実現性評価
- 既存実装との比較

### 📋 [実装計画書](implementation-plan.md)
- 5週間の開発計画
- フェーズ別の詳細タスク
- 品質保証戦略
- リスク管理計画

### 🗺️ [実装ロードマップ](implementation-roadmap.md)
- タイムラインとマイルストーン
- 成功基準の定義
- 品質ゲートチェックリスト
- リスクと対策

### 🔧 [技術アプローチ](technical-approach.md)
- システムアーキテクチャ
- 実装詳細とコード例
- パフォーマンス最適化手法
- 統合方法

## キーポイント

### なぜ新しいアプローチか？

**PR #118の失敗**:
- MeCabを単独で移植しようとした
- 辞書フォーマットの非互換性で失敗（精度0%）

**新アプローチの利点**:
- OpenJTalk全体を移植（wasm_open_jtalk方式）
- 辞書互換性の問題を回避
- Node.js版で実証済み

### 技術的実現性

✅ **実現可能と判断する理由**:
1. wasm_open_jtalkが既にOpenJTalkのWebAssembly化に成功
2. Node.js → ブラウザの変換は技術的に単純
3. Emscriptenの成熟度と豊富な実績

### 実装スケジュール

| フェーズ | 期間 | 主要成果物 |
|---------|------|-----------|
| Phase 1 | 2週間 | 基本的なブラウザ動作 |
| Phase 2 | 2週間 | 最適化とPiper統合 |
| Phase 3 | 1週間 | プロダクション準備 |

## 技術スタック

- **音素変換**: OpenJTalk (C++)
- **WebAssembly化**: Emscripten 3.x
- **音声合成**: ONNX Runtime Web
- **並列処理**: Web Workers
- **対象ブラウザ**: Chrome/Edge（初期）

## 期待される成果

1. **高精度な日本語TTS**: PyOpenJTalk同等の音素変換精度
2. **ブラウザ完結**: プラグイン不要、オフライン動作可能
3. **高性能**: 初期化5秒以内、変換100ms/文以内

## 次のステップ

1. wasm_open_jtalkのソースコード分析
2. ビルド環境の構築
3. 最小限のプロトタイプ作成

---

作成日: 2025-07-31
プロジェクト: piper-plus WebAssembly実装