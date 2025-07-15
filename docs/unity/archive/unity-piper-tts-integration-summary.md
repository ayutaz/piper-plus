# Unity Piper TTS 統合計画サマリー

## プロジェクト概要

Unity 6000.0.35f1 と Sentis 2.1.2 を使用した、クロスプラットフォーム対応の日本語TTSプラグイン開発。

## 主要な技術決定

### 1. アーキテクチャ
```
テキスト → [音素化（ネイティブ）] → 音素 → [Sentis] → 音声
```

- **音素化**: OpenJTalk/espeak-ng（プラットフォーム別ネイティブライブラリ）
- **音声合成**: Unity Sentis 2.1.2（ONNX Runtime不要）

### 2. 技術スタック
- **Unity**: 6000.0.35f1
- **言語**: C# 11
- **AI推論**: Unity Sentis 2.1.2
- **音素化**: OpenJTalk（日本語）、espeak-ng（多言語）
- **ビルド**: CMake、Emscripten（WebGL）

### 3. 主要な利点
- ONNX Runtimeが不要（バイナリサイズ33%削減）
- クロスプラットフォーム対応が簡素化
- Unity内で音声合成が完結

## 開発フェーズ（15週間）

### Phase 0: Unity 6 & Sentis検証（1週間）
- Unity 6環境確認
- Sentis 2.1.2動作確認
- 最小プロトタイプ作成

### Phase 1: Windows/Linux（2週間）
- 音素化ライブラリ実装
- Sentis統合
- 基本API完成

### Phase 2: Android（3週間）
- NDKビルド
- JNI統合
- モバイル最適化

### Phase 3: WebGL（2週間）
- Emscriptenビルド
- Sentis WebGPU対応
- ブラウザデモ公開

### Phase 4: macOS（2週間）
- Universal Binary対応
- コード署名

### Phase 5: iOS（2週間）
- 静的ライブラリビルド
- App Store対応

### Phase 6: 多言語対応（2週間）
- espeak-ng統合
- 50言語以上サポート

### Phase 7: 品質保証（1週間）
- 最終テスト
- ドキュメント完成
- リリース準備

## 成果物

### パッケージ構成
```
com.piper.tts/
├── Runtime/          # C#スクリプト
├── Editor/           # エディタ拡張
├── Models/           # ONNXモデル
├── Plugins/          # 音素化ライブラリ
└── package.json      # Unity Package定義
```

### 配布方法
1. Unity Package Manager（Git URL）
2. OpenUPM
3. Unity Asset Store（将来）

## リスクと対策

| リスク | 対策 |
|--------|------|
| Sentis互換性 | Phase 0で早期検証 |
| WebGLメモリ制限 | 段階的ロード実装 |
| 辞書サイズ | 圧縮とストリーミング |

## 成功指標

### 技術指標
- 音素化精度: 98%（OpenJTalk）
- 処理速度: <100ms/文
- メモリ使用量: <100MB

### ビジネス指標
- 5プラットフォーム対応
- 50言語以上サポート
- Apache 2.0ライセンス

## 次のステップ

1. **WebGL優先順位決定完了** ✅
   - WebGLをPhase 3に配置（macOSより優先）
   - Sentisによる実装簡素化を活用

2. **Phase 0開始準備**
   - uPiperプロジェクトセットアップ
   - Sentis 2.1.2インストール
   - 開発環境構築

3. **リポジトリ準備**
   - GitHub設定
   - CI/CD初期設定
   - ドキュメント整備

## 関連ドキュメント

1. [技術調査報告書](unity-plugin-investigation-ja.md)
2. [詳細開発計画書](unity-piper-tts-development-plan.md)
3. [テストケース仕様書](unity-piper-tts-test-cases.md)
4. [Sentis統合アーキテクチャ](unity-piper-tts-sentis-architecture.md)
5. [優先順位再検討](unity-piper-tts-revised-priorities.md)

---

**プロジェクトステータス**: 計画完了、実装準備完了