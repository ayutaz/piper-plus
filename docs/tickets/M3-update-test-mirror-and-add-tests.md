# M3: テストミラー更新 + テストケース追加

> **マイルストーン:** [M3](../milestones-346-cpp-cjk-closing-bracket.md#m3-テストミラー更新--テストケース追加)
> **Issue:** [#346](https://github.com/ayutaz/piper-plus/issues/346)
> **ブランチ:** `fix/cpp-cjk-closing-bracket-346`
> **前提チケット:** [M2](M2-add-closing-bracket-consumption-loop.md)
> **後続チケット:** [M4](M4-ci-verification-and-pr.md)

---

## 1. タスク目的とゴール

`src/cpp/tests/test_split_sentences.cpp` は `piper.cpp` の `splitTextToSentences()` アルゴリズムを匿名名前空間にミラーコピーして単体テストを行っている (ONNX Runtime リンク回避のため)。M1/M2 で `piper.cpp` に追加した `isClosingPunctuation()` ヘルパーと閉じ括弧消費ループをこのミラーにも反映し、10 個の新規テストケースで動作を検証する。

**ゴール:**

1. テストミラーを `piper.cpp` の M1/M2 変更と同期させる
2. CJK 閉じ括弧 (6 テスト)、Western 閉じ括弧 (2 テスト)、リグレッション防止 (2 テスト) の合計 10 テストケースを追加する
3. 既存の 26 テスト (SplitSentencesTest: 22 + DynamicChunkSizeTest: 4) が全て PASS のまま維持されることを確認する

---

## 2. 実装する内容の詳細

### 2.1 テストミラー更新

**対象ファイル:** `src/cpp/tests/test_split_sentences.cpp`

テストファイルの匿名名前空間 (18-129 行) に `piper.cpp` のアルゴリズムがミラーされている。以下の 2 箇所を変更する。

#### 2.1.1 `isClosingPunctuation()` の追加

**挿入場所:** 匿名名前空間内、`splitTextToSentences()` 関数の直前 (56 行付近)。既存の `isPunctCodepoint()` (32-40 行) と `calculateDynamicChunkSize()` (43-55 行) に続く形で、独立した関数として追加する。

```cpp
// ---- Mirror of piper.cpp isClosingPunctuation (Issue #346, M1) ----
bool isClosingPunctuation(char32_t cp) {
  switch (cp) {
    case U')': case U']': case U'}': case U'"': case U'\'':
    case U'\u300D': // 」 Right Corner Bracket
    case U'\u300F': // 』 Right White Corner Bracket
    case U'\uFF09': // ） Fullwidth Right Parenthesis
    case U'\uFF3D': // ］ Fullwidth Right Square Bracket
    case U'\u3011': // 】 Right Black Lenticular Bracket
    case U'\uFF63': // ｣  Halfwidth Right Corner Bracket
    case U'\u201D': // "  Right Double Quotation Mark
      return true;
    default:
      return false;
  }
}
```

**注意:** この関数は匿名名前空間のファイルスコープ関数として追加する。ミラー版の `splitTextToSentences()` 内のラムダではなく独立関数とする (piper.cpp 側が static 関数であるため)。

#### 2.1.2 閉じ括弧消費ループの追加

**挿入場所:** ミラー版 `splitTextToSentences()` 内、boundary punctuation 消費ループの直後、`i = punctEnd - 1;` の直前 (現在の 111 行付近)。

現在のコード (106-111 行):
```cpp
      while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {
        if (isSentenceTerminator(cps[punctEnd])) hasTerminator = true;
        punctEnd++;
      }
      i = punctEnd - 1;
```

変更後:
```cpp
      while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {
        if (isSentenceTerminator(cps[punctEnd])) hasTerminator = true;
        punctEnd++;
      }
      // Issue #346: 文末記号の後の閉じ括弧を消費
      if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
          punctEnd++;
        }
      }
      i = punctEnd - 1;
```

`hasTerminator` ガードにより、文末記号がない場合 (カンマのみ等) の閉じ括弧は消費しない。これは `piper.cpp` (M2) と同一のロジックである。

### 2.2 テストケース一覧

全テストは `SplitSentencesTest` テストスイートに追加する。既存テスト (JapaneseBasic, EnglishBasic 等) と同じパターンで、`splitTextToSentences()` のミラー関数を直接呼び出す。

#### Priority 1: CJK 閉じ括弧 (Issue #346 直接対象) -- 6 テスト

| # | テスト名 | 入力 | 期待出力 | PhonemeType | テスト意図 |
|---|---------|------|---------|-------------|-----------|
| 1 | `CJKClosingBracket_BasicKakko` | `「こんにちは。」次の文。` | `["「こんにちは。」", "次の文。"]` (2文) | `MultilingualPhonemes` | Issue #346 の基本再現ケース。Rust `test_split_sentences_with_closing_brackets` および C# `ClosingPunctuation_JapaneseQuotes` と同一入力。鉤括弧 `」` (U+300D) が文末記号 `。` の後に正しく消費されること |
| 2 | `CJKClosingBracket_DoubleCornerBracket` | `『素晴らしい！』感動した。` | `["『素晴らしい！』", "感動した。"]` (2文) | `MultilingualPhonemes` | 二重鉤括弧 `』` (U+300F) の消費。全角感嘆符 `！` (U+FF01) が文末記号として機能し、`』` が同じ文に含まれること |
| 3 | `CJKClosingBracket_FullwidthParen` | `結果は（成功です。）次へ。` | `["結果は（成功です。）", "次へ。"]` (2文) | `MultilingualPhonemes` | 全角丸括弧 `）` (U+FF09) の消費。括弧内の `。` が文末記号として発動し、`）` まで消費して分割すること |
| 4 | `CJKClosingBracket_Sumitsuki` | `【テスト。】次。` | `["【テスト。】", "次。"]` (2文) | `MultilingualPhonemes` | 隅付き括弧 `】` (U+3011) の消費。CJK 特有の括弧種での動作確認 |
| 5 | `CJKClosingBracket_HalfwidthKakko` | `｢テスト。｣次。` | `["｢テスト。｣", "次。"]` (2文) | `MultilingualPhonemes` | 半角鉤括弧 `｣` (U+FF63) の消費。半角 CJK 括弧での動作確認 |
| 6 | `CJKClosingBracket_MultipleBrackets` | `「『OK。』」次。` | `["「『OK。』」", "次。"]` (2文) | `MultilingualPhonemes` | 連続する複数の閉じ括弧の貪欲消費。`。` の後に `』` と `」` が続くケースで両方とも消費されること |

#### Priority 2: Western 閉じ括弧 -- 2 テスト

| # | テスト名 | 入力 | 期待出力 | PhonemeType | テスト意図 |
|---|---------|------|---------|-------------|-----------|
| 7 | `WesternClosingQuote` | `She said "Hello." Then left.` | `["She said \"Hello.\"", ...]` (2文以上、第1文に `"` が含まれること) | `MultilingualPhonemes` | ASCII ダブルクォート `"` (U+0022) の消費。C# `ClosingPunctuation_WesternQuotes` と同一入力。英語の引用パターンでの閉じ括弧消費 |
| 8 | `WesternClosingParen` | `Result (ok.) Next.` | `["Result (ok.)", ...]` (2文以上、第1文に `)` が含まれること) | `MultilingualPhonemes` | ASCII 丸括弧 `)` (U+0029) の消費。英語テキストでの括弧閉じ消費 |

**注意:** Western テストの期待出力は、C++ ミラーが空白のトリミングを行わない (Rust/C# は行う) ため、第2文以降の先頭空白の有無で Rust/C# と微妙に異なる可能性がある。テストでは第1文の内容を厳密に検証し、分割数は `>=2` でアサートする。実際のミラーコード確認後、空白の扱いに応じて期待値を調整する。

#### Priority 3: リグレッション防止 + エッジケース -- 2 テスト

| # | テスト名 | 入力 | 期待出力 | PhonemeType | テスト意図 |
|---|---------|------|---------|-------------|-----------|
| 9 | `CJKClosingBracket_NoClosingNoop` | `テスト。次のテスト。` | `["テスト。", "次のテスト。"]` (2文) | `MultilingualPhonemes` | 閉じ括弧なしの既存動作が変わらないことの確認。消費ループが空回りして既存分割に影響しないこと |
| 10 | `CJKClosingBracket_NoTerminatorNoop` | `「テスト」続き。` | 1文 (`["「テスト」続き。"]`) | `MultilingualPhonemes` | 文末記号なしの閉じ括弧は消費しないことの確認。`hasTerminator` ガードにより、`「テスト」` の `」` の前に文末記号がないため分割が発生しないこと |

### 2.3 テストコードの配置

新規テストは既存のセクション構造に従い、ファイル末尾 (409 行の `HighPunctDensityCJK` テストの後) に新しいセクションとして追加する:

```cpp
// ========================================================================
// Issue #346: CJK closing bracket consumption
// ========================================================================

TEST(SplitSentencesTest, CJKClosingBracket_BasicKakko) { ... }
// ... (10テスト)
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CJK テスト実装 | 1名 | テストミラー更新 (2.1.1, 2.1.2) + CJK テスト 6個 (#1-#6) の実装 |
| Western テスト実装 | 1名 | Western テスト 2個 (#7-#8) + リグレッションテスト 2個 (#9-#10) の実装 |
| クロスランタイム照合 | 1名 | Rust `streaming.rs` / C# `TextSplitterTests.cs` / Go `text_splitter_test.go` のテストケースとの照合。期待出力の整合性を確認 |
| レビュー | 1名 | ミラーと `piper.cpp` の差分確認、テストの網羅性、UTF-8 リテラルの正しさ、MSVC ビルド互換性を検証 |

**合計: 4名** (CJK 実装とミラー更新は同一人物が担当してよい。実質 2-3 名で完了可能)

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲

| 項目 | スコープ内 | スコープ外 |
|------|----------|-----------|
| テストミラー更新 | `isClosingPunctuation()` + 消費ループ追加 | ミラー方式の廃止・リファクタ |
| テストケース | 10 個の新規テスト | 既存 26 テストの変更 |
| CMake | 変更なし (`test_split_sentences` は既に `TEST_SOURCES` の 63 行目に登録済み) | 新規テストバイナリの追加 |
| リンク依存 | 変更なし (gtest + gtest_main + `utf8_utils.hpp` のみ、126-130 行で include path 設定済み) | ONNX Runtime リンクの追加 |
| テスト対象 PhonemeType | `MultilingualPhonemes` (全 10 テスト) | `OpenJTalkPhonemes` / `EnglishPhonemes` での閉じ括弧テスト |

**MultilingualPhonemes を選択する理由:** Issue #346 のユースケースはマルチリンガルモデルでの CJK テキスト合成。`MultilingualPhonemes` は `。！？.!?` の全てを文末記号として扱うため、CJK と Western の両方をカバーできる。

### 4.2 ユニットテスト

#### テストケース詳細仕様

**テスト #1: CJKClosingBracket_BasicKakko**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_BasicKakko) {
  auto result = splitTextToSentences(
      u8"「こんにちは。」次の文。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"「こんにちは。」");
  EXPECT_EQ(result[1], u8"次の文。");
}
```

**テスト #2: CJKClosingBracket_DoubleCornerBracket**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_DoubleCornerBracket) {
  auto result = splitTextToSentences(
      u8"『素晴らしい！』感動した。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"『素晴らしい！』");
  EXPECT_EQ(result[1], u8"感動した。");
}
```

**テスト #3: CJKClosingBracket_FullwidthParen**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_FullwidthParen) {
  auto result = splitTextToSentences(
      u8"結果は（成功です。）次へ。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"結果は（成功です。）");
  EXPECT_EQ(result[1], u8"次へ。");
}
```

**テスト #4: CJKClosingBracket_Sumitsuki**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_Sumitsuki) {
  auto result = splitTextToSentences(
      u8"【テスト。】次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"【テスト。】");
  EXPECT_EQ(result[1], u8"次。");
}
```

**テスト #5: CJKClosingBracket_HalfwidthKakko**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_HalfwidthKakko) {
  auto result = splitTextToSentences(
      u8"｢テスト。｣次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"｢テスト。｣");
  EXPECT_EQ(result[1], u8"次。");
}
```

**テスト #6: CJKClosingBracket_MultipleBrackets**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_MultipleBrackets) {
  auto result = splitTextToSentences(
      u8"「『OK。』」次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"「『OK。』」");
  EXPECT_EQ(result[1], u8"次。");
}
```

**テスト #7: WesternClosingQuote**
```cpp
TEST(SplitSentencesTest, WesternClosingQuote) {
  auto result = splitTextToSentences(
      "She said \"Hello.\" Then left.",
      MultilingualPhonemes);
  ASSERT_GE(result.size(), 2u);
  EXPECT_EQ(result[0], "She said \"Hello.\"");
}
```

**テスト #8: WesternClosingParen**
```cpp
TEST(SplitSentencesTest, WesternClosingParen) {
  auto result = splitTextToSentences(
      "Result (ok.) Next.",
      MultilingualPhonemes);
  ASSERT_GE(result.size(), 2u);
  EXPECT_EQ(result[0], "Result (ok.)");
}
```

**テスト #9: CJKClosingBracket_NoClosingNoop**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_NoClosingNoop) {
  auto result = splitTextToSentences(
      u8"テスト。次のテスト。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"テスト。");
  EXPECT_EQ(result[1], u8"次のテスト。");
}
```

**テスト #10: CJKClosingBracket_NoTerminatorNoop**
```cpp
TEST(SplitSentencesTest, CJKClosingBracket_NoTerminatorNoop) {
  // 「テスト」 -- 」 の前に文末記号がないため分割しない
  auto result = splitTextToSentences(
      u8"「テスト」続き。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"「テスト」続き。");
}
```

### 4.3 E2Eテスト

**テストミラーと piper.cpp の乖離検出方法:**

テストミラーは `piper.cpp` のアルゴリズムを手動コピーしているため、将来の `piper.cpp` 変更でミラーが古くなるリスクがある。現在の検出方法:

1. **コメント警告:** ミラーコードの先頭コメント (1-6 行) に「These tests mirror the algorithm in piper.cpp」と明記済み。変更者に同期義務を通知する
2. **test_streaming.cpp:** `piper.cpp` を直接リンクする統合テスト (CMakeLists.txt 231-310 行で piper.cpp + 全依存をリンク)。`splitTextToSentences()` の実関数を経由して `textToAudioStreaming()` をテストしている。ミラーと実関数の乖離は、統合テストの結果との不一致で間接的に検出される
3. **本チケットのスコープ:** ミラーの `isClosingPunctuation()` と消費ループが `piper.cpp` の M1/M2 実装と一致していることをレビューで目視確認する

---

## 5. 懸念事項とレビュー項目

| 懸念事項 | リスクレベル | 詳細 | 対策 |
|---------|------------|------|------|
| テストミラー乖離 | 中 | `piper.cpp` の将来変更でミラーが更新されない可能性。現在 26 + 10 = 36 テストがミラーに依存する | ミラーコード先頭のコメントを更新し、M1/M2 の変更箇所を明記する。将来的には `piper.cpp` を直接リンクするテストへの移行を検討 (セクション 6 参照) |
| UTF-8 エンコーディング | 低 | CJK テストリテラルが `u8"..."` プレフィックスを使用。ソースファイルが UTF-8 BOM なしで保存されている必要がある | 既存テスト (JapaneseBasic 等) が同じパターンで動作しているため、エンコーディング問題は発生しない。CI で 3 OS (Ubuntu/macOS/Windows) でビルド確認 |
| MSVC 対応 | 低 | MSVC の `char32_t` リテラル (`U'\uXXXX'`) と `u8` 文字列リテラルの挙動。C++17 準拠であれば問題なし | 既存テスト (`OnlyPunctuation`, `ConsecutivePunctuation`) が同じ Unicode リテラルパターンを使用して Windows CI で PASS しているため、互換性は確認済み |
| 既存テストとの整合性 | 低 | 消費ループ追加により既存テストの期待出力が変わる可能性 | 既存の 26 テストに閉じ括弧を含む入力は存在しない (全テスト確認済み)。`hasTerminator` ガードにより、文末記号のないケースは影響を受けない |
| Western テストの空白処理 | 低 | C++ ミラーは Rust/C# と異なり文間の空白をトリミングしない。`"She said \"Hello.\" Then left."` の第2文が `" Then left."` (先頭空白あり) になる可能性 | テスト #7, #8 では `ASSERT_GE(result.size(), 2u)` + 第1文のみ厳密検証とし、第2文の先頭空白の有無に依存しない設計にする |
| isClosingPunctuation のスコープ | 低 | ミラーでは匿名名前空間のフリー関数、piper.cpp では static 関数。シグネチャ (`bool isClosingPunctuation(char32_t)`) は同一 | 匿名名前空間内のためリンケージ問題なし |

**レビューチェックリスト:**

- [ ] ミラーの `isClosingPunctuation()` が `piper.cpp` (M1) の 12 文字セットと完全一致すること
- [ ] ミラーの消費ループが `piper.cpp` (M2) と同一ロジックであること (`hasTerminator` ガード、`punctEnd` インクリメント)
- [ ] 10 個のテストの期待出力が Rust/C# の対応テストと一致すること (空白処理の差異を除く)
- [ ] 既存の 26 テストが変更なく PASS すること
- [ ] ソースファイルが UTF-8 (BOM なし) で保存されていること
- [ ] `u8` プレフィックスが全 CJK リテラルに付与されていること

---

## 6. ゼロから作り直すとしたら

### 6.1 テストミラー方式の廃止: piper.cpp 直接リンク

**現状の課題:** `splitTextToSentences()` のアルゴリズムが `piper.cpp` (本番) と `test_split_sentences.cpp` (ミラー) の 2 箇所に重複している。変更時に同期漏れが発生するリスクがある。

**代替案:** `test_streaming.cpp` と同じ方式で `piper.cpp` を直接リンクする。CMakeLists.txt で `piper.cpp` + 依存 (spdlog, fmt, onnxruntime, openjtalk 等) をリンクすれば、ミラーは不要になる。

**不採用の理由:** `piper.cpp` は ONNX Runtime ヘッダー (`onnxruntime_cxx_api.h`) に依存しており、リンクコストが大きい。`test_split_sentences` は「文分割ロジックの単体テスト」であり、軽量なミラー方式の方が CI 実行時間とビルド複雑度の面で優れている。ただし、ミラーのテスト数が 36 個に増えた現在、将来的には `splitTextToSentences()` を独立ヘッダー (`text_splitter.hpp`) に抽出してミラーを廃止することを検討すべきである。

### 6.2 言語横断テスト仕様 (contract test)

**概要:** C++/Rust/C#/Go の 4 ランタイムが同一の入力に対して同一の出力を返すことを保証する contract test。共通テストデータを JSON/TOML ファイルで定義し、各ランタイムのテストがそのファイルを読み込む。

**例:**
```toml
# docs/spec/split-sentences-contract.toml
[[cases]]
name = "CJK closing bracket"
input = "「こんにちは。」次の文。"
expected = ["「こんにちは。」", "次の文。"]
note = "All runtimes must agree"
```

**メリット:** テストケースの一元管理、ランタイム間の乖離自動検出。
**課題:** 各ランタイムの文分割アルゴリズムは微妙に異なる (Go は depth tracking、C++ は空白非トリミング)。全ケースで完全一致を要求すると false positive が頻発する。

### 6.3 Property-based testing

**概要:** ランダム生成された入力に対して「分割結果を結合すると元の文字列に戻る」「各チャンクが空でない」等の性質を検証する。

**C++ での実装:** Google Test には property-based testing が組み込まれていないため、RapidCheck や類似ライブラリの追加が必要。

**不採用の理由:** 依存追加のコストに対して、文分割の性質テストで検出できるバグは限定的。10 個の具体的なテストケースの方が Issue #346 の修正検証には直接的。

### 6.4 テストデータの外部ファイル化

**概要:** テストの入力/期待出力を `test/data/split_sentences.json` 等の外部ファイルに切り出し、データ駆動テスト (parameterized test) にする。

**メリット:** テストケース追加時に C++ コードの変更が不要。非プログラマーでもテストケースを追加可能。
**課題:** Google Test の `INSTANTIATE_TEST_SUITE_P` は JSON パースを組み込みサポートしていない。nlohmann/json 等の追加が必要。現在のテスト数 (36 個) では外部ファイル化のメリットが小さい。

---

## 7. 後続タスクへの連絡事項

M4 (CI 検証 + PR 作成) が知るべきこと:

### 7.1 テスト数

| カテゴリ | 変更前 | 変更後 |
|---------|--------|--------|
| SplitSentencesTest | 22 | 32 (+10) |
| DynamicChunkSizeTest | 4 | 4 (変更なし) |
| **合計** | **26** | **36** |

### 7.2 実行コマンド

```bash
# テストのみビルド + 実行
cmake -B build -DBUILD_TESTS=ON
cmake --build build --target test_split_sentences
ctest -R test_split_sentences -V --test-dir build

# 全 C++ テスト (リグレッション確認)
ctest -E "test_c_api_integration|test_c_api_audio_regression" --test-dir build
```

### 7.3 期待される CI 結果

- `test_split_sentences`: 36/36 PASS (既存 26 + 新規 10)
- 他の C++ テスト: 変更なし (test_split_sentences.cpp のみ変更のため影響なし)
- CMake 変更なし: `test_split_sentences` は既に `TEST_SOURCES` (CMakeLists.txt 63 行) に登録済み。追加のリンク依存もない (gtest + gtest_main + `utf8_utils.hpp` のインクルードパス設定が 126-130 行で既設定)

### 7.4 ランタイム間テスト対応表

M4 の PR レビューで参照する、各ランタイムの対応テスト:

| C++ テスト (新規) | Rust テスト | C# テスト | Go テスト |
|------------------|------------|----------|----------|
| `CJKClosingBracket_BasicKakko` | `test_split_sentences_with_closing_brackets` | `ClosingPunctuation_JapaneseQuotes` | `TestSplitSentences_JapaneseQuotes` (注: Go は depth tracking で動作が異なる) |
| `WesternClosingQuote` | (なし) | `ClosingPunctuation_WesternQuotes` | `TestSplitSentences_QuotesNotSplit` (注: Go は引用内分割を抑制) |
| `CJKClosingBracket_NoClosingNoop` | (既存テストでカバー) | (既存テストでカバー) | (既存テストでカバー) |

### 7.5 変更ファイル一覧

- `src/cpp/tests/test_split_sentences.cpp` -- ミラー更新 + テスト 10 個追加 (このファイルのみ)
