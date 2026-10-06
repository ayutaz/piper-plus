# Issue #760: 実装と検証記録

検証日: 2026-10-06 JST。対象: [Issue #760](https://github.com/ayutaz/piper-plus/issues/760)。
基準: `dev` の `b044ca55c193741b3bff8c2aa43b3e3cc9a2fe07`。
関連: [調査](issue-760-wasm-demo-investigation.md)、[TDD・CI 計画](issue-760-wasm-demo-tdd-ci-plan.md)。

## 修正した動作

モデルの公開 `session.inputMetadata` から話者入力の dtype / shape を読み取り、静的な embedding 幅と mask の rank に合わせて Tensor を作る。未指定の embedding はモデルが宣言する幅のゼロ配列、mask は 0。指定時は有限値・長さを検証し、宣言された shape の mask を 1 にする。入力が宣言されていない場合は追加しない。

動的な embedding 幅では指定配列の長さを使う。未指定の幅を推測せず、metadata 不足、非対応 dtype / rank、解決できない mask 幅は明示エラーにする。WebGPU から WASM へセッションを再作成するときにも入力定義を読み直す。

公開 metadata を持つ ONNX Runtime Web **1.22.0 以上**を対応条件にした。package / lockfile / デモ CDN / README / runtime 一覧 / migration / CHANGELOG を整合させ、npm パッケージの次版を **0.8.0**として準備した。Python、PyTorch、native ORT のバージョンは変更していない。

## TDD と不具合検出の証拠

| 検証 | 実行結果 |
| --- | --- |
| 実装前の新規テスト（RED、commit `ff9581da`） | 12 件中 8 件失敗、4 件成功、skip 0、exit 1。helper 不在と実 ORT Web の shape エラーを検出 |
| 実装前の CI 構成テスト | 8 件失敗。必須 job / matrix / gate / 共通 script の不足を検出 |
| 修正後、実 ORT Web 1.22.0（GREEN） | 36 件成功、失敗 0、skip 0 |
| 修正後、実 ORT Web 1.30.0 | 36 件成功、失敗 0、skip 0 |
| ゼロ embedding を 192 固定へ一時的に戻した試験 | exit 1。回帰テストが不一致を検出 |
| mask を rank 1 固定へ一時的に戻した試験 | exit 1。回帰テストが rank 不一致を検出 |
| helper import / 256 次元 fixture をそれぞれ一時的に欠落 | いずれも exit 1。skip 成功にはならない |
| 正常 suite に `test.skip` を一時追加 | JUnit 検査で exit 1。必須 suite の skip を拒否 |
| 最終的な npm package 全体 | 844 件、843 件成功、失敗 0、既存の別テスト 1 件 skip |
| CI 構成の契約テスト | 9 件成功。success 以外の gate 結果を拒否 |

一時的な改変はすべて戻してから GREEN を再実行した。実 runtime 試験は `executionProviders: ['wasm']`、Node 24、`numThreads=1`。native ORT や推論成功のモックではない。小型 ONNX fixture は 192 / 256 / 320 次元、rank 1 / 2、mask なし、embedding なし、動的幅を含み、embedding と mask が出力に影響する演算を持つ。現在の fixture は 279–594 bytes。生成 script と SHA-256 manifest を同梱した。

Windows ローカルの実行ログは `%TEMP%/piper-plus-760-*.log` に保存。CI は同じ入口 `npm run test:onnx-inputs` と JUnit を使い、実行 runtime のバージョンも出力する。

## 実モデルを使ったブラウザ検証

Chromium / Playwright、実 Rust G2P WASM、実 ORT Web 1.22.0 で **3 テスト成功**（最終実行 41.9 秒）。モデル / config は `test/browser/models.json` の revision と SHA-256 に固定し、取得時とキャッシュ再利用時に検証する。ネットワークの配布先のみ localhost の検証済み asset へ向け、推論・G2P・再生は実際に実行する。デモが要求する CDN の runtime バージョンと試験 runtime の一致も検証する。

| ページ / モデル | 確認内容 |
| --- | --- |
| 公式デモ / CSS10 | 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語の 6 言語で UI から合成、WAV を取得し decode / 再生 |
| README importmap 例 / Tsukuyomi | README 本文から HTML を抽出して初期化・合成・実 AudioBuffer 再生 |
| README Basic Usage 例 / Tsukuyomi | README 本文の JavaScript を実行して初期化・合成・実 AudioBuffer 再生 |

CSS10 の 6 ファイルすべてで RIFF/WAVE、22050 Hz の WAV header、サンプル数 > 0、有限かつ非ゼロの音声を確認した。Tsukuyomi も有限かつ非ゼロの再生 buffer を確認。pageerror / console error はなし。WAV、ページ screenshot、JUnit、失敗時 trace を CI artifact として保存する。

これは合成・音声データ・ブラウザ再生の機械的検証である。自然さや声の品質に関する人手の聴取評価は未実施。

## PR CI とマージ条件

- `wasm-onnx-contract` は `dev` 向け全 PR で常時実行し、ORT Web 1.22.0 / 1.30.0 の両方を固定して試験する。path filter と `continue-on-error` は使用しない。
- `ci-required` はこの matrix job の success のみを許容する。failure / cancelled / skipped は失敗にする。構成の契約テスト自身も常時 job で実行する。
- 既存 npm job は実 WASM build 後、公開モデルのブラウザ試験を実行する。`test-webassembly.yml` と npm publish の検証にも共通の実 ONNX 試験を追加した。
- Pages 公開後は `PIPER_PLUS_DEMO_URL` を指定した同じ CSS10 ブラウザ試験で、配布中の runtime / G2P / モデルによる合成・再生を確認する。ライブ試験では localhost への経路変更を行わない。

ローカルでは TypeScript / 型定数同期、新規 JS の lint / format、Python Ruff、変更 workflow の actionlint、migration cross-reference、ORT version drift、doc audit を確認した。既存 `index.js` の null 比較にある ESLint `eqeqeq` 指摘 5 件は変更前からのもの。

PR 作成時点では GitHub 上の新規 CI と required status check 設定の確認が残る。最新 PR head の CI 成功と ruleset の `ci-required` 必須化は PR の検証欄に記録する。マージ、npm 公開、Pages 公開、および公開後のライブ試験は今回の「PR まで」の依頼範囲では実行していない。
