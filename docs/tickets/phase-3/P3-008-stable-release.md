# P3-008: 安定版リリース (v1.0.0)

> Phase: 3 (JS/WASM)
> マイルストーン: v1.0.0
> 対応要求: FR-300, NFR-300, NFR-301, NFR-302
> 依存チケット: P3-001, P3-002, P3-003, P3-004, P3-005, P3-006, P3-007
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

v0.1.0 (ベータ) でのユーザーフィードバックを反映し、API を安定化させた v1.0.0 をリリースする。バンドルサイズの最適化 (tree-shaking 対応、subpath exports)、ブラウザ互換性の最終検証、ドキュメントの整備を行う。

### ゴール

- npm publish: `@piper-plus/g2p@1.0.0` (provenance 付き)
- バンドルサイズ: JA なし < 30KB gzip, JA 込み (辞書除く) < 430KB gzip
- Tree-shaking: webpack / Vite / Rollup で未使用言語がバンドルから除外される
- ブラウザ互換: Chrome 80+, Firefox 113+, Safari 16.4+ で動作検証済み
- Node.js 互換: Node.js 18+ で動作検証済み
- 既存 `piper-plus` パッケージとの完全互換
- pua_compat_version: 1 (Python/Rust と互換)
- README.md + API ドキュメントが完備

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 変更 | `src/wasm/g2p/package.json` | version: 1.0.0、exports 最終調整、files フィールド |
| 変更 | `src/wasm/g2p/src/index.js` | tree-shaking 対応の re-export 構造 |
| 新規 | `src/wasm/g2p/README.md` | npm README (API リファレンス、Getting Started) |
| 変更 | `src/wasm/g2p/src/ja/index.js` | v0.1.0 フィードバック反映 |
| 変更 | `src/wasm/g2p/src/en/index.js` | v0.1.0 フィードバック反映 |

### 実装手順

1. **v0.1.0 フィードバック収集と反映**: npm でのベータ公開後、ユーザーからの Issue/Feature Request を収集し、v1.0.0 に反映する。想定されるフィードバック領域:
   - API の使いやすさ (メソッド名、引数の構造)
   - 型定義の精度
   - バンドルサイズへの懸念
   - 特定ブラウザでの不具合

2. **Tree-shaking 対応**:
   - `package.json` の `exports` フィールドで subpath exports を最終定義
   - `sideEffects: false` を設定
   - 各モジュールが独立して import 可能なことを確認
   - webpack / Vite / Rollup それぞれでバンドルサイズを計測

   ```json
   {
     "name": "@piper-plus/g2p",
     "version": "1.0.0",
     "type": "module",
     "sideEffects": false,
     "exports": {
       ".": {
         "types": "./types/index.d.ts",
         "default": "./src/index.js"
       },
       "./ja": {
         "types": "./types/ja.d.ts",
         "default": "./src/ja/index.js"
       },
       "./en": {
         "types": "./types/en.d.ts",
         "default": "./src/en/index.js"
       },
       "./zh": {
         "types": "./types/zh.d.ts",
         "default": "./src/zh/index.js"
       },
       "./es": {
         "types": "./types/es.d.ts",
         "default": "./src/es/index.js"
       },
       "./fr": {
         "types": "./types/fr.d.ts",
         "default": "./src/fr/index.js"
       },
       "./pt": {
         "types": "./types/pt.d.ts",
         "default": "./src/pt/index.js"
       },
       "./detect": {
         "types": "./types/detect.d.ts",
         "default": "./src/detect.js"
       },
       "./dict": {
         "types": "./types/dict.d.ts",
         "default": "./src/dict-loader.js"
       },
       "./encode": {
         "types": "./types/encode.d.ts",
         "default": "./src/encode.js"
       },
       "./custom-dict": {
         "types": "./types/custom-dict.d.ts",
         "default": "./src/custom-dictionary.js"
       }
     },
     "files": [
       "src/",
       "dist/",
       "types/",
       "README.md",
       "LICENSE"
     ],
     "engines": {
       "node": ">=18.0.0"
     },
     "pua_compat_version": 1
   }
   ```

3. **バンドルサイズ検証**:

   | コンポーネント | サイズ上限 (gzip) | 計測方法 |
   |---------------|-----------------|---------|
   | JS コード (全言語) | < 30KB | `gzip -c src/**/*.js | wc -c` |
   | OpenJTalk WASM | < 400KB | `gzip -c dist/openjtalk.wasm | wc -c` |
   | JA なし合計 | < 30KB | tree-shaking で JA 除外後のバンドル |
   | JA 込み合計 (辞書除く) | < 430KB | 全言語バンドル + WASM |

4. **ブラウザ互換性テスト**:
   - Chrome 80+ (DecompressionStream, crypto.subtle, indexedDB)
   - Firefox 113+ (DecompressionStream)
   - Safari 16.4+ (DecompressionStream)
   - BrowserStack or Playwright で自動テスト

5. **README.md 作成**: npm パッケージの README として以下を含む:
   - Getting Started (インストール + 基本使用例)
   - API リファレンス (G2P, DictLoader, encode)
   - 対応言語一覧
   - subpath exports の使い方
   - `piper-plus` との関係
   - ライセンス情報

6. **pua_compat_version メタデータ**: `package.json` に `"pua_compat_version": 1` を追加。Python (`piper-g2p`) / Rust (`piper-g2p`) と PUA テーブルの互換性を保証する。

### API / インターフェース

(v0.1.0 からの API 変更がある場合、ここに記載。想定は変更なし。)

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| リードエンジニア | 1 | v0.1.0 フィードバックの分析・優先順位付け、API 安定化判断 |
| フロントエンドエンジニア | 1 | tree-shaking 対応、バンドルサイズ最適化 |
| テストエンジニア | 1 | ブラウザ互換性テスト、バンドルサイズ計測 |
| テクニカルライター | 1 | README.md、API ドキュメント |

---

## 4. テスト計画

### 提供範囲

- バンドルサイズが閾値以下
- Tree-shaking が 3 バンドラーで動作
- ブラウザ互換性 (3 ブラウザ)
- Node.js 互換性 (18/20/22)
- 既存 piper-plus 282 テスト全通過
- npm publish --dry-run が成功

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| バンドルサイズ | 各コンポーネントの gzip サイズが閾値以下 | 4 |
| tree-shaking (webpack) | JA 未使用時に WASM がバンドルに含まれない | 1 |
| tree-shaking (Vite) | 同上 | 1 |
| tree-shaking (Rollup) | 同上 | 1 |
| pua_compat | PUA テーブルのバージョンが Python/Rust と一致 | 1 |
| sideEffects | `sideEffects: false` で import 時に副作用なし | 2 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| Chrome | G2P.create() → phonemize() → encode() が Chrome 80+ で動作 |
| Firefox | 同上、Firefox 113+ |
| Safari | 同上、Safari 16.4+ |
| Node.js 18 | 同上、Node.js 18 (最低バージョン) |
| piper-plus 統合 | `piper-plus` + `@piper-plus/g2p` の組み合わせでフル TTS パイプラインが動作 |
| npm install | 新規プロジェクトで `npm install @piper-plus/g2p` → import → phonemize() が動作 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **v0.1.0 のユーザー数**: ベータ版の利用者が少ない場合、十分なフィードバックが得られない。npm の weekly download 数とGitHub Issues を監視し、最低 1 ヶ月のベータ期間を設ける。
2. **破壊的変更の必要性**: v0.1.0 フィードバックで API 変更が必要な場合、v0.2.0 を挟んでから v1.0.0 をリリースする。SemVer 0.x.x は破壊的変更を許容する。
3. **WASM バイナリのバージョニング**: OpenJTalk WASM バイナリのバージョンが `@piper-plus/g2p` のバージョンと独立して変わる可能性がある。WASM の変更は MINOR バージョン bump とする。
4. **セキュリティ**: npm provenance で supply chain security を担保する。`npm audit` でゼロ脆弱性を確認する。
5. **ライセンスファイル**: `MIT` ライセンスファイルを `src/wasm/g2p/LICENSE` に配置。OpenJTalk (BSD-3-Clause) のライセンス表記も `NOTICE` ファイルに含める。

### レビュー項目

- [ ] `package.json` の `version` が `1.0.0` である
- [ ] バンドルサイズが NFR-300 の閾値を全て満たす
- [ ] `sideEffects: false` が設定されている
- [ ] `files` フィールドで `src/`, `dist/`, `types/`, `README.md`, `LICENSE` のみ含まれる
- [ ] `peerDependencies` に `onnxruntime-web` が含まれていない
- [ ] `engines.node` >= 18.0.0 が設定されている
- [ ] `pua_compat_version: 1` が設定されている
- [ ] README.md が Getting Started + API リファレンスを含む
- [ ] LICENSE ファイルが MIT で、NOTICE に OpenJTalk の BSD-3-Clause 表記がある
- [ ] `npm publish --dry-run` で意図したファイルのみが含まれる
- [ ] npm provenance が正しく設定されている

---

## 6. 一から作り直すとしたら

v1.0.0 リリースの準備を振り返ると、バンドルサイズの最適化と tree-shaking 対応が最も工数がかかる。一から作り直すなら:

- **パッケージ構造を最初から tree-shaking 対応で設計する**。1 ファイルに複数の class を定義せず、1 ファイル 1 export を徹底する。
- **WASM バイナリを npm パッケージに含めない**。代わりに `DictLoader` と同様に CDN / GitHub Releases から実行時ダウンロードする。これによりインストールサイズが大幅に削減される。ただし初回ロード時間とのトレードオフ。
- **ESM only を最初から宣言する**。CJS fallback を一切用意しない (Node.js 18+ は ESM ネイティブ対応)。
- **README 駆動開発**: README を最初に書き、API のユーザー体験を設計してから実装する。

---

## 7. 後続タスクへの連絡事項

- **piper-plus v2**: `@piper-plus/g2p@1.0.0` の安定後、`piper-plus` 本体の次期バージョンで `@piper-plus/g2p` を正式 dependency に昇格。
- **新言語追加**: v1.0.0 以降の MINOR バージョンで韓国語 (KO) 等の言語追加。PUA エントリ追加は MINOR bump。
- **Python/Rust との PUA 同期**: `pua_compat_version: 1` が 3 パッケージで同期されていることを定期的に確認。PUA テーブル変更時は全パッケージで同時に `pua_compat_version` を bump する。
- **ユーザーフィードバックの継続収集**: v1.0.0 後も GitHub Issues と npm の weekly downloads を監視し、PATCH リリースの判断材料とする。
