# `@piper-plus/g2p` の英語を CMU 辞書と g2p_en の正規化で読む (Issue #828)

`@piper-plus/g2p` の英語 G2P (`src/wasm/g2p/src/en/`) は、ブラウザ向け npm `piper-plus` の英語でも使われている。これまでは小さな内蔵辞書と綴りの規則で読んでいたため、Python 学習側 (g2p_en) と 45 件ずれていた。例えば brown を `b ɹ ˈ o ʊ n` と読み、数字は落としていた。

## 方針

CMU 辞書は npm に同梱することにした (ユーザー決定)。手順は、C++ / Rust (#821) と Go (#841) に移植済みの Rust の `EnglishPhonemizer` をそのまま JS に移した。

- **正規化** (`src/en/normalize.js`): `english_normalize.rs` を移植した。
  - 数字は inflect 方式で読み、年 (1001〜2999)、序数、`$` / `£`、小数も扱う。
  - アクセントを除き、`i.e.` / `e.g.` を展開し、TweetTokenizer の必要な部分を移した。
  - 空白は Unicode White_Space を明示的に列挙して判定する。JS の `\s` は Python と範囲が違うので使わない。
- **辞書引き** (`src/en/index.js`): 次の順に試す。
  1. CMU 辞書
  2. 接尾辞の fallback
  3. `-` / `.` での分割
  4. アポストロフィの再試行
  5. CamelCase の分割
  6. 文字の名前で読む
  - IPA への変換規則と prosody (a2 = 強勢、a3 = 単語の音素数) は Python と同じにした。
- **辞書の同梱と読み込み**: `data/cmudict_data.json` (3.7 MB) は canonical の `src/rust/piper-plus-g2p/data/` とバイト一致している。読み込みは遅延させる。
  - `G2P.create()` は en が有効なときだけ辞書を await する。
  - Node では、初回の呼び出しで同期的に読み込む。
  - ブラウザで初期化前に同期 API を呼ぶと、`await initialize()` を促すエラーにする。
  - 辞書は `cmuDict` オプションで外から渡すこともできる。

## 結果

- js-g2p / wasm の英語 45 件のうち、37 件が Python と一致した。数字の 7 件 (`0` / `7` / `42` / `100` / `1984` / `3.14` / `$5`) も、語が落ちなくなった。
- 残る 8 件は、辞書にない語を Python がニューラル予測で読むケースで、C++ / Rust で accepted として記録済みのものと同じ出力になる。そのため、それらの項目の runtimes に `wasm` と `js-g2p` を加えた。
- wasm の中国語の文中にある数字 (`123` / `0` / `100`) は Rust WASM の英語の区間を通るため、この変更では直らない。#847 として残した。

## サイズ

- tarball は 78 kB → 950 kB、展開後は 0.3 MB → 4.1 MB になった (この PR 単体の値)。
- #829 の pinyin 辞書と合わせると約 1.8 MB になるので、G2P WASM CI の size-check の上限を 1 MB から 3 MB に上げた。

## 再発防止

- `docs/spec/dictionary-mirrors.toml` に CMU 辞書を登録した (npm と `test/models/` の写し)。`dictionary-consistency` (pre-commit とワークフロー) がバイト一致を検査し、どの写しが変わっても走る。
- `test-english-normalize.js` は共有の正規化ケース `english_normalize_cases.json` を読む。g2p-wasm-ci は、このケースか canonical の辞書が変わっても走る。
- `test-package-metadata.js` は、`files` と `npm pack --dry-run` の内容に辞書と CMU のライセンス表記が含まれることを検査する。
- `test-english-cmudict.js` は次の点を検査する。
  - canonical とのバイト一致
  - golden の句
  - prosody
  - 遅延ロードと未初期化時の挙動
  - `constructor` などの prototype の名前が辞書の語に混ざらないこと
