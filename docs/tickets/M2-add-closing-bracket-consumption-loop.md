# M2: splitTextToSentences() 閉じ括弧消費ループ追加

> **マイルストーン:** [M2](../milestones-346-cpp-cjk-closing-bracket.md#m2-splittexttosentences-に閉じ括弧消費ループ追加)
> **Issue:** [#346](https://github.com/ayutaz/piper-plus/issues/346)
> **ブランチ:** `fix/cpp-cjk-closing-bracket-346`
> **前提チケット:** [M1](M1-add-isClosingPunctuation-helper.md)
> **後続チケット:** [M3](M3-update-test-mirror-and-add-tests.md)

---

## 1. タスク目的とゴール

### なぜこのタスクが必要か

C++ の `splitTextToSentences()` は文末記号（。！？.!?）の後の **CJK 閉じ括弧**（」『）等）を同一文として消費しないため、引用符で終わる文が誤分割される。Rust (`streaming.rs`)、C# (`TextSplitter.cs`)、Go (`text_splitter.go`) の3ランタイムでは既に正しく処理されており、C++ だけが取り残されている。

### Before / After

```
入力:  「こんにちは。」次の文。

Before (C++ 現状):  ["「こんにちは。", "」次の文。"]   -- 」が次の文に漏れる
After  (修正後):    ["「こんにちは。」", "次の文。"]   -- Rust/C# と同一動作
```

```
入力:  「『OK。』」次。

Before: ["「『OK。", "』」次。"]
After:  ["「『OK。』」", "次。"]
```

### 完了の定義

- `piper.cpp` の `splitTextToSentences()` 内、boundary punctuation 消費ループ直後に閉じ括弧消費ループが追加されていること
- `「こんにちは。」次の文。` が `["「こんにちは。」", "次の文。"]` と分割されること
- 既存テスト（`test_split_sentences.cpp` の全テスト）がリグレッションなく PASS すること

---

## 2. 実装する内容の詳細

### 2.1 挿入ポイント

**ファイル:** `src/cpp/piper.cpp`
**行番号:** 2165行と2166行の間（boundary punctuation 消費ループの `punctEnd++` ループ終了直後、`i = punctEnd - 1` の直前）

現在のコード（2156-2177行）:

```cpp
    if (isBoundaryPunct(c)) {
      // Consume the entire run of boundary punctuation
      bool hasTerminator = isSentenceTerminator(c);
      size_t punctEnd = i + 1;
      while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {   // L2160
        if (isSentenceTerminator(cps[punctEnd])) {
          hasTerminator = true;
        }
        punctEnd++;
      }                                                               // L2165
      i = punctEnd - 1; // advance past punctuation run               // L2166

      // Split if this contains a sentence terminator, or chunk is too long
      size_t chunkLen = punctEnd - sentenceStart;                     // L2169
      if (hasTerminator || chunkLen > dynamicChunkSize) {
        std::string chunk = cpsToUtf8(cps, sentenceStart, chunkLen);
        ...
      }
    }
```

### 2.2 追加するコード

L2165 (`}` -- while ループ閉じ) と L2166 (`i = punctEnd - 1`) の間に以下を挿入する:

```cpp
      // Issue #346: Consume closing brackets/quotes after sentence terminator
      // so that 「こんにちは。」 stays in one chunk (matches Rust/C# behavior).
      if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
          punctEnd++;
        }
      }
```

### 2.3 修正後の全体像（diff 形式）

```diff
       while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {
         if (isSentenceTerminator(cps[punctEnd])) {
           hasTerminator = true;
         }
         punctEnd++;
       }
+      // Issue #346: Consume closing brackets/quotes after sentence terminator
+      // so that 「こんにちは。」 stays in one chunk (matches Rust/C# behavior).
+      if (hasTerminator) {
+        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
+          punctEnd++;
+        }
+      }
       i = punctEnd - 1; // advance past punctuation run (for-loop will ++)

       // Split if this contains a sentence terminator, or chunk is too long
       size_t chunkLen = punctEnd - sentenceStart;
```

### 2.4 `hasTerminator` ガードの理由

`hasTerminator` 条件で閉じ括弧消費を制限するのは、**カンマ等の非終端句読点の後の括弧を誤消費しない**ため。

具体例:

| 入力 | `hasTerminator` | 閉じ括弧消費 | 結果 |
|------|----------------|-------------|------|
| `「こんにちは。」次。` | `true` (。) | `」`を消費 | `["「こんにちは。」", "次。"]` |
| `「テスト」続き。` | `」` は boundary punct ではないため通常文字として蓄積。`。` で分割 → 閉じ括弧消費ループは no-op (文末) | -- | `["「テスト」続き。"]` (1文) |
| `テスト、（補足）続き。` | `false` (、は terminator ではない) | 消費しない | カンマで不要な分割をしない |

ガードがないと、例えば English モードで `Hello, (world).` のカンマ+括弧が誤って1チャンクに切り出される可能性がある。Rust streaming.rs と C# は文末記号検出時のみ閉じ括弧消費に入る構造になっており、C++ でも `hasTerminator` でこれを模倣する。

### 2.5 `punctEnd` 更新の仕組み

`punctEnd` は boundary punctuation 消費ループで「句読点列の末尾+1」を指すインデックス。閉じ括弧消費ループはこの `punctEnd` をさらに先に進める。その結果:

1. `i = punctEnd - 1` -- for ループの `++i` と合わせて、閉じ括弧の次のコードポイントから走査再開
2. `chunkLen = punctEnd - sentenceStart` -- 閉じ括弧を含むチャンク長が正しく計算される
3. `sentenceStart = punctEnd` -- 次のチャンク開始位置が閉じ括弧の次になる

つまり `punctEnd` を進めるだけで、下流の `i` / `chunkLen` / `sentenceStart` は全て自動的に整合する。追加の変数や戻り値の変更は不要。

### 2.6 Rust/C# との構造対応

| C++ (修正後) | Rust streaming.rs (279-285行) | C# TextSplitter.cs (49-53行) |
|-------------|------------------------------|------------------------------|
| `if (hasTerminator) { while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) { punctEnd++; } }` | `while let Some(&next_ch) = chars.peek() { if is_closing_punctuation(next_ch) { current.push(chars.next().unwrap()); } else { break; } }` | `while (i < text.Length && IsClosingPunctuation(text[i])) { current.Append(text[i]); i++; }` |

C++ はインデックスベース走査、Rust は `Peekable<Chars>` イテレータ、C# は `int i` インデックスとスタイルは異なるが、**「文末記号検出後に閉じ括弧を貪欲消費する」** というロジックは同一。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| **実装担当** | 1名 | `piper.cpp` に閉じ括弧消費ループを挿入（5行）。M1 の `isClosingPunctuation()` が存在することを前提とする |
| **参照確認担当** | 1名 | Rust `streaming.rs` (279-285行)、C# `TextSplitter.cs` (49-53行)、Go `text_splitter.go` (22-107行) の閉じ括弧消費ロジックと C++ 実装の動作等価性を確認 |
| **レビュー担当** | 1名 | `hasTerminator` ガードの妥当性、`punctEnd` と `i` の整合性、既存テストへのリグレッションがないことを検証 |

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲

| 項目 | 含まれる | 備考 |
|------|---------|------|
| `piper.cpp` 閉じ括弧消費ループ追加 | はい | 本チケットの主成果物 |
| `isClosingPunctuation()` ヘルパー | いいえ | M1 で完了済み（前提） |
| テストミラー更新 | いいえ | M3 で実施 |
| テストケース追加 | いいえ | M3 で実施 |
| CI 実行・PR 作成 | いいえ | M4 で実施 |

### 4.2 ユニットテスト

M3 で実施。M2 では以下の手動検証のみ行う:

**手動検証手順:**

```bash
# 1. ミラーを手動で一時的に更新して動作確認（M3 の先取り）
# test_split_sentences.cpp のミラー関数にも同じ5行を挿入

# 2. ビルド + 実行
cmake -B build -DBUILD_TESTS=ON
cmake --build build --target test_split_sentences
ctest -R test_split_sentences -V --test-dir build

# 3. 既存テスト全 PASS を確認（リグレッションなし）
```

**手動確認すべき入出力:**

| 入力 | 期待出力 |
|------|---------|
| `「こんにちは。」次の文。` | `["「こんにちは。」", "次の文。"]` |
| `『素晴らしい！』感動した。` | `["『素晴らしい！』", "感動した。"]` |
| `テスト。次のテスト。` | `["テスト。", "次のテスト。"]` (既存動作と同一) |

### 4.3 E2Eテスト

M4 で CI 全テスト実行。M2 単独では E2E テストは不要（文分割のみの変更で音声合成ロジックに影響しないため）。

---

## 5. 懸念事項とレビュー項目

### 5.1 `hasTerminator` ガードの妥当性

**確認ポイント:** `hasTerminator` が `false` のケースで閉じ括弧消費をスキップすることが正しいか。

- **問題ないケース:** `isBoundaryPunct` に入る時点で句読点が検出されている。`hasTerminator` が `false` になるのは、boundary punct が terminator ではない場合（例: 日本語モードの `、`、英語モードの `,` `;` `:`）。これらの後の閉じ括弧を消費するのは意味的に不正。
- **エッジケース:** Multilingual モードの `…` (U+2026) は `isBoundaryPunct` だが `isSentenceTerminator` ではない。`そうですか…」次。` のようなケースで `」` は消費されない。これは Rust/C# でも同様（`…` が terminator でないため、そもそもフラッシュが発生しない）。

### 5.2 `punctEnd` と `i` の整合性

**確認ポイント:** 閉じ括弧消費後の `i = punctEnd - 1` が正しいか。

- `punctEnd` は閉じ括弧列の末尾+1を指す
- `i = punctEnd - 1` の後、for ループの `++i` で `i = punctEnd` になる
- 結果: 閉じ括弧の次のコードポイントから走査再開 -- 正しい
- `sentenceStart = punctEnd` も閉じ括弧の次を指す -- 正しい

**リスク:** `punctEnd` が `cpLen` と等しくなるケース（文末が閉じ括弧で終わる場合）。`i = cpLen - 1` → `++i` で `i = cpLen` → for ループ終了。残余テキストフラッシュ（L2180-2186）の `sentenceStart < cpLen` は `sentenceStart == cpLen` で `false` → 空チャンクを emit しない。正常。

### 5.3 動的チャンクサイズとの相互作用

**確認ポイント:** `chunkLen = punctEnd - sentenceStart` に閉じ括弧分の長さが加算されることで、`dynamicChunkSize` を超過するケースがあるか。

- 閉じ括弧は通常1-3文字。`dynamicChunkSize` は最小50コードポイント。超過する現実的なシナリオはない。
- 仮に超過しても、`hasTerminator` が `true` の場合は `hasTerminator || chunkLen > dynamicChunkSize` の最初の条件で分割が確定するため、動作に影響しない。

### 5.4 Go との動作差異

Go は `depth tracking` 方式で括弧内の文末記号を**抑制**する（括弧内では分割しない）。C++ (および Rust/C#) は括弧内の文末記号でも分割し、閉じ括弧を後から消費する `post-consume` 方式。

```
入力: 彼は「元気です。」と言った。終わり。

Go (depth tracking):  ["彼は「元気です。」と言った。", "終わり。"]  (2文)
C++ (post-consume):   ["彼は「元気です。」", "と言った。", "終わり。"]  (3文)
```

この差異は **Issue #346 のスコープ外** であり、許容する。C++ を depth tracking 方式に変更するのは全面書き換えに相当し、本チケットの範囲を超える。

### 5.5 レビューチェックリスト

- [ ] `isClosingPunctuation()` が M1 で追加済みであることを確認
- [ ] 挿入位置が L2165 の `}` (while ループ閉じ) と L2166 の `i = punctEnd - 1` の間であることを確認
- [ ] `hasTerminator` ガードが存在すること
- [ ] `punctEnd` が `cpLen` を超えないこと（`while (punctEnd < cpLen && ...)` の条件）
- [ ] 既存テスト全 PASS（リグレッションなし）

---

## 6. ゼロから作り直すとしたら（エージェントチーム議論結果）

M2 実装後に4名のエージェントチーム（アーキテクチャ / クロスランタイム一貫性 / エッジケース・堅牢性 / テスタビリティ・保守性）でレビュー・議論を実施。以下はその統合結果。

### 6.1 状態マシン vs ad-hoc ループ（結論: 現行維持）

現在の C++ は boundary punctuation while ループ + 閉じ括弧 while ループの2段構成。明示的な状態マシン (`Normal` → `InPunctuation` → `InClosingBracket`) への書き換えを検討したが、**実質2状態しかないため過剰設計**と判断。Rust/C# も同一パターン（scan → detect terminator → inner while-loop for closers）を採用しており、3ランタイムで実証済みの設計。

状態マシンが正当化されるのは、SSML タグ解析等で文法が大幅に拡張された場合のみ。

### 6.2 post-consume vs depth-tracking（結論: post-consume が TTS に最適）

| 観点 | post-consume (C++/Rust/C#) | depth-tracking (Go) |
|------|--------------------------|---------------------|
| チャンク長 | 短い（文単位） | 長い（括弧内を含む） |
| TTS レイテンシ | 低い（first-audio 高速） | 高い |
| 実装複雑性 | 低い（ペアテーブル不要） | 高い（depth カウンタ + inQuote トグル） |
| アンバランス括弧 | 安全（常にフラッシュ） | 危険（全テキスト1文になりうる） |
| 結果 | `「元気です。」` → 3文 | `「元気です。」と言った。` → 2文 |

**一から作り直すなら全ランタイムを post-consume に統一**すべき。Go の depth-tracking は言語的に正確だが、TTS 用途では短チャンク＝低レイテンシ＋高合成品質が優先される。

### 6.3 関心の分離: `text_splitter.h/.cpp` 抽出（結論: 最高優先リファクタ）

`piper.cpp` は 2200+ 行で、音素化・ONNX推論・音声後処理・ウォームアップ・テキスト分割が同居。他3ランタイムは既に分離済み（`streaming.rs`, `TextSplitter.cs`, `text_splitter.go`）。C++ だけがアウトライヤー。

**推奨構成:**
- `src/cpp/text_splitter.h` — 公開API + `PhonemeType` サブセット
- `src/cpp/text_splitter.cpp` — 実装（依存: `utf8_utils.hpp` + `spdlog` のみ）
- `piper.cpp` は `#include "text_splitter.h"` で委譲

これにより**テストミラー問題が根本解決**される（テストバイナリが `text_splitter.cpp` を直接リンク）。ただし M2 スコープ外。フォローアップ Issue として推奨。

### 6.4 エッジケース全数検証（結論: 12パターン全て正常、バグなし）

| # | ケース | 入力 | 結果 | 正常 |
|---|--------|------|------|------|
| 1 | 深いネスト | `「『（OK。）』」次。` | 3括弧全て消費 → `["「『（OK。）』」", "次。"]` | ✅ |
| 2 | ミスマッチ | `「OK。）次。` | `)` を貪欲消費 → `["「OK。）", "次。"]` | ✅ |
| 3 | 連続ターミネータ+括弧 | `OK。！」次。` | 全て1チャンク → `["OK。！」", "次。"]` | ✅ |
| 4 | 先行ターミネータなし | `テスト）続き。` | 消費しない → `["テスト）続き。"]` | ✅ |
| 5 | 閉じ括弧のみ | `」』）` | 残余テキスト → `["」』）"]` | ✅ |
| 6 | 先頭に閉じ括弧 | `」こんにちは。` | 通常文字扱い → `["」こんにちは。"]` | ✅ |
| 7 | CJK多種括弧 | `OK。」』】` | 3種全消費 → `["OK。」』】"]` | ✅ |
| 8 | 英語引用符 | `He said "Hello." She replied.` | `"` 消費 → `["He said \"Hello.\"", ...]` | ✅ |
| 9 | フランス語ギュメ | `«Bonjour.» Au revoir.` | `»` 消費 → `["«Bonjour.»", ...]` | ✅ |
| 10 | 空文+括弧 | `。」` | → `["。」"]` | ✅ |
| 11 | dynamicChunkSize 超過 | 長テキスト+括弧 | `hasTerminator` で分割確定、チャンク長は影響なし | ✅ |
| 12 | 中間の曖昧引用符 | `It's a "test" of the system.` | `"` `'` は terminator 直後でないため無影響 | ✅ |

**セキュリティ:** バッファオーバーフロー（`punctEnd < cpLen` ガード）、無限ループ（`punctEnd++` 単調増加）、整数アンダーフロー（`punctEnd >= i + 1` 保証）— **全てリスクなし**。

### 6.5 クロスランタイム一貫性（新発見: Go の U+FF0E ターミネータ）

**閉じ括弧文字セット乖離（既知）:**

| ランタイム | 充足率 | 不足文字 |
|---|---|---|
| C++ | 14/14 | なし |
| Rust | 11/14 | `U+201D` `U+2019` `U+00BB` |
| C# | 11/14 | `U+201D` `U+2019` `U+00BB` |
| Go | 8/14 | `U+0022` `U+0027` `U+FF3D` `U+FF63` `U+2019` `U+00BB` |

**文末ターミネータ乖離（新発見）:**

Go の `text_splitter.go` に `U+FF0E`（全角ピリオド ．）が `isSentenceEnd()` (L163), `isCJKSentenceEnd()` (L172), `isPunctuation()` (L204) の3箇所で一貫使用されていることを発見。他3ランタイムには存在しない。

| ランタイム | ターミネータ数 | U+FF0E |
|---|---|---|
| C++ | 6/7 | なし |
| Rust | 6/7 | なし |
| C# | 6/7 | なし |
| Go | 7/7 | あり |

**対応:** `docs/spec/text-splitter-contract.toml` に U+FF0E を7番目の正規ターミネータとして追加し、乖離ステータスを記載済み。

### 6.6 テスタビリティ（結論: ミラー非同期は M3 で対応）

**テストミラー問題:** `test_split_sentences.cpp` は `piper.cpp` のアルゴリズムを匿名名前空間にコピーしている。M1/M2 の変更はまだミラーに反映されておらず、**現在のテストは修正前の動作を検証している**。M3 で対応。

**M3 で追加すべきテストケース（最低7件）:**

1. CJK 基本括弧消費（`「こんにちは。」次の文。`）
2. 二重角括弧（`『素晴らしい！』感動した。`）
3. ネスト括弧（`「『OK。』」次。`）
4. 英語引用符（`He said "Hello." Then left.`）
5. リグレッション防止・括弧なし（`テスト。次のテスト。`）
6. hasTerminator ガード（`そうですか…」次の話。` — 省略記号は terminator ではない）
7. 全角丸括弧（`結果は（成功です。）次へ。`）

### 6.7 Contract test と CI 強制（結論: フォローアップ推奨）

TOML 仕様は現在ドキュメントのみで CI 強制がない。推奨アプローチ:

1. `docs/spec/text-splitter-vectors.json` にテストベクターを定義（`{input, expected_chunks, strategy}` 形式）
2. 各ランタイムのテストスイートがベクターを読み込んで実行
3. Go 用ベクターは `strategy: "depth-tracking"` でタグ付け
4. TOML のコードポイント一覧と各ランタイムの実装を照合する lint スクリプト（~50行 Python）を CI に追加

推定工数は小だが、M2 スコープ外。4ランタイム×8言語の乖離が広がる前に対応すべき。

### 6.8 一から作り直すなら: Top 3 アクション

1. **`text_splitter.h/.cpp` を `piper.cpp` から抽出** — 設定構造体でモード分岐を明示化。テストミラー不要に
2. **全ランタイムを post-consume に統一** — Go の depth-tracking を揃える
3. **CI 強制の contract test** — TOML → テストベクター自動生成、4ランタイム共通で実行

---

## 7. 後続タスクへの連絡事項

### M3 が知るべきこと

#### 7.1 変更した行範囲

`piper.cpp` の L2165-L2166 間に5行を挿入。挿入後は L2165 の `}` (while ループ閉じ) の後に:

```cpp
      // Issue #346: Consume closing brackets/quotes after sentence terminator
      if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
          punctEnd++;
        }
      }
```

が追加され、元の `i = punctEnd - 1` は L2171 付近に移動する。

#### 7.2 テストミラーに反映すべき差分

`test_split_sentences.cpp` の匿名名前空間内ミラー関数（現在 L99-127）に対して、以下の2箇所を更新する必要がある:

1. **`isClosingPunctuation()` 関数の追加** (M1 のミラー)
   - 匿名名前空間内、`splitTextToSentences()` の前に `static` (不要、名前空間内なので) もしくはフリー関数として追加
   - 文字セットは M1 で定義された14文字と完全一致させること

2. **閉じ括弧消費ループの追加** (M2 のミラー)
   - ミラーの L110 (`while` ループ閉じ `}`) と L111 (`i = punctEnd - 1`) の間に同じ5行を挿入
   - M1 で追加した `isClosingPunctuation()` を呼び出す

#### 7.3 期待される動作変更

修正前後で以下の動作差分が発生する。M3 のテストケースはこれらを検証すること:

| 入力 | 修正前 | 修正後 |
|------|--------|--------|
| `「こんにちは。」次の文。` | `["「こんにちは。", "」次の文。"]` | `["「こんにちは。」", "次の文。"]` |
| `『素晴らしい！』感動した。` | `["『素晴らしい！", "』感動した。"]` | `["『素晴らしい！』", "感動した。"]` |
| `結果は（成功です。）次へ。` | `["結果は（成功です。", "）次へ。"]` | `["結果は（成功です。）", "次へ。"]` |
| `「『OK。』」次。` | `["「『OK。", "』」次。"]` | `["「『OK。』」", "次。"]` |

**変化しないケース** (リグレッション防止):

| 入力 | 動作 (変更なし) |
|------|----------------|
| `テスト。次のテスト。` | `["テスト。", "次のテスト。"]` -- 閉じ括弧なし、消費ループは no-op |
| `「テスト」続き。` | `["「テスト」続き。"]` -- 文末記号なし、`isBoundaryPunct` に到達しないため消費ループに入らない |
| `Hello. World.` | `["Hello.", " World."]` -- ASCII のみ、閉じ括弧なし |
