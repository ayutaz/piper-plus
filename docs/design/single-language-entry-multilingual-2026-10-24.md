# 1 言語を指定する入口を多言語の音素化器に通す (Issue #827 / #833)

## 問題

言語を 1 つ指定して音素化する入口のうち、次の 2 つは多言語の音素化器 (`MultilingualPhonemizer`) を通らず、指定言語の音素化器にテキスト全体を渡していた。

- C# CLI の text mode (`--language zh` 等、`src/csharp/PiperPlus.Cli/TextModePhonemizer.cs`)
- Rust の C FFI `piper_plus_g2p_phonemize` (`src/rust/piper-plus-g2p/src/ffi.rs`)。Swift の `PiperPlusG2P` はこれを呼ぶ

そのため英字を含む中国語の文 (`Hello你好`、`我用 GPS 导航`、`ChatGPT 很厉害` など 10 件) で、英字を pinyin で読む ZH-EN loanword の経路 (#384) に入らず、英字が生の文字 (`H e l l o`) のまま出た。音素 ID の表にない記号で、学習時 (Python の `MultilingualPhonemizer`) と違う入力になる。Swift では中国語として渡した数字 (`0`、`100`) も消えていた。

## 変更

| 入口 | 変更後 |
|------|--------|
| C# CLI `--language zh` | `MultilingualPhonemizer({zh, en})`、ラテン文字の既定は en |
| C# CLI `--language en/es/fr/pt/sv` | その言語だけを登録した `MultilingualPhonemizer`、ラテン文字の既定もその言語。golden の結果は変わらない (登録が 1 言語なので、中立な文字は同じ区間に入る) |
| C# CLI `--language ja/ko` | 従来どおり単独の音素化器 |
| Rust C FFI | ハンドルに登録した言語 (指定順) で `MultilingualPhonemizer` を作り、`phonemize_with_language(text, lang)` で読む。未登録の言語は従来どおり NULL |
| Rust C FFI の ja | 従来どおり日本語の音素化器にテキスト全体を渡す |

C# の `MultilingualPhonemizer` は、日本語以外の文末 `?` まで EOS として取り除いていた。Rust (`is_boundary_token`)・Go (`isBoundaryToken`)・Python ランタイムと同じく、日本語以外では `^` と `$` だけを取り除き、`?` は音素として残すようにした。これを直さないと、`--language zh` を多言語経路に通した時点で `你好吗？` の `?` が消える。

FFI が Latin 言語のときに自分で行っていた CJK 句読点の置き換え (#823) は、多言語経路の Latin 区間が同じことをするため削除した。C# CLI の `CjkPunctuationAsAsciiPhonemizer` も同じ理由で削除した。

### en を登録しない場合

Python の `MultilingualPhonemizer(["zh"])` は、英字を生の文字のまま出す。FFI もこれに合わせ、Swift で `Phonemizer(languages: [.chinese])` のように en を登録しない場合は英字がそのまま残る。英字を pinyin で読ませたいときは `.english` も登録する。

### ja を多言語経路に通さない理由

Rust・Python の多言語経路は、日本語の疑問の EOS (`?` と PUA の疑問マーカー) を区間の境界として取り除き、かなを含まない漢字 (`Hello世界`) を中国語と判定し、英字を OpenJTalk ではなく英語の音素化器で読む。FFI と C# CLI の `--language ja` はこれまで日本語の音素化器にテキスト全体を渡しており、Swift の `GoldenPhonemeTests` と C# の ID 組み立て (`JapanesePhonemizer.PostProcessIds`) はその出力を前提にしているため、変えない。

## 再発防止

- C# CLI: `src/csharp/PiperPlus.Cli.Tests/TextModeZhEnTests.cs` が CLI の入口 (`Program.ResolveTextModePhonemizer("zh")`) を通り、ZH-EN の 10 入力が `zh-en` 指定と同じ出力で、すべてテストモデルの `phoneme_id_map` にある音素でできていることを検査する。golden 照合 (`G2pGoldenParityTests`) も CLI の入口を通る。
- Rust C FFI: `src/rust/piper-plus-g2p/tests/golden_parity.rs` の `ffi_matches_phonemize_with_language` が、Swift の照合と同じ言語の順でハンドルを作り、golden 6 言語 347 件で FFI の出力が `phonemize_with_language` と一致することを検査する (`--all-features` で CI 実行)。これが通れば Swift の既知の差は Rust と同じになる。
- `known_divergences.json`: csharp の #833 の 10 件と swift の #827 の 10 件、swift の zh `0` / `100` を外し、swift の zh `123` を Rust と同じ accepted 項目に移した。一覧にある差が一致し始めると各ランタイムの照合テストが失敗するので、入口が再び多言語経路を外れると差の増加として検出される。

## 残る差

- C# の zh 数字 (`0`、`100`、`123`): 英語の区間に入るが、DotNetG2P.English が数字を展開しないため生のトークンのまま。#832 (C# の英語を CMU 辞書と正規化に置き換える) で扱う。
- `--language ja` で日本語の文に英字が混ざる場合、C# CLI と FFI は英字を OpenJTalk で読む。Python は英語として読む。golden に該当ケースがなく、照合では見えていない。
