# WebAssembly実装推奨事項（2025年7月31日）

## エグゼクティブサマリー

PR #118でのMeCab直接実装は失敗したが、`wasm_open_jtalk`のアプローチ（OpenJTalk全体の移植）により、WebAssemblyでの日本語TTS実現は**技術的に可能**である。

## 推奨事項

### 1. 実装アプローチの転換

#### ❌ 避けるべきアプローチ（PR #118）
```
MeCab単独の移植 → 辞書フォーマット非互換 → 失敗
```

#### ✅ 推奨アプローチ
```
OpenJTalk全体の移植（wasm_open_jtalk） → 辞書互換性確保 → 成功可能性高
```

### 2. 具体的な実装計画

#### Phase 1: 技術検証（1週間）
1. **wasm_open_jtalkのフォーク**
   ```bash
   git clone https://github.com/hrhr49/wasm_open_jtalk
   cd wasm_open_jtalk
   ```

2. **Emscripten設定の変更**
   ```makefile
   # Makefileの修正
   EMCC_FLAGS = \
     -s ENVIRONMENT='web,worker' \
     -s MODULARIZE=1 \
     -s EXPORT_ES6=1 \
     -s EXPORTED_RUNTIME_METHODS='["FS", "cwrap", "ccall"]' \
     -s INITIAL_MEMORY=256MB \
     -s ALLOW_MEMORY_GROWTH=1
   ```

3. **最小限の動作確認**
   - 簡単なHTMLページで読み込みテスト
   - 基本的な音素変換の確認

#### Phase 2: ブラウザ最適化（1週間）
1. **辞書の最適化**
   - 頻出語辞書の作成（10MB以下）
   - gzip圧縮での配信
   - CDN活用

2. **JavaScript APIの設計**
   ```javascript
   class PiperWebTTS {
     async initialize() {
       this.openjtalk = await OpenJTalkModule();
       await this.loadDictionary();
     }
     
     async textToPhonemes(text) {
       return this.openjtalk.convertToPhonemes(text);
     }
     
     async synthesize(text) {
       const phonemes = await this.textToPhonemes(text);
       return this.onnxRuntime.run(phonemes);
     }
   }
   ```

3. **Web Worker統合**
   - メインスレッドのブロッキング回避
   - 非同期処理の実装

#### Phase 3: 本番実装（2週間）
1. **piper-plusとの統合**
   - 既存のONNX Runtime実装との接続
   - ストリーミング対応

2. **パフォーマンス最適化**
   - IndexedDBキャッシュ
   - 遅延初期化
   - メモリプーリング

3. **エラーハンドリング**
   - 辞書ロード失敗時のフォールバック
   - メモリ不足対応

### 3. リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 辞書サイズ（103MB） | 高 | CDN + 圧縮 + キャッシュ |
| 初期化時間 | 中 | Web Worker + 非同期初期化 |
| ブラウザ互換性 | 低 | Chrome/Edge優先 |
| メモリ使用量 | 中 | 段階的ロード + GC最適化 |

### 4. 成功指標

- **技術的成功**
  - 音素変換精度: PyOpenJTalk同等（95%以上）
  - 初期化時間: 3秒以内
  - 変換速度: 100ms/文以内

- **ユーザー体験**
  - 初回ロード: 5秒以内
  - 2回目以降: 即座に利用可能
  - オフライン動作: 可能

### 5. 代替案の評価

| 方式 | 実装難易度 | 精度 | オフライン | 推奨度 |
|------|------------|------|------------|--------|
| wasm_open_jtalk改良 | 中 | 高 | ✅ | ⭐⭐⭐⭐⭐ |
| kuromoji.js + カスタム辞書 | 低 | 中 | ✅ | ⭐⭐⭐ |
| Web Speech API | 極低 | 高 | ❌ | ⭐⭐ |
| サーバーAPI | 低 | 高 | ❌ | ⭐⭐⭐ |

## 結論

**推奨: wasm_open_jtalkアプローチでの実装を進める**

理由：
1. 技術的実現性が確認済み（Node.js版の存在）
2. PR #118の失敗原因が明確（アプローチの問題）
3. 辞書互換性の問題が解決済み
4. オフライン動作が可能
5. 高精度な音素変換が期待できる

## 次のステップ

1. **即座に実行可能**
   - wasm_open_jtalkのソースコード分析
   - ビルド環境の構築
   - 基本的な動作確認

2. **1週間以内**
   - ブラウザ対応のプロトタイプ作成
   - 技術的課題の洗い出し

3. **2週間以内**
   - Go/No-Go判定
   - 本格実装への移行

---

作成: Claude (AI技術アドバイザー)
日付: 2025年7月31日