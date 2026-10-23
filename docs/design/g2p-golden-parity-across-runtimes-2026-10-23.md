# G2P の正解照合を全ランタイムでそろえる (2026-10-23)

## 1. 何が起きていたか

`tests/fixtures/g2p/phoneme_test_cases_golden.json` は Python の
`MultilingualPhonemizer` が出す音素列で、学習データの音素化と同じ処理です。
各ランタイムの G2P がこれと同じ音素列を出さないと、学習時と違う入力を
モデルに渡すことになります。

ところが、正解と完全一致で比べていたのは Kotlin (L3) と Rust の中国語の一部だけでした。
Swift は違うケースを決め打ちの一覧で飛ばし、Go と WASM の golden テストは辞書がないと黙ってスキップしていました。
ほかのテストは「この音素を含む」「何音素以上」といった構造チェックにとどまり、
次の不具合が見逃されていました。

| 見逃されていた不具合 | ランタイム | 対応 |
|---|---|---|
| 辞書にない英単語・数字・アクセント付き文字が音素ゼロになる | C++ / Rust | #821 |
| フランス語のエリジオン (`c'est`) とリエゾン (`est-il`) が未実装 | C++ / Rust | #822 |
| es / fr / pt / sv の文末 `?` が消える (日本語の疑問 EOS と同じ扱い) | Rust | 本変更で修正 |
| 英字の中国語読みで `E` (yi1) に「一」の声調変化をかける | Rust | 本変更で修正 |
| `language_override` が音素化に届かず、ラテン文字が常に英語として読まれる | Rust (piper-core) | 本変更で修正 |
| 英語の Rust golden テストが CMU 辞書のない環境で黙ってスキップする | Rust | 本変更で置き換え |
| `voice.rs` の単体テスト (44 件) が CI で一度も動いていない | Rust | 本変更で CI に追加 |
| 言語指定 (`WithLanguage` / `language_id`) が音素化に届かない | Go / python_run | 本変更で修正 |
| ja 以外の文末 `?` が消える | Go / python_run | 本変更で修正 |
| 英字の中国語読みに声調変化をかける | Go / C# | 本変更で修正 |
| スペイン語の強勢記号が音節の頭に付く (Python は強勢母音の直前) | Go / C# | 本変更で修正 |
| python_run の `CHAR2TOKEN` が後の項目で上書きされ、多文字音素の PUA 変換が壊れる | python_run | 本変更で修正 |
| piper-wasm が ja 以外でも言語指定なしの音素化を使う | WASM (Rust) | 本変更で修正 |
| C# の英語で句読点付きの語やアクセント付きの語が辞書に当たらない、フランス語の `y` が日本語の音素になる、ポルトガル語の破擦音と鼻母音が ID 表にない形になる | C# | 本変更で修正 |
| 外部 DotNetG2P (es/fr/pt/en) が Python と違う規則で読む | C# | #832 |
| `--language zh` で英字が中国語読みにならない | C# | #833 |
| 英語 G2P が g2p_en と違う (未知語・数字・句読点) | WASM / npm g2p | #828 |
| npm g2p の中国語が辞書と違う読みを出す | npm g2p | #829 |
| 英字の中国語読みが Python と違う | Swift | #827 |
| sv の読みが学習側と違う | python_run | #830 |

## 2. 仕組み

### 2.1 既知の差の記録

- `tests/fixtures/g2p/known_divergences.json` — ランタイムごとに、正解と違うことが分かっているケースを記録します。
  各項目には Issue 番号と理由が必須です。
  `status` は 2 つあります。`planned` は Issue で直す予定のものです。
  `accepted` は Python の学習済み推定器や品詞判定に頼るため、完全一致を目指さないものです。
- `tests/fixtures/g2p/english_no_drop_words.json` — 単独で渡したときに音素ゼロになってはいけない英単語です。
  まだ落とすランタイムは `known_drops` に記録します。

### 2.2 テストのルール (全ランタイム共通)

1. 記録にない差があれば失敗する。
2. 記録にあるのに一致したら失敗する。
   直した人が記録を消すことになり、記録は直った分だけ縮みます。
3. 比べたケースが 0 件なら失敗する。
   正解ファイルや辞書の読み込みが壊れたときに、黙って成功しないようにするためです。
4. 失敗は最初の 1 件で止めず、全件をまとめて報告する。

表記の違いは差として数えません。

- 正解側の `rr` / `tʃ` / `tone3` は `pua.json` で PUA 1 文字に変換して比べます。
  ランタイム側は変換しません。両側を変換すると、PUA 化を忘れた実装まで一致扱いになるためです。
- 中国語の句読点と単語区切りは除いて比べます (#823 まで)。

### 2.3 記録そのものの検査

`scripts/check_g2p_known_divergences.py` は、ランタイムをビルドせずに記録を検査します。
pre-commit hook `g2p-known-divergences` と workflow `G2P Known Divergences Gate` で実行されます。
検査内容は次のとおりです。

- 各項目に、宣言済みのランタイム・Issue 番号・理由があること。
- 記録したケースが正解ファイルに存在すること。
- 同じランタイムに同じケースが重複していないこと。
- `runtimes` に宣言した各ランタイムのテストファイルが存在し、`known_divergences.json` を読んでいること。
  テストを消したり記録を読まなくなったりすると、ここで落ちます。

## 3. ランタイムごとの照合対象

| runtime | 照合する入口 | テスト |
|---|---|---|
| `cpp` | `piper_plus_g2p_phonemize` (C API。C++ CLI・Android AAR・iOS が同じ実装) | `src/cpp/tests/test_c_api_g2p_golden.cpp` (ctest)、Android L3 `PhonemeFixtureParityTest` |
| `rust` | `MultilingualPhonemizer::phonemize_with_language` (piper-core が言語指定ありで使う入口) | `src/rust/piper-plus-g2p/tests/golden_parity.rs` |
| `go` | `MultilingualPhonemizer.PhonemizeWithLanguage` (`piperplus` の `WithLanguage` が使う入口) | `src/go/phonemize/golden_parity_test.go` |
| `wasm` | piper-wasm の G2P を含むブラウザ版 `piper-plus` の音素化 | `src/wasm/openjtalk-web/test/js/test-g2p-golden-parity.js` |
| `js-g2p` | `@piper-plus/g2p` の音素化 | `src/wasm/g2p/test/test-g2p-golden-parity.js` |
| `python_run` | `PiperVoice.phonemize(text, language_id)` の G2P | `src/python_run/tests/test_g2p_golden_parity.py` |
| `swift` | `Phonemizer.phonemize(_:language:)` | `tests/PiperPlusG2PTests/GoldenParityTests.swift`、`GoldenPhonemeTests.swift` |
| `csharp` | CLI の text mode (`TextModePhonemizer`、`--language` 付き) | `src/csharp/PiperPlus.Cli.Tests/G2pGoldenParityTests.cs` |

辞書は `src/rust/piper-plus-g2p/data/` の CMU / pinyin を使います。
リポジトリに入っているファイルなので、読み込めなければスキップせずに失敗します。
日本語 (OpenJTalk 辞書) と韓国語 (正解ファイルにも学習済みモデルにもない) は対象外です。

Swift の `GoldenPhonemeTests.swift` は、決め打ちのスキップ一覧をやめて `known_divergences.json` を読みます。
Swift は Windows / Linux で実行できないため、Swift G2P CI (macOS) で確認します。

ランタイムごとの既知の差の件数は次のとおりです (2026-10-23)。

| runtime | 差の件数 | 内訳 (Issue) | 落とす英単語 |
|---|---|---|---|
| `cpp` / `rust` / `go` | 24 | #821 21、#822 3 | 20 / 20 / 7 |
| `swift` | 30 | #821 21、#822 3、#827 6 | 20 |
| `wasm` | 48 | #828 45、#822 3 | 7 |
| `js-g2p` | 101 | #828 42、#829 56、#822 3 | 7 |
| `python_run` | 51 | #830 51 (sv) | 0 |
| `csharp` | 106 | #832 83、#821 17、#833 6 | 8 |

Go は辞書にない英単語を生の文字のまま出すため、C++ / Rust と同じケースでも理由を分けて記録しています。

## 4. 言語指定の扱い (Rust)

Python の正解は、ケースの言語をラテン文字の既定言語にして生成しています。
文字種で分けたうえで、ラテン文字の部分をその言語として読む方式です。
C API も `languageId` から同じ既定言語を選びます。

Rust には、テキスト全体を 1 つの phonemizer に渡す `phonemize_with_language_hint` しかありませんでした。
また piper-core はこれも使わず、言語指定を language_id の選択にしか使っていませんでした。

そこで trait に `phonemize_with_language(text, language)` を追加しました。

- `MultilingualPhonemizer` は、ラテン文字言語ごとに検出器を用意してこれを実装します。
- piper-core の `SynthesisParams::language_override` と CLI の `--test-mode` はこの経路を通ります。
- 言語指定がないときの動作は変わりません。

## 5. CI の起動条件

正解ファイル・記録・`pua.json`・辞書を変えたときにも、それを読むテストが動くようにしました。

- `CI` (ci.yml): 新しい filter `g2p-golden` を追加し、`cpp-tests` と `rust-tests` の起動条件に入れた。
- `rust-tests.yml` / `G2P Rust CI`: 正解ファイル・記録・`pua.json` を paths に追加した。
- `Kotlin G2P CI`: #811 で追加済み。
- `Go CI` / `C# CI` / `Python Tests` / `G2P WASM CI` / `WebAssembly` / `Swift G2P CI`: 正解ファイル・記録・`pua.json`・辞書を paths に追加した。
- `CI` (ci.yml): `npm-package-tests` と `csharp-tests` / `csharp-build` の起動条件に `g2p-golden` を入れ、`npm-package-tests` に「G2P golden parity (runtime wasm)」ステップを追加した。
- pre-commit hook と `G2P Known Divergences Gate` の対象に、全ランタイムの照合テストを入れた。
