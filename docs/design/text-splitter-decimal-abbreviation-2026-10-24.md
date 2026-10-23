# 文分割で小数点と e.g. / i.e. を文の終わりにしない (Issue #831)

## 問題

ストリーミング合成と `PiperVoice.phonemize` は、テキストを文に分けてから文ごとに音素化する。分割は `.` を文の終わりとして扱うため、次のように割れていた。

| 入力 | 旧分割 |
|------|--------|
| `It costs 3.14 dollars.` | `It costs 3.` / `14 dollars.` |
| `Version 2.0.1 is out.` | `Version 2.` / `0.` / `1 is out.` |
| `Fruit, e.g. an apple.` | `Fruit, e.` / `g.` / `an apple.` |
| `気温は3.5度です。` | `気温は3.` / `5度です。` |

学習データは文分割をせずに音素化している。分割すると英語 G2P は `3.14` を「three point one four」ではなく「three」と「fourteen」と読み、`e.g.` を「for example」に置き換えない。golden 照合は分割前の音素化器を見ていたため、この差が見えなかった。

## 規則

契約 `docs/spec/text-splitter-contract.toml` の「Full stops that do not end a sentence」節に書いた。`.` (U+002E) と `．` (U+FF0E) は、次のどちらかなら文の終わりにしない。

1. 直前と直後がどちらも数字 (ASCII 0-9 または全角 U+FF10-FF19)。`3.14`、`2.0.1`、`３．５`。
2. 略語 `e.g.` / `i.e.` の中の `.`。ASCII の大文字小文字は区別しない。略語の前がテキストの先頭か ASCII 英数字以外のときだけ略語とみなす (`Note.g.` の `g.` は略語ではない)。

文の終わりでない `.` の後ろでは、閉じ括弧の取り込みもしない。終止符の集合、閉じ括弧の取り込み、空白の除去、SSML の扱いは変えない。

### 選ばなかった案

- **略語の一覧を広げる (Mr. / Dr. / etc. など)**: Rust の `text_splitter.rs` には独自の一覧があるが、学習側の G2P がどう読むかは語ごとに違う。今回は golden に入っていて学習時と食い違いが確認できた `e.g.` / `i.e.` だけにした。増やすときは契約の `[[non_terminating_abbreviations]]` に足せば、全ランタイムのテストが一覧の一致を検査する。
- **`3.` の後ろに空白がなければ切らない**: `Count to 3.Then stop.` のように空白なしで次の文が続く書き方もある。数字に挟まれたときだけ切らない規則のほうが誤りが少ない。

## 再発防止

- 契約に `[[split_cases]]` (13 件) を置き、`scripts/regenerate_text_splitter_fixture.py` が `tests/fixtures/text_splitter/contract.json` にコピーする。各ランタイムの契約テストは全ケースで分割結果の完全一致を検査する。
- `scripts/check_text_splitter_contract.py` は、契約の `[consumers].split_case_tests` に並べたテストが存在し、fixture の `split_cases` を読み続けていることを検査する (pre-commit と parity-hub)。
- Python ランタイムの golden 照合 (`src/python_run/tests/test_g2p_golden_parity.py`) は、全ケースを `PiperVoice.phonemize` (分割あり) にも通す。本当に複数の文である入力 (`。，！`) を除き、1 文のまま分割なしと同じ音素列になることを検査する。旧分割では `3.14` (en/es) と `e.g. and i.e.` で失敗する。
- Python / Rust / Go / C# / C++ / JS のテストを動かす CI (python-tests、rust-tests、go-ci、csharp-ci、ci、test-webassembly) は、`tests/fixtures/text_splitter/**` の変更でも走る。以前は fixture だけを変えた PR で各ランタイムの契約テストが走らなかった。
- ゲート自身のテスト (`tests/scripts/test_check_text_splitter_contract.py`) は parity-hub の text-splitter ジョブで動かす。`tests/scripts` 配下は CI で一括実行されないため、#823 の `test_check_cjk_punctuation_contract.py` も実行されていなかった。parity-hub に cjk-punctuation ジョブを足して、こちらも動かす。

## 各ランタイムの実装

| ランタイム | 分割の実装 | 契約テスト |
|------------|------------|------------|
| Python | `src/python_run/piper_plus/text_splitter.py` (`_ends_sentence`) | `src/python_run/tests/test_text_splitter_contract.py` |
| Rust | `piper-core/src/streaming.rs` (`ends_sentence`) | `piper-core/tests/test_text_splitter_contract.rs` |
| Go | `piperplus/text_splitter.go` (`endsSentence`) | `piperplus/text_splitter_contract_test.go` |
| C# | `PiperPlus.Core/Phonemize/TextSplitter.cs` (`EndsSentence`) | `PiperPlus.Core.Tests/TextSplitterContractTests.cs` |
| C++ | `src/cpp/sentence_split.hpp` (`isNonTerminatingFullStop`) | `src/cpp/tests/test_text_splitter_contract.cpp` (新規) |
| JS | `openjtalk-web/src/streaming-pipeline.js` (`TextChunker`) | `openjtalk-web/test/js/test-streaming-pipeline.js` |

Rust の `text_splitter.rs` (`split_chunks`) は `.` の直後が空白か文末のときだけ切るため、もともと `3.14` では切らない。回帰テストだけを足した。

## 今回は直さなかった差

今回の規則とは別の、以前からある差である。`split_cases` はどのランタイムでも通る。

- Rust (`streaming.rs`) と C# は `．` (U+FF0E) を終止符にしない (契約の `RUNTIME_*_OMITS` で記録済み)。`３．５` のケースは、この差によっても通る。
- C++ の OpenJTalk mode は `。！？` でしか切らない。Multilingual mode は `…` でも切り、長いテキストを長さで分ける。チャンク前後の空白は除かない (契約テストは前後の空白を除いて比較する)。
- JS の `TextChunker` は言語ごとに終止符が違う (ja は `。！？!?`、それ以外は `.!?`)。閉じ括弧を取り込まない。英語では Mr. / Dr. など 30 語の略語でも切らない。
