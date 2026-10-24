# C# の英語 G2P を PiperPlus.Core に移す (Issue #832 英語 / #821)

## 経緯

C# CLI は英語の G2P を外部パッケージ `DotNetG2P.English` に任せており、Python 学習側の g2p_en と違う出力になっていた。g2p_en は、正規化をしてから CMU 辞書を引き、辞書にない語は予測で読む。

- **英語のずれ (golden 19 件)**: 数字が落ちる。`3.14` や `It's 3 o'clock.` が Python と違う。`She's reading a book.` など辞書の違いもある。
- **数字だけの語が無音になる**: `0` `7` `42` `100` `1984` `3.14` `$5` `R2D2` は音素がなかった。
- **中国語の文中の数字 (3 件)**: 英語の経路で読まれるため、同じくずれていた。

C++ / Rust (#821) と Go (#841) は、g2p_en の正規化と辞書にない語の扱いを移植済みだった。

## 変更

### 移植

- `EnglishTextNormalizer` (internal) は、Rust の `english_normalize.rs` / Go の `english_normalize.go` を 1 対 1 で移したもの。次を扱う。
  - inflect 方式の数の読み (年号・小数・序数・`$`・`£`)
  - アクセントの除去
  - Unicode の空白を半角空白にする
  - `i.e.` / `e.g.` の置き換え
  - TweetTokenizer 風の分割
- `EnglishG2PEngine` (public、Core) は、正規化した語を次の順に読む。
  1. CMU 辞書
  2. 語尾を外して引き直す
  3. `-` / `.` で分ける
  4. `'` を除いて引き直す
  5. CamelCase で分ける
  6. 英字の名前で 1 文字ずつ読む

  ARPAbet から IPA への変換、強勢、prosody は既存の `EnglishPhonemizer` のまま変えていない。

### CLI と配布

- CLI は `BundledEnglishG2PEngine` を使い、canonical の `src/rust/piper-plus-g2p/data/cmudict_data.json` を埋め込みリソースとして読む。pinyin 辞書と同じ方式で、複製は持たない。
- `DotNetG2P.English` と `DotNetEnglishG2PEngine.cs` を削除した。日本語用の DotNetG2P (MeCab) は残す。
- Core の NuGet は辞書を含まない。利用者は `EnglishG2PEngine.FromJson` に辞書を渡す。
- Cli の nupkg に `THIRD_PARTY_NOTICES.md` を同梱した。埋め込んだ CMU 辞書と pinyin 辞書の許諾表示がこれまでなかったため。

## 結果

### 一致したもの

- csharp の en planned 13 件と zh 2 件 (`0` / `100`) が Python と一致した。
- 数字の 7 語と `R2D2` も無音でなくなった。

### 残る差

残る 9 件は Rust と同じ出力なので、既存の accepted 項目に csharp を加えた。

- en: `123` `a-b-c` `ChatGPT and GitHub` `aaaaa` `xyz` `résumé` `UPPERCASE` `MixedCase`
- zh: `123`

残る理由は Rust / C++ と同じで、次の 3 つ。

- Python のニューラル予測を移植していない
- 品詞判定がない
- CMU 辞書に `twenty-three` がない

## 再発防止

- `EnglishNormalizeTests` は、共有の正規化ケース `tests/fixtures/g2p/english_normalize_cases.json` を全件照合する。
- `BundledDictionaryTests` は次を検査する。
  - 埋め込んだ辞書が canonical とバイト単位で一致すること
  - 埋め込んだ JSON ごとに `THIRD_PARTY_NOTICES.md` が許諾表示を持ち、nupkg に入ること
- `TextModeCoreEnginesTests` は、CLI が `DotNetG2P.English` を参照しないこと、英語が Core のエンジンと同じ出力になることを検査する。
- golden の入力で、ID 表にない音素が出ないことを検査する。このテストを en にも広げた。
- csharp-ci の path filter に、canonical の CMU 辞書と正規化ケースを加えた。
