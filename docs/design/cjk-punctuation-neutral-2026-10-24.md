# CJK 句読点をどの言語にも属さない文字として扱う (#823、2026-10-24)

## 1. 何が起きていたか

多言語の言語判定 (`UnicodeLanguageDetector`) は、、。，！？「」などの CJK 句読点と全角の記号を、
言語に `ja` が含まれていると日本語に振り分けていました (Python・Rust・Go・`@piper-plus/g2p`・C#)。
C++ だけは #262 で既にどの言語にも属さない文字 (中立) として扱っていました。

日本語に振り分けると、多言語モデルで次のことが起きます。

| 入力 | 修正前 | 本来 |
|---|---|---|
| `北京欢迎你。` | `。` が日本語の区間になり、日本語の音素化器が何も出さないので `.` が消える | 中国語の区間のまま `.` を出す |
| `你好，GPS` | `，` の日本語区間が中国語と英語の間に挟まり、GPS が中国語読み (ZH-EN loanword) にならない | GPS を中国語読みする |

Python 自身もこの動作だったため、正解ファイル (`phoneme_test_cases_golden.json`) も中国語の句読点を持っていませんでした。
他のランタイムの照合テストは、中国語の句読点と単語区切りを除いてから比べる回避策で差を隠していました。

## 2. 決めたこと

正本は [`docs/spec/cjk-punctuation-contract.toml`](../spec/cjk-punctuation-contract.toml) です。

1. **中立にする範囲**: U+3000-303F、U+FF00-FF20、U+FF3B-FF40、U+FF5B-FF64、U+FFE0-FFEF。
   全角ラテン文字 (U+FF21-FF3A、U+FF41-FF5A) は従来どおりラテン文字、半角カナ等 (U+FF65-FFDF) は文字として従来どおりに扱います。
   中立な文字は前の区間に付くので、中国語の文は句読点ごと 1 つの区間になります。
2. **ラテン文字の区間での置き換え**: 言語が en / es / fr / pt (pt-PT を含む) / sv の区間は、音素化器に渡す前に次のように置き換えます。
   - U+FF01-FF5E (全角の ASCII 記号と数字) → 対応する ASCII
   - 、 ､ → `,`、 。 ｡ → `.`
   - その他の中立な文字 → 半角空白 1 個

   置き換えないと、英語 G2P (g2p_en とその移植) が知らない文字を消すため、`Hello，world` の 2 語がつながります。
   中国語の音素化器は ，。！？ を自分で `,` `.` `!` `?` にし、日本語は OpenJTalk がそのまま読むので、置き換えません。
3. **1 言語だけで読む経路も同じ**: C# CLI の `--language en` などと、Rust の C FFI (`piper_plus_g2p_phonemize`、Swift の `PiperPlusG2P` が使う) は多言語の区間分けを通らないため、ラテン文字の言語ではそこで同じ置き換えをします。

## 3. 学習データへの影響

`prepare_multilingual_dataset.py` は言語ごとの音素化器 (`get_phonemizer(lang)`) で学習データを作るので、変わりません。
中国語の学習データは、もともと句読点を `,` `.` として持っていました。
今回の変更で、推論時の多言語音素化が 1 言語の文を学習時と同じ音素列にするようになります
(`test_one_language_text_matches_the_training_phonemizer` で固定)。

`preprocess.py` の多言語経路 (`--language ja-en-zh...`) は `MultilingualPhonemizer` を使うので、
中国語の文の句読点が出るようになります。

## 4. 再発防止

- **契約から作る fixture**: `scripts/build_cjk_punctuation_fixture.py` が契約から
  `tests/fixtures/g2p/cjk_punctuation_cases.json` を作ります。ランタイムの出力から作らないので、
  契約からずれたランタイムは自分のテストで失敗します。
- **全ランタイムの契約テスト**: Python (学習側・`piper-plus`)、Rust、Go、`@piper-plus/g2p`、C#、C++ の
  7 つのテストが fixture を読み、中立の判定・全角ラテン文字・置き換え・中国語の文・`你好，GPS`・ラテン文字の 4 例を確かめます。
- **ゲート**: pre-commit `cjk-punctuation-contract` (`scripts/check_cjk_punctuation_contract.py`) が、
  fixture が契約と同期していることと、`[consumers].tests` の各テストが存在して fixture を読んでいることを検査します。
  ゲート自体のテストは `tests/scripts/test_check_cjk_punctuation_contract.py` です。
- **正解ファイル**: #823 の 9 ケース (中国語の句読点、中国語と英語の混在、全角の句読点・数字を含む英語とスペイン語) を追加し、
  中国語の句読点を除く回避策を C++ / Rust / Go / JS / C# / Swift / Android の照合テストから削除しました。
  各ランタイムの CI は fixture の変更でも走ります。

## 5. 残る差

次は既存の Issue の原因で一致しないため、`known_divergences.json` に記録しています。

| ランタイム | ケース | 原因 |
|---|---|---|
| Swift | 中国語と英語の混在 4 件 | FFI は 1 言語の音素化器で読み、ZH-EN loanword を通らない (#827) |
| C# | 中国語と英語の混在 4 件 | `--language zh` は中国語の音素化器だけで読む (#833) |
| C# | `Hello，world` / `Hello、world。` / `Hola，amigo！` | DotNetG2P の英語・スペイン語の差 (#832) |
| C# / Go | `I have ３ cats．` | 数字を英単語にしない (#821) |
| `@piper-plus/g2p` | 中国語 5 件 | 文字単位で辞書がない (#829) |
| `@piper-plus/g2p` / piper-wasm | 英語 3 件 | JS の英語 G2P の差 (#828) |

Go のスペイン語は句読点の後の単語区切りを落としていたため (`Hola, amigo` で `,` の直後に区切りがない)、Python に合わせて直しました。

英単語の直後の句読点 (`Hello，你好` の `，`、半角の `Hello, 你好` の `,`) は、英語の区間が中国語読みの経路に渡されて
その経路が句読点を出さないため、Python でも出ません。今回の変更の前からある動作で、変えていません。

## 6. ランタイムごとの違い (契約の外)

半角カナ・半角ハングル (U+FF65-FFDF) の扱いは今回変えていないため、ランタイムで違いが残っています。
Python は `ja` があればすべて日本語、Go は `ja` がなく `zh` があると中国語、
C++ は U+FFA0-FFDC を韓国語にします。学習済みモデルに韓国語は含まれません。
