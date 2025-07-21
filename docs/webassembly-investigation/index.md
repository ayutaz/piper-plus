# WebAssembly実装ドキュメント一覧

最終更新: 2025-07-21

## 概要

Piper-plusのWebAssembly対応（[Issue #106](https://github.com/ayutaz/piper-plus/issues/106)）に関するドキュメント群です。日本語TTSを最優先、Unity WebGL対応を前提としています。

## ドキュメント構成

### 📋 概要・計画
- **[README.md](./README.md)** - プロジェクト概要と最新ステータス
- **[webassembly-implementation-master-plan.md](./webassembly-implementation-master-plan.md)** - 統合実装計画（10-12週間）
- **[webassembly-technical-investigation.md](./webassembly-technical-investigation.md)** - 詳細な技術調査レポート
- **[detailed-implementation-plan.md](./detailed-implementation-plan.md)** - 2日単位の詳細タスク計画

### 🔧 技術詳細
- **[japanese-tts-implementation.md](./japanese-tts-implementation.md)** - 日本語TTS実装の技術詳細
- **[dictionary-optimization-strategy.md](./dictionary-optimization-strategy.md)** - 辞書最適化戦略（103MB→2-3MB）
- **[unity-webgl-integration.md](./unity-webgl-integration.md)** - Unity WebGL統合ガイド

### 🔍 調査・分析
- **[existing-implementations-survey.md](./existing-implementations-survey.md)** - 既存WebAssembly実装調査
- **[build-process-documentation.md](./build-process-documentation.md)** - WebAssemblyビルドプロセス
- **[technical-constraints-analysis.md](./technical-constraints-analysis.md)** - 技術的制約事項分析
- **[task-0.2-technical-investigation-report.md](./task-0.2-technical-investigation-report.md)** - Task 0.2 統合調査レポート
- **[task-0.3-prototype-report.md](./task-0.3-prototype-report.md)** - Task 0.3 プロトタイプ実装レポート
- **[task-0.4-performance-report.md](./task-0.4-performance-report.md)** - Task 0.4 パフォーマンス測定レポート

### 📊 Go/No-Go判定資料
- **[task-0.5-technical-verification-summary.md](./task-0.5-technical-verification-summary.md)** - 技術検証結果サマリー
- **[task-0.5-risk-assessment.md](./task-0.5-risk-assessment.md)** - リスク評価書
- **[task-0.5-implementation-policy.md](./task-0.5-implementation-policy.md)** - 実装方針最終案
- **[task-0.5-presentation.md](./task-0.5-presentation.md)** - Go/No-Go判定プレゼンテーション

### ✅ 品質保証
- **[test-strategy.md](./test-strategy.md)** - テスト戦略（単体・統合・性能・品質）
- **[error-handling-strategy.md](./error-handling-strategy.md)** - エラーハンドリングとフォールバック戦略

## クイックリファレンス

### 技術スタック
- **音素化**: OpenJTalk + MeCab（日本語）
- **音声合成**: ONNX Runtime Web（WebGPU/WebGL/WASM）
- **音声出力**: AudioWorklet + Web Audio API
- **Unity統合**: WebGL JavaScript Bridge (.jslib)
- **ビルド**: Emscripten 3.1.61+

### 実装タイムライン（改訂版）
| Phase | 期間 | 内容 |
|-------|------|------|
| 0 | 1週間 | 技術検証 |
| 1 | 3-4週間 | 日本語音素化基盤 |
| 2 | 2週間 | ONNX Runtime統合 |
| 3 | 2週間 | 最適化 |
| 4 | 1-2週間 | Unity WebGL統合 |
| 5 | 2週間 | テスト・デモ |

### パフォーマンス目標（段階的）
| Phase | 辞書 | 初期化 | 生成遅延 | メモリ |
|-------|------|--------|----------|--------|
| 1 | 10MB | < 5秒 | < 500ms | < 200MB |
| 2 | 5MB | < 3秒 | < 400ms | < 150MB |
| 3 | 2-3MB | < 2秒 | < 300ms | < 100MB |

## 開発者向けガイド

### 開始方法
1. [技術調査レポート](./webassembly-technical-investigation.md)で全体像を把握
2. [統合実装計画](./webassembly-implementation-master-plan.md)でフェーズを確認
3. 実装時は各技術詳細ドキュメントを参照

### Unity WebGL開発者
- [Unity WebGL統合ガイド](./unity-webgl-integration.md)から開始
- メモリ制限（256MB）とシングルスレッド制約に注意
- 提供されているC#インターフェースとjslibを使用

### 日本語TTS実装者
- [日本語TTS実装詳細](./japanese-tts-implementation.md)を参照
- OpenJTalk/MeCabのWebAssembly移植が必要
- PUAマッピングで既存モデルとの互換性維持

## 関連リソース

### 外部リンク
- [eSpeak-NG WebAssembly](https://github.com/espeak-ng/espeak-ng/tree/master/emscripten)
- [MeCab WebAssembly](https://github.com/leyhline/mecab-web-worker)
- [OpenJTalk WASM](https://github.com/hrhr49/wasm_open_jtalk)
- [ONNX Runtime Web](https://onnxruntime.ai/docs/get-started/with-javascript.html)

### 問い合わせ先
- Issue: [piper-plus #106](https://github.com/ayutaz/piper-plus/issues/106)
- Unity統合: [uPiper #17](https://github.com/ayutaz/uPiper/issues/17)

---

このドキュメント群は定期的に更新されます。最新情報はREADME.mdをご確認ください。