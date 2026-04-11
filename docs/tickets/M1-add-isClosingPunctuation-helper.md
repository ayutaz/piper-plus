# M1: isClosingPunctuation() ヘルパー関数追加

> **マイルストーン:** [M1](../milestones-346-cpp-cjk-closing-bracket.md#m1-ヘルパー関数追加)
> **Issue:** [#346](https://github.com/ayutaz/piper-plus/issues/346)
> **ブランチ:** `fix/cpp-cjk-closing-bracket-346`
> **前提チケット:** なし
> **後続チケット:** [M2](M2-add-closing-bracket-consumption-loop.md)

---

## 1. タスク目的とゴール

### なぜ必要か

C++ の `splitTextToSentences()` は文末記号 (。！？.!?) の後の CJK 閉じ括弧 (`」`, `』`, `）` 等) を消費しないため、引用テキストで終わる文が誤分割される。

```
入力:  「こんにちは。」次の文。

C++ (現状):  ["「こんにちは。", "」次の文。"]   -- 」が次の文に漏れる
Rust/C#/Go:  ["「こんにちは。」", "次の文。"]   -- 正しい
```

M1 では、M2 の閉じ括弧消費ループが使う判定関数 `isClosingPunctuation()` を `piper.cpp` に追加する。関数単体の追加であり、既存の動作は一切変更しない。

### 完了の定義

- `isClosingPunctuation(char32_t)` が `piper.cpp` に `static` 関数として存在すること
- 12文字の閉じ括弧文字セットを正しく判定すること
- コンパイルが通ること (関数は M1 時点では未呼び出しでよい)

---

## 2. 実装する内容の詳細

### 2.1 挿入場所

**ファイル:** `src/cpp/piper.cpp`
**挿入位置:** 2088行 (`calculateDynamicChunkSize()` の閉じ括弧 `}`) と 2090行 (`splitTextToSentences()` のコメント) の間

```
2087:  return baseSize * 2;  // Medium density
2088:}
2089:                              <-- ★ ここに挿入
2090:// Split text into sentences at natural boundaries (public API).
```

既存の `isPunctCodepoint()` (2048行) や `calculateDynamicChunkSize()` (2063行) と同じ `static` 関数パターンに従い、`splitTextToSentences()` の直前に配置する。

### 2.2 関数シグネチャ

```cpp
// Helper: is a codepoint a closing punctuation mark that should be
// consumed after a sentence terminator? (Issue #346)
static bool isClosingPunctuation(char32_t c) {
  switch (c) {
    case U')':     // U+0029  Right Parenthesis
    case U']':     // U+005D  Right Square Bracket
    case U'}':     // U+007D  Right Curly Bracket
    case U'"':     // U+0022  Quotation Mark
    case U'\'':    // U+0027  Apostrophe
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

### 2.3 文字セット12文字の根拠

Rust `streaming.rs` の11文字と Go `text_splitter.go` の `U+201D` を合わせた全ランタイムスーパーセット。

| # | 文字 | Unicode | Rust streaming.rs (326-340行) | C# TextSplitter.cs (100-113行) | Go text_splitter.go (190-198行) | C++ (本チケット) |
|---|------|---------|------|----|----|-----|
| 1 | `)` | U+0029 | YES | YES | YES | YES |
| 2 | `]` | U+005D | YES | YES | YES | YES |
| 3 | `}` | U+007D | YES | YES | YES | YES |
| 4 | `"` | U+0022 | YES | YES | -- | YES |
| 5 | `'` | U+0027 | YES | YES | -- | YES |
| 6 | `」` | U+300D | YES | YES | YES | YES |
| 7 | `』` | U+300F | YES | YES | YES | YES |
| 8 | `）` | U+FF09 | YES | YES | YES | YES |
| 9 | `］` | U+FF3D | YES | YES | -- | YES |
| 10 | `】` | U+3011 | YES | YES | YES | YES |
| 11 | `｣` | U+FF63 | YES | YES | -- | YES |
| 12 | `"` | U+201D | -- | -- | YES | YES |

- Rust/C#: 11文字 (U+201D なし)
- Go: 8文字 (U+201D あり、`"`, `'`, `］`, `｣` なし)
- C++ (本チケット): 12文字 = Rust 11 + Go の U+201D

### 2.4 既存パターンとの整合

`piper.cpp` の既存ヘルパー関数は全て `static` + `switch` パターン:

| 関数名 | 行番号 | パターン |
|--------|--------|---------|
| `isPunctCodepoint()` | 2048-2058 | `static bool` + `switch` |
| `calculateDynamicChunkSize()` | 2063-2088 | `static size_t` (関連ヘルパー) |
| `isSingleCodepoint()` | 121-123 | `bool` (非 static、ヘッダー公開) |
| `getCodepoint()` | 126-129 | `Phoneme` (非 static、ヘッダー公開) |

`isClosingPunctuation()` はファイルスコープ限定のため `static` とし、`isPunctCodepoint()` と同じパターンに従う。ヘッダー (`piper.hpp`) への公開は不要。

---

## 3. エージェントチームの役割と人数

このチケットは単一の `static` 関数追加であり、最小構成で実施可能。

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| **実装エージェント** | 1名 | `piper.cpp` への `isClosingPunctuation()` 追加、コンパイル確認 |
| **参照確認エージェント** | 0名 (実装エージェントが兼務) | Rust `streaming.rs:326-340`、C# `TextSplitter.cs:100-113`、Go `text_splitter.go:190-198` との文字セット照合は本チケットの対応表で完了済み |
| **レビュー** | 1名 | 12文字の網羅性、`switch` 構文の正しさ、`static` 修飾、コメントの正確さを確認 |

**合計: 2名** (実装1 + レビュー1)

M1 は関数追加のみで既存動作を変更しないため、独立した参照確認エージェントは不要。文字セットの根拠は上記セクション 2.3 の対応表で文書化済み。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (スコープ)

**含むもの:**

- `src/cpp/piper.cpp` に `isClosingPunctuation()` を1関数追加
- 関数直上のドキュメントコメント (Issue #346 への参照を含む)

**含まないもの:**

- `splitTextToSentences()` の動作変更 (M2 で実施)
- テストミラーへの反映 (M3 で実施)
- テストケース追加 (M3 で実施)
- `piper.hpp` の変更 (不要)
- CMake の変更 (不要)

### 4.2 ユニットテスト

**M1 単体のユニットテストは不要。** 理由:

1. `isClosingPunctuation()` は `static` 関数であり、テストファイルからは直接呼び出せない
2. テストファイル (`src/cpp/tests/test_split_sentences.cpp`) は `piper.cpp` の関数を匿名名前空間にミラーコピーして使用するパターン (1-129行) であり、M3 でミラー追加と同時にテストする
3. M1 時点では関数は未呼び出し状態 (dead code) だが、M2 で即座に使用される

**M3 で追加されるテスト (参考):**

`isClosingPunctuation()` 単体テストではなく、`splitTextToSentences()` を通じた統合テスト10個 (マイルストーン文書参照)。文字セットの網羅性はテストケース #1-#8 で全括弧タイプをカバー。

### 4.3 E2Eテスト

**M1 では E2E 不要。** E2E 検証は M4 (CI 検証 + PR 作成) で実施。M4 の検証コマンド:

```bash
cmake -B build -DBUILD_TESTS=ON
cmake --build build --target test_split_sentences
ctest -R test_split_sentences -V --test-dir build
```

---

## 5. 懸念事項とレビュー項目

### 5.1 Apostrophe 問題 (`U+0027`)

`'` (U+0027, Apostrophe) は英語の短縮形 (`don't`, `it's`, `I'm`) で頻出する。`isClosingPunctuation()` に含めることで、以下のケースが影響を受ける可能性がある:

```
入力: She said 'hello.' Don't worry.
```

ただし、`isClosingPunctuation()` が呼ばれるのは **M2 で `hasTerminator` が `true` の場合のみ** (文末記号の直後) であるため、単語内の apostrophe には影響しない。文末記号の直後に `'` が来るケースは閉じ引用符としての用法であり、消費して正しい。

**レビュー確認項目:** M2 の `hasTerminator` ガードが正しく機能することを前提に、`U+0027` を含めることは安全。Rust/C# も同一の判断を採用済み。

### 5.2 `U+0022` (Quotation Mark) の対称性

`"` (U+0022) は開き/閉じの区別がない。`isClosingPunctuation()` に含めると、文末記号の直後の `"` は常に閉じと判定される。これは Rust/C# と同一の挙動。

```
入力: She said "Hello." Then left.
結果: ["She said \"Hello.\"", " Then left."]  -- 正しい
```

**レビュー確認項目:** `"text." more text` パターンで `"` が正しく消費されること。

### 5.3 文字セットの選定根拠

12文字 = 全ランタイムのスーパーセット (union) を採用。Rust/C# にない `U+201D` を追加した理由:

- Go が `U+201D` (Right Double Quotation Mark) を含めている
- 英語の書籍・記事では `"quoted text."` パターンが一般的
- 追加のリスクはゼロ (`U+201D` は閉じ引用符としてのみ使われる)

### 5.4 将来の拡張性

- 文字セットの追加は `switch` 文に `case` を1行追加するだけ
- 全ランタイムで同一文字セットを仕様として固定する場合は、`docs/spec/` に共通定義ファイルを設けることを検討 (本チケットのスコープ外)

### 5.5 レビューチェックリスト

- [ ] 12文字が正しい Unicode コードポイントか
- [ ] `static` 修飾が付いているか
- [ ] `switch` の `default: return false;` が存在するか
- [ ] コメントに Issue #346 への参照があるか
- [ ] 挿入位置が `calculateDynamicChunkSize()` の直後、`splitTextToSentences()` の直前か
- [ ] `U+0027` と `U+0022` の包含が意図的であることがコメントから読み取れるか

---

## 6. ゼロから作り直すとしたら

C++ の文分割を一から設計するなら、`isClosingPunctuation()` はどうあるべきか。

### 6.1 Unicode カテゴリベース

ICU ライブラリの `u_charType()` を使い、Unicode General Category `Pe` (Close Punctuation) と `Pf` (Final Punctuation) で判定する方法。

```cpp
#include <unicode/uchar.h>

static bool isClosingPunctuation(char32_t c) {
  int8_t type = u_charType(c);
  return type == U_END_PUNCTUATION ||    // Pe: )  ]  }  」 』 ） ］ 】 ｣
         type == U_FINAL_PUNCTUATION;     // Pf: " ' 
}
```

**メリット:** 将来の Unicode 追加に自動対応、全ランタイムで同一ロジック
**デメリット:** ICU 依存の追加 (piper-plus は現在 ICU 非依存)、`U+0022` / `U+0027` は `Po` (Other Punctuation) であり `Pe`/`Pf` に含まれないため別途処理が必要

### 6.2 テーブル駆動 (共通仕様ファイル)

`docs/spec/closing-punctuation.toml` 等に全ランタイム共通の文字テーブルを定義し、各言語実装はそれを参照する。

```toml
# docs/spec/closing-punctuation.toml
[closing_punctuation]
chars = [
  { char = ")", code = "U+0029", name = "Right Parenthesis" },
  { char = "]", code = "U+005D", name = "Right Square Bracket" },
  # ...
]
```

**メリット:** Single Source of Truth、ランタイム間の乖離を防止
**デメリット:** ビルド時にTOMLをパースするか、手動同期が必要。現状の piper-plus は `docs/spec/ort-session-contract.toml` で類似パターンを採用済みだが、コードへの自動反映機構はない

### 6.3 ヘッダー共有 (C++ 内)

`isClosingPunctuation()` を `piper_text_utils.hpp` 等の共有ヘッダーに移し、`piper.cpp` とテストミラーの二重管理を解消する。

```cpp
// src/cpp/piper_text_utils.hpp
#pragma once
#include <cstdint>

namespace piper::text_util {
inline bool isClosingPunctuation(char32_t c) { ... }
inline bool isSentenceTerminator(char32_t c) { ... }
}
```

**メリット:** テストミラーが不要になる、`isBoundaryPunct` / `isSentenceTerminator` も共有可能
**デメリット:** テストファイルが `piper.hpp` を include すると ONNX Runtime リンク依存が発生する。これが現在のミラーパターン採用の理由 (`test_split_sentences.cpp:1-7` のコメント参照)。テキスト処理関数だけを分離した軽量ヘッダーなら実現可能だが、リファクタリング範囲が Issue #346 を超える

### 6.4 現実的な推奨

現時点では **手動 `switch` テーブル + テストミラー** が最も低リスク。理由:

1. 文字セットは12文字で安定しており、頻繁な変更は見込めない
2. ICU 依存の追加はビルドシステムへの影響が大きい
3. テキスト処理ヘッダーの分離は有益だが、Issue #346 のスコープを大幅に超える
4. 将来的にヘッダー分離を行う場合、`isClosingPunctuation()` はそのまま移動できる

**中期的な改善案:** `splitTextToSentences()` 周辺のヘルパー群 (`isPunctCodepoint`, `isBoundaryPunct`, `isSentenceTerminator`, `isClosingPunctuation`, `calculateDynamicChunkSize`) を `piper_text_utils.hpp` に切り出し、テストミラーを廃止する。これは別 Issue として追跡すべき。

---

## 7. 後続タスクへの連絡事項

M2 (閉じ括弧消費ループ追加) が知るべきこと:

### 7.1 関数情報

| 項目 | 値 |
|------|-----|
| 関数名 | `isClosingPunctuation` |
| シグネチャ | `static bool isClosingPunctuation(char32_t c)` |
| 戻り値 | 引数が12文字の閉じ括弧文字セットに含まれれば `true` |
| 配置場所 | `src/cpp/piper.cpp` 2089行付近 (`calculateDynamicChunkSize()` と `splitTextToSentences()` の間) |
| スコープ | `static` (ファイルスコープ、ヘッダー非公開) |

### 7.2 M2 での使用方法

`splitTextToSentences()` 内、boundary punctuation 消費ループの直後 (現在の2165-2166行の間) に以下を挿入:

```cpp
      // Issue #346: consume closing brackets after sentence terminators
      if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
          punctEnd++;
        }
      }
```

### 7.3 M3 でのテストミラー反映

M3 は `src/cpp/tests/test_split_sentences.cpp` の匿名名前空間 (18-129行) に `isClosingPunctuation()` の完全コピーを追加する必要がある。挿入位置は `splitTextToSentences()` ミラー内の `isBoundaryPunct` ラムダの直前 (74行付近) ではなく、`calculateDynamicChunkSize()` の直後 (55行) と `splitTextToSentences()` ミラーの直前 (57行) の間が `piper.cpp` のレイアウトと一致する。

### 7.4 注意事項

- M1 時点では `isClosingPunctuation()` は未呼び出し (dead code) であり、コンパイラの `unused function` 警告が出る可能性がある。`piper.cpp` のビルドフラグに `-Wno-unused-function` が含まれていなければ、M2 を同一 PR で実施することで解消できる (マイルストーン計画では M1-M4 は同一ブランチ `fix/cpp-cjk-closing-bracket-346` での連続作業)
- 12文字の文字セットを変更する場合は、本チケットのセクション 2.3 の対応表と M3 のテストケース両方を更新すること
