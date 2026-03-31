# P3-007: CI ワークフロー

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: NFR-300
> 依存チケット: P3-001, P3-006
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

`@piper-plus/g2p` パッケージの品質を自動的に保証する CI ワークフローを構築する。テスト、型チェック、lint、パッケージサイズ検証、npm publish を自動化する。既存の `piper-plus` CI (`ci.yml`, `npm-publish.yml`) と共存し、G2P パッケージ専用のトリガーとマトリクスで動作する。

### ゴール

- `g2p-wasm-ci.yml` が PR/push 時に自動実行される (パス: `src/wasm/g2p/**`)
- テストマトリクス: 3 OS (ubuntu, macos, windows) x Node.js 18/20/22
- `tsc --noEmit --strict` が CI で実行される
- パッケージサイズ (gzip) が閾値を超えた場合に fail する
- タグ `wasm-g2p-v*` で npm publish ジョブが起動する
- 既存 `piper-plus` の 282 テストが回帰しないことを確認する

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 新規 | `.github/workflows/g2p-wasm-ci.yml` | G2P WASM CI ワークフロー |
| 新規 | `.github/workflows/g2p-wasm-publish.yml` | npm publish ワークフロー |
| 新規 | `src/wasm/g2p/scripts/check-bundle-size.js` | バンドルサイズ検証スクリプト |
| 参照 | `.github/workflows/ci.yml` | 既存 piper-plus CI (参考) |
| 参照 | `.github/workflows/npm-publish.yml` | 既存 npm publish (参考) |

### 実装手順

1. **`g2p-wasm-ci.yml` の作成**:

   ```yaml
   name: G2P WASM CI

   on:
     push:
       branches: [dev, main]
       paths:
         - 'src/wasm/g2p/**'
     pull_request:
       paths:
         - 'src/wasm/g2p/**'

   jobs:
     test:
       runs-on: ${{ matrix.os }}
       strategy:
         matrix:
           os: [ubuntu-latest, macos-latest, windows-latest]
           node-version: [18, 20, 22]
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: ${{ matrix.node-version }}
         - run: cd src/wasm/g2p && npm ci
         - run: cd src/wasm/g2p && npm test
         - run: cd src/wasm/g2p && npx tsc --noEmit --strict

     bundle-size:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: 22
         - run: cd src/wasm/g2p && npm ci
         - run: cd src/wasm/g2p && node scripts/check-bundle-size.js

     piper-plus-regression:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: 22
         - run: cd src/wasm/openjtalk-web && npm ci
         - run: cd src/wasm/openjtalk-web && npm test
   ```

2. **`g2p-wasm-publish.yml` の作成**:

   ```yaml
   name: G2P WASM Publish

   on:
     push:
       tags:
         - 'wasm-g2p-v*'

   jobs:
     publish:
       runs-on: ubuntu-latest
       permissions:
         id-token: write
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: 22
             registry-url: 'https://registry.npmjs.org'
         - run: cd src/wasm/g2p && npm ci
         - run: cd src/wasm/g2p && npm test
         - run: cd src/wasm/g2p && npx tsc --noEmit --strict
         - run: cd src/wasm/g2p && node scripts/check-bundle-size.js
         - run: cd src/wasm/g2p && npm publish --provenance --access public
           env:
             NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
   ```

3. **`check-bundle-size.js` の作成**: gzip 後のサイズを計測し、閾値を超えた場合にエラー:

   ```javascript
   // 閾値 (NFR-300 準拠)
   const LIMITS = {
       'JS (全言語, gzip)': { path: 'src/**/*.js', limit: 30 * 1024 },
       'WASM (gzip)': { path: 'dist/openjtalk.wasm', limit: 400 * 1024 },
       'JA なし合計 (gzip)': { computed: true, limit: 30 * 1024 },
       'JA 込み合計 (gzip, 辞書除く)': { computed: true, limit: 430 * 1024 },
   };
   ```

4. **テスト実行の設定**: `src/wasm/g2p/package.json` の `test` スクリプトを設定:
   ```json
   {
     "scripts": {
       "test": "node --test test/**/*.test.js",
       "typecheck": "tsc --noEmit --strict",
       "check-size": "node scripts/check-bundle-size.js"
     }
   }
   ```

### API / インターフェース

(CI ワークフローのためインターフェースなし)

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| DevOps エンジニア | 1 | CI ワークフロー設計・実装、npm publish 設定 |
| テストエンジニア | 1 | バンドルサイズ検証スクリプト、回帰テスト確認 |

---

## 4. テスト計画

### 提供範囲

- CI ワークフローが正しくトリガーされる
- テストマトリクスが全 OS x Node バージョンで pass する
- バンドルサイズ検証が閾値を正しく判定する
- npm publish が正しくトリガーされる (dry-run)
- 既存 piper-plus テストの回帰テスト

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| check-bundle-size | 閾値以下で success、超過で failure | 2 |
| CI トリガー | `src/wasm/g2p/**` 変更時のみ起動 (他パス変更時は不起動) | 2 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| CI 実行 | PR 作成時にワークフローが起動し、全ジョブが pass |
| publish dry-run | `npm publish --dry-run` でパッケージ内容の確認 |
| provenance | npm provenance が正しく付与される |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **OpenJTalk WASM バイナリの CI 取得**: テスト実行には OpenJTalk WASM バイナリが必要。CI で WASM をビルドするか、事前ビルド済みバイナリを取得するか。事前ビルド済みを `dist/` に含めるか、CI artifact から取得するか。
2. **Node.js 18 での互換性**: `DecompressionStream`, `crypto.subtle` は Node.js 18 で利用可能だが、`indexedDB` は Node.js にネイティブでない。テスト時に `fake-indexeddb` 等のモックが必要。
3. **CI 実行時間**: 3 OS x 3 Node バージョン = 9 ジョブ。WASM 初期化を含むテストは時間がかかる可能性がある。テストの並列化やキャッシュの活用が必要。
4. **npm provenance**: `--provenance` フラグは GitHub Actions の OIDC トークンを使用する。リポジトリの Actions 設定で `id-token: write` 権限が必要。
5. **monorepo 構成**: `src/wasm/g2p/` と `src/wasm/openjtalk-web/` が同一リポジトリ内にある場合、`npm ci` で `@piper-plus/g2p` をローカルから解決する必要がある。npm workspaces の導入を検討。

### レビュー項目

- [ ] `g2p-wasm-ci.yml` のパスフィルタが `src/wasm/g2p/**` に限定されている
- [ ] テストマトリクスが 3 OS x 3 Node バージョン (18/20/22)
- [ ] `tsc --noEmit --strict` が CI に含まれている
- [ ] バンドルサイズ閾値が NFR-300 と一致 (JS < 30KB gzip, WASM < 400KB gzip)
- [ ] npm publish タグが `wasm-g2p-v*` パターン
- [ ] `--provenance` フラグが publish ジョブに含まれている
- [ ] 既存 piper-plus テスト (282) の回帰チェックジョブが含まれている

---

## 6. 一から作り直すとしたら

CI の設計を振り返ると、`piper-plus` と `@piper-plus/g2p` が同一リポジトリ内の別パッケージとして存在し、CI ワークフローが分散している。一から作り直すなら:

- **npm workspaces (monorepo)** を最初から導入する。`package.json` のルートに `workspaces: ["src/wasm/g2p", "src/wasm/openjtalk-web"]` を設定し、パッケージ間の依存解決を npm に任せる。
- **統合 CI ワークフロー**を作成する。パス変更に基づいて影響範囲を自動判定し、必要なパッケージのテストのみ実行する。Nx / Turborepo のようなモノレポツールの採用を検討。
- **バンドルサイズの自動レポート**を PR コメントに出力する。`bundlesize` / `size-limit` のようなツールを使い、PR ごとにサイズ変化を可視化する。

---

## 7. 後続タスクへの連絡事項

- **P3-008 (安定版リリース)**: v1.0.0 リリース時に `wasm-g2p-v1.0.0` タグをプッシュして publish ジョブを起動する。
- **P3-005 (互換レイヤー)**: `piper-plus-regression` ジョブで `piper-plus` のテストが pass することを確認。互換レイヤーの変更は `ci.yml` と `g2p-wasm-ci.yml` の両方でテストされる必要がある。
- **P3-006 (TypeScript 型定義)**: `tsc --noEmit --strict` ステップは本チケットで CI に追加。P3-006 の型定義ファイルが正しいことの自動検証。
