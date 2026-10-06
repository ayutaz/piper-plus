# Issue #760: WASM 音声合成修正の TDD・PR CI 計画

作成日: 2026-10-06 JST。
対象: [Issue #760](https://github.com/ayutaz/piper-plus/issues/760)。
調査元: [入力形状不一致の調査](issue-760-wasm-demo-investigation.md)。
基準 commit: `b044ca55c193741b3bff8c2aa43b3e3cc9a2fe07`。
作業ブランチ: `fix/issue-760-wasm-speaker-embedding`。

## 目的と現在の到達点

通常合成と話者埋め込み指定時の入力を ONNX モデルの宣言と一致させ、192/256 次元モデルの双方を扱う。同じ種類の不一致は、修正前に失敗するテストを先に追加し、PR の CI で検出する。

現時点で完了したのは追加調査と計画の作成である。以下のテストファイル、実装修正、workflow 変更、保護設定変更はこれから実施する。調査実験は一時ディレクトリのみで行い、既存の依存環境や実装は変更していない。

## 追加調査で確認した事実

### 実 ONNX Runtime Web での検出が小さなモデルで可能

Python `onnx` で、192 次元と 256 次元の埋め込み、rank 2 の mask を宣言する診断モデルを作成した。各ファイルは **549 bytes**、IR 9 / opset 13。embedding と mask を実際に使う演算を持ち、16 サンプルの診断用出力を返す。音声品質を評価するモデルではない。

一時 npm 環境に公式 `onnxruntime-web` の `1.21.0` / `1.22.0` / `1.30.0` を個別にインストールし、Node.js `v24.15.0` 上で `executionProviders: ['wasm']`、`numThreads=1` として実行した。native の `onnxruntime-node` は使用していない。

| runtime | 192 次元モデル + 現在の JS | 256 次元モデル + 現在の JS | モデルに合わせた対照入力 | 公開 `inputMetadata` |
| --- | --- | --- | --- | --- |
| 1.21.0 | mask rank 不一致で失敗 | `Got: 192 Expected: 256` で失敗 | 両モデルとも成功 | なし |
| 1.22.0 | mask rank 不一致で失敗 | 同じ次元エラーで失敗 | 両モデルとも成功 | あり |
| 1.30.0 | mask rank 不一致で失敗 | 同じ次元エラーで失敗 | 両モデルとも成功 | あり |

6 通りすべてで現行 JS が失敗し、6 通りすべてで対照入力が成功した。対照入力はモデルに合う `[1,D]` と `[1,1]` を直接生成したもので、ライブラリ修正の成功を示すものではない。ブラウザ UI の試験でもない。

結果 JSON、試験スクリプト、診断モデルは `C:\Users\yuta\AppData\Local\Temp\piper-plus-issue-760-ci-probe` に保存した。これにより、PR の必須検証で毎回 40 MB の音声モデルを取得する必要がないことを確認できた。

### CI が現在保証していない範囲

- `.github/workflows/ci.yml` の `npm-package-tests` は `npm run test:npm-package:all` を実行するが、今回の話者入力テストは shape を検証しないモックである。
- `test-piper-plus-speaker-embedding.js` は import エラーを catch して suite を skip する。また、mask `[1]` を正しい値として assert している。新しい必須回帰テストでこの形式を踏襲しない。
- `.github/workflows/test-webassembly.yml` は別のテスト一覧を直接列挙している。npm script に追加しただけでは、この別 workflow に新しいテストが追加されるとは限らない。
- `.github/workflows/ci.yml` の `ci-required` は `npm-package-tests` の失敗を拾う。新しい軽量 job の結果もここへ追加するのが既存構成に合う。
- `ci-config-wasm` の変更検出には、Pages デプロイ workflow と新しい fixture 等のルートディレクトリは現在含まれていない。追加するか、常時実行の検証で漏れを防ぐ必要がある。
- `Required Status Check Gate` は RTF / Memory / CodeQL / Parity / PUA を監視し、CI 本体は監視対象ではない。今回だけのために監視 workflow を増やさず、既存 `ci-required` の依存関係へ組み込む。

2026-10-06 の GitHub API 確認では、active ruleset `piper-dev` に required status checks の規則はなく、従来の `dev` branch protection API は `Branch not protected` / 404 を返した。PR を必須にする ruleset 自体は存在するが、CI 成功は現状の規則では必須になっていない。**CI を実行する変更と、失敗時にマージを禁止する設定は別の作業である。**

## 推奨する実装方針

### 入力定義を単一の情報源にする

新しい内部 helper（仮称 `src/onnx-input-contract.js`）にモデル入力の読み取りと shape 解決をまとめる。`_init()` は実セッションからこの情報を取得し、`_infer()` はこの定義で embedding / mask を構築する。セッションを作り直す経路も同じ取得処理を使う。

- metadata は `session.inputMetadata` の **配列**から `name` で探す。`inputMetadata[name]` という辞書扱いや、非公開 handler API には依存しない。
- 埋め込みの静的な第 2 軸を優先し、未指定時はその長さのゼロ配列を作る。192/256 の二択に固定しない。
- mask は宣言された rank / shape に合わせる。rank 1 の `[batch]` と rank 2 の `[batch,1]` を区別する。batch は現在の API の単発合成に合わせて 1 とする。
- 宣言されていない入力は feed しない。mask=0 / 1 は通常合成 / 埋め込み指定の意図を維持する。
- 埋め込み指定時の静的次元不一致、空配列、非有限値、モデルに埋め込み入力がない場合は、入力名と期待値が分かるエラーを返す。padding / truncation で黙って調整しない。
- 埋め込みの第 2 軸が動的なら、指定された embedding の長さを使える。未指定の場合は推測で 192/256 を選ばず、埋め込みが必要であることを明示する。
- metadata 欠落、解決不能な mask 軸、非対応 dtype / rank は明示エラーにする。寸法エラーを捕捉して「合成成功」にしない。

### runtime の互換性に関する推奨判断

[ORT 1.22.0 の公式 API](https://github.com/microsoft/onnxruntime/blob/v1.22.0/js/common/lib/inference-session.ts) と実動作で metadata の利用を確認した。最小の保守可能な修正として、**最低対応 runtime を 1.22.0 とし、1.22.0 と報告環境の 1.30.0 を CI の固定バージョンで検証する案を推奨する。** 1.30.0 のみを最低条件にする必要はない。

この案では peer dependency、lockfile、デモの固定 CDN、README、`docs/reference/ort-versions.md` を一緒に更新し、1.21.0 利用者への変更を CHANGELOG に明記する。デモの CDN は 1.22.0 に固定し、そのバージョンでブラウザ試験を通す。1.21.0 は「正常合成のサポート対象」にはせず、metadata 不足を説明する診断の負例として確認する。パッケージのリリース番号はこの互換性変更を含めて決定する。

1.21.0 の継続サポートを優先する場合は、ONNX protobuf から入力定義を読む経路が別途必要になる。モデルの二重 download、大きな parser の導入、独自 protobuf reader の保守を伴う可能性があり、今回の必須回帰テストを作った後に比較する。既知モデルを常に 256 にする fallback だけで互換性維持と扱う案は採らない。

## TDD の順序とテストケース

### 1. RED: 正しい契約を先にテストする

新規 `test/js/test-onnx-input-contract.js` と `test/js/test-piper-plus-onnx-inputs.js` を追加する。新規テストは直接 import し、import / fixture 不足は失敗にする。旧モックの期待値を先に実装へ合わせて変更することは避ける。

| ケース | テストで固定する動作 |
| --- | --- |
| embedding 256 / mask rank 2、未指定 | `[1,256]` のゼロ embedding と `[1,1]` / mask=0 |
| embedding 192 / mask rank 2、未指定 | `[1,192]` と `[1,1]` / mask=0 |
| embedding 320 | metadata の任意の正の静的次元を利用し、192/256 の分岐に依存しない |
| embedding 指定 | 指定配列を渡し、宣言された mask shape / mask=1 を使う |
| mask rank 1 | `[1]` を生成し、rank 2 へ一律固定しない |
| mask 入力なし | embedding のみ渡し、未知の入力を追加しない |
| embedding 入力なし | 通常合成で embedding / mask を追加しない |
| embedding 寸法不一致・空・NaN・Infinity | 明示エラー。無言の切詰め・埋め合わせ・成功扱いをしない |
| embedding の動的次元 | 指定配列なら長さを使い、未指定では説明可能なエラー |
| metadata 不足、非対応 dtype / rank | helper の入力検証または初期化が説明可能なエラーを返す |
| セッション再作成 | 新セッションの入力契約を読み直し、古い寸法を再利用しない |

初期化を通る統合テストでは `PiperPlus.initialize()` が capability を設定した後に `synthesize()` を呼ぶ。低層テストで private method を呼ぶ場合も capability を実セッションの inputNames と一致させ、未指定の必須 embedding 経路を必ず通す。

fixture の生成 script と小さな `.onnx` を `test/fixtures/onnx-inputs/` 配下に置く。まず調査済み 192/256 + rank 2 の 2 モデルで、現行 `_infer()` が実 ORT Web に拒否される RED を保存する。続けて mask なし、embedding なし、rank 1 を追加する。fixture は模型であることを明記し、モデルの input 名・dtype・shape・生成方法を manifest に残す。

### 2. GREEN: helper と feed を修正する

入力契約 helper、初期化時の取得、feed 生成を実装し、RED のケースを通す。既存の話者入力テストの `[1]` assertion と未指定経路のモックも、この正しい契約へ置き換える。`synthesizeWithVoiceCloning()` / `synthesizeFromReferenceAudio()` 経由の mask=1 も確認する。

### 3. REFACTOR: 重複と配布例を整合させる

すべての mask 構築経路を共通 helper に集約する。README の importmap に `@piper-plus/g2p` を含め、ORT を import して `initialize({ model, ort })` に渡す動く例へ更新する。デモの runtime と package の最低対応条件を整合させる。

### 4. テストが不具合を検出することを確認する

修正後、作業コピー内でゼロ embedding を 192 固定へ戻すと 256 fixture のテストが失敗し、mask を `[1]` 固定へ戻すと rank 2 fixture のテストが失敗することを確認する。実行後は改変を戻す。新規テストの import / fixture 欠落も skip 成功にならないことを確認する。単なるテスト件数増加を完了条件にしない。

## PR の CI 構成

### 常時実行する軽量検証

`.github/workflows/ci.yml` に `wasm-onnx-contract` job を追加する。`dev` 向けの **すべての PR** と `dev` push で実行し、path filter で回帰検証を取りこぼさない。Node 24、ubuntu-24.04、ORT Web `1.22.0` / `1.30.0` の matrix、`fail-fast: false`、当初の timeout は各 10 分を目安とする。

- Rust / Emscripten のコンパイル、GPU、秘密情報、大きな音声モデルの download は不要。
- runtime は matrix の正確なバージョンを明示して install する。各ログへ実際の runtime バージョンを記録する。
- テストで使う G2P は worktree の `file:../g2p` にする。native ORT を使わない lane では不要な npm install script を無効にして native binary download を避ける。
- unit テストと **実 ORT Web WASM** の fixture 試験を実行する。新規 `test:onnx-inputs` npm script を共通入口にする。
- test import / fixture / runtime / WASM asset の欠落で fail し、環境変数がないことを理由に skip しない。新規必須 suite の JUnit 結果は skipped=0、予定の主要ケースが実行済みであることを確認する。
- `continue-on-error` は付けない。失敗時に runtime、model fixture、期待 shape、実際の feeds が分かるログと JUnit を保存する。

`ci-required` の `needs` に `wasm-onnx-contract` を追加する。この job については **success のみ**を許容し、failure / cancelled / skipped をすべて失敗にする。他の path filter 付き既存 job の正当な skip 条件は維持する。matrix の一方だけが成功しても通過させない。

workflow の契約テストも `tests/scripts/test_wasm_onnx_ci_contract.py` として先に追加する。新 job が PR trigger から外れた、script が実行されない、matrix の最低 runtime が消えた、`continue-on-error` が追加された、`ci-required` の依存から外れた、という変更を検出する。既存 Python CI は主に `src/python/tests/` を収集しており、ルートの `tests/scripts/` へ置くだけでは実行されない。新しい常時実行 job に Python / pytest / YAML parser の小さな検証 step を明示して追加し、`python -m pytest tests/scripts/test_wasm_onnx_ci_contract.py -q -o addopts=` で実行する。PyTorch 等の training extras はインストールしない。

### 既存 npm 検証へも登録する

`test:npm-package:all` に新規 unit テストを追加する。実 runtime fixture 試験は `test:onnx-inputs` を別 step で実行し、モック試験と結果を区別する。`test-webassembly.yml` のテスト列挙も共通 npm script を使うか、対象を明示的に追加する。npm publish 前の検証も同じ入口を利用する。

### ブラウザと公開モデルを使う検証

既存 `npm-package-tests` は実 Rust WASM を build するため、この job に Chromium のブラウザ試験を追加する。`ci-config-wasm` に Pages デプロイ workflow、ブラウザ試験 harness、公開モデル manifest の変更を含める。この job が実行される PR では、ブラウザ試験の失敗も `ci-required` を失敗させる。

- Playwright を dev dependency として追加し、テストで使う Chromium を固定した package/lockfile で管理する。
- CSS10 / Tsukuyomi のモデルと config は調査済みの revision を固定して取得する。SHA-256 を manifest と照合し、GitHub Actions の download cache を revision / hash で分離する。通信失敗は成功/skip に変換しない。
- 公式デモと同じ asset layout、実 G2P WASM、実 ORT Web を localhost から配信する。ページの synthesize handler、初期化、公開 `synthesize()` を実行する。ORT の `run()` を偽の成功に置き換えない。
- CSS10 デモの 6 言語、Tsukuyomi の通常合成、README importmap の例を確認する。入力形状エラー、pageerror、合成エラー表示がないこと、WAV の RIFF/WAVE header、sample rate、サンプル数 > 0、PCM が有限値であることを検証する。
- 自動ブラウザで音声ファイルの decode / 再生状態も確認する。自然さや声の品質は機械的成功と分け、Windows / Chrome の人手再生確認で記録する。
- job の timeout は現状 15 分なので、既存 build 時間と追加試験時間を測り、必要な増分を反映する。重い試験が遅くても、常時実行の小型 fixture 検証は独立して先に結果を返す。

## マージ条件と配布確認

1. RED/GREEN の結果、失敗を再導入したときの検出結果を PR に記載する。
2. 最新 PR head に対して両 runtime の fixture job、関連 npm / ブラウザ job、`ci-required` の成功を確認する。古い head の成功で代用しない。
3. 実装 PR の CI が正常に動作することを確認後、GitHub ruleset の required status check に GitHub Actions の **`ci-required`** を登録する。workflow ファイルだけではこの保護設定は変更されない。設定変更後に API で必須条件を確認する。
4. 意図的な CI 失敗が required check の失敗として扱われることを、テスト用の失敗を最終 head に残さず確認する。skipped / cancelled を成功と扱う変更も契約テストで検出する。
5. docs 例の更新による既存 doc audit の差分、ORT version drift、lint / format / types / 関連既存テストを確認する。audit の失敗を無効化しない。
6. 修正を含む npm 版と Pages の公開後、配布中の JS / runtime / model で再度合成を確認する。公開側はモデル alias が `main` を解決するため、固定 revision の PR 試験とは別に、実際に配信される model revision / 入力 shape を記録する。

公開後の probe は既存 `scripts/verify_pages_assets.py` のファイル存在検査に加えて、実際の合成を確認するブラウザ試験を呼び出す。配布モデルが PR の固定 revision から変わったときも、モデルから shape を読む修正で対応し、非対応の契約なら明示的な失敗を検出する。未実行の公開確認を成功と報告しない。

## 実装するファイルの目安

| 対象 | 変更内容 |
| --- | --- |
| `src/wasm/openjtalk-web/src/onnx-input-contract.js`（新規） | metadata の読み取り、shape / dtype 検証、feed shape 解決 |
| `src/wasm/openjtalk-web/src/index.js` | 入力契約の取得・再取得、embedding / mask feed を修正 |
| 同 package `test/js/`、`test/fixtures/onnx-inputs/`（新規） | unit、実 ORT Web、tiny ONNX、生成 script、manifest |
| 同 package `test/js/test-piper-plus-speaker-embedding.js` | 初期化と整合するモック、正しい mask、skip で隠れない検証 |
| 同 package `package.json` / `package-lock.json` | script 登録、runtime 条件、ブラウザ検証依存 |
| `.github/workflows/ci.yml` | 常時 fixture job、matrix、集約 gate、既存 job のブラウザ試験 |
| `.github/workflows/test-webassembly.yml` / `npm-publish.yml` | 共通 script での検証呼出し |
| `tests/scripts/test_wasm_onnx_ci_contract.py`（新規） | CI が回帰テストを実行し失敗を集約する構成の保証 |
| 同 package `test/multilingual-demo/index.html`、`README.npm.md` | runtime と動作例の整合 |
| `docs/reference/ort-versions.md`、CHANGELOG、必要な audit snapshot | 対応範囲・変更点・既存 gate の整合 |

この計画の完了条件は、モデル形状を変えても固定 192/256 と mask rank の不一致が PR CI で検出され、正しいモデル契約では通常合成と埋め込み指定経路が成功すること。ブラウザ品質の人手確認と公開後の確認は、その試験結果を別々に記録する。
