# Issue #760: WASM サンプルページの入力形状不一致調査

調査日: 2026-10-06 JST。対象: [Issue #760](https://github.com/ayutaz/piper-plus/issues/760)。

追加調査と実装手順: [TDD・PR CI 計画](issue-760-wasm-demo-tdd-ci-plan.md)。実 ONNX Runtime Web の小型 fixture による再現結果、runtime 互換性、PR の必須検証とマージ条件を記載した。

## 調査環境と結論

- 最新の `origin/dev` を fetch し、`b044ca55c193741b3bff8c2aa43b3e3cc9a2fe07` からブランチ `fix/issue-760-wasm-speaker-embedding` を作成した。
- worktree: `C:\Users\yuta\Desktop\Private\piper-plus-issue-760`。
- 公式デモが使う CSS10 モデルは `speaker_embedding` に `[batch_size, 256]`、`speaker_embedding_mask` に `[batch_size, 1]` を要求する。
- 現在のブラウザ向け `PiperPlus._infer()` は埋め込み未指定時に `[1, 192]`、mask に `[1]` を渡す。次元数と rank の両方がモデル定義と不一致である。
- 実モデルへの入力検証で不一致を確認した。192 を 256 に変更するだけでは mask の rank エラーが残る。
- 調査用の入力補正で両方の形状を合わせると、Python ONNX Runtime の CPU 推論は成功した。ブラウザ UI での再現・修正後の再生・音質評価は未実施。
- この調査では実装、依存バージョン、配布モデルを変更していない。

## Issue の報告内容

報告環境は Windows 11 / Chrome 154、`piper-plus ^0.7.0`。公式ページでモデル読込後に「音声合成」を押すと、`speaker_embedding` の第 2 軸が `Got: 192 Expected: 256` で失敗する。README の最小例でも問題が報告されており、利用側の ONNX Runtime は `^1.30.0` と記載されている。

## 配布物と実装の照合

| 対象 | 確認結果 |
| --- | --- |
| [公開ページ](https://ayutaz.github.io/piper-plus/) | `model: 'css10'`。ONNX Runtime Web `1.21.0` を CDN から読込。公開中の `src/index.js` に `[1,192]` のゼロ埋め込みが残っている |
| `src/wasm/openjtalk-web/test/multilingual-demo/index.html:487–493` | dev のデモも同じ runtime とモデルを選択する |
| `src/wasm/openjtalk-web/src/model-manager.js:22` | `css10` は `ayousanz/piper-plus-css10-ja-6lang` に解決する |
| npm 公開 `piper-plus@0.7.0` | registry tarball の `package/src/index.js` に同じ 192 次元固定の処理がある。`inputMetadata` の利用はない |
| `src/wasm/openjtalk-web/src/index.js:919` | 初期化で入力名から能力フラグを設定するが、埋め込みの次元は読み取らない |
| 同ファイル `:1151` | 埋め込み未指定時に `new Float32Array(192)` / `[1,192]` を構築する |
| 同ファイル `:1145,1153,1165` | 埋め込みあり・なしの各経路で mask の形状が `[1]` になっている |
| `src/python/piper_train/ort_utils.py:340–356` | Python のベンチ入力生成はモデルの `shape[1]` を読む。mask は `[[0]]` で生成する |
| `src/wasm/openjtalk-web/bin/piper-cli.js:258–266` | Node CLI の処理は 256 次元と `[1,1]` の mask。今回のブラウザ経路とは異なる。ただし 256 固定なので一般化は別途検討が必要 |

### 実モデルの入力定義

Hugging Face の revision を固定して ONNX をダウンロードし、`onnx.load(..., load_external_data=False)` で graph input を検査した。両モデルの `config.json` には埋め込み次元を指定する項目がなく、config だけから 256 を取得することはできない。

| モデル | 固定 revision | `speaker_embedding` | `speaker_embedding_mask` |
| --- | --- | --- | --- |
| [CSS10](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang/tree/bd0d812d4db9182ecdb907ef074becf9e230c17f) | `bd0d812d4db9182ecdb907ef074becf9e230c17f` | float32 `[batch_size,256]` | int64 `[batch_size,1]` |
| [Tsukuyomi](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/36b59c825c36bd386b8960cf3f604382f52f2a87) | `36b59c825c36bd386b8960cf3f604382f52f2a87` | float32 `[batch_size,256]` | int64 `[batch_size,1]` |

CSS10 のファイルは `css10-ja-6lang-fp16.onnx`、39,652,717 bytes。SHA-256 は `5ebc51dbf897238523f3df0d6e0f6c93033bc5cda3f8602a8379ebe2a4738c42`。

## 再現確認

Windows ネイティブ Node.js `v24.15.0` で、worktree の変更していない `PiperPlus._infer()` を呼び出し、セッションの `run()` のみを差し替えて feeds を保存した。初期化・G2P は迂回しており、ブラウザの操作を再現したものではない。`@piper-plus/g2p` は一時 ESM loader で worktree 内のソースへ解決した。

保存した feeds を NumPy 配列に変換し、既存の Python 環境の ONNX Runtime `1.28.0` / `CPUExecutionProvider` に渡した。phoneme IDs は 5 個の診断用入力であり、自然な文章の音声品質を検証する入力ではない。

| 実モデルへ渡した入力 | 結果 |
| --- | --- |
| 現在の JS と同じ embedding `[1,192]` / mask `[1]` | 失敗: `Invalid rank for input: speaker_embedding_mask Got: 1 Expected: 2` |
| embedding だけ `[1,256]` に補正 / mask `[1]` | 同じ mask rank エラー |
| embedding `[1,192]` / mask だけ `[1,1]` に補正 | 失敗: `Got invalid dimensions for input: speaker_embedding ... index: 1 Got: 192 Expected: 256`。Issue と同じ寸法エラー |
| embedding `[1,256]` / mask `[1,1]`、値はゼロ | 成功: 出力 shape `[1,1,1536]` と `[1,5]`、どちらも有限値 |

入力チェックの順序によって先に表示されるエラーは異なる。上記の成功は入力契約の原因を切り分ける結果であり、JS 実装自体を修正した結果ではない。

再現用 loader、feeds、モデルメタデータ、結果 JSON、ダウンロードしたモデルはローカルの `C:\Users\yuta\AppData\Local\Temp\piper-plus-issue-760-investigation` に保存した。モデルはリポジトリへ追加していない。

## 既存テストが見逃す理由

`test-piper-plus-speaker-embedding.js` と `test-piper-plus-boundary.js` を Node.js で実行し、27 passed / 0 failed / 0 skipped を確認した。

- 埋め込み用テストの `createMockInstance()` はセッションに入力名を持つが、初期化時の `_hasSpeakerEmbedding` 設定を再現しない。そのため埋め込み未指定テストは「feed しない」という経路を検証し、実モデル初期化後の必須ゼロ埋め込み経路を通らない。
- 埋め込み指定時の mask の assertion が `[1]` であり、モデルが要求する `[1,1]` と一致していない。
- モックの `run()` は入力 shape を検証しないため、ONNX の入力契約違反でも成功する。
- Pages デプロイの asset/importmap 検査はファイル配置や import の検査であり、今回確認したモデル入力の shape を検証するものではない。

## 修正時に解決すべき互換性

[現在の ONNX Runtime JS API](https://onnxruntime.ai/docs/api/js/interfaces/InferenceSession.html) は `inputMetadata` を公開する。npm 公式配布 `onnxruntime-common@1.30.0` の `lib/inference-session.ts` では、配列の tensor metadata に `name` と `shape` がある。一方、`1.21.0` では `inputMetadata` の宣言がコメントアウトされている。

公式デモは `1.21.0`、パッケージの peer dependency は `onnxruntime-web >=1.21.0`。したがって、新 API のみを参照する修正では既存のサポート範囲を満たせない。修正実装前に、旧 runtime 向けにも ONNX 入力定義を取得する経路を持つか、対応 runtime の下限とデモ/CDN を更新するかを決める必要がある。調査段階で runtime のアップグレードが必要だと確定したわけではない。

192 次元は CAM++ 系のモデルで使われるため、すべてを 256 に固定する修正は避ける。既知の静的入力 shape を優先し、動的軸または metadata が取得できない場合の扱いを明示する。ユーザーが指定した埋め込みを黙って padding / truncation して次元を合わせてはいけない。

README の importmap 最小例にも独立した問題候補がある。現在の例は `@piper-plus/g2p` の importmap 定義がなく、`ort` を import して `initialize()` に渡す処理もない。ソースでは bare import と `options.ort || globalThis.ort` が必要なので、ブラウザで最小例をそのまま実行する確認も修正範囲に含める。これは静的照合による指摘であり、報告者の実行時コードや同一エラーに至った経路を確認したものではない。

## 対応計画と完了条件

1. **回帰テストを先に追加**: 実際の `_init()` と同じ capability 設定・metadata を持つモックで、embedding 未指定時の 256 次元、192 次元、mask の rank、mask 入力なしを検証する。現行実装で失敗することを確認する。埋め込み指定時も 192/256 の対応と不正寸法の扱いを検証する。
2. **モデル入力情報の取得方法を決定**: ORT `1.21.0` 互換を保持できる方法と新 API 利用を比較する。配布モデルの静的 shape を優先し、旧 API / 動的軸の対応をテストで固定する。最低対応バージョンを変更する場合は package peer dependency、デモの CDN、README を同時に整合させる。
3. **feed を修正**: ゼロ埋め込みをモデルに合う次元で構築する。mask は宣言された shape と入力の有無に合わせ、通常合成で 0、埋め込み指定で 1 を渡す。すべての mask 構築経路を確認する。
4. **実モデルでの JS 推論**: revision 固定の CSS10 / Tsukuyomi と 192 次元モデルまたは最小 ONNX fixture を使い、修正済み JS の feeds が実 runtime で通ることを確認する。モック成功のみで完了扱いにしない。
5. **ブラウザ確認**: Windows / Chrome で公式デモと同じ配布レイアウト、README importmap / Basic Usage を実行し、モデル読込、合成、WAV 生成、再生を確認する。公式デモの 6 言語を確認する。参照音声の voice cloning は対応する encoder と TTS モデルの次元の組を別に検証する。
6. **配布と追跡**: 回帰テストを CI に組み込み、CHANGELOG と README を更新する。npm `0.7.0` は既存配布なので、利用者へ修正を届けるには新バージョン公開が必要。Pages 更新後の URL でも確認し、成果を Issue に紐づける。

現時点の完了範囲は原因調査・worktree 作成・修正計画まで。コード修正、PR 作成、npm 公開、Pages デプロイ、Issue close は未実施。
