# T-M2-02: ローンワード接尾辞検出

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M2: G2Pコアエンジン |
| 依存チケット | T-M2-01 (構造体 + トークン化), M1 (定数定義: `svAgeNativeWords`) |
| 後続チケット | T-M2-05 (単語G2P統合で `svDetectLoanwordSuffix` を呼び出す) |
| 対象ファイル | `src/go/phonemize/swedish.go` (追記) |
| 推定行数 | ~60行 |

## 1. タスク目的とゴール

スウェーデン語のローンワード (外来語) は接尾辞の発音がネイティブ規則と大きく異なる。例えば `-tion` は `/ɧuːn/` と発音される。本チケットでは 7 種の接尾辞パターンを検出し、対応する固定音素列を返す `svDetectLoanwordSuffix()` を実装する。

**完了時の状態:**
- `svDetectLoanwordSuffix()` が 7 接尾辞パターンを検出し `(stem, suffixPhonemes)` を返却
- `AGE_NATIVE_WORDS` に含まれる単語は `-age` ローンワードから除外
- Python 参照実装 `detect_loanword_suffix()` と同等の動作

## 2. 実装する内容の詳細

### 2.1 ローンワード接尾辞規則テーブル

M1 で定義済みの `svAgeNativeWords` を使用。規則テーブルは本チケットで定義する。

```go
type svLoanwordRule struct {
    suffix   string
    phonemes []string
}

var svLoanwordSuffixRules = []svLoanwordRule{
    {"ssion", []string{"\u0267", "u\u02d0", "n"}},  // -ssion → ɧ uː n
    {"tion",  []string{"\u0267", "u\u02d0", "n"}},   // -tion  → ɧ uː n
    {"sion",  []string{"\u0267", "u\u02d0", "n"}},   // -sion  → ɧ uː n
    {"age",   []string{"\u0251\u02d0", "\u0267"}},    // -age   → ɑː ɧ
    {"eur",   []string{"\u00f8\u02d0", "r"}},         // -eur   → øː r
    {"eum",   []string{"e\u02d0", "\u0275", "m"}},    // -eum   → eː ɵ m
    {"ium",   []string{"\u026a", "\u0275", "m"}},     // -ium   → ɪ ɵ m
}
```

**全パターンの音素詳細:**

| # | 接尾辞 | 音素列 | Unicode | 例語 |
|---|--------|--------|---------|------|
| 1 | -ssion | ɧ + uː + n | `\u0267` + `u\u02d0` + `n` | passion → pas + ɧuːn |
| 2 | -tion | ɧ + uː + n | `\u0267` + `u\u02d0` + `n` | station → sta + ɧuːn |
| 3 | -sion | ɧ + uː + n | `\u0267` + `u\u02d0` + `n` | vision → vi + ɧuːn |
| 4 | -age | ɑː + ɧ | `\u0251\u02d0` + `\u0267` | garage → gar + ɑːɧ |
| 5 | -eur | øː + r | `\u00f8\u02d0` + `r` | friseur → fris + øːr |
| 6 | -eum | eː + ɵ + m | `e\u02d0` + `\u0275` + `m` | museum → mus + eːɵm |
| 7 | -ium | ɪ + ɵ + m | `\u026a` + `\u0275` + `m` | stadium → stad + ɪɵm |

**重要:** テーブルの順序は最長一致を保証するよう `ssion` (5文字) → `tion` (4文字) → `sion` (4文字) の順。`station` は `-ssion` にマッチしない場合のみ `-tion` にフォールバック。

### 2.2 AGE_NATIVE_WORDS 除外リスト

M1 で定義済み:

```go
var svAgeNativeWords = map[string]bool{
    "bage": true, "lage": true, "sage": true, "dage": true,
    "mage": true, "hage": true, "tage": true, "klage": true,
    "frage": true, "plage": true, "drage": true,
}
```

### 2.3 検出関数

```go
// svDetectLoanwordSuffix checks for loanword suffix patterns.
// Returns (stem, suffixPhonemes, true) if found, or ("", nil, false).
func svDetectLoanwordSuffix(word string) (string, []string, bool) {
    for _, rule := range svLoanwordSuffixRules {
        if strings.HasSuffix(word, rule.suffix) && len(word) > len(rule.suffix) {
            // -age のネイティブ例外チェック
            if rule.suffix == "age" && svAgeNativeWords[word] {
                continue
            }
            stem := word[:len(word)-len(rule.suffix)]
            return stem, rule.phonemes, true
        }
    }
    return "", nil, false
}
```

**Python 参照実装との対応:**

| Python | Go |
|---|---|
| `detect_loanword_suffix(word) -> tuple[str, list[str]] \| None` | `svDetectLoanwordSuffix(word string) -> (string, []string, bool)` |
| `return (stem, phonemes)` | `return stem, phonemes, true` |
| `return None` | `return "", nil, false` |

Go では `None` 相当を `(zero, nil, false)` の 3 値返却で表現する。Python のタプル/None パターンより明示的。

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装エージェント | 規則テーブル定義、`svDetectLoanwordSuffix` 関数実装 | 1 |
| 2 | レビューエージェント | Python 参照実装との音素列一致検証、テーブル順序確認 | 1 |

**合計: 2 エージェント**

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svLoanwordRule` 構造体
- `svLoanwordSuffixRules` テーブル (7エントリ)
- `svDetectLoanwordSuffix()` 関数

**含まない:**
- ステムの G2P 変換 (T-M2-05 で `svConvertWordNative` を呼び出す)
- ローンワード接頭辞検出 (`sch/sh/ch/ph/th` は T-M2-03 の子音変換で処理)
- ストレス位置のローンワード調整 (M3 のストレス検出で処理)

### 4.2 テスト項目

| # | テスト | 入力 | 期待 stem | 期待音素 | 期待 found |
|---|--------|------|----------|---------|-----------|
| 1 | -tion 検出 | `"station"` | `"sta"` | `[ɧ, uː, n]` | `true` |
| 2 | -ssion 検出 | `"passion"` | `"pa"` | `[ɧ, uː, n]` | `true` |
| 3 | -sion 検出 | `"vision"` | `"vi"` | `[ɧ, uː, n]` | `true` |
| 4 | -age 検出 | `"garage"` | `"gar"` | `[ɑː, ɧ]` | `true` |
| 5 | -age ネイティブ除外 | `"mage"` | `""` | `nil` | `false` |
| 6 | -age ネイティブ除外 | `"hage"` | `""` | `nil` | `false` |
| 7 | -eur 検出 | `"friseur"` | `"fris"` | `[øː, r]` | `true` |
| 8 | -eum 検出 | `"museum"` | `"mus"` | `[eː, ɵ, m]` | `true` |
| 9 | -ium 検出 | `"stadium"` | `"stad"` | `[ɪ, ɵ, m]` | `true` |
| 10 | 接尾辞のみ (ステムなし) | `"tion"` | `""` | `nil` | `false` |
| 11 | 該当なし | `"hund"` | `""` | `nil` | `false` |

### 4.3 Unitテスト

```go
func TestSvDetectLoanwordSuffix(t *testing.T) {
    tests := []struct {
        word      string
        wantStem  string
        wantFound bool
        wantPh    []string // nil if not found
    }{
        {"station", "sta", true, []string{"\u0267", "u\u02d0", "n"}},
        {"passion", "pa", true, []string{"\u0267", "u\u02d0", "n"}},
        {"garage", "gar", true, []string{"\u0251\u02d0", "\u0267"}},
        {"mage", "", false, nil},   // AGE_NATIVE_WORDS
        {"hage", "", false, nil},   // AGE_NATIVE_WORDS
        {"museum", "mus", true, []string{"e\u02d0", "\u0275", "m"}},
        {"stadium", "stad", true, []string{"\u026a", "\u0275", "m"}},
        {"friseur", "fris", true, []string{"\u00f8\u02d0", "r"}},
        {"hund", "", false, nil},   // 該当なし
        {"tion", "", false, nil},   // ステムなし (len(word) == len(suffix))
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            stem, ph, found := svDetectLoanwordSuffix(tt.word)
            if found != tt.wantFound {
                t.Fatalf("svDetectLoanwordSuffix(%q) found=%v, want %v", tt.word, found, tt.wantFound)
            }
            if stem != tt.wantStem {
                t.Errorf("stem = %q, want %q", stem, tt.wantStem)
            }
            // 音素列の一致検証
        })
    }
}
```

### 4.4 E2Eテスト

本チケット単独での E2E テストは不要。T-M2-05 で `station` → `s t a ɧ uː n` の完全パイプラインをテストする。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **テーブル順序の重要性**: `ssion` (5文字) は `sion` (4文字) より先にチェックする必要がある。`passion` が `-ssion` にマッチすべきだが、順序が逆だと `-sion` にマッチして `pas` ではなく `pas` + `s` がステムになる (ステムが `pass` になってしまう)。テーブル順序のテストを追加すること。
2. **`-age` のネイティブ例外**: `svAgeNativeWords` のリストは Python 参照実装と完全一致している必要がある。M1 で定義済みだが、抜け漏れがないかクロスチェック必須。
3. **語長チェック**: `len(word) > len(rule.suffix)` の条件は文字列長 (バイト数) で比較。スウェーデン語の接尾辞は全て ASCII なのでバイト長 == ルーン長で問題ない。

### 5.2 レビューチェックリスト

- [ ] 7 接尾辞全ての音素列が Python `_LOANWORD_SUFFIX_RULES` と完全一致
- [ ] テーブル順序が長い接尾辞優先 (ssion > tion > sion > age > eur > eum > ium)
- [ ] `-age` + `svAgeNativeWords` の除外が動作
- [ ] ステムが空の場合 (word == suffix) は `false` を返す
- [ ] 3 値返却 (stem, phonemes, found) のシグネチャが Go イディオム準拠
- [ ] `go build ./phonemize/...` 成功

## 6. 一から作り直すとしたら

- 規則テーブルを `map[string][]string` にする手もあるが、マッチ順序を保証するためにスライスが適切。Python 参照実装もタプルのスライスで順序を保持している。
- 3 値返却の代わりに `*svLoanwordResult` (struct pointer, nil if not found) パターンも検討したが、Go のイディオムとしてはシンプルな多値返却が好まれる。既存の Go コード (ES `esG2P` の `stressPhIdx = -1` パターン) に倣った。

## 7. 後続タスクへの連絡事項

- **T-M2-05 (統合):** `svDetectLoanwordSuffix` が `true` を返した場合、ステム部分のみを `svConvertWordNative` で変換し、接尾辞の音素列を結合する。ストレス位置はステムの音節数で調整する (Python `_phonemize_word` 参照)。
- **音素内の長母音 (`uː`, `ɑː`, `øː`, `eː`)**: これらは PUA マッピング対象 (`MapSequence` で変換)。T-M2-05 で `MapSequence` を呼び出す前に結合すること。
- **`ssion` vs `tion` のステム差異**: `passion` のステムは `pa` (ssion で 2 文字消費)、`station` のステムは `sta` (tion で 3 文字消費)。ステム G2P の入力が異なることに注意。
