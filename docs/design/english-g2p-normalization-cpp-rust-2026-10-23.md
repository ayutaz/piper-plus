# 英語 G2P の前処理を C++ / Rust に移植する (#821、2026-10-23)

## 1. 何が起きていたか

C++ (`src/cpp/english_phonemize.cpp`) と Rust (`src/rust/piper-plus-g2p/src/english.rs`) の英語 G2P は、
英字とアポストロフィの並びだけを単語として切り出し、CMU 辞書で引いていました。
そのため Python の正解 (`tests/fixtures/g2p/phoneme_test_cases_golden.json`) と次の点で違っていました。

| 入力 | Python | C++ / Rust (修正前) |
|---|---|---|
| `0` / `100` / `3.14` / `$5` / `2nd` | 数を英単語に展開して読む | 数字を区切りとして捨て、音素ゼロ |
| `café` / `naïve` | アクセントを外して `cafe` / `naive` を引く | アクセント付きの文字で単語が割れ、辞書にない断片を捨てる |
| `uh-huh` | ハイフン付きのまま 1 語として引く | `uh` と `huh` に分ける |
| `e.g.` / `i.e.` | `for example` / `that is` に置き換える | 1 文字ずつの単語として読む |
| `'quote'` | 両端の `'` を別の語にする | `'quote'` を 1 語として引き、辞書になく捨てる |
| `ChatGPT` / `TTS` / `xyz` | 学習済みのニューラル推定器で読む | 辞書になく捨てる (音素ゼロ) |

辞書にない語を捨てたときにも単語区切りのフラグだけが立つため、
出力の先頭に空白が入る不具合もありました。

## 2. Python がしていること

Python の英語 G2P は g2p_en (`src/python/g2p/piper_plus_g2p/_vendor/g2p_en/g2p.py`) です。
`G2p.__call__` は次の順で処理します。

1. `normalize_numbers` (`expand.py`) で数を英単語にする。
2. NFD に分解して結合文字 (アクセント) を除き、小文字にする。
3. `a-z ' . , ? ! -` と半角空白以外の文字を消す。タブと改行も消えるので、前後の語がつながる。
4. `i.e.` を `that is`、`e.g.` を `for example` に置き換える。
5. nltk の `TweetTokenizer` で単語に分ける。
6. 英字を含まない語はそのまま 1 トークンにする。英字を含む語は、同形異義語の表 (品詞で選ぶ)、CMU 辞書、ニューラル推定器の順に引く。

`english.py` の `phonemize_english_with_prosody` は、g2p_en の出力を語ごとに IPA にします。

- 語が `, . ; : ! ?` の 1 文字だけなら句読点として扱い、直前の語に空白なしで付ける。
- それ以外の語 (`...`、`'`、`-` を含む) は前に単語区切りを入れ、IPA の文字を 1 つずつ音素にする。`. . .` のような語では空白も 1 音素になる。
- 機能語 (`_FUNCTION_WORDS`) は強勢を外す。機能語かどうかは、**数字展開の前の元の文字列**を小文字にして `[a-zA-Z']+` で切り出した語を、句読点以外の語へ順に対応させて判定する。数字を展開すると対応がずれますが、学習データもこの動作で作られているので、そのまま再現します。

## 3. 移植の仕様

C++ と Rust は同じ仕様で実装し、共有 fixture で検査します。

### 3.1 共有 fixture

`tests/fixtures/g2p/english_normalize_cases.json` は `scripts/build_english_normalize_fixture.py` が
Python のコード (g2p_en の `normalize_numbers` と nltk の `TweetTokenizer`) から生成します。

- `numbers`: `normalize_numbers(input)` の結果。
- `tokens`: 2 章の手順 1〜5 を通した後の、小文字の語の列。

両ランタイムのテストはこのファイルを読み、全件の一致を求めます。件数が 0 なら失敗します。

### 3.2 数の展開 (`normalize_numbers`)

正規表現の置換を、この順に文字列全体へかけます。

1. `([0-9][0-9,]+[0-9])` の中のカンマを消す。
2. `£([0-9,]*[0-9]+)` → `\1 pounds`。
3. `\$([0-9.,]*[0-9]+)` → ドル表記。`.` で分けて 3 つ以上なら `<元の文字列> dollars`。ドルとセントが両方 0 以外なら `D dollar(s), C cent(s)`、片方だけならその単位だけ、両方 0 なら `zero dollars`。単数は 1 のときだけ。
4. `([0-9]+\.[0-9]+)` → `.` を ` point ` に置き換える。
5. `[0-9]+(st|nd|rd|th)` → 序数 (下記)。
6. `[0-9]+` → 整数 (下記)。

整数 `n` の読み:

- `1000 < n < 3000` は年号の読み。`2000` は `two thousand`、`2001`〜`2009` は `two thousand` + 1 桁、`n % 100 == 0` は `<n / 100> hundred` (例 `nineteen hundred`、`twenty-one hundred`)、それ以外は上 2 桁と下 2 桁を空白でつなぐ。下 2 桁が 1 桁なら `oh <数>` (例 `ten oh one`)。
- それ以外は `words(n, and="")`。

`words(n, and)` は inflect の `number_to_words` と同じです。

- `0` は `zero`。21〜99 の 1 の位は `-` でつなぐ (`twenty-three`)。
- 3 桁ごとの組に分け、0 でない組を `<百の位> hundred<and><下 2 桁> <単位>` にする。`<and>` は `and` が空なら空白 1 つ、そうでなければ ` and `。単位は `thousand`、`million`、`billion`、`trillion`、`quadrillion`、`quintillion`。
- 組は `, ` でつなぐ。ただし最後の組が 1〜99 で、上に組があるときは、最後の組の前を `<and>` でつなぐ (`one million one`、`five thousand and fifth`)。
- 先頭の 0 は無視する (`007` は `seven`)。

序数は `words(n, and="and")` の最後の語を序数にします。`one`→`first`、`two`→`second`、`three`→`third`、`five`→`fifth`、`eight`→`eighth`、`nine`→`ninth`、`twelve`→`twelfth`、`zero`→`zeroth`、`-y` で終わる語は `-ieth`、それ以外は `-th` を付けます。序数には年号の読みを使いません (`1100th` は `one thousand, one hundredth`)。

### 3.3 文字の正規化

数の展開の後、NFD に分解して結合文字を除きます。
`a-zA-Z ' . , ? ! -` と半角空白以外の文字を消し、`i.e.` と `e.g.` を大文字小文字を問わずに置き換えます。
Python は小文字にしてから処理しますが、移植では大文字小文字を残します。
CamelCase を分けるのに元の大文字が要るためです。語を辞書で引くときに小文字にします。

### 3.4 単語分割 (`TweetTokenizer` のうち、この文字種で起こる部分)

まず、英字・数字以外の同じ文字が 4 つ以上続くところを 3 つに詰めます (`!!!!` → `!!!`、`a----b` → `a---b`)。

次に、文字列の先頭から、各位置で次の候補を上から順に試し、最初に一致したものを 1 語として取ります。
最長一致ではありません。英字の比較は大文字小文字を区別しません。

1. ドメイン形: `[a-z]+([.-][a-z]+)*\.[a-z]{2,13}` の直後が英字でない (例 `hello.world`、`foo.bar.baz`、`uh-huh.ok`)。`a.b` は 2 文字目以降が 1 文字なので一致しない。
2. アポストロフィ・ハイフン入りの語: `[a-z]([a-z]|['-])+[a-z]` (例 `don't`、`o'clock`、`uh-huh`、`a---b`)。
3. 英字の並び: `[a-z]+`。
4. 省略記号: `\.( *\.)+` (例 `...`、`. . .`)。
5. 空白以外の 1 文字。

空白は語を区切るだけで、語にはなりません。

### 3.5 語の読み

- 英字を含まない語はそのまま 1 トークンにする。`, . ! ?` の 1 文字なら句読点、それ以外は語として扱う (2 章)。
- 英字を含む語は小文字にして CMU 辞書を引く。同形異義語の品詞判定は移植しない (#821 で accepted)。
- 辞書にない語は、次の順で読みます。どれも Python のニューラル推定器とは一致しませんが、音素ゼロにはしません。
  1. 既存の形態素フォールバック (語尾 `-s` / `-ed` / `-ing` などを外して引き直す)。
  2. `-` か `.` を含む語 (`uh-huh` 以外の辞書にないハイフン語や、ドメイン形の語) は `-` と `.` で分け、各部分をこの手順で読んで 1 語につなげる。
  3. `'` を含む語は `'` を除いて引き直し、なければ除いた形で次の手順に進む。
  4. 元の文字列に大文字があれば `[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+` で分け、2 つ以上に分かれたら各部分をこの手順で読んで 1 語につなげる (`ChatGPT` → `Chat` + `GPT`、`iPhone` → `i` + `Phone`)。
  5. 1 文字ずつ英字の名前で読む (`TTS` → `T` + `T` + `S`)。読みは下の表で、部分の間に単語区切りは入れない。

| 英字 | ARPAbet | 英字 | ARPAbet | 英字 | ARPAbet |
|---|---|---|---|---|---|
| a | EY1 | j | JH EY1 | s | EH1 S |
| b | B IY1 | k | K EY1 | t | T IY1 |
| c | S IY1 | l | EH1 L | u | Y UW1 |
| d | D IY1 | m | EH1 M | v | V IY1 |
| e | IY1 | n | EH1 N | w | D AH1 B AH0 L Y UW0 |
| f | EH1 F | o | OW1 | x | EH1 K S |
| g | JH IY1 | p | P IY1 | y | W AY1 |
| h | EY1 CH | q | K Y UW1 | z | Z IY1 |
| i | AY1 | r | AA1 R | | |

### 3.6 機能語の判定

数字展開の前の入力を ASCII の小文字にし、`[a-zA-Z']+` で切り出した語を、句読点以外の語へ順に対応させます (2 章)。

## 4. 変わらないもの

- 同形異義語は CMU の最初の読みのままです (Python は品詞で選ぶ)。
- 2 桁の複合数 (`twenty-three` など) は CMU にないので、Python はニューラル推定器で読みます。移植は `twenty` と `three` の読みを 1 語につなげるため、強勢の位置が Python と違います。`123` は accepted として記録に残します。
- piper-core の `phonemize::english` (公開 API だが音声合成では使っていない旧実装) は変更しません。音声合成は piper-plus-g2p の英語 G2P を使います。

## 5. テストと CI

| テスト | 見ているもの |
|---|---|
| Rust `piper-plus-g2p/tests/english_normalize.rs`、C++ ctest `test_english_normalize` | `english_normalize_cases.json` の全件 (`numbers` と `tokens`) と、辞書にない語の読み方 (3.5) |
| Rust `golden_parity.rs`、C++ ctest `G2pGolden.*` | Python の正解との全件照合。記録 (`known_divergences.json` / `english_no_drop_words.json`) にない差と、記録にあるのに一致した項目で失敗する |
| pre-commit `english-normalize-fixture-drift` | `scripts/build_english_normalize_fixture.py --check`。vendored の g2p_en を変えたのに fixture を作り直していないと失敗する |

fixture・記録・CMU 辞書が変わったときにも C++ と Rust のテストが走るよう、
`ci.yml` の `g2p-golden` と `g2p-rust-ci.yml` / `rust-tests.yml` の paths に fixture を入れています。

移植後の照合結果は次のとおりです。

- 一致するようになった 12 件 (en `0` / `1` / `3.14` / `100` / `It's 3 o'clock.` / `e.g. and i.e.` / `uh-huh` / `naïve` / `café` / `'quote'`、zh `0` / `100`) を `cpp` / `rust` の記録から外しました。
- `english_no_drop_words.json` の 20 語はどちらのランタイムでも読まれるようになったので、`known_drops` から `cpp` / `rust` を外しました。
- 残る英語の差は、`123` (4 章)、辞書にない語 5 件 (`ChatGPT and GitHub` / `UPPERCASE` / `MixedCase` / `xyz` / `aaaaa`)、`a-b-c`、`résumé` です。いずれも Python のニューラル推定器か品詞判定が要るので accepted です。
- Android (L3) は C++ の記録を共有するので、同じ結果になります。
- Swift (`PiperPlusG2P`) は C FFI 経由で piper-plus-g2p の英語 G2P を使います。英語の 10 件と 20 語が同じく直るので、`swift` も記録から外しました。テキスト全体を指定言語の phonemizer に渡すため、zh の `0` / `100` は英語の経路を通らず、記録に残ります。残る英語の差 6 件は `cpp` / `rust` と同じ accepted の項目にまとめました。
