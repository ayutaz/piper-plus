# Task 0.5 実装方針最終案

作成日: 2025-07-21

## 実装方針概要

技術検証の成功を受け、以下の方針でPiper-plus WebAssembly実装を進めます。

## 基本方針

### 1. 段階的実装アプローチ

**原則**: Small Start, Quick Win, Iterative Improvement

```
Phase 0 (完了): 技術検証 ✅
Phase 1 (4週間): 日本語音素化基盤
Phase 2 (2週間): ONNX Runtime統合  
Phase 3 (2週間): 最適化・ブラウザ統合
Phase 4 (2週間): Unity WebGL統合
Phase 5 (2週間): テスト・品質保証
```

### 2. 技術スタック確定

| レイヤー | 技術選定 | 理由 |
|---------|---------|------|
| **ビルドツール** | Emscripten 3.1.61+ | 安定性・実績 |
| **音素化** | MeCab + OpenJTalk | 日本語精度 |
| **推論** | ONNX Runtime Web | 公式サポート |
| **音声処理** | AudioWorklet | 低遅延 |
| **最適化** | SIMD + WebGPU | Chrome最適化 |

### 3. 制約と割り切り

- **ブラウザ**: Chrome限定（将来拡張前提）
- **プラットフォーム**: PC Web限定（モバイル非対応）
- **Unity**: Unity 6000+（WebGL 2.0必須）

## Phase 1: 日本語音素化基盤（4週間）

### Week 1-2: MeCab WebAssembly本実装

```cpp
// 実装優先順位
1. MeCabコア機能のWebAssembly化
2. 最小辞書（10MB）での動作確認  
3. Embindインターフェース実装
4. 基本的なエラーハンドリング
```

**成果物**:
- `mecab_wasm.wasm` (本番用)
- `MeCabWrapper.js` (JavaScriptインターフェース)
- 単体テストスイート

### Week 3: OpenJTalk統合

```cpp
// 実装内容
1. OpenJTalkテキスト解析部の移植
2. MeCabとの統合
3. 音素列生成機能
4. PUAマッピング実装
```

**成果物**:
- `openjtalk_wasm.wasm`
- 音素化APIの完成
- 統合テスト

### Week 4: 辞書圧縮Phase 1

```
目標: 103MB → 50MB
手法:
1. 不要フィールド削除
2. バイナリ形式最適化
3. 基本的な圧縮（zlib）
```

**成果物**:
- 圧縮辞書フォーマット仕様
- 辞書ローダー実装
- パフォーマンステスト結果

## Phase 2: ONNX Runtime統合（2週間）

### Week 5: ONNX Runtime Web初期統合

```javascript
// 実装構成
1. ONNX Runtime Web読み込み
2. モデルローディング機構
3. 推論パイプライン構築
4. WebGPUバックエンド設定
```

**成果物**:
- ONNX統合レイヤー
- モデルローダー
- 推論ベンチマーク

### Week 6: エンドツーエンド統合

```javascript
// 統合フロー
Text → MeCab → OpenJTalk → Phonemes → ONNX → Audio
```

**成果物**:
- 完全な音声合成パイプライン
- デモページ
- パフォーマンスレポート

## Phase 3: 最適化・ブラウザ統合（2週間）

### Week 7: パフォーマンス最適化

**最適化項目**:
1. SIMD有効化（-msimd128）
2. WebAssembly Streaming
3. Worker並列化検討
4. キャッシング戦略

**目標メトリクス**:
- 初期化: < 2秒
- 生成遅延: < 300ms
- メモリ: < 100MB

### Week 8: Web Audio統合

```javascript
// AudioWorklet実装
class TTSProcessor extends AudioWorkletProcessor {
    process(inputs, outputs, parameters) {
        // 低遅延音声処理
    }
}
```

**成果物**:
- AudioWorklet実装
- ストリーミング再生
- 音声品質評価

## Phase 4: Unity WebGL統合（2週間）

### Week 9: JavaScript Bridge実装

```csharp
// Unity側インターフェース
[DllImport("__Internal")]
private static extern void InitializeTTS(string config);

[DllImport("__Internal")]
private static extern void SynthesizeSpeech(string text, string voiceId);
```

```javascript
// piper-tts.jslib
var PiperTTSPlugin = {
    InitializeTTS: function(configPtr) {
        // WebAssembly TTSの初期化
    },
    SynthesizeSpeech: function(textPtr, voiceIdPtr) {
        // 音声合成実行
    }
};
```

### Week 10: Unity統合テスト

**テスト項目**:
- メモリ制限確認
- 音声再生統合
- エラーハンドリング
- パフォーマンス測定

## Phase 5: テスト・品質保証（2週間）

### Week 11: 包括的テスト

**テストカバレッジ**:
1. 単体テスト（各モジュール）
2. 統合テスト（E2E）
3. パフォーマンステスト
4. ブラウザ互換性テスト

### Week 12: 最終調整・リリース準備

**作業内容**:
- ドキュメント完成
- デモサイト構築
- パフォーマンスチューニング
- リリースビルド作成

## 実装優先順位

### Must Have (必須)
1. ✅ MeCab WebAssembly基本実装
2. ✅ Chrome対応
3. ✅ 基本的な日本語音声合成
4. ✅ 50MB以下の辞書

### Should Have (推奨)
1. ⏳ ONNX Runtime WebGPU活用
2. ⏳ Unity WebGL統合
3. ⏳ 10MB以下の辞書圧縮
4. ⏳ AudioWorklet実装

### Nice to Have (あれば良い)
1. ⏸ 他ブラウザ対応
2. ⏸ 2-3MBの最終辞書圧縮
3. ⏸ Web Worker並列化
4. ⏸ 複数話者対応

## 技術的決定事項

### 1. モジュール構成

```
piper-wasm/
├── mecab/          # MeCab WebAssembly
├── openjtalk/      # OpenJTalk WebAssembly  
├── runtime/        # ONNX Runtime統合
├── audio/          # Web Audio処理
├── unity/          # Unity Bridge
└── demo/           # デモ・サンプル
```

### 2. ビルド設定

```cmake
# 共通フラグ
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s WASM=1")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s MODULARIZE=1")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s ENVIRONMENT=web")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -msimd128")  # Chrome SIMD

# メモリ設定
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s INITIAL_MEMORY=64MB")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s MAXIMUM_MEMORY=256MB")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s ALLOW_MEMORY_GROWTH=1")
```

### 3. API設計

```typescript
// TypeScript定義
interface PiperTTS {
    initialize(config: TTSConfig): Promise<void>;
    synthesize(text: string, options?: SynthesisOptions): Promise<AudioBuffer>;
    synthesizeStreaming(text: string, options?: SynthesisOptions): ReadableStream<AudioChunk>;
    getVoices(): Voice[];
    dispose(): void;
}

interface TTSConfig {
    wasmPath: string;
    modelPath: string;
    dictionaryPath: string;
    workletPath?: string;
}
```

## 品質基準

### パフォーマンス基準

| メトリクス | 目標 | 許容範囲 |
|-----------|------|----------|
| 初期化時間 | < 2秒 | < 3秒 |
| 音声生成遅延 | < 300ms | < 500ms |
| メモリ使用量 | < 100MB | < 150MB |
| CPU使用率 | < 30% | < 50% |

### 品質指標

- テストカバレッジ: > 80%
- エラー率: < 0.1%
- 音声品質: MOS > 3.5

## リリース戦略

### 1. アルファ版（Week 6）
- 基本機能動作
- Chrome限定
- 限定ユーザーテスト

### 2. ベータ版（Week 10）
- Unity統合完了
- パフォーマンス最適化
- 公開ベータテスト

### 3. 正式版（Week 12）
- 全機能実装
- ドキュメント完備
- プロダクション対応

## 成功の定義

1. **技術的成功**
   - すべてのパフォーマンス目標達成
   - Unity WebGL統合成功
   - 安定動作（エラー率 < 0.1%）

2. **ユーザー価値**
   - ブラウザで日本語TTS実現
   - 低遅延・高品質
   - 簡単な統合

3. **将来性**
   - 他ブラウザ拡張可能
   - 継続的な最適化基盤
   - コミュニティ貢献

## 結論

本実装方針は、技術検証で実証された実現可能性に基づき、段階的かつ確実な実装を目指します。Chrome限定という制約を受け入れつつ、高品質な日本語WebAssembly TTSの実現を最優先とします。

各フェーズでの成果物と品質基準を明確にし、12週間での完成を目指します。