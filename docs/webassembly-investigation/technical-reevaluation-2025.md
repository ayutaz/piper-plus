# WebAssembly実装の技術的再評価（2025年7月）

## 背景

PR #118では、MeCabをWebAssemblyで実装しようとしたが、辞書フォーマットの非互換性により失敗した（精度0%）。その後、`wasm_open_jtalk`の存在により、新たな可能性が見えてきた。

## 技術的再評価

### 1. 過去の実装（PR #118）の問題点

#### アプローチ
- MeCabを直接WebAssembly化
- NAIST-JDIC辞書（102MB）の直接読み込み
- DARTS（Double Array Trie）の独自実装

#### 失敗原因
1. **辞書フォーマットの非互換性**
   - ルートノード構造が非標準的（base=-2, check=199）
   - 公式仕様書が存在しない
   - リバースエンジニアリングの限界

2. **文頭文字の欠落**
   - DARTS検索が機能せず
   - 結果として未知語処理のみが動作

### 2. wasm_open_jtalkの調査結果

#### 既存の調査（2025年7月21日時点）
- Node.js CLI専用として記載
- ブラウザ対応は未実装と判断

#### 今回の再調査（2025年7月31日）
- **確認済み事項**:
  - OpenJTalk全体のWebAssembly化に成功
  - `open_jtalk.js`と`open_jtalk.wasm`を生成
  - Node.js環境で正常動作
  - 辞書読み込みも成功

- **重要な発見**:
  - MeCabだけでなくOpenJTalk全体が移植されている
  - 辞書フォーマットの問題は解決済み

### 3. 技術的可能性の再評価

#### なぜPR #118は失敗したか
- **間違ったアプローチ**: MeCabを単独で移植しようとした
- **正しいアプローチ**: OpenJTalk全体を移植する（wasm_open_jtalkのアプローチ）

#### wasm_open_jtalkをブラウザ対応させる方法

1. **Emscriptenの設定変更**
   ```javascript
   // Node.js専用設定から
   -s ENVIRONMENT='node'
   
   // ブラウザ対応設定へ
   -s ENVIRONMENT='web,worker,node'
   -s MODULARIZE=1
   -s EXPORT_ES6=1
   ```

2. **ファイルシステムの対応**
   ```javascript
   // 辞書ファイルの事前埋め込み
   --preload-file dict/naist-jdic@/dict
   
   // または動的ロード
   FS.createPreloadedFile('/dict', 'sys.dic', 'dict/sys.dic', true, false);
   ```

3. **メモリ設定の最適化**
   ```javascript
   -s INITIAL_MEMORY=256MB
   -s ALLOW_MEMORY_GROWTH=1
   -s MAXIMUM_MEMORY=512MB
   ```

### 4. 実装可能性評価

#### ✅ 技術的に可能な理由

1. **実証済みの基盤**
   - wasm_open_jtalkがOpenJTalkの完全な移植に成功
   - 辞書互換性の問題は解決済み

2. **Emscriptenの成熟度**
   - 大規模C++プロジェクトの移植実績多数
   - ファイルシステムエミュレーション機能

3. **既存の成功例**
   - mecab-web-worker（MeCabのブラウザ実装）
   - その他のC++ライブラリのWASM移植例

#### ⚠️ 課題と対策

1. **辞書サイズ（103MB）**
   - **対策**: CDN配信 + IndexedDBキャッシュ
   - 初回のみダウンロード、以降はローカルキャッシュ

2. **初期化時間**
   - **対策**: Web Worker + 非同期初期化
   - バックグラウンドでの事前ロード

3. **メモリ使用量**
   - **対策**: 必要最小限の辞書のみロード
   - 使用頻度の低い辞書は遅延ロード

## 推奨実装戦略

### Phase 1: wasm_open_jtalkのブラウザ対応（2週間）
1. wasm_open_jtalkをフォーク
2. Emscripten設定をブラウザ対応に変更
3. 基本的な動作確認

### Phase 2: 最適化と統合（2週間）
1. 辞書の圧縮と最適化
2. Web Worker統合
3. piper ONNXモデルとの接続

### Phase 3: プロダクション対応（1週間）
1. CDN配信設定
2. キャッシュ戦略実装
3. エラーハンドリング

## 結論

**実装推奨度: ✅ 高**

理由：
1. PR #118の失敗原因が明確（アプローチの誤り）
2. 正しいアプローチ（OpenJTalk全体の移植）の実例が存在
3. 技術的な障壁は既に解決済み

**次のアクション**：
1. wasm_open_jtalkをフォークしてブラウザ対応を試みる
2. 小規模なPOCで動作確認
3. 成功したら本格的な実装へ移行

---

作成日: 2025年7月31日
作成者: Claude (技術調査AI)