# P3-003: DictLoader 分離

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: FR-301
> 依存チケット: P3-001
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

現在の `DictManager` (`src/wasm/openjtalk-web/src/dict-manager.js`) は OpenJTalk 辞書 (8 ファイル) と HTS voice ファイルの両方をダウンロード・キャッシュする。G2P パッケージでは HTS voice は不要であり、辞書ロードだけを独立して行える `DictLoader` クラスを提供する。また、IndexedDB キャッシュ + SHA-256 検証のロジックは `DictManager` から変更なく動作する品質であり、これを G2P パッケージとして再利用する。

### ゴール

- `DictLoader` クラスが辞書のみのダウンロード・キャッシュを行える (`includeVoice: false` がデフォルト)
- SHA-256 検証 (`verifySha256`) が独立関数として利用可能
- tar.gz 解凍 (`decompressGzip`) + tar パース (`parseTar`) が独立関数として利用可能
- IndexedDB キャッシュが正常に動作する (2 回目以降は即座にロード)
- 進捗コールバックがバイトレベルで報告される
- `piper-plus` 既存の `DictManager` から `DictLoader` への内部委譲が可能 (P3-005 で統合)

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 新規 | `src/wasm/g2p/src/dict-loader.js` | `DictLoader` クラス (辞書ダウンロード + IndexedDB キャッシュ) |
| 新規 | `src/wasm/g2p/src/utils/sha256.js` | SHA-256 検証ユーティリティ |
| 新規 | `src/wasm/g2p/src/utils/tar.js` | tar.gz 解凍 + tar パースユーティリティ |
| 新規 | `src/wasm/g2p/src/utils/idb.js` | IndexedDB ヘルパー (openDB, wrapRequest) |
| 新規 | `src/wasm/g2p/src/utils/fetch-progress.js` | プログレス付き fetch |
| 参照 | `src/wasm/openjtalk-web/src/dict-manager.js` | 移植元 (DictManager, 522 行) |

### 実装手順

1. **ユーティリティの分離**: `dict-manager.js` の内部ヘルパー関数を独立モジュールに分離する:
   - `sha256.js`: `verifySha256()` (Web Crypto API ベース)
   - `tar.js`: `decompressGzip()` (DecompressionStream API) + `parseTar()` (POSIX tar パーサー)
   - `idb.js`: `openDB()`, `wrapRequest()` (IndexedDB Promise ラッパー)
   - `fetch-progress.js`: `fetchWithProgress()` (ReadableStream + Content-Length)

2. **`DictLoader` クラスの作成**: `DictManager` をベースに以下を変更:
   - `loadDictionary()` → `loadJaDict()` にリネーム
   - `includeVoice` オプション追加 (デフォルト: `false`)
   - `voiceData` は `includeVoice: true` の場合のみダウンロード
   - `resolveUrls()` は辞書 URL のみ返す (voice URL は `includeVoice: true` 時のみ)
   - `DICT_TAR_GZ_URL`, `DICT_SHA256`, `TAR_ROOT_DIR` の定数は変更なし (GitHub Releases の同一 URL)
   - `DB_NAME` は `'piper-g2p-dict'` に変更 (`piper-plus-dict` との分離)

3. **キャッシュ分離**: G2P パッケージの IndexedDB データベース名を `piper-g2p-dict` に変更し、`piper-plus` の `piper-plus-dict` と独立させる。同一辞書データの二重キャッシュが懸念されるが、P3-005 互換レイヤーで `cachePrefix` の共有を検討する。

4. **subpath export の追加**: `package.json` に `"./dict": "./src/dict-loader.js"` を追加し、`import { DictLoader } from '@piper-plus/g2p/dict'` でアクセス可能にする。

### API / インターフェース

```javascript
// src/wasm/g2p/src/dict-loader.js

export class DictLoader {
    /**
     * @param {Object} [options]
     * @param {string} [options.cachePrefix='piper-g2p-dict']
     */
    constructor(options = {}) { ... }

    /**
     * 日本語 G2P 用辞書をダウンロード (or キャッシュから取得)。
     * @param {Object} [options]
     * @param {string} [options.dictUrl] - カスタム tar.gz URL
     * @param {boolean} [options.includeVoice=false] - HTS voice も取得するか
     * @param {string} [options.voiceUrl] - voice ファイル URL
     * @param {Function} [options.onProgress] - {loaded, total} コールバック
     * @returns {Promise<JaDictData>}
     */
    async loadJaDict(options = {}) { ... }

    /**
     * 辞書がキャッシュ済みかどうか。
     * @returns {Promise<boolean>}
     */
    async isCached() { ... }

    /**
     * キャッシュをクリア。
     * @returns {Promise<void>}
     */
    async clearCache() { ... }
}

// JaDictData
// {
//   dictFiles: Record<string, ArrayBuffer>,  // 8 辞書ファイル
//   voiceData?: ArrayBuffer,                  // includeVoice=true 時のみ
// }
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| フロントエンドエンジニア | 1 | DictLoader 実装、ユーティリティ分離 |
| テストエンジニア | 1 | IndexedDB モック、ダウンロード・キャッシュテスト |

---

## 4. テスト計画

### 提供範囲

- tar.gz ダウンロード + SHA-256 検証
- tar パース (8 辞書ファイルの抽出)
- IndexedDB キャッシュ (保存・取得・クリア)
- 進捗コールバック
- `includeVoice: false` のデフォルト動作
- カスタム辞書 URL 対応

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| SHA-256 | 既知ハッシュの検証成功・失敗 | 2 |
| tar パース | テスト用 tar から 8 ファイル抽出 | 2 |
| gzip 解凍 | 圧縮データの解凍 | 1 |
| IndexedDB | 保存 → 取得 → クリアのライフサイクル | 3 |
| DictLoader | `loadJaDict()` の正常系 (キャッシュあり/なし) | 2 |
| voice 省略 | `includeVoice: false` で voice ダウンロードがスキップされる | 1 |
| カスタム URL | `dictUrl` 指定時に SHA-256 検証がスキップされる | 1 |
| 進捗コールバック | `onProgress` が呼ばれる回数と引数の検証 | 1 |
| エラー処理 | ダウンロード失敗、SHA-256 不一致、必須ファイル欠損 | 3 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| フルパイプライン | `DictLoader.loadJaDict()` → `G2P.create({jaDict})` → `phonemize()` |
| キャッシュ動作 | 1 回目: ダウンロード、2 回目: IndexedDB から即座にロード |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **IndexedDB の二重キャッシュ**: `piper-plus` (DB: `piper-plus-dict`) と `@piper-plus/g2p` (DB: `piper-g2p-dict`) で同一辞書データが二重にキャッシュされる。P3-005 の互換レイヤーで `cachePrefix` を共有するか、`DictLoader` 側で `piper-plus-dict` からのマイグレーションを検討する。
2. **DecompressionStream API の可用性**: Chrome 80+, Firefox 113+, Safari 16.4+ で利用可能。NFR-301 のブラウザ互換性要件と一致するが、古いブラウザ向けの polyfill は提供しない (要件外)。
3. **Node.js 対応**: `indexedDB` と `DecompressionStream` は Node.js ではネイティブ利用不可。Node.js 18+ では `globalThis.crypto.subtle` は利用可能。Node.js 対応は NFR-301 の要件だが、IndexedDB のモック or fallback が必要になる。
4. **辞書ファイルサイズ**: tar.gz は約 5MB。ブラウザのストレージ制限 (通常 50MB+) には十分だが、`DictLoader` は `getUsage()` のようなクォータチェック機能は持たない。

### レビュー項目

- [ ] SHA-256 ハッシュ値が `dict-manager.js` の `DICT_SHA256` と一致
- [ ] tar パーサーが UStar prefix 対応 (bytes 345-499)
- [ ] 必須 8 ファイル (`char.bin`, `matrix.bin`, `sys.dic`, `unk.dic`, `left-id.def`, `right-id.def`, `pos-id.def`, `rewrite.def`) の欠損チェック
- [ ] `includeVoice: false` 時に voice 関連の fetch が発生しない
- [ ] IndexedDB エラー (プライベートブラウジング等) 時のフォールバック動作が定義されている

---

## 6. 一から作り直すとしたら

`DictManager` の設計は堅実で、SHA-256 検証、tar パース、IndexedDB キャッシュ、進捗コールバックの実装品質は高い。一から作り直すなら:

- **辞書と voice のライフサイクルを最初から分離する**。G2P は辞書のみ、TTS は辞書 + voice。現在は `loadDictionary()` が両方を返す設計で、G2P 単体利用時に不要な voice ダウンロードが発生する。
- **キャッシュレイヤーを汎用化する**。`CacheManager` (`src/wasm/openjtalk-web/src/cache-manager.js`) が既に存在するが、`DictManager` は独自の IndexedDB 管理を持つ。キャッシュレイヤーを統一し、辞書・モデル・voice が同一のキャッシュ戦略で管理されるようにする。
- **ストリーミング tar パースを検討する**。現在は tar 全体をメモリに読み込んでからパースする。5MB 程度なら問題ないが、将来的な辞書サイズ増加に備えてストリーミングパーサーを検討してもよい。

---

## 7. 後続タスクへの連絡事項

- **P3-002 (OpenJTalk WASM DI 化)**: `DictLoader.loadJaDict()` が返す `JaDictData.dictFiles` の形式は `OpenJTalkAdapter.initialize(dictFiles)` が受け取る形式と一致させる。
- **P3-005 (互換レイヤー)**: `piper-plus` の `DictManager` を `DictLoader` に内部委譲する際、`cachePrefix` の共有戦略を決定する。二重キャッシュを避けるために `DictLoader({cachePrefix: 'piper-plus-dict'})` を推奨。
- **P3-008 (安定版リリース)**: バンドルサイズ検証で `dict-loader.js` + ユーティリティのサイズを計測する。tree-shaking で `DictLoader` を使わない場合にバンドルから除外されることを確認。
