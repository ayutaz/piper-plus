# Piper WebAssembly実装 - 技術調査と実装計画

最終更新: 2025-07-21

## 🚀 実装進捗

### Task 0.1: 開発環境構築 ✅ **完了** (2025-07-21)
- Emscripten SDK 4.0.11 インストール完了
- CMake設定ファイル（Chrome最適化）作成
- サンプルWebAssemblyプロジェクトのビルド成功
- ブラウザテスト環境構築完了
- GitHub Actions CI/CD設定完了
- 日本語UTF-8文字列処理の動作確認済み

### Task 0.2: 既存実装調査 ✅ **完了** (2025-07-21)
- MeCab WebAssembly実装の調査完了
  - mecab-web-worker（推奨）、mecab-emscripten等を分析
- OpenJTalk WebAssembly実装の調査完了
  - wasm_open_jtalk（Node.js版）を発見
- ビルドプロセスのドキュメント化
- 技術的制約事項の分析完了

## 概要

piper-plusプロジェクトのWebAssembly対応（[Issue #106](https://github.com/ayutaz/piper-plus/issues/106)）に関する包括的な技術調査と実装計画です。日本語TTSを最優先とし、Unity WebGLでの動作を前提としています。

## 実現可能性評価: ✅ **高い**

### 技術スタック対応状況

| コンポーネント | 対応状況 | 詳細 |
|---------------|---------|------|
| **ONNX Runtime** | ✅ 完全対応 | onnxruntime-web、WebGPU/WebGL/WASM backends |
| **eSpeak-NG** | ✅ 公式対応 | ChromeOSで実績あり（英語は後回し） |
| **MeCab** | ✅ 実装済み | コミュニティによる移植版が存在 |
| **OpenJTalk** | ⚠️ 要移植 | 新規移植が必要だが技術的に可能 |

## 実装計画（改訂版）

### タイムライン: 10-12週間

| フェーズ | 期間 | 内容 |
|---------|------|------|
| Phase 0 | 1週間 | 技術検証（OpenJTalk移植実現性、最小辞書検証） |
| Phase 1 | 3-4週間 | 日本語音素化基盤（MeCab/OpenJTalk移植） |
| Phase 2 | 2週間 | ONNX Runtime統合と音声合成 |
| Phase 3 | 2週間 | 最適化とブラウザ統合 |
| Phase 4 | 1-2週間 | Unity WebGL統合 |
| Phase 5 | 2週間 | テスト、デモ、ドキュメント |

### 成功指標（段階的目標）

| Phase | 辞書サイズ | 初期化時間 | 音声生成遅延 | メモリ使用量 |
|-------|-----------|------------|--------------|------------|
| 1 | 10MB | < 5秒 | < 500ms | < 200MB |
| 2 | 5MB | < 3秒 | < 400ms | < 150MB |
| 3 | 2-3MB | < 2秒 | < 300ms | < 100MB |

## 主要な技術課題と解決策

### 1. 辞書サイズ最適化
- **現状**: 103MB（sys.dic: 99MB）
- **目標**: 段階的に2-3MBまで削減
- **解決策**: 
  - 頻度ベースの語彙選定
  - Brotli圧縮（約80%削減）
  - プログレッシブローディング

### 2. Unity WebGLメモリ制限
- **制約**: 256MBヒープ制限
- **解決策**:
  - Web Worker活用
  - メモリプール実装
  - AudioClipキャッシング

### 3. ブラウザ互換性
- **WebGPU**: Chrome/Edge 113+で対応
- **フォールバック**: WebGL → WASM実装
- **Safari対策**: WebGPU非対応のためWASMフォールバック必須

## ドキュメント構成

### 実装計画
- [webassembly-implementation-master-plan.md](./webassembly-implementation-master-plan.md) - 統合実装計画
- [webassembly-technical-investigation.md](./webassembly-technical-investigation.md) - 詳細技術調査

### 技術詳細
- [japanese-tts-implementation.md](./japanese-tts-implementation.md) - 日本語TTS実装詳細
- [unity-webgl-integration.md](./unity-webgl-integration.md) - Unity WebGL統合方法
- [dictionary-optimization-strategy.md](./dictionary-optimization-strategy.md) - 辞書最適化戦略

### 品質保証
- [test-strategy.md](./test-strategy.md) - テスト戦略
- [error-handling-strategy.md](./error-handling-strategy.md) - エラーハンドリング

## 現在のステータス

- **現在のブランチ**: `feat/webassembly-support`
- **完了タスク**: Task 0.1, Task 0.2
- **次のタスク**: Task 0.3 (最小プロトタイプ実装)

## 次のステップ

1. **Task 0.3**: 最小プロトタイプ実装
   - MeCab WebAssemblyプロトタイプ作成
   - 基本的な日本語テキスト処理機能
   - ブラウザでの動作確認
2. **Task 0.4**: メモリ・性能測定
3. **Task 0.5**: Go/No-Go判定準備

## 関連リンク

- [Issue #106: WebAssembly対応](https://github.com/ayutaz/piper-plus/issues/106)
- [uPiper Issue #17: WebGL Platform Support](https://github.com/ayutaz/uPiper/issues/17)