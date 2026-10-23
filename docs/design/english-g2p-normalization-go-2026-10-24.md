# Go の英語 G2P に g2p_en の正規化を移す (Issue #841)

#821 で C++ と Rust に移した英語の正規化 ([english-g2p-normalization-cpp-rust-2026-10-23.md](english-g2p-normalization-cpp-rust-2026-10-23.md)) を、Go (`src/go/phonemize`) にも移した。規則・意図的な変更点 (Unicode の空白を半角空白にする) は Rust と同じで、Rust の `english_normalize.rs` / `english.rs` を 1 対 1 で移している。

## 変更

- `english_normalize.go` (新規): 数の読み (inflect と同じ規則。年号・小数・序数・`$`・`£`)、アクセント記号の除去、文字の絞り込み、`i.e.` / `e.g.` の置き換え、TweetTokenizer のうちこの文字種で起こる部分。依存は標準ライブラリだけ。
- `english.go`: 処理の順序を Rust と同じにした。正規化 → 辞書 → 語尾を外して引き直す → `-` / `.` で分ける → `'` を除いて引き直す → CamelCase で分ける → 英字の名前で 1 文字ずつ読む。何も出さない語の前に区切りを入れない。機能語の判定は数字を展開する前の語に対応させる。句読点の A3 を 1 にした (Python・Rust と同じ)。
- 辞書にない語の読みが「生の文字を出す」から「英字の名前で読む」に変わったため、既存テスト 3 本 (`TestOOVFallback` ほか) の期待値を Rust と同じ値に書き換えた。

## 結果

- `english_normalize_cases.json` の `numbers` 131 件・`tokens` 52 件が Python と一致する。
- golden で Go が一致するようになったケース: en `0` `1` `100` `3.14` `It's 3 o'clock.` `e.g. and i.e.` `uh-huh` `café` `naïve` `'quote'` `I have ３ cats．`、zh `0` `100`。
- 残る英語の差 (`123`、`ChatGPT and GitHub`、`UPPERCASE`、`MixedCase`、`xyz`、`aaaaa`、`a-b-c`、`résumé`) は Python のニューラル推測と品詞判定によるもので、Go の音素列は C++ / Rust と同じ。`known_divergences.json` では go 単独の項目を消し、C++ / Rust / Swift の accepted 項目に go を合流させた。
- `english_no_drop_words.json` の数字 7 件の `known_drops` から go を外した。

## 再発防止

- Go のテスト `src/go/phonemize/english_normalize_test.go` が共有 fixture を読み、全件の完全一致を検査する。
- `scripts/build_english_normalize_fixture.py --check` (pre-commit) は、`CONSUMER_TESTS` に並べた C++・Rust・Go のテストが存在し fixture を読み続けていることも検査する。ゲート自身のテスト (`tests/scripts/test_build_english_normalize_fixture.py`) は parity-hub の english-normalize ジョブで動かす。
- Go CI は `english_normalize_cases.json` の変更でも走る。

## 残る差

中国語に埋め込まれた英語を pinyin で読む経路では、Go は英語部分の韻律を返さず、Rust は値を返す。音素列は一致しており (golden 照合は音素列だけを比べる)、英語の正規化とは別の以前からある差なので今回は変えない。
