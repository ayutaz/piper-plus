# `@piper-plus/g2p` の中国語を pinyin 辞書で読む (Issue #829)

`@piper-plus/g2p` の中国語 G2P (`src/wasm/g2p/src/zh/`) は pinyin 辞書を使わず、文字を 1 つずつ素通ししていた。そのため、Python の正解 (`phoneme_test_cases_golden.json`) の中国語ケースはすべてずれていた。例えば `你好` は `你 好` のままだった。ブラウザ向け npm `piper-plus` は zh を含むモデルで Rust WASM を使うので、影響を受けたのは `@piper-plus/g2p` を単体で使う利用者になる。

## 方針

pinyin 辞書は npm に同梱することにした (ユーザー決定)。手順は Rust の `ChinesePhonemizer` (`src/rust/piper-plus-g2p/src/chinese.rs`) をそのまま JS に移し、他のランタイムと同じ辞書・同じ手順にそろえた。

- **辞書**: `src/wasm/g2p/data/pinyin_single.json` / `pinyin_phrases.json` を同梱する。canonical の `src/rust/piper-plus-g2p/data/` とバイト一致しており、数字声調で、合計 2.7MB。
  - 読み込みは遅延ロードで、`G2P.create()` は zh が有効なときだけ辞書を await する。
  - 利用者が自分で読み込んだ辞書は、`pinyinDict` オプションか `createPinyinDictionary` で渡せる。
- **手順** (`src/zh/pinyin.js`): 次の順に処理する。
  1. 句の最長一致 (2〜8 字)
  2. 1 字辞書
  3. y/w の正規化
  4. 声調変化 (三声の連続、一、不)
  5. pinyin から IPA への変換
  6. 儿化
  7. 句読点の ASCII 化
  - prosody も Rust と同じく、a1 = 声調、a2 = 漢字の連なりの中での位置、a3 = 連なりの長さとした。
- **ZH-EN loanword** (`src/zh/loanword.js`): 中国語に隣接する英字は、Rust の `phonemize_embedded_english_with_prosody` と同じく pinyin で読む (#384)。
- **言語指定 zh の分割** (`src/index.js`): Rust の `phonemize_with_language(text, "zh")` と同じく、文字種で分割する。中国語の部分がない入力 (数字だけ等) は各言語の G2P に渡す。

## 後方互換

- 追加した API は `loadPinyinDictionary`、`createPinyinDictionary`、`PinyinDictionary`、`isPinyinDictionaryLoaded`、`pinyinDict` オプション、`ChineseG2P#initialize` / `setPinyinDictionary` で、すべて追加のみ。
- `new ChineseG2P()` を `initialize()` せずに使う場合は、これまでどおり文字単位で素通しする (mode `fallback`)。
- 同梱によってパッケージは大きくなった。tarball は 78 kB から 834 kB、展開後は 0.3 MB から 3.0 MB になる。

## 結果

- js-g2p の中国語 61 件のうち、数字だけの 3 件を除く 58 件が pinyin 辞書で Python と一致した。これらは `known_divergences.json` から削除した。
- 数字だけの 3 件 (`123` / `0` / `100`) は英語 G2P に渡る。#828 (英語の CMU 辞書と正規化) のマージ後に `0` と `100` は Python と一致した。`123` は C++ / Rust と同じ出力 (CMU 辞書に `twenty-three` がないため強勢が違う) なので、既存の accepted 項目に js-g2p を加えた。

## 再発防止

- `docs/spec/dictionary-mirrors.toml` に同梱分を mirror として登録した。`dictionary-consistency` (pre-commit とワークフロー) がバイト一致を検査する。
  - ワークフローの path filter には、これまで pinyin 辞書が 1 つも入っていなかったので追加した。
- `test-package-metadata.js` で次の 3 点を検査する。
  - `files` に辞書が含まれ、`npm pack --dry-run` の内容に入ること
  - 同梱した辞書が canonical と一致すること
  - pypinyin の許諾文を同梱していること
- g2p-wasm-ci は canonical の pinyin 辞書が変わったときにも走る。
