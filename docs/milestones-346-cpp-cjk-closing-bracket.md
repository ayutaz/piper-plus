# Issue #346 マイルストーン: C++ splitTextToSentences() CJK閉じ括弧対応

> **ブランチ:** `fix/cpp-cjk-closing-bracket-346`
> **関連:** [調査レポート](investigation-346-cpp-cjk-closing-bracket.md) | [チケット一覧](tickets/README.md)
>
> **チケット:** [M1](tickets/M1-add-isClosingPunctuation-helper.md) → [M2](tickets/M2-add-closing-bracket-consumption-loop.md) → [M3](tickets/M3-update-test-mirror-and-add-tests.md) → [M4](tickets/M4-ci-verification-and-pr.md)

---

## 前提: 調査による修正方針の更新

初期調査では C++ の `splitTextToSentences()` を regex ベースと記載していたが、計画策定エージェントが実コードを読んだ結果、**PR #343 で既にコードポイントベースの逐次走査に書き換え済み**であることが判明。

このため修正方針を変更:
- ~~方針B: 後処理追加~~ → **インライン消費（Rust/C# と同一パターン）**
- 既存の boundary punctuation 消費ループの直後に、閉じ括弧消費ループを追加するだけで済む

---

## M1: ヘルパー関数追加

**対象ファイル:** `src/cpp/piper.cpp`

### タスク

1. `isClosingPunctuation(char32_t)` を `splitTextToSentences()` の直前に static 関数として追加

### 閉じ括弧文字セット（12文字）

| 文字 | Unicode | 名称 |
|------|---------|------|
| `)` | U+0029 | Right Parenthesis |
| `]` | U+005D | Right Square Bracket |
| `}` | U+007D | Right Curly Bracket |
| `"` | U+0022 | Quotation Mark |
| `'` | U+0027 | Apostrophe |
| `」` | U+300D | Right Corner Bracket |
| `』` | U+300F | Right White Corner Bracket |
| `）` | U+FF09 | Fullwidth Right Parenthesis |
| `］` | U+FF3D | Fullwidth Right Square Bracket |
| `】` | U+3011 | Right Black Lenticular Bracket |
| `｣` | U+FF63 | Halfwidth Right Corner Bracket |
| `"` | U+201D | Right Double Quotation Mark |

### 設計根拠

- Rust streaming.rs (11文字) + Go の U+201D = 12文字の全ランタイムスーパーセット
- `static` 関数（`piper.cpp` ファイルスコープ）。ヘッダー公開不要
- 既存の `isSingleCodepoint()`, `getCodepoint()` と同じパターン

### 完了条件

- [ ] `isClosingPunctuation()` が `piper.cpp` に追加されていること

---

## M2: splitTextToSentences() に閉じ括弧消費ループ追加

**対象ファイル:** `src/cpp/piper.cpp` (2156-2177行付近)

### タスク

1. boundary punctuation 消費ループの直後、`i = punctEnd - 1` の前に閉じ括弧消費ループを挿入

### 修正箇所

既存コード（概要）:
```cpp
if (isBoundaryPunct(c)) {
    bool hasTerminator = isSentenceTerminator(c);
    size_t punctEnd = i + 1;
    while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {
        if (isSentenceTerminator(cps[punctEnd])) hasTerminator = true;
        punctEnd++;
    }
    // ★ ここに閉じ括弧消費ループを挿入
    i = punctEnd - 1;
    // ... chunk emission
}
```

追加するコード:
```cpp
    // Issue #346: 文末記号の後の閉じ括弧を消費
    if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
            punctEnd++;
        }
    }
```

### 設計判断

| 判断 | 内容 | 理由 |
|------|------|------|
| `hasTerminator` ガード | 文末記号がある場合のみ消費 | カンマ等の後の括弧を誤消費しない |
| 貪欲消費 | 連続する閉じ括弧を全て消費 | `「『OK。』」` → `『` `」` 両方消費 |
| depth tracking なし | Go 方式は採用しない | 既存アーキテクチャとの整合性、変更最小化 |

### Go との動作差異（許容）

```
入力: 彼は「元気です。」と言った。終わり。

Go (depth tracking):  ["彼は「元気です。」と言った。", "終わり。"]  (2文)
C++ (post-consume):   ["彼は「元気です。」", "と言った。", "終わり。"]  (3文)
```

C++ は括弧内の文末記号を抑制しない。これは C#/Rust streaming.rs と同じ動作であり、Issue #346 のスコープ外。

### 完了条件

- [ ] `piper.cpp` の `splitTextToSentences()` に閉じ括弧消費ループが追加されていること
- [ ] `「こんにちは。」次の文。` が `["「こんにちは。」", "次の文。"]` と分割されること

---

## M3: テストミラー更新 + テストケース追加

**対象ファイル:** `src/cpp/tests/test_split_sentences.cpp`

### 背景

テストファイルは `piper.cpp` の `splitTextToSentences()` アルゴリズムを**匿名名前空間にミラーコピー**している（ONNX Runtime リンク回避のため）。M1/M2 の変更をミラーにも反映する必要がある。

### タスク

1. 匿名名前空間に `isClosingPunctuation()` を追加
2. ミラーの `splitTextToSentences()` に閉じ括弧消費ループを追加
3. 10個の新規テストケースを追加

### テストケース一覧

**Priority 1: CJK 閉じ括弧（Issue #346 直接対象）**

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| 1 | `CJKClosingBracket_BasicKakko` | `「こんにちは。」次の文。` | `["「こんにちは。」", "次の文。"]` |
| 2 | `CJKClosingBracket_DoubleCornerBracket` | `『素晴らしい！』感動した。` | `["『素晴らしい！』", "感動した。"]` |
| 3 | `CJKClosingBracket_FullwidthParen` | `結果は（成功です。）次へ。` | `["結果は（成功です。）", "次へ。"]` |
| 4 | `CJKClosingBracket_Sumitsuki` | `【テスト。】次。` | `["【テスト。】", "次。"]` |
| 5 | `CJKClosingBracket_HalfwidthKakko` | `｢テスト。｣次。` | `["｢テスト。｣", "次。"]` |
| 6 | `CJKClosingBracket_MultipleBrackets` | `「『OK。』」次。` | `["「『OK。』」", "次。"]` |

**Priority 2: Western 閉じ括弧**

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| 7 | `WesternClosingQuote` | `She said "Hello." Then left.` | `["She said \"Hello.\"", ...]` |
| 8 | `WesternClosingParen` | `Result (ok.) Next.` | `["Result (ok.)", ...]` |

**Priority 3: リグレッション防止 + エッジケース**

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| 9 | `CJKClosingBracket_NoClosingNoop` | `テスト。次のテスト。` | 2文（既存動作と同一） |
| 10 | `CJKClosingBracket_NoTerminatorNoop` | `「テスト」続き。` | 1文（文末記号なしの括弧は消費しない） |

### CMake 変更

**変更不要。** `test_split_sentences` は既に `TEST_SOURCES` に登録済み（`CMakeLists.txt:63`）。追加のリンク依存もない。

### 完了条件

- [ ] テストミラーに `isClosingPunctuation()` + 消費ループが反映されていること
- [ ] 10個の新規テストが追加されていること
- [ ] `ctest -R test_split_sentences -V` で全テスト PASS

---

## M4: CI 検証 + PR 作成

### タスク

1. ローカルビルド・テスト実行確認
2. 全 C++ テスト実行（リグレッション確認）
3. PR 作成

### CI マトリックス

| OS | Build Type | テスト |
|----|-----------|--------|
| Ubuntu 22.04 | Release / Debug | test_split_sentences + 全テスト |
| macOS latest | Release / Debug | test_split_sentences + 全テスト |
| Windows latest | Release / Debug | test_split_sentences + 全テスト |

### ローカル検証コマンド

```bash
# ビルド + テスト
cmake -B build -DBUILD_TESTS=ON
cmake --build build --target test_split_sentences
ctest -R test_split_sentences -V --test-dir build

# 全テスト（リグレッション確認）
ctest -E "test_c_api_integration|test_c_api_audio_regression" --test-dir build
```

### リグレッションリスク

| リスク | レベル | 理由 |
|--------|-------|------|
| 既存テスト破壊 | **低** | 消費ループは `hasTerminator` 時のみ発動。既存テストに閉じ括弧パターンなし |
| C API 動作変更 | **低** | `piper_plus_synth_start()` 経由で同じ関数を呼ぶが、文境界改善のみ |
| 音声品質影響 | **なし** | 文分割の改善であり、合成ロジックは不変 |
| テストミラー乖離 | **中** | 将来 `piper.cpp` 変更時にミラー更新忘れのリスク。コメントで警告 |

### 完了条件

- [ ] ローカルで全テスト PASS
- [ ] PR 作成済み
- [ ] CI 全グリーン

---

## 全体サマリ

| マイルストーン | 対象ファイル | 変更内容 | 見積もり |
|--------------|------------|---------|---------|
| **M1** | `piper.cpp` | `isClosingPunctuation()` 追加 | 小 |
| **M2** | `piper.cpp` | 消費ループ追加（~5行） | 小 |
| **M3** | `test_split_sentences.cpp` | ミラー更新 + テスト10個 | 中 |
| **M4** | - | CI 検証 + PR | 小 |

**変更ファイル数:** 2ファイル (`piper.cpp`, `test_split_sentences.cpp`)
**ヘッダー変更:** なし
**CMake 変更:** なし
**依存追加:** なし
