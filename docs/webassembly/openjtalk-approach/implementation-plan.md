# WebAssembly OpenJTalkアプローチ - 実装計画書

作成日: 2025-07-31
プロジェクト: piper-plus WebAssembly対応

## 1. 実装概要

### 1.1 プロジェクト目標
ブラウザ上で動作する高精度な日本語音声合成システムの実現
- PyOpenJTalk同等の音素変換精度
- オフライン動作可能
- 主要ブラウザ対応（Chrome/Edge優先）

### 1.2 技術アーキテクチャ
```
[ブラウザ]
    ↓
[JavaScript API層]
    ↓
[WebAssembly (OpenJTalk)]
    ↓
[ONNX Runtime Web (Piper音声合成)]
    ↓
[Web Audio API]
```

## 2. 実装フェーズ

### Phase 1: 基礎実装（2週間）

#### Week 1: 環境構築とプロトタイプ
1. **wasm_open_jtalkのフォーク**
   ```bash
   git clone https://github.com/hrhr49/wasm_open_jtalk
   cd wasm_open_jtalk
   ```

2. **ビルド環境の構築**
   - Emscripten 3.1.x のセットアップ
   - Docker環境の準備（再現性確保）

3. **ブラウザ対応ビルド設定**
   ```makefile
   EMCC_FLAGS = \
     -s ENVIRONMENT='web,worker' \
     -s MODULARIZE=1 \
     -s EXPORT_ES6=1 \
     -s EXPORTED_RUNTIME_METHODS='["FS","cwrap","ccall"]' \
     -s INITIAL_MEMORY=256MB \
     -s ALLOW_MEMORY_GROWTH=1 \
     -s FILESYSTEM=1 \
     -s FORCE_FILESYSTEM=1
   ```

4. **最小動作確認**
   - 基本的なHTMLテストページ
   - コンソールでの動作確認

#### Week 2: 基本API実装
1. **JavaScript APIラッパー**
   ```javascript
   class OpenJTalkWeb {
     async initialize(dictUrl, voiceUrl) {
       this.module = await OpenJTalkModule();
       await this.loadDictionary(dictUrl);
       await this.loadVoice(voiceUrl);
     }
     
     async textToPhonemes(text) {
       return this.module.ccall(
         'text_to_phonemes',
         'string',
         ['string'],
         [text]
       );
     }
   }
   ```

2. **辞書ロード機能**
   - Fetch APIでの辞書ダウンロード
   - Emscripten FSへの書き込み
   - エラーハンドリング

3. **基本的なデモページ**
   - テキスト入力
   - 音素変換結果表示
   - エラー表示

### Phase 2: 最適化と統合（2週間）

#### Week 3: パフォーマンス最適化
1. **辞書の最適化**
   - 辞書圧縮（gzip/brotli）
   - 頻出語辞書の作成
   - 段階的ロード実装

2. **メモリ最適化**
   - メモリプロファイリング
   - 不要データの削除
   - GC最適化

3. **初期化時間短縮**
   - WebAssembly Streaming
   - 非同期初期化
   - プリロード実装

#### Week 4: Piper統合
1. **ONNX Runtime Web統合**
   ```javascript
   class PiperWebTTS {
     async initialize() {
       this.openjtalk = new OpenJTalkWeb();
       this.onnxRuntime = new PiperONNXRuntime();
       await Promise.all([
         this.openjtalk.initialize(),
         this.onnxRuntime.loadModel()
       ]);
     }
     
     async synthesize(text) {
       const phonemes = await this.openjtalk.textToPhonemes(text);
       const audio = await this.onnxRuntime.synthesize(phonemes);
       return audio;
     }
   }
   ```

2. **ストリーミング対応**
   - チャンク単位の処理
   - プログレッシブ音声生成

3. **Web Audio統合**
   - AudioContext管理
   - バッファリング
   - 再生制御

### Phase 3: プロダクション対応（1週間）

1. **Web Worker実装**
   - メインスレッドのブロッキング回避
   - 並列処理対応

2. **キャッシング戦略**
   - IndexedDBでの辞書キャッシュ
   - Service Workerでのアセットキャッシュ

3. **エラーハンドリング**
   - ネットワークエラー対応
   - メモリ不足対応
   - フォールバック実装

4. **CDN配信準備**
   - アセットの最適化
   - バージョニング
   - キャッシュヘッダー設定

## 3. 技術的実装詳細

### 3.1 ディレクトリ構造
```
src/wasm/openjtalk-web/
├── build/              # ビルド設定
│   ├── Dockerfile
│   ├── build.sh
│   └── emscripten-flags.mk
├── src/               # ソースコード
│   ├── openjtalk_wrapper.cpp
│   ├── api.js
│   └── worker.js
├── dist/              # ビルド成果物
│   ├── openjtalk.js
│   ├── openjtalk.wasm
│   └── openjtalk.d.ts
├── demo/              # デモページ
│   ├── index.html
│   ├── demo.js
│   └── style.css
└── test/              # テスト
    ├── unit/
    ├── integration/
    └── benchmark/
```

### 3.2 ビルドパイプライン
```bash
# Dockerを使用したビルド
docker build -t piper-openjtalk-web .
docker run -v $(pwd)/dist:/dist piper-openjtalk-web

# ローカルビルド
./build/build.sh
```

### 3.3 API設計
```typescript
interface OpenJTalkWeb {
  initialize(config: OpenJTalkConfig): Promise<void>;
  textToPhonemes(text: string): Promise<string[]>;
  textToLabels(text: string): Promise<Label[]>;
  destroy(): void;
}

interface OpenJTalkConfig {
  dictUrl?: string;
  voiceUrl?: string;
  useWorker?: boolean;
  cacheEnabled?: boolean;
}

interface Label {
  phoneme: string;
  start: number;
  duration: number;
}
```

## 4. 品質保証

### 4.1 テスト戦略
1. **単体テスト**
   - API関数のテスト
   - エラーケースのテスト

2. **統合テスト**
   - エンドツーエンドテスト
   - ブラウザ互換性テスト

3. **パフォーマンステスト**
   - 初期化時間測定
   - 変換速度測定
   - メモリ使用量測定

### 4.2 成功指標
| 指標 | 目標値 | 測定方法 |
|------|--------|----------|
| 音素変換精度 | 95%以上 | PyOpenJTalkとの比較 |
| 初期化時間（初回） | 5秒以内 | Performance API |
| 初期化時間（キャッシュ済） | 1秒以内 | Performance API |
| 変換速度 | 100ms/文 | Performance API |
| メモリ使用量 | 256MB以内 | Chrome DevTools |

## 5. リスク管理

### 5.1 技術的リスク
| リスク | 可能性 | 影響 | 対策 |
|--------|--------|------|------|
| Emscriptenバージョン非互換 | 中 | 高 | Docker環境で固定 |
| 辞書サイズ問題 | 高 | 中 | 段階的最適化 |
| ブラウザメモリ制限 | 中 | 高 | メモリプロファイル + 最適化 |
| 初期化時間超過 | 中 | 中 | 非同期 + プログレス表示 |

### 5.2 対策計画
1. **週次進捗レビュー**
2. **早期プロトタイプでの検証**
3. **段階的リリース**
4. **フォールバック実装**

## 6. デリバリー計画

### 6.1 マイルストーン
- **M1（Week 1）**: 基本動作確認
- **M2（Week 2）**: API実装完了
- **M3（Week 3）**: 最適化完了
- **M4（Week 4）**: Piper統合完了
- **M5（Week 5）**: プロダクション準備完了

### 6.2 成果物
1. **ライブラリ**
   - openjtalk-web.js
   - TypeScript定義ファイル
   - ドキュメント

2. **デモ**
   - オンラインデモページ
   - 統合サンプル

3. **ドキュメント**
   - API リファレンス
   - 統合ガイド
   - トラブルシューティング

## 7. 今後の拡張計画

### 7.1 短期（3ヶ月）
- Firefox/Safari対応
- 軽量辞書オプション
- React/Vue コンポーネント

### 7.2 中期（6ヶ月）
- WebGPU活用
- マルチ話者対応
- リアルタイムストリーミング

### 7.3 長期（1年）
- 完全なオフライン対応
- プログレッシブWebApp
- 音声認識統合

## 8. 承認事項

本実装計画は、技術的実現性を確認した上で作成されています。
実装を開始する前に、以下の点について承認が必要です：

1. Chrome/Edge優先のブラウザサポート戦略
2. 5週間の開発期間
3. 辞書サイズ最適化の段階的アプローチ

---

承認者: _______________
日付: _______________