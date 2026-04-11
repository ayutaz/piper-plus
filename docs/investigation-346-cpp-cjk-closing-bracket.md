# Issue #346 調査レポート: C++ CLI splitTextToSentences() CJK閉じ括弧未消費

## 概要

C++ の `splitTextToSentences()` が文末記号（。！？）の後の CJK 閉じ括弧（」『）等）を消費しないため、引用テキストで終わる文が誤分割される。Rust, C#, Go の3ランタイムでは正しく処理済み。

**再現:**
```
入力:  「こんにちは。」次の文。

C++ (現状):  ["「こんにちは。", "」次の文。"]   ← 」が次の文に漏れる
Rust/C#/Go:  ["「こんにちは。」", "次の文。"]   ← 正しい
```

---

## 1. C++ 現状分析

### 1.1 関数構造 (`src/cpp/piper.cpp:2074-2130`)

`splitTextToSentences()` は **regex ベース** の分割を使用。`std::sregex_token_iterator` で文末記号にマッチし、交互に「テキスト/デリミタ」トークンを生成する。

```
シグネチャ: splitTextToSentences(text, phonemeType, maxChunkSize)

2074-2077: 関数シグネチャ
2079-2081: 空文字チェック
2083-2084: 動的チャンクサイズ計算 (calculateDynamicChunkSize)
2086-2094: 3つの static regex パターン定義
2096-2101: phonemeType に基づく regex 選択
2103-2105: sregex_token_iterator で分割
2107-2123: メインループ（テキスト蓄積 + デリミタ追加 + フラッシュ）
2125-2129: 残余テキストフラッシュ
```

### 1.2 regex パターン

| パターン名 | 正規表現 | 使用条件 |
|-----------|---------|---------|
| `multilingualSentenceEnd` | `([。！？.!?]+\|[…]+\|[\\.]{3,})` | `MultilingualPhonemes` |
| `japaneseSentenceBoundary` | `([。！？、]+)` | `usesOpenJTalk()` (非Multilingual) |
| `englishSentenceBoundary` | `([.!?,;:]+\|\\s+(?:and\|or\|but\|...)\\s+)` | その他 |

### 1.3 根本原因

regex アプローチでは閉じ括弧 `」` は句読点パターンにマッチしないため、**次のテキストトークンの先頭**になる。

```
入力: 「こんにちは。」次の文。
regex: ([。！？.!?]+)

トークン列: ["「こんにちは", "。", "」次の文", "。"]
結果: chunk1 = "「こんにちは。", chunk2 = "」次の文。"
```

### 1.4 既存 Unicode ユーティリティ

| 関数 | 場所 | 用途 |
|------|------|------|
| `utf8.h` (utfcpp) | `src/cpp/utf8.h` | UTF-8 ライブラリ（vendored, header-only） |
| `utf8_utils.hpp` | `src/cpp/utf8_utils.hpp` | `toCodepoints()`, `utf8ToU32()`, `cpToUtf8()` 等 |
| `isSingleCodepoint()` | `piper.cpp:121` | 文字列が1コードポイントか判定 |
| `getCodepoint()` | `piper.cpp:126` | 先頭コードポイント取得 |
| `UnicodeLanguageDetector` | `language_detector.cpp` | `isKana()`, `isCJK()` 等の範囲判定 |

**重要:** `isSentenceTerminator()` と `isClosingPunctuation()` は C++ に**存在しない**。

### 1.5 既存テスト

`splitTextToSentences` の**専用ユニットテストはゼロ**。`test_streaming_simple.cpp` がチャンキングロジックのインライン複製をテストしているが、実関数は呼んでいない。テストフレームワークは Google Test v1.14.0。

---

## 2. 他ランタイム実装比較

### 2.1 アーキテクチャ比較

| 観点 | C++ (現状) | Rust (streaming.rs) | C# (TextSplitter.cs) | Go (text_splitter.go) |
|------|-----------|---------------------|----------------------|----------------------|
| **アルゴリズム** | regex 分割 | コードポイント逐次走査 | char 逐次走査 | rune 逐次走査 |
| **閉じ括弧消費** | なし | 貪欲消費ループ | 貪欲消費ループ | depth tracking |
| **括弧 depth 追跡** | なし | なし | なし | あり（唯一） |
| **引用符内抑制** | なし | なし | なし | あり (`inQuote`) |
| **略語認識** | なし | なし (text_splitter.rs にはあり) | なし | なし |

### 2.2 閉じ括弧文字セット（全ランタイム統合）

| 文字 | Unicode | Rust streaming | C# | Go | Issue推奨 |
|------|---------|---------------|-----|-----|----------|
| `)` | U+0029 | ✅ | ✅ | ✅ | ✅ |
| `]` | U+005D | ✅ | ✅ | ❌ | ✅ |
| `}` | U+007D | ✅ | ✅ | ❌ | ✅ |
| `"` | U+0022 | ✅ | ✅ | ❌ | ✅ |
| `'` | U+0027 | ✅ | ✅ | ❌ | ✅ |
| `」` | U+300D | ✅ | ✅ | ✅ | ✅ |
| `』` | U+300F | ✅ | ✅ | ✅ | ✅ |
| `）` | U+FF09 | ✅ | ✅ | ✅ | ✅ |
| `］` | U+FF3D | ✅ | ✅ | ❌ | ✅ |
| `】` | U+3011 | ✅ | ✅ | ✅ | ✅ |
| `｣` | U+FF63 | ✅ | ✅ | ❌ | ✅ |
| `"` | U+201D | ❌ | ❌ | ✅ | Issue言及 |

**推奨セット:** Rust/C# の11文字 + U+201D = **12文字**

### 2.3 文末記号文字セット（全ランタイム共通）

| 文字 | Unicode | 名称 |
|------|---------|------|
| `.` | U+002E | Period |
| `!` | U+0021 | Exclamation |
| `?` | U+003F | Question |
| `。` | U+3002 | Ideographic Full Stop |
| `！` | U+FF01 | Fullwidth Exclamation |
| `？` | U+FF1F | Fullwidth Question |

Go のみ追加: `．` (U+FF0E, Fullwidth Full Stop)

---

## 3. 各ランタイム詳細

### 3.1 Rust (`src/rust/piper-core/src/streaming.rs`)

**閉じ括弧消費ループ (279-285行):**
```rust
while let Some(&next_ch) = chars.peek() {
    if is_closing_punctuation(next_ch) {
        current.push(chars.next().unwrap());
    } else { break; }
}
```

`is_closing_punctuation()` (326-340行) は11文字を判定。文末記号検出→閉じ括弧を貪欲消費→フラッシュ→空白スキップ、のシンプルなフロー。

**Rust には2つの実装が並存:**
- `streaming.rs`: シンプル版（11文字消費、略語なし）
- `text_splitter.rs`: 高機能版（略語、引用符、段落、省略記号対応）。CJK 後は5文字のみ消費。

### 3.2 C# (`src/csharp/PiperPlus.Core/Phonemize/TextSplitter.cs`)

**閉じ括弧消費ループ (49-53行):**
```csharp
while (i < text.Length && IsClosingPunctuation(text[i]))
{
    current.Append(text[i]);
    i++;
}
```

`IsClosingPunctuation()` (100-113行) はRust streaming と同一の11文字。Rust streaming.rs のミラー実装。

### 3.3 Go (`src/go/piperplus/text_splitter.go`)

**設計が他と大きく異なる:**
- `isOpenBracket()`/`isCloseBracket()` で8文字ずつペアリング追跡
- `depth` カウンタで括弧ネスト深度を管理
- `inQuote` トグルで ASCII `"` を追跡
- `depth > 0 || inQuote` の間は文分割を抑制
- `justClosed` フラグで閉じ括弧直前の文末記号を検出

**潜在的問題:** `「こんにちは。」次の文。` で `」` の後に空白なしで次文が続くケースで、CJK 即時分割パスに入らない可能性あり（`」` は文末記号ではないため）。

### 3.4 Python (`src/python_run/piper/phonemize/japanese.py`)

- `re.compile(r"(?<=[。！？\n])")` による単純 regex 分割のみ
- 閉じ括弧処理なし（C++ と同じ問題を抱える）
- ただし Python はストリーミング用途ではなく OpenJTalk バッファオーバーフロー防止の安全分割

---

## 4. テストケース分析

### 4.1 各ランタイム CJK 括弧テスト

| ランタイム | テスト名 | 入力 | 期待出力 |
|-----------|---------|------|---------|
| Rust | `test_split_sentences_with_closing_brackets` | `「こんにちは。」次の文。` | `["「こんにちは。」", "次の文。"]` |
| C# | `ClosingPunctuation_JapaneseQuotes` | `「こんにちは。」次の文。` | `["「こんにちは。」", "次の文。"]` |
| Go | `TestSplitSentences_JapaneseQuotes` | `彼は「元気です。」と言った。終わり。` | `["彼は「元気です。」と言った。", "終わり。"]` |
| C++ | (なし) | - | - |

### 4.2 C++ に追加すべきテストケース

**Priority 1: CJK 閉じ括弧（Issue #346 直接関連）**

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| 1 | `CJKClosingBracket_Kagi` | `「こんにちは。」次の文。` | `["「こんにちは。」", "次の文。"]` |
| 2 | `CJKClosingBracket_DoubleKagi` | `『テスト。』次。` | `["『テスト。』", "次。"]` |
| 3 | `CJKClosingBracket_FullwidthParen` | `（テスト。）次。` | `["（テスト。）", "次。"]` |
| 4 | `CJKClosingBracket_Sumitsuki` | `【テスト。】次。` | `["【テスト。】", "次。"]` |
| 5 | `CJKClosingBracket_HalfwidthKagi` | `｢テスト。｣次。` | `["｢テスト。｣", "次。"]` |
| 6 | `CJKClosingBracket_Multiple` | `「テスト。」」次。` | `["「テスト。」」", "次。"]` |
| 7 | `WesternClosingQuote` | `She said "Hello." Then left.` | `["She said \"Hello.\"", "Then left."]` |
| 8 | `WesternClosingParen` | `(test.) next.` | `["(test.)", "next."]` |

**Priority 2: 基本テスト（リグレッション防止）**

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| 9 | `BasicJapanese` | `こんにちは。さようなら。` | 2文 |
| 10 | `BasicEnglish` | `Hello. World.` | 2文 |
| 11 | `FullwidthPunctuation` | `すごい！本当ですか？はい。` | 3文 |
| 12 | `MixedLanguage` | `Hello. こんにちは。` | 2文 |
| 13 | `Chinese` | `你好。今天天气很好！` | 2文 |

**Priority 3: エッジケース**

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| 14 | `EmptyInput` | `""` | `[]` |
| 15 | `WhitespaceOnly` | `"   "` | `[]` |
| 16 | `NoTerminator` | `"No punctuation here"` | 1文 |
| 17 | `NewlineSeparator` | `"Hello.\nWorld."` | 2文 |
| 18 | `TrailingSpaces` | `"Hello.   World.   "` | 2文 (trimmed) |

---

## 5. 修正方針

### 5.1 アプローチ比較

| 方針 | 概要 | メリット | デメリット |
|------|------|---------|-----------|
| **A: regex 拡張** | 既存 regex に閉じ括弧を含める | 変更量最小 | 複雑な regex になり保守困難 |
| **B: 後処理追加** | regex 分割後に閉じ括弧を次チャンクから移動 | 既存ロジック維持 | やや ad-hoc |
| **C: codepoint 書き換え** | Rust/C# 方式の逐次走査に全面書き換え | 他ランタイムと一致、拡張容易 | 変更量大 |

### 5.2 推奨: 方針 B（後処理追加）

**理由:**
- Issue #346 のスコープは「閉じ括弧消費の追加」であり、全面書き換えは過剰
- 既存の regex 分割ロジックは他の文分割機能（チャンクサイズ制限等）と結合している
- 後処理なら既存コードへの影響を最小化できる
- テストで動作を検証し、将来的な全面書き換えの足がかりにできる

**実装イメージ:**
```cpp
// piper.cpp に追加するヘルパー
static bool isClosingPunctuation(char32_t cp) {
    switch (cp) {
        case ')': case ']': case '}': case '"': case '\'':
        case 0x300D: // 」
        case 0x300F: // 』
        case 0xFF09: // ）
        case 0xFF3D: // ］
        case 0x3011: // 】
        case 0xFF63: // ｣
        case 0x201D: // "
            return true;
        default: return false;
    }
}

// splitTextToSentences のフラッシュ後に:
// 次チャンクの先頭から閉じ括弧を取り出して前チャンクに付加
```

### 5.3 追加すべき関数

| 関数名 | シグネチャ | 用途 |
|--------|----------|------|
| `isClosingPunctuation` | `static bool isClosingPunctuation(char32_t cp)` | 閉じ括弧判定（12文字） |
| `isSentenceTerminator` | `static bool isSentenceTerminator(char32_t cp)` | 文末記号判定（6文字） |

### 5.4 依存関係

- 追加ライブラリ不要（既存の `utf8.h` で UTF-8 デコード可能）
- `utf8::unchecked::next(it)` でコードポイント単位のイテレーション可能

---

## 6. CI・テスト実行

- **フレームワーク:** Google Test v1.14.0 (CMake FetchContent)
- **ビルド:** `cmake -B build -DBUILD_TESTS=ON && cmake --build build`
- **実行:** `ctest -R test_split_sentences -V`
- **CI:** `.github/workflows/cpp-tests.yml` → `_build-test-cpp.yml`
- **テスト登録:** `src/cpp/tests/CMakeLists.txt` の `TEST_SOURCES` に追加

---

## 7. 参照ファイル一覧

| ランタイム | ファイル | 行番号 |
|-----------|---------|--------|
| **C++ (修正対象)** | `src/cpp/piper.cpp` | 2074-2130 |
| **C++ ヘッダー** | `src/cpp/piper.hpp` | 248 |
| **C++ UTF-8** | `src/cpp/utf8.h`, `src/cpp/utf8_utils.hpp` | - |
| **C++ テスト** | `src/cpp/tests/` (新規追加) | - |
| **Rust streaming** | `src/rust/piper-core/src/streaming.rs` | 262-340 |
| **Rust text_splitter** | `src/rust/piper-core/src/text_splitter.rs` | 82-257 |
| **C#** | `src/csharp/PiperPlus.Core/Phonemize/TextSplitter.cs` | 29-113 |
| **Go** | `src/go/piperplus/text_splitter.go` | 22-198 |
| **Python** | `src/python_run/piper/phonemize/japanese.py` | 133-153 |
