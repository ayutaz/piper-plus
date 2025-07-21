# Task 0.2 技術調査レポート

作成日: 2025-07-21

## エグゼクティブサマリー

Task 0.2では、MeCabとOpenJTalkの既存WebAssembly実装を調査し、piper-plus WebAssembly実装の実現可能性を評価しました。

**結論**: 技術的に実現可能。既存実装を参考に、Chrome PC限定で高品質な実装が可能。

## 調査結果

### 1. 既存実装の成熟度

#### MeCab
- **複数の実装が存在**: 成熟した技術
- **推奨実装**: mecab-web-worker (leyhline)
- **動作確認**: Chrome最新版で安定動作
- **辞書処理**: ZIP圧縮、動的ロード確立

#### OpenJTalk
- **Node.js実装のみ**: wasm_open_jtalk
- **ブラウザ対応**: 未実装だが技術的に可能
- **課題**: 辞書サイズ（103MB）の最適化必要

### 2. ビルドプロセス

確立されたビルドプロセス：
```bash
# 1. Emscriptenでコンパイル
emconfigure ./configure --with-charset=utf8
emmake make

# 2. WebAssemblyモジュール生成
em++ -O3 -s WASM=1 -s MODULARIZE=1 --bind
```

### 3. 技術的制約と解決策

| 制約 | 影響 | 解決策 |
|-----|------|--------|
| メモリ制限 | 高 | 辞書圧縮、段階的ロード |
| SharedArrayBuffer | 中 | Web Worker分離 |
| 初期化時間 | 中 | キャッシュ、プログレッシブロード |
| Unity WebGL | 高 | メモリ最適化、分割処理 |

## 実装可能性評価

### 技術的実現性: ✅ 高い

**根拠**:
1. MeCab WebAssembly実装が安定稼働
2. OpenJTalkのNode.js実装が存在
3. Emscriptenツールチェーンが成熟
4. Chrome限定で最新技術活用可能

### 推定工数

| フェーズ | 内容 | 工数 |
|---------|------|------|
| MeCab統合 | 既存実装ベース | 3-5日 |
| OpenJTalk移植 | ブラウザ対応追加 | 5-7日 |
| 辞書最適化 | 圧縮、選定 | 3-4日 |
| 統合テスト | 動作確認 | 2-3日 |

**合計**: 13-19日（約3週間）

## リスクと対策

### 高リスク項目
1. **辞書サイズ（103MB）**
   - 対策: 段階的実装（10MB → 5MB → 2-3MB）
   - 頻度ベース語彙選定
   - Brotli圧縮

2. **Unity WebGLメモリ制限**
   - 対策: 分割ロード実装
   - メモリプール管理
   - ガベージコレクション最適化

### 中リスク項目
1. **ブラウザ互換性**
   - 対策: Chrome PC限定
   - Feature detection実装
   - Graceful degradation

## 推奨実装アプローチ

### Phase 1: MeCab WebAssembly実装（3-5日）
```javascript
// mecab-web-workerをベースに実装
import { MecabWorker } from './mecab-worker';

const worker = await MecabWorker.create('/dict/ipadic-min.zip');
const tokens = await worker.parse('こんにちは世界');
```

### Phase 2: OpenJTalk統合（5-7日）
```javascript
// wasm_open_jtalkをブラウザ対応
import { OpenJTalkModule } from './openjtalk-wasm';

const oj = await OpenJTalkModule.create();
await oj.loadDictionary('/dict/openjtalk-min.zip');
const phonemes = await oj.textToPhonemes('こんにちは世界');
```

### Phase 3: 統合とテスト（2-3日）
```javascript
// 統合API
export class PiperPhonemizerWASM {
    async initialize(config) {
        this.mecab = await MecabWorker.create(config.mecabDict);
        this.openjtalk = await OpenJTalkModule.create();
        await this.openjtalk.loadDictionary(config.ojDict);
    }
    
    async textToPhonemes(text) {
        const tokens = await this.mecab.parse(text);
        return await this.openjtalk.processTokens(tokens);
    }
}
```

## 次のステップ（Task 0.3）

1. **MeCab WebAssemblyプロトタイプ作成**
   - mecab-web-workerのフォーク
   - Chrome最適化実装
   - 最小辞書での動作確認

2. **メモリ使用量測定**
   - Chrome DevToolsでプロファイリング
   - Unity WebGLでのメモリテスト
   - ベンチマーク作成

3. **Go/No-Go判定準備**
   - 技術検証結果まとめ
   - リスク評価更新
   - 実装計画最終化

## 結論と推奨事項

### 結論
WebAssembly実装は技術的に実現可能。既存実装をベースに、3週間程度で基本実装が完成見込み。

### 推奨事項
1. **Chrome PC限定で開発開始**
2. **段階的辞書最適化アプローチ採用**
3. **既存実装（mecab-web-worker）をベースに開発**
4. **Unity WebGL統合は別フェーズで対応**

### 成功の鍵
- 既存実装の有効活用
- Chrome最新機能の積極採用
- 段階的な最適化アプローチ
- 継続的なパフォーマンス測定

以上の調査により、piper-plus WebAssembly実装の技術的実現性が確認されました。