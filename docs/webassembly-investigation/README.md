# Piper WebAssembly実装 - 技術調査と実装計画

最終更新: 2025-07-21

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

## 次のステップ

1. **Phase 0 開始**: OpenJTalk WebAssembly移植の実現性検証
2. **最小辞書プロトタイプ**: 1000語での動作確認
3. **Unity WebGLメモリ測定**: 実環境でのメモリ使用量確認

## 関連リンク

- [Issue #106: WebAssembly対応](https://github.com/ayutaz/piper-plus/issues/106)
- [uPiper Issue #17: WebGL Platform Support](https://github.com/ayutaz/uPiper/issues/17)