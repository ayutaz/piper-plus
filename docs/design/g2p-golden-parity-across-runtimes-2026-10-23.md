# G2P の正解照合を全ランタイムでそろえる (2026-10-23)

## 1. 何が起きていたか

`tests/fixtures/g2p/phoneme_test_cases_golden.json` は Python の
`MultilingualPhonemizer` が出す音素列で、学習データの音素化と同じ処理です。
各ランタイムの G2P がこれと同じ音素列を出さないと、学習時と違う入力を
モデルに渡すことになります。

ところが、正解と完全一致で比べていたのは Kotlin (L3) と Rust の中国語の一部だけでした。
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

辞書は `src/rust/piper-plus-g2p/data/` の CMU / pinyin を使います。
リポジトリに入っているファイルなので、読み込めなければスキップせずに失敗します。
日本語 (OpenJTalk 辞書) と韓国語 (正解ファイルにも学習済みモデルにもない) は対象外です。

Go / C# / WASM / python_run の照合と、Swift のスキップ一覧の記録化は後続の変更で足します。

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
