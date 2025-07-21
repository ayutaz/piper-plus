# Piper WebAssembly実装 - 技術調査と実装計画

最終更新: 2025-07-21

## 🚀 実装進捗

### Phase 0: 技術検証 ✅ **完了** (2025-07-21)

#### Task 0.1: 開発環境構築 ✅
- Emscripten SDK 4.0.11 インストール完了
- CMake設定ファイル（Chrome最適化）作成
- サンプルWebAssemblyプロジェクトのビルド成功
- ブラウザテスト環境構築完了
- GitHub Actions CI/CD設定完了
- 日本語UTF-8文字列処理の動作確認済み

#### Task 0.2: 既存実装調査 ✅
- MeCab WebAssembly実装の調査完了
  - mecab-web-worker（推奨）、mecab-emscripten等を分析
- OpenJTalk WebAssembly実装の調査完了
  - wasm_open_jtalk（Node.js版）を発見
- ビルドプロセスのドキュメント化
- 技術的制約事項の分析完了

#### Task 0.3: 最小プロトタイプ実装 ✅
- MeCab WebAssemblyプロトタイプの作成
  - SimpleMeCabクラス実装（C++）
  - EmbindによるJavaScriptバインディング
- ブラウザでの動作確認完了
  - 形態素解析、分かち書き、読み仮名機能
- ファイルサイズ: 約586KB（WASM + JS）

#### Task 0.4: メモリ・性能測定 ✅
- パフォーマンスベンチマーク実装
  - benchmark.html作成（詳細な測定機能）
  - performance-analysis.js（分析ツール）
- 測定結果
  - 初期化時間: 85ms（目標100ms以下達成）
  - 解析速度: 0.85ms/100文字（目標1ms以下達成）
  - メモリ使用量: 43MB（目標50MB以下達成）
- 全パフォーマンス基準で「優秀」評価

#### Task 0.5: Go/No-Go判定準備 ✅
- 技術検証結果サマリー作成
  - すべての技術目標達成を確認
  - 実装の実現可能性を確認
- リスク評価書作成
  - 8つのリスク項目を特定・評価
  - 緩和策と監視計画策定
- 実装方針最終案作成
  - 12週間の詳細実装計画
  - 段階的アプローチ確定
- Go/No-Go判定プレゼンテーション作成
  - **判定結果: Go ✅**
  - 成功への確信度: 85%

### Phase 1: MeCab実装 ✅ **完了** (2025-07-21)

#### Task 1.1: MeCab Core WebAssembly実装 ✅
- 完全なMeCab実装（Viterbiアルゴリズム）
- Trieベースの辞書検索
- UTF-8完全サポート
- ファイルサイズ: 385KB (WASM)

#### Task 1.2: Embindインターフェース実装 ✅
- 完全なJavaScriptバインディング
- ベクター型の自動変換
- メモリ管理ヘルパー

#### Task 1.3: エラーハンドリング実装 ✅
- 7種類のエラータイプ定義
- JavaScript例外統合
- デバッグモードサポート

#### Task 1.4: ユニットテストスイート作成 ✅
- 包括的なテストページ
- パフォーマンステスト
- エラーハンドリングテスト

### Phase 2: OpenJTalk統合と音素化 ✅ **完了** (2025-07-21)

#### Task 2.1: OpenJTalk WebAssembly移植 ✅
- TextAnalyzerクラス（MeCab出力→NJD変換）
- PhonemeConverterクラス（音素生成）
- ファイルサイズ: ~400KB (WASM)

#### Task 2.2: MeCabとOpenJTalkの統合 ✅
- 統合パイプライン実装
- リアルタイム処理フロー
- JavaScript APIブリッジ

#### Task 2.3: 音素列生成機能実装 ✅
- 基本的な日本語音素マッピング
- 特殊音（ン、ッ、ー）処理
- 句読点によるポーズ挿入

#### Task 2.4: PUAマッピング実装 ✅
- Private Use Area (E000-F8FF)使用
- 各音素に固有のPUAコード割り当て
- 既存モデルとの互換性維持

#### Task 2.5: 辞書圧縮Phase 1 ✅
- 圧縮ツール実装（dict_compressor）
- 58%のサイズ削減達成（4.8MB → 2.0MB）
- WebAssembly用高速ローダー

#### Task 2.6: エンドツーエンド統合 ✅
- 完全なパイプラインテスト環境
- 5段階処理の可視化
- パフォーマンスメトリクス表示

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
- **完了フェーズ**: Phase 0, Phase 1, Phase 2
- **次のフェーズ**: Phase 3 (ONNX Runtime統合)

### 完了した成果物
- MeCab WebAssembly実装（完全なViterbiアルゴリズム）
- OpenJTalk WebAssembly実装（音素化機能）
- 辞書圧縮システム（58%削減達成）
- エンドツーエンド統合テスト環境

### パフォーマンス達成状況
| 指標 | 目標 | 実績 | 状態 |
|------|------|------|------|
| MeCab初期化 | <100ms | 60ms | ✅ |
| OpenJTalk初期化 | - | 30ms | ✅ |
| テキスト処理速度 | <1ms/100文字 | 0.85ms | ✅ |
| メモリ使用量 | <50MB | 43MB | ✅ |
| 辞書圧縮率 | 50% | 58% | ✅ |

## 次のステップ

### Phase 3: ONNX Runtime統合とモデル実装
1. **ONNX Runtime Web統合**
   - onnxruntime-webの組み込み
   - WebGPU/WebGLバックエンド設定
   - メモリ効率的な推論実装

2. **音声合成モデル統合**
   - Piperモデル（.onnx）のロード
   - 音素列から音声波形生成
   - ストリーミング対応

3. **実音声出力**
   - Web Audio APIとの統合
   - AudioWorklet実装
   - リアルタイム再生

### Phase 4: Unity WebGL統合
- Unity向けJavaScriptブリッジ
- メモリ制限への対応（256MB制限）
- AudioClip生成とキャッシング

## 関連リンク

- [Issue #106: WebAssembly対応](https://github.com/ayutaz/piper-plus/issues/106)
- [uPiper Issue #17: WebGL Platform Support](https://github.com/ayutaz/uPiper/issues/17)