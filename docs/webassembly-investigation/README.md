# Piper-WASM WebAssembly対応 技術調査サマリー

調査日: 2025年7月20日

## 調査概要

piper-plusおよびuPiperプロジェクトのWebAssembly対応について、技術的実現可能性と実装戦略を調査しました。

### 調査対象Issue
- **piper-plus #106**: WebAssembly対応によるブラウザ内TTS実行
- **uPiper #17**: WebGL Platform Support for OpenJTalk Phonemizer

## 調査結果

### 1. 実現可能性評価: ✅ **高い**

#### 依存関係のWebAssembly対応状況

| コンポーネント | 対応状況 | 詳細 |
|---------------|---------|------|
| **ONNX Runtime** | ✅ 完全対応 | onnxruntime-web v1.22.0、WebGPU/WebGL/WASM backends |
| **eSpeak-NG** | ✅ 公式対応 | 公式Emscriptenポート、Chrome OS実装済み |
| **OpenJTalk** | ⚠️ 限定対応 | 古いnpmパッケージ存在、移植が必要 |
| **MeCab** | ✅ 実証済み | 複数のWebAssemblyポート確認 |

### 2. 推奨実装戦略

**piper-plus側でWebAssembly基盤を構築**し、その後uPiper側でUnity WebGL統合を行う段階的アプローチを推奨。

#### 実装優先順位
1. **OpenJTalk/MeCab WebAssembly移植**（最優先）
2. **辞書データ最適化**（103MB → 2-3MB）
3. **ONNX Runtime Web統合**
4. **Unity WebGLプラグイン化**

### 3. 実装スケジュール

#### 日本語TTS最優先の場合
- **2-3週間**: 基本的な音素変換（テキスト→音素）
- **4-6週間**: 音声合成まで含む最小実装
- **8-10週間**: Unity WebGL完全統合

#### 段階的リリース計画
- **v0.1**: テキスト→音素変換のみ（2-3週間）
- **v0.2**: 基本的な音声合成（4-5週間）
- **v0.3**: Unity WebGL対応（6-8週間）

### 4. 技術的課題と解決策

#### 辞書サイズ問題
- **現状**: 103MB（sys.dic: 99MB）
- **目標**: 2-3MB（最小辞書）
- **解決策**: 
  - 頻度ベースの語彙選定
  - Brotli圧縮（約80%削減）
  - 段階的ロード機能

#### メモリ制約
- **解決策**:
  - Web Worker活用
  - 遅延初期化
  - LRUキャッシュ実装

#### Unity WebGL制約
- **解決策**:
  - Native Plugin（.jslib）実装
  - WebAssembly 2023機能活用
  - 非同期API設計

### 5. 成果物

#### piper-plus側
- `piper-wasm` npmパッケージ
- WebAssemblyビルド（piper-openjtalk.wasm）
- 最小辞書セット（dict-minimal/）
- JavaScript/TypeScript API

#### uPiper側
- Unity WebGLプラグイン
- C# API ラッパー
- サンプルプロジェクト
- Asset Store対応パッケージ

## 詳細ドキュメント

以下のファイルに詳細な実装計画が含まれています：

1. **piper-wasm-japanese-implementation-plan.md**
   - 最小限の日本語TTS実装計画
   - 具体的なコード例
   - ビルドコマンド

2. **dictionary-optimization-strategy.md**
   - 辞書データ最適化戦略
   - 圧縮技術の詳細
   - 段階的ロード実装

3. **unity-webgl-implementation-strategy.md**
   - Unity WebGL統合方法
   - プラグイン実装詳細
   - デプロイメント設定

## 結論

WebAssembly対応は技術的に実現可能であり、既存の実装例とツールを活用することで、**1.5-2ヶ月で実用的な日本語TTSのWebAssembly版**が実現可能です。

推奨アプローチ：
1. piper-plus側でWebAssembly基盤構築
2. 最小辞書での早期リリース
3. 段階的な機能拡張とUnity統合

これにより、ブラウザ内でのオフライン日本語音声合成が実現し、新しい活用シーンを開拓できます。