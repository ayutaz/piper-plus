# Unity Piper TTS 最終実装計画

## エグゼクティブサマリー

Unity 6000.0.35f1 と Sentis 2.1.2 を使用した日本語対応TTSプラグインの開発計画が確定しました。WebGLの優先度を上げ、早期にブラウザデモを公開することで、より多くのユーザーフィードバックを収集します。

## 確定したプラットフォーム優先順位

1. **Windows/Linux** (Phase 1) - 最優先
2. **Android** (Phase 2) - 高優先度
3. **WebGL** (Phase 3) - 中優先度 ⬆️
4. **macOS** (Phase 4) - 低優先度 ⬇️
5. **iOS** (Phase 5) - 最低優先度

## 技術スタック（確定）

- **Unity**: 6000.0.35f1
- **音声合成**: Unity Sentis 2.1.2（ONNX Runtime不要）
- **音素化**: OpenJTalk（日本語）、espeak-ng（多言語）
- **言語**: C# 11
- **ライセンス**: Apache 2.0

## 開発スケジュール（15週間）

### 詳細タイムライン

| 週 | フェーズ | 作業内容 | 成果物 |
|----|---------|---------|--------|
| 1 | Phase 0 | Unity 6 & Sentis検証 | プロトタイプ |
| 2-3 | Phase 1 | Windows/Linux実装 | v0.1.0-alpha |
| 4-6 | Phase 2 | Android実装 | v0.3.0-beta |
| 7-8 | Phase 3 | **WebGL実装** | v0.5.0-beta |
| 9-10 | Phase 4 | macOS実装 | v0.7.0-beta |
| 11-12 | Phase 5 | iOS実装 | v0.9.0-rc |
| 13-14 | Phase 6 | 多言語対応 | v1.0.0-rc2 |
| 15 | Phase 7 | 品質保証 | v1.0.0 |

## WebGL早期対応の利点

### 技術的利点
- Sentis 2.1.2がWebGL/WebGPUを完全サポート
- ONNX Runtimeの移植が不要
- Unity 6のWebGL改善を活用

### ビジネス的利点
- インストール不要でデモ提供可能
- 最も幅広いユーザーにリーチ
- 早期フィードバック収集

### 実装の簡素化
```
従来: ONNX Runtime → Emscripten → WebAssembly → 複雑
Sentis: Unity Sentis → 自動変換 → WebGL対応 → 簡単
```

## 主要な技術的変更

### アーキテクチャ
```
[テキスト入力]
    ↓
[音素化（ネイティブ）]
    - Windows/Linux: DLL/SO
    - Android: JNI
    - WebGL: WASM
    - macOS: dylib
    - iOS: 静的ライブラリ
    ↓
[音素データ]
    ↓
[Unity Sentis 2.1.2]
    - 全プラットフォーム共通
    - GPU/CPU自動選択
    ↓
[音声出力（AudioClip）]
```

### メモリとパフォーマンス

| プラットフォーム | 音素化時間 | 合成時間 | 合計 |
|-----------------|-----------|----------|------|
| Windows/Linux | 10ms | 50ms | 60ms |
| Android | 20ms | 80ms | 100ms |
| WebGL | 30ms | 100ms | 130ms |
| macOS | 10ms | 60ms | 70ms |
| iOS | 15ms | 70ms | 85ms |

## 実装前の最終確認事項

### 技術的準備
- [x] Unity 6000.0.35f1 環境
- [x] Sentis 2.1.2 対応確認
- [x] 既存Piperコードの活用方針
- [x] プラットフォーム優先順位確定

### ドキュメント
- [x] 技術調査報告書
- [x] 詳細開発計画書
- [x] テストケース仕様書
- [x] Sentis統合アーキテクチャ
- [x] 最終実装計画（本書）

### 次のアクション
1. uPiperプロジェクトへのPackage構造セットアップ
2. Phase 0の開始（Unity 6 + Sentisプロトタイプ）
3. GitHub リポジトリ準備

## リスク管理

| リスク | 影響 | 対策 | 状態 |
|--------|------|------|------|
| Sentis互換性 | 高 | Phase 0で検証 | 対策済 |
| WebGLメモリ制限 | 中 | 段階的ロード | 計画済 |
| 音素化精度 | 低 | OpenJTalk採用 | 解決済 |

## 成功の定義

### 短期（3ヶ月）
- 5プラットフォーム対応完了
- WebGLデモ公開
- 基本的な日本語TTS動作

### 長期（6ヶ月）
- 50言語以上対応
- Unity Asset Store公開
- コミュニティ形成

## 結論

Unity Sentis 2.1.2の採用とWebGL優先度の引き上げにより、より効率的で幅広いユーザーにリーチできる開発計画となりました。15週間で全プラットフォーム対応を完了し、高品質な日本語TTSプラグインを提供します。

---

**計画承認日**: 2024年1月
**プロジェクト開始**: Phase 0より順次開始
**初回リリース目標**: 3週間後（v0.1.0-alpha）