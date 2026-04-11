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
- 14文字の閉じ括弧文字セットを正しく判定すること
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
// 14 chars — superset of all runtimes. See docs/spec/text-splitter-contract.toml.
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
    case U'\u2019': // '  Right Single Quotation Mark
    case U'\u00BB': // »  Right-Pointing Double Angle Quotation Mark
      return true;
    default:
      return false;
  }
}
```

### 2.3 文字セット14文字の根拠

Rust `streaming.rs` の11文字と Go `text_splitter.go` の `U+201D` を合わせ、さらに U+2019 と U+00BB を追加した全ランタイムスーパーセット。

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
| 13 | `'` | U+2019 | -- | -- | -- | YES |
| 14 | `»` | U+00BB | -- | -- | -- | YES |

- Rust/C#: 11文字 (U+201D, U+2019, U+00BB なし)
- Go: 8文字 (U+201D あり、`"`, `'`, `］`, `｣`, U+2019, U+00BB なし)
- C++ (本チケット): 14文字 = 全ランタイムスーパーセット (Rust 11 + Go U+201D + U+2019 + U+00BB)

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
| **レビュー** | 1名 | 14文字の網羅性、`switch` 構文の正しさ、`static` 修飾、コメントの正確さを確認 |

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

14文字 = 全ランタイムのスーパーセット (union) を採用。Rust/C# にない `U+201D`, `U+2019`, `U+00BB` を追加した理由:

- Go が `U+201D` (Right Double Quotation Mark) を含めている
- 英語の書籍・記事では `"quoted text."` パターンが一般的
- 追加のリスクはゼロ (`U+201D` は閉じ引用符としてのみ使われる)

### 5.4 将来の拡張性

- 文字セットの追加は `switch` 文に `case` を1行追加するだけ
- 全ランタイムで同一文字セットを仕様として固定する場合は、`docs/spec/` に共通定義ファイルを設けることを検討 (本チケットのスコープ外)

### 5.5 レビューチェックリスト

- [ ] 14文字が正しい Unicode コードポイントか
- [ ] `static` 修飾が付いているか
- [ ] `switch` の `default: return false;` が存在するか
- [ ] コメントに Issue #346 への参照があるか
- [ ] 挿入位置が `calculateDynamicChunkSize()` の直後、`splitTextToSentences()` の直前か
- [ ] `U+0027` と `U+0022` の包含が意図的であることがコメントから読み取れるか

---

## 6. ゼロから作り直すとしたら

C++ の文分割における閉じ括弧判定を一から設計するなら、以下の4軸で検討する。エージェントチーム (システムアーキテクト、クロスランタイム整合性、実用主義エンジニア、Unicode テキスト分割専門家) による議論結果を反映。

### 6.1 Unicode カテゴリベース (ICU)

ICU ライブラリの `u_charType()` で Pe (Close Punctuation) / Pf (Final Punctuation) を判定する方式。

**賛成:** 手動リストの漏れを構造的に排除。Pe カテゴリは ~75 コードポイント存在し、手動管理はスケールしない。将来の Unicode 追加に自動対応。

**反対:** ICU は共有ライブラリで 25-30 MB。組み込み機器・WASM・iOS バイナリサイズ制約下では過剰。5 ランタイム中 ICU を使えるのは C++ のみ（Rust は `unicode-general-category`、C# は `char.GetUnicodeCategory()`、Go は `unicode.Is()`）。「ICU で統一」が 1/5 しか成立しない。

**また:** Pe/Pf は広すぎる。Pe ~75 文字の大半は対応言語で使われない（チベット文字、エチオピア文字等）。TTS では precision > recall (false positive のコストが高い)。

**結論:** 不採用。

### 6.2 仕様駆動 + 契約テスト (推奨)

`docs/spec/text-splitter-contract.toml` に全ランタイム共通の文字テーブルを定義し、各ランタイムのテストが「実装の文字セット ⊇ 仕様の文字セット」を自動検証する contract test 方式。

```
docs/spec/text-splitter-contract.toml     ← Single Source of Truth
  │
  ├── 各ランタイムの isClosingPunctuation()  (手動実装)
  │     C++ switch / Rust match / C# switch / Go switch / JS Set
  │
  └── 各ランタイムの contract test           (TOML を読んで検証)
        「実装の文字セット ⊇ 仕様の文字セット」を自動検証
```

**メリット:** Single Source of Truth、ランタイム間の乖離自動検出。`ort-session-contract.toml` と `short-text-contract.toml` で既にプロジェクト内に前例あり。コード生成パイプラインは不要（5ランタイムの各数行の switch のためにはオーバーエンジニアリング）。

**本チケットで実施:** `docs/spec/text-splitter-contract.toml` を作成済み。14文字の正規定義、各ランタイムの準拠状況、行動契約 (post-consume vs depth-tracking) を記載。

### 6.3 ヘッダー分離 (テストミラー廃止)

`isClosingPunctuation()` を含むテキスト処理ヘルパーを `piper_text_utils.hpp` に切り出し、テストミラーの二重管理を解消する方式。

**実現方法:** `PhonemeType` + `usesOpenJTalk()` を軽量ヘッダー `piper_types.hpp` に分離 → テキスト処理関数を `piper_text_utils.hpp` に抽出 → テストが軽量ヘッダーのみ include。

**不採用の理由 (現時点):**
1. `piper.hpp` の分割は広範囲に影響し、全 `.cpp` ファイルのインクルード修正が必要
2. `splitTextToSentences()` の変更頻度が低い (直近で #343 の 1 回のみ)
3. テストミラーは ~130 行で認知負荷が低い
4. Issue #346 のスコープを大幅に超える

**中期的改善案:** 変更頻度が上がった場合に別 Issue として追跡。

### 6.4 文字セット設計: 14文字の根拠

エージェントチームの Unicode 専門家が、対応8言語で使われる閉じ括弧を網羅調査した結果:

| 追加文字 | Unicode | 用途 | 優先度 |
|---------|---------|------|--------|
| `'` | U+2019 | EN/FR の右シングル引用符 | **高** (5言語で使用) |
| `»` | U+00BB | FR/PT/ES/SV のギュメ (閉じ) | **高** (4言語で使用) |
| `》` | U+300B | ZH の書名号 (閉じ) | 中 (将来追加候補) |
| `〉` | U+3009 | ZH/JA の右山括弧 | 低 |

U+2019 と U+00BB は対応言語で日常的に使用されるため、12文字 → 14文字に拡張。中優先度以下は将来の追加候補として `text-splitter-contract.toml` で追跡。

### 6.5 ランタイム間の現状と今後

| ランタイム | 準拠文字数 | 欠落 | 評価 |
|-----------|-----------|------|------|
| C++ | 14/14 | なし | **完全準拠** (本チケット) |
| Rust | 11/14 | U+201D, U+2019, U+00BB | バグ — 別 Issue で修正 |
| C# | 11/14 | U+201D, U+2019, U+00BB | バグ — 別 Issue で修正 |
| Go | 8/14 | U+0022, U+0027, U+FF3D, U+FF63, U+2019, U+00BB | バグ — 別 Issue で修正 |

**エージェントチームの合意:** 差異は「acceptable tech debt」ではなく**バグ**。同一入力に対して異なる文分割結果を返すとランタイム間で再現困難な問題になる。`text-splitter-contract.toml` を基準に全ランタイムを統一すべき。

---

## 7. 後続タスクへの連絡事項

M2 (閉じ括弧消費ループ追加) が知るべきこと:

### 7.1 関数情報

| 項目 | 値 |
|------|-----|
| 関数名 | `isClosingPunctuation` |
| シグネチャ | `static bool isClosingPunctuation(char32_t c)` |
| 戻り値 | 引数が14文字の閉じ括弧文字セットに含まれれば `true` |
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
- 14文字の文字セットを変更する場合は、`docs/spec/text-splitter-contract.toml`、本チケットのセクション 2.3 の対応表、および M3 のテストケースを全て更新すること
