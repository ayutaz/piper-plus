# M2-3: CI ワークフローへのテスト統合

**マイルストーン**: M2
**依存チケット**: M2-1, M2-2
**後続チケット**: M3-1, M3-2

## タスク目的とゴール

M2-1 / M2-2 で作成したテストファイルを CI ワークフローに統合し、PR ごとに自動実行されるようにする。既存テストが壊れないことを確認する。

## 実装する内容の詳細

### 1. `.github/workflows/test-webassembly.yml` の更新

新規テストファイル `test-piper-plus-wasm-g2p.js` を既存の実行ステップに追加する:

```yaml
- name: Run WASM G2P integration tests
  working-directory: src/wasm/openjtalk-web
  run: node --test test/js/test-piper-plus-wasm-g2p.js
```

### 2. `package.json` テストスクリプトの更新

`src/wasm/openjtalk-web/package.json` の `scripts.test` に新規テストファイルを追加:

```json
{
  "scripts": {
    "test": "node --test test/js/test-piper-plus.js test/js/test-npm-package.js test/js/test-piper-plus-wasm-g2p.js",
    "test:wasm-g2p": "node --test test/js/test-piper-plus-wasm-g2p.js"
  }
}
```

### 3. 既存テストの影響確認

以下の既存テストが引き続きパスすることを確認:
- `npm test` (メインテストスイート)
- `npm run test:optimization` (最適化テスト)
- 個別テスト: `test-piper-plus-g2p-init.js`, `test-piper-plus-init-success.js` など

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| CI エンジニア | 1 | ワークフロー更新、package.json 更新、既存テストの回帰確認 |

## 提供範囲

- `.github/workflows/test-webassembly.yml` の更新
- `src/wasm/openjtalk-web/package.json` の `scripts` セクション更新
- 既存テストの回帰なし確認

## テスト項目

### ユニットテスト

| # | テストケース | 検証内容 |
|---|------------|----------|
| 1 | 新規テスト実行 | `test-piper-plus-wasm-g2p.js` が CI で全パス |
| 2 | 既存テスト回帰なし | `npm test` が引き続きパス |
| 3 | 個別実行 | `npm run test:wasm-g2p` が正常動作 |

### E2E テスト

| # | テストケース | 検証内容 |
|---|------------|----------|
| 1 | CI ワークフロー実行 | `test-webassembly.yml` が PR で自動トリガーされること |
| 2 | パス条件 | `src/wasm/**` の変更で CI がトリガーされること |

## 懸念事項

- **WASM バイナリの CI 可用性**: 新規テストは `import()` をモックするため実 WASM バイナリは不要だが、将来的に実バイナリを使うテストを追加する場合、CI で WASM ビルドが必要になる。現在の `test-webassembly.yml` は Emscripten セットアップを含むが、Rust WASM (`wasm-pack`) のビルドステップはない
- **テスト実行順序**: Node.js の `--test` ランナーはファイル順に実行する。グローバルモック (`globalThis.fetch` 等) の汚染が次テストに影響しないよう、各テストファイルで `afterEach` リストアを徹底すること
- **CI タイムアウト**: 現在の `timeout-minutes: 30` は新規テスト追加後も十分な余裕がある (モックテストは高速)

## レビュー項目

- [ ] `test-webassembly.yml` に新規テスト実行ステップが追加されていること
- [ ] `package.json` の `test` スクリプトに新規ファイルが含まれていること
- [ ] `test:wasm-g2p` 個別実行スクリプトが追加されていること
- [ ] CI ワークフローのパストリガー (`paths`) が `src/wasm/**` をカバーしていること (既存で対応済みのはず)
- [ ] 既存の全テストが引き続きパスすること

## 一から作り直すとしたら

CI で実 WASM バイナリを使った E2E テストの実行を検討すべきである。現在の全 WASM テストはモックベースであり、以下のリスクがある:

- Rust WASM API の変更 (引数、戻り値の型) がモックに反映されず、テストは通るが実環境で壊れる
- `phonemize()` の出力互換性が検証できない

改善案:
- **`wasm-build.yml` との連携**: 既存の `wasm-build.yml` ワークフローでビルドされた WASM バイナリを artifact として保存し、`test-webassembly.yml` でダウンロードして実テストに使う
- **Playwright ブラウザテスト**: CI で Playwright を使い、デモページを serve してブラウザ内で E2E テストを実行する。WASM ロード + ONNX 推論を含む完全な統合テスト
- **テスト分離**: モックテスト (高速、PR ごと) と E2E テスト (低速、マージ前 or nightly) を分離する

## 後続タスクへの連絡事項

- M3-1 / M3-2 は手動ブラウザテストだが、将来的に CI 自動化する場合はこの CI ワークフローを拡張する
- 新規テストファイルを追加する際は `package.json` の `test` スクリプトと `test-webassembly.yml` の両方を更新すること
- `wasm-build.yml` で WASM バイナリ artifact を公開する仕組みが整ったら、実バイナリテストの CI ジョブを追加検討すること
