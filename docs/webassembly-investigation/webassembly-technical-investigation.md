# Piper WebAssembly技術調査レポート

## 調査日: 2025-07-21

## エグゼクティブサマリー

本調査は、piper-plusプロジェクトのWebAssembly対応（Issue #106）に向けた技術的実現可能性と実装戦略について詳細に検討したものです。調査の結果、WebAssembly実装は技術的に十分実現可能であり、既存のツールとライブラリを活用することで、効率的な実装が可能であることが判明しました。

## 1. 技術スタック評価

### 1.1 コア技術の対応状況

| コンポーネント | WebAssembly対応 | 成熟度 | 備考 |
|---------------|----------------|--------|------|
| **ONNX Runtime** | ✅ 完全対応 | 高 | WebGPU/WebGL/WASM backends完備 |
| **eSpeak-NG** | ✅ 公式対応 | 高 | ChromeOSで本番運用実績 |
| **MeCab** | ✅ 実装済み | 中 | コミュニティによる移植版が存在 |
| **OpenJTalk** | ⚠️ 未対応 | - | 新規移植が必要 |
| **HTS Engine** | ❌ 未対応 | - | ONNX Runtimeで代替予定 |

### 1.2 ブラウザサポート状況（2025年7月現在）

| 機能 | Chrome | Firefox | Safari | Edge |
|------|--------|---------|--------|------|
| WebAssembly | ✅ | ✅ | ✅ | ✅ |
| SIMD | ✅ | ✅ | ✅ | ✅ |
| WebGPU | ✅ 113+ | 🚧 開発中 | ❌ | ✅ 113+ |
| AudioWorklet | ✅ | ✅ | ✅ | ✅ |
| Memory64 | ✅ | ✅ | ❌ | ✅ |

## 2. 実装アーキテクチャ

### 2.1 システム構成図

```
┌─────────────────────────────────────────────────────────────┐
│                     ブラウザ環境                              │
├─────────────────────────────────────────────────────────────┤
│                  JavaScript/TypeScript API                     │
│                     (@piper-tts/wasm)                         │
├──────────────────┬────────────────┬──────────────────────────┤
│   Text Processing │  Audio Synthesis │     Audio Output       │
│  ┌─────────────┐ │ ┌──────────────┐│ ┌──────────────────┐ │
│  │   MeCab     │ │ │ONNX Runtime  ││ │  AudioWorklet    │ │
│  │   (WASM)    │ │ │    Web       ││ │   + Web Audio    │ │
│  ├─────────────┤ │ │ (WebGPU/WASM)││ └──────────────────┘ │
│  │ OpenJTalk   │ │ └──────────────┘│                       │
│  │  (WASM)     │ │                  │                       │
│  └─────────────┘ │                  │                       │
├──────────────────┴────────────────┴──────────────────────────┤
│                    WebAssembly Runtime                         │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 データフロー

```mermaid
graph LR
    A[テキスト入力] --> B[形態素解析<br/>MeCab WASM]
    B --> C[音素変換<br/>OpenJTalk WASM]
    C --> D[音素エンコード]
    D --> E[ONNX推論<br/>ONNX Runtime Web]
    E --> F[音声波形生成]
    F --> G[AudioWorklet<br/>再生]
```

## 3. 技術的課題と解決策

### 3.1 メモリ管理

**課題**:
- WebAssemblyの線形メモリモデルの制約
- 大規模な辞書データの効率的な管理
- リアルタイム処理でのメモリ断片化

**解決策**:
```javascript
// メモリプール実装例
class WasmMemoryPool {
    constructor(initialSize = 16 * 1024 * 1024) { // 16MB
        this.memory = new WebAssembly.Memory({
            initial: initialSize / 65536,
            maximum: 256 * 1024 * 1024 / 65536 // 256MB max
        });
        this.allocations = new Map();
    }
    
    allocate(size) {
        // カスタムアロケータ実装
        const aligned = (size + 7) & ~7; // 8バイトアライメント
        // ... allocation logic
    }
}
```

### 3.2 辞書最適化戦略

**現状の課題**:
- sys.dic: 99MB（非圧縮）
- unk.dic: 4MB
- 合計: 103MB

**最適化アプローチ**:

1. **頻度ベース辞書分割**
```python
# 辞書分析スクリプト（概念）
def analyze_dictionary_usage():
    word_frequencies = analyze_corpus(large_japanese_corpus)
    
    tiers = {
        'minimal': top_n_words(5000),      # 2-3MB
        'standard': top_n_words(30000),    # 10-15MB
        'full': top_n_words(100000)        # 30-40MB
    }
    
    return optimize_dictionary(tiers)
```

2. **圧縮技術の適用**
- Brotli圧縮: ~80%サイズ削減
- 辞書特化圧縮: トライ木構造の最適化
- 差分エンコーディング

3. **プログレッシブローディング**
```javascript
class ProgressiveDictionary {
    async load(level = 'minimal') {
        // 基本辞書をロード
        await this.loadBase();
        
        // 必要に応じて追加辞書をロード
        if (level === 'standard' || level === 'full') {
            await this.loadExtended();
        }
    }
}
```

### 3.3 パフォーマンス最適化

**ONNX Runtime Web最適化**:
```javascript
// WebGPU使用時の設定
const sessionOptions = {
    executionProviders: [{
        name: 'webgpu',
        deviceType: 'gpu',
        powerPreference: 'high-performance'
    }],
    graphOptimizationLevel: 'all',
    enableCpuMemArena: false,
    enableMemPattern: false
};
```

**ベンチマーク結果（推定）**:
| バックエンド | 推論時間 | 相対速度 |
|-------------|---------|----------|
| WASM (CPU) | 100ms | 1.0x |
| WebGL | 50ms | 2.0x |
| WebGPU | 5-10ms | 10-20x |

## 4. 実装ロードマップ

### Phase 1: MVP (4-6週間)
- [x] 技術調査（完了）
- [ ] 開発環境構築
- [ ] eSpeak-NG WebAssembly統合
- [ ] 基本的な音声合成

### Phase 2: 日本語対応 (3-4週間)
- [ ] MeCab WebAssembly統合
- [ ] OpenJTalk移植
- [ ] 最小辞書作成
- [ ] 日本語音声合成

### Phase 3: 最適化 (2-3週間)
- [ ] WebGPU対応
- [ ] プログレッシブ辞書
- [ ] ストリーミング実装
- [ ] パフォーマンスチューニング

### Phase 4: プロダクション化 (2週間)
- [ ] npmパッケージ化
- [ ] ドキュメント整備
- [ ] デモサイト構築
- [ ] CI/CD設定

## 5. リスク評価

| リスク | 影響 | 確率 | 対策 |
|--------|------|------|------|
| 辞書サイズ削減の限界 | 高 | 中 | 早期プロトタイプで検証 |
| WebGPU非対応ブラウザ | 中 | 高 | フォールバック実装 |
| 初期化時間の長さ | 中 | 中 | 遅延ロード、キャッシング |
| メモリ使用量超過 | 高 | 低 | メモリプール、GC戦略 |

## 6. 競合分析

### 既存のWebAssembly TTS実装

| プロジェクト | 言語サポート | 技術スタック | 特徴 |
|-------------|-------------|-------------|------|
| MeloTTS | 多言語（日本語含む） | PyTorch → ONNX | CPU最適化 |
| Sherpa-ONNX | 英語のみ | ONNX Runtime | WebAssemblyデモあり |
| eSpeak-NG WASM | 多言語 | C++ → WASM | 軽量、音質は低め |

**Piperの優位性**:
- 高品質なVITSベースの音声合成
- 日本語に特化した最適化
- オープンソース、カスタマイズ可能

## 7. 推奨事項

### 7.1 技術選定
1. **音素化**: OpenJTalk + MeCab（日本語）、eSpeak-NG（その他）
2. **音声合成**: ONNX Runtime Web（WebGPU優先）
3. **音声出力**: AudioWorklet + Web Audio API
4. **ビルドツール**: Emscripten 3.1.61+（最新版）

### 7.2 実装優先順位
1. **最優先**: 日本語最小辞書での動作確認
2. **高**: WebGPUによる高速化
3. **中**: プログレッシブエンハンスメント
4. **低**: 完全辞書サポート

### 7.3 品質基準
- 初期化時間: < 1秒（最小辞書）
- メモリ使用量: < 50MB（ピーク時）
- 音声生成遅延: < 100ms（文あたり）
- 音質: MOS 4.0以上

## 8. 結論

WebAssembly実装は技術的に実現可能であり、以下の理由から推進を推奨します：

1. **技術的成熟度**: 必要な技術要素はすべて利用可能
2. **パフォーマンス**: WebGPUにより実用的な速度を達成可能
3. **ユーザー価値**: オフライン動作、プライバシー保護
4. **差別化**: 高品質な日本語TTSのブラウザ実装は希少

推定開発期間: 10-12週間（フルタイム1名想定）

## 付録

### A. 参考実装
- [eSpeak-NG WebAssembly](https://github.com/espeak-ng/espeak-ng/tree/master/emscripten)
- [MeCab WebAssembly](https://github.com/alexbirch/mecab-wasm)
- [ONNX Runtime Web Examples](https://github.com/microsoft/onnxruntime-inference-examples/tree/main/js)

### B. 技術リソース
- [WebAssembly仕様](https://webassembly.github.io/spec/)
- [Emscriptenドキュメント](https://emscripten.org/docs/)
- [Web Audio API](https://www.w3.org/TR/webaudio/)

---

作成: Claude (Anthropic)
最終更新: 2025-07-21