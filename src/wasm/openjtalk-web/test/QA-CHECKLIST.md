# QA Checklist: piper-plus npm パッケージ

このチェックリストは `piper-plus` npm パッケージの品質検証に使用する。
設計ドキュメント: `docs/design/npm-package-plan.md`

---

## 1. package.json

- [ ] `name` が `"piper-plus"` である
- [ ] `version` が `"0.4.0"` である
- [ ] `license` が `"MIT"` である
- [ ] `type` が `"module"` である
- [ ] `exports["."].import` が `"./src/index.js"` を指す
- [ ] `exports["."].types` が `"./types/index.d.ts"` を指す
- [ ] `exports["./phonemizer"].import` が `"./src/phonemizer-compat.js"` を指す
- [ ] `exports["./streaming"].import` が `"./src/streaming-pipeline.js"` を指す
- [ ] `main` が `"src/index.js"` を指す
- [ ] `types` が `"types/index.d.ts"` を指す
- [ ] `files` に `src/**/*.js` が含まれている
- [ ] `files` に `dist/openjtalk.wasm` が含まれている
- [ ] `files` に `dist/openjtalk.js` が含まれている
- [ ] `files` に `dist/load-dictionary.js` が含まれている
- [ ] `files` に `types/` が含まれている
- [ ] `files` に `THIRD-PARTY-LICENSES.md` が含まれている
- [ ] `files` に `dist/espeak-ng` が含まれて**いない** (GPL 回避)
- [ ] `files` に `dist/*.bak` が含まれて**いない**
- [ ] `files` に `test/` が含まれて**いない**
- [ ] `files` に `demo/` が含まれて**いない**
- [ ] `files` に `build/` が含まれて**いない**
- [ ] `files` に `assets/` が含まれて**いない**
- [ ] `files` に `models/` が含まれて**いない**
- [ ] `peerDependencies` に `onnxruntime-web` が `">=1.21.0"` で指定されている
- [ ] `engines.node` が `">=24.0.0"` である
- [ ] `repository.url` が `"https://github.com/ayutaz/piper-plus"` である

---

## 2. エントリーポイント (src/index.js)

- [ ] `PiperPlus` クラスが export されている
- [ ] `G2P` 関連クラスが `@piper-plus/g2p` から re-export されている (`phonemizer-compat.js` 経由)
- [ ] `StreamingTTSPipeline` / `TextChunker` が re-export されている (`streaming-pipeline.js` から)
- [ ] `AudioResult` が re-export されている (`audio-result.js` から)
- [ ] 全 re-export のパスが実在するファイルを指している
- [ ] 存在しないモジュールを import していない
- [ ] ES Module 形式 (`import`/`export`) を使用している (`require` 不使用)
- [ ] eSpeak-ng 関連モジュールを import して**いない** (`espeak_ng_wrapper.js`, `espeak_phoneme_extractor.js`, `espeak_phonemizer.js`)

---

## 3. API 一貫性

設計ドキュメントの想定 API と実装が一致すること。

### PiperPlus クラス

- [ ] `PiperPlus.initialize(options)` が存在し `Promise` を返す
- [ ] `initialize` の `options.model` で HuggingFace リポジトリ名を受け取れる
- [ ] `tts.synthesize(text, options)` が存在し `AudioResult` (または同等オブジェクト) を返す
- [ ] `synthesize` の `options.language` で言語指定ができる
- [ ] `tts.synthesizeStreaming(text, options)` が存在する
- [ ] `synthesizeStreaming` の `options.onChunk` コールバックが機能する
- [ ] `tts.dispose()` が存在し例外をスローしない
- [ ] `dispose()` を複数回呼んでも例外をスローしない

### AudioResult

- [ ] `audio.play()` メソッドが存在する
- [ ] `audio.toBlob()` メソッドが存在する

### G2P (phonemizer-compat 経由)

- [ ] `G2P.create(options)` が `Promise` を返す
- [ ] `g2p.encode(text, phonemeIdMap, { language })` が機能する

### オプションのデフォルト値

- [ ] 言語指定なしの場合のデフォルト動作が定義されている
- [ ] `noiseScale` 等の合成パラメータにデフォルト値がある

---

## 4. TypeScript 型定義 (types/index.d.ts)

- [ ] ファイルが `types/index.d.ts` に存在する
- [ ] `PiperPlus` クラスの型が定義されている
- [ ] `PiperPlusOptions` (initialize のオプション) の型が定義されている
- [ ] `SynthesizeOptions` の型が定義されている
- [ ] `AudioResult` の型が定義されている
- [ ] `StreamingTTSPipeline` の型が定義されている
- [ ] `TextChunker` の型が定義されている
- [ ] オプショナルパラメータに `?` がついている
- [ ] `initialize()` の戻り値が `Promise<PiperPlus>` である
- [ ] `synthesize()` の戻り値型が正しい
- [ ] `dispose()` の戻り値が `void` または `Promise<void>` である
- [ ] `export` 宣言が `src/index.js` の export と一致している

---

## 5. ライセンス

### THIRD-PARTY-LICENSES.md

- [ ] ファイルが存在する
- [ ] OpenJTalk のライセンス (BSD-3-Clause) が記載されている
- [ ] HTS Engine API のライセンス (BSD-3-Clause) が記載されている
- [ ] MeCab のライセンス (BSD-3-Clause) が記載されている
- [ ] eSpeak-ng が記載されて**いない** (npm パッケージから除外されているため)
- [ ] 各ライセンスの原文 (または正確な要約) が含まれている

### LICENSE.md

- [ ] ファイルが存在する
- [ ] MIT ライセンスの全文が記載されている

---

## 6. テスト

- [ ] `npm test` (`node --test`) で全テストが実行可能
- [ ] テストが Node.js 18 以上で動作する
- [ ] ブラウザ専用 API (`AudioContext`, `navigator`, `indexedDB` 等) のモック処理が適切
- [ ] `PiperPlus.initialize()` の基本テストが存在する
- [ ] `synthesize()` の基本テストが存在する
- [ ] `dispose()` の基本テストが存在する
- [ ] eSpeak-ng に依存するテストが npm パッケージ用テストに含まれて**いない**
- [ ] テストが外部ネットワークなしでも実行可能 (または明確にスキップされる)

---

## 7. CI/CD (npm-publish.yml)

- [ ] ワークフローファイル `.github/workflows/npm-publish.yml` が存在する
- [ ] 作業ディレクトリが `src/wasm/openjtalk-web/` に設定されている
- [ ] タグまたはリリーストリガーで publish が実行される
- [ ] `npm publish` 前にテストが実行される
- [ ] パッケージサイズチェックが含まれている (WASM + JS で ~5MB 以下を検証)
- [ ] NPM_TOKEN がシークレットから参照されている
- [ ] `--dry-run` による事前検証ステップがある (推奨)
- [ ] Node.js バージョンが 18 以上に設定されている

---

## 8. セキュリティ

- [ ] `files` フィールドに `.env` が含まれて**いない**
- [ ] `files` フィールドに `credentials` 系ファイルが含まれて**いない**
- [ ] `postinstall` スクリプトが存在しない、または安全な操作のみ行う
- [ ] `prepublishOnly` スクリプトが危険な操作を行って**いない**
- [ ] npm パッケージに含まれるファイルにハードコードされた API キー・トークンがない
- [ ] `scripts` 内に `rm -rf /` 等の危険なコマンドがない

### `npm pack --dry-run` による検証

- [ ] パッケージに含まれるファイル一覧が想定通りである
- [ ] パッケージサイズが妥当 (~5MB 以下)
- [ ] `dist/espeak-ng/` ディレクトリが含まれて**いない**
- [ ] `assets/` ディレクトリが含まれて**いない**
- [ ] `models/` ディレクトリが含まれて**いない**

---

## 9. ドキュメント

- [ ] README.npm.md (npm 向け) が存在する
- [ ] インストール方法 (`npm install piper-plus`) が記載されている
- [ ] 基本的な使い方のコード例が記載されている
- [ ] 対応言語一覧 (ja, en, zh, es, fr, pt) が記載されている
- [ ] ライセンス情報が記載されている
- [ ] ブラウザ専用であることが明記されている

---

## 10. exports パスの実ファイル検証

`package.json` の `exports` と `files` で参照される全パスが実在すること。

- [ ] `src/index.js` が存在する
- [ ] `src/phonemizer-compat.js` が存在する
- [ ] `src/streaming-pipeline.js` が存在する
- [ ] `types/index.d.ts` が存在する
- [ ] `dist/openjtalk.wasm` が存在する
- [ ] `dist/openjtalk.js` が存在する
- [ ] `dist/load-dictionary.js` が存在する
- [ ] `THIRD-PARTY-LICENSES.md` が存在する
- [ ] `LICENSE.md` が存在する
- [ ] `README.npm.md` が存在する
