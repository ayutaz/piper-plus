# T-M2-04: 母音長判定 (Complementary Quantity)

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M2: G2Pコアエンジン |
| 依存チケット | T-M2-01 (構造体 + トークン化), M1 (定数定義: 母音マッピング表, 例外語リスト) |
| 後続チケット | T-M2-05 (単語G2P統合で `svGetVowelPhoneme` を呼び出す) |
| 対象ファイル | `src/go/phonemize/swedish.go` (追記) |
| 推定行数 | ~120行 |

## 1. タスク目的とゴール

スウェーデン語の母音長は Complementary Quantity (相補的量) 規則に基づく: ストレスのある音節では「長母音+短子音」または「短母音+長子音 (ジェミネート/クラスタ)」のいずれかになる。本チケットでは 5 段階の優先度判定と例外規則を実装し、各母音文字を正しい長/短 IPA 音素に変換する。

**完了時の状態:**
- `svGetVowelPhoneme()` が全 10 母音文字 (a, e, i, o, u, y, å, ä, ö) の長/短を正しく判定
- 5 段階優先度 (非ストレス→機能語→FINAL_M→子音数→デフォルト) が実装済み
- "o" の `O_LONG_AS_OO` 例外、r+C 例外が動作
- Python 参照実装 `get_vowel_phoneme()` と同等の動作

## 2. 実装する内容の詳細

### 2.1 母音マッピング表 (M1 で定義済み)

**長母音:**

| 文字 | 長母音 IPA | Unicode | PUA |
|---|---|---|---|
| a | ɑː | `\u0251\u02d0` | 0xE05E |
| e | eː | `e\u02d0` | 0xE05B |
| i | iː | `i\u02d0` | 0xE059 |
| o (デフォルト) | uː | `u\u02d0` | 0xE060 |
| o (O_LONG_AS_OO) | oː | `o\u02d0` | 0xE05F |
| u | ʉː | `\u0289\u02d0` | 0xE061 |
| y | yː | `y\u02d0` | 0xE05A |
| å | oː | `o\u02d0` | 0xE05F |
| ä | ɛː | `\u025b\u02d0` | 0xE05C |
| ö | øː | `\u00f8\u02d0` | 0xE05D |

**短母音:**

| 文字 | 短母音 IPA | Unicode |
|---|---|---|
| a | a | `a` |
| e | ɛ | `\u025b` |
| i | ɪ | `\u026a` |
| o | ɔ | `\u0254` |
| u | ɵ | `\u0275` |
| y | ʏ | `\u028f` |
| å | ɔ | `\u0254` |
| ä | ɛ | `\u025b` |
| ö | œ | `\u0153` |

### 2.2 後続子音カウント関数

```go
// svCountFollowingConsonants counts consecutive consonant characters after pos.
func svCountFollowingConsonants(word []rune, pos int) int {
    count := 0
    i := pos + 1
    for i < len(word) && svConsonants[word[i]] {
        count++
        i++
    }
    return count
}
```

Python 参照: `_count_following_consonants(word, pos)`

### 2.3 母音長判定関数

```go
// svGetVowelPhoneme determines the vowel phoneme (long or short) at position pos.
// Implements Complementary Quantity rules.
// Parameters:
//   - word: the word as rune slice (for position-based access)
//   - pos: position of the vowel character
//   - fullWord: complete word string (for exception list lookup)
//   - isStressed: whether this syllable carries primary stress
func svGetVowelPhoneme(word []rune, pos int, fullWord string, isStressed bool) string
```

### 2.4 5段階優先度フロー

```
1. 非ストレス音節 → 短母音
2. 機能語 (FUNCTION_WORDS) → 短母音
3. FINAL_M_SHORT_WORDS に該当 → 短母音
4. 後続子音数カウント:
   a. 語末 (子音0個, pos == len(word)-1) → 長母音
   b. r + 語末 → 長母音
   c. r + 単一子音 ("o" 除外) → 長母音
   d. 子音2個以上 (ジェミネート/クラスタ) → 短母音
   e. 単一子音 → 長母音
```

**完全な実装:**

```go
func svGetVowelPhoneme(word []rune, pos int, fullWord string, isStressed bool) string {
    ch := word[pos]

    // 1. 非ストレス → 短母音
    if !isStressed {
        return svShortVowelMap[ch]
    }

    // 2. 機能語 → 短母音
    if svFunctionWords[fullWord] {
        return svShortVowelMap[ch]
    }

    // 3. FINAL_M 例外 → 短母音
    if svFinalMShortWords[fullWord] {
        return svShortVowelMap[ch]
    }

    // 4. 後続子音数で判定
    nFollowing := svCountFollowingConsonants(word, pos)

    // 4a. 語末母音 (子音0個) → 長母音
    if nFollowing == 0 && pos == len(word)-1 {
        return svLongVowel(ch, fullWord)
    }

    // 4b+4c. r + 単一子音例外: 母音は長 (r がレトロフレックスに吸収されるため)
    // ただし "o" は除外 (kort=/ɔ/ vs bord=/uː/ の曖昧性)
    if nFollowing == 2 && ch != 'o' && pos+1 < len(word) && word[pos+1] == 'r' {
        return svLongVowel(ch, fullWord)
    }

    // 4d. ジェミネート / クラスタ (2+子音) → 短母音
    if nFollowing >= 2 {
        return svShortVowelMap[ch]
    }

    // 4e. 単一子音 → 長母音
    return svLongVowel(ch, fullWord)
}

// svLongVowel returns the long vowel IPA for ch, with O_LONG_AS_OO check.
func svLongVowel(ch rune, fullWord string) string {
    if ch == 'o' && svOLongAsOO[fullWord] {
        return "o\u02d0"  // oː
    }
    return svLongVowelMap[ch]
}
```

### 2.5 "o" の曖昧性 (O_LONG_AS_OO)

スウェーデン語の "o" は長母音のデフォルトが /uː/ (例: sol → suːl) だが、`O_LONG_AS_OO` リストの語では /oː/ (例: son → soːn) になる。

M1 で定義済み:
```go
var svOLongAsOO = map[string]bool{
    "son": true, "mor": true, "bror": true, "lov": true, "dom": true,
    "ton": true, "zon": true, "fon": true, "ion": true, "ko": true,
    "lo": true, "ro": true, "tro": true, "bo": true, "god": true,
    "jord": true, "ord": true, "kol": true, "pol": true, "kontroll": true,
    "roll": true, "mol": true, "fot": true, "rot": true, "blod": true,
    "flod": true, "mod": true, "nod": true, "rod": true, "tog": true,
}
```

### 2.6 r+C 例外の詳細

母音 + r + 単一子音のパターンでは、r が後続子音とレトロフレックスに同化するため、母音にとっては実質的に「単一子音」と同等の環境になる。結果として母音は長母音を保つ。

**例:**
- `barn`: a + r + n → `nFollowing=2`, `word[pos+1]='r'` → 長母音 ɑː (4c適用)
- `kort`: o + r + t → `nFollowing=2`, `ch='o'` → **除外** → 短母音 ɔ (4d適用)
- `park`: a + r + k → `nFollowing=2`, `word[pos+1]='r'` → しかし `nFollowing` は r 含めて 2 なので 4b+4c 条件: `nFollowing == 2 && ch != 'o' && word[pos+1] == 'r'` → 長母音 ɑː

**注意:** `nFollowing == 2` かつ `word[pos+1] == 'r'` は「母音の直後が r で、その後にもう 1 子音がある」パターン。r が後の子音と同化して実質 1 子音になるため、母音は長を保つ。

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装エージェント | `svGetVowelPhoneme`, `svCountFollowingConsonants`, `svLongVowel` の実装 | 1 |
| 2 | レビューエージェント | 5段階優先度の正しさ、Python参照実装との一致、エッジケース検証 | 1 |

**合計: 2 エージェント**

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svGetVowelPhoneme()` 関数
- `svCountFollowingConsonants()` ヘルパー
- `svLongVowel()` ヘルパー (O_LONG_AS_OO チェック付き)

**含まない:**
- 母音マッピング表 (`svLongVowelMap`, `svShortVowelMap`) の定義 (M1)
- 例外語リスト (`svFunctionWords`, `svFinalMShortWords`, `svOLongAsOO`) の定義 (M1)
- 子音変換 (T-M2-03)
- 統合ループでのストレス音節判定 (T-M2-05)

### 4.2 テスト項目

**長母音テスト (全10母音):**

| # | 単語 | 母音位置 | isStressed | 期待 | 備考 |
|---|------|---------|-----------|------|------|
| 1 | gata | 0 (a) | true | ɑː | 単一子音→長 |
| 2 | hel | 0 (e) | true | eː | 単一子音→長 |
| 3 | fin | 0 (i) | true | iː | 単一子音→長 |
| 4 | sol | 0 (o) | true | uː | デフォルト長o |
| 5 | son | 0 (o) | true | oː | O_LONG_AS_OO |
| 6 | hus | 0 (u) | true | ʉː | 単一子音→長 |
| 7 | by | 0 (y) | true | yː | 語末→長 |
| 8 | gå | 0 (å) | true | oː | 語末→長 |
| 9 | bär | 0 (ä) | true | ɛː | 単一子音→長 |
| 10 | öl | 0 (ö) | true | øː | 単一子音→長 |

**短母音テスト:**

| # | 単語 | 母音位置 | isStressed | 期待 | 備考 |
|---|------|---------|-----------|------|------|
| 11 | katt | 0 (a) | true | a | 2子音(tt)→短 |
| 12 | fest | 0 (e) | true | ɛ | 2子音(st)→短 |
| 13 | fisk | 0 (i) | true | ɪ | 2子音(sk)→短 |
| 14 | ost | 0 (o) | true | ɔ | 2子音(st)→短 |
| 15 | full | 0 (u) | true | ɵ | 2子音(ll)→短 |
| 16 | bygg | 0 (y) | true | ʏ | 2子音(gg)→短 |

**特殊ケーステスト:**

| # | テスト | 入力 | 期待 | 備考 |
|---|--------|------|------|------|
| 17 | 非ストレス→短 | isStressed=false, 'a' | a | 優先度1 |
| 18 | 機能語→短 | fullWord="jag", 'a' | a | 優先度2 |
| 19 | FINAL_M→短 | fullWord="hem", 'e' | ɛ | 優先度3 |
| 20 | r+C例外→長 | `barn` pos=0 ('a') | ɑː | r+n → 長保持 |
| 21 | r+C例外 o除外→短 | `kort` pos=0 ('o') | ɔ | o は r+C除外 |
| 22 | 語末母音→長 | `ko` pos=0 ('o') | oː | O_LONG_AS_OO + 語末 |

### 4.3 Unitテスト

```go
func TestSvGetVowelPhoneme_Long(t *testing.T) {
    tests := []struct {
        word       string
        pos        int
        fullWord   string
        isStressed bool
        want       string
    }{
        {"gata", 0, "gata", true, "\u0251\u02d0"},   // ɑː
        {"hel", 0, "hel", true, "e\u02d0"},           // eː
        {"fin", 0, "fin", true, "i\u02d0"},           // iː
        {"sol", 0, "sol", true, "u\u02d0"},           // uː (デフォルト)
        {"son", 0, "son", true, "o\u02d0"},           // oː (O_LONG_AS_OO)
        {"hus", 0, "hus", true, "\u0289\u02d0"},      // ʉː
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            runes := []rune(tt.word)
            got := svGetVowelPhoneme(runes, tt.pos, tt.fullWord, tt.isStressed)
            if got != tt.want {
                t.Errorf("svGetVowelPhoneme(%q, %d, %q, %v) = %q, want %q",
                    tt.word, tt.pos, tt.fullWord, tt.isStressed, got, tt.want)
            }
        })
    }
}

func TestSvGetVowelPhoneme_Short(t *testing.T) {
    tests := []struct {
        word       string
        pos        int
        fullWord   string
        isStressed bool
        want       string
    }{
        {"katt", 0, "katt", true, "a"},        // 2子音→短
        {"fest", 0, "fest", true, "\u025b"},    // ɛ
        {"jag", 0, "jag", false, "a"},          // 非ストレス→短
        {"hem", 0, "hem", true, "\u025b"},      // FINAL_M→短
    }
    // ...
}

func TestSvCountFollowingConsonants(t *testing.T) {
    tests := []struct {
        word string
        pos  int
        want int
    }{
        {"katt", 0, 2},  // a→tt
        {"gata", 0, 1},  // a→t
        {"ko", 0, 0},    // o→語末
        {"barn", 0, 2},  // a→rn
    }
    // ...
}
```

### 4.4 E2Eテスト

本チケット単独での E2E テストは限定的。T-M2-05 で `gata` → `ɡ ɑː t a` (子音+母音統合) をテストする。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **`[]rune` パラメータ**: `svGetVowelPhoneme` は `[]rune` を受け取る設計。T-M2-05 の統合ループで `[]rune(word)` 変換が必要。FR/ES/PT では `string` の `[]rune` を都度変換しているが、SV では統合ループの冒頭で 1 回だけ変換し使い回す方が効率的。
2. **`svCountFollowingConsonants` とマルチバイト文字**: 子音セット (`svConsonants`) は全て ASCII なのでルーン判定で問題ない。母音 (å, ä, ö) は子音セットに含まれないため自然に停止する。
3. **r+C 例外と `nFollowing == 2` の条件**: Python 参照実装は `n_following == 2 and ch != "o" and pos + 1 < len(word) and word[pos + 1] == "r"` で判定。Go も同じ条件。`nFollowing == 2` は「母音の後に正確に 2 子音」ではなく「少なくとも 2 子音」と読めるが、Python コードでは `count_following_consonants` が連続子音数を返すため、`== 2` は「正確に 2 子音」。ただし `>= 2` で先に短母音判定 (4d) が来るため、`== 2` は `>= 2` の前でチェックされる必要がある (実際の順序を確認)。
4. **`svLongVowelMap` のデフォルト値**: マッピングに存在しない文字が渡された場合のフォールバック。Python は `.get(ch, ch)` でフォールバック。Go では `map` のゼロ値は空文字列になるため、存在チェックが必要。

### 5.2 レビューチェックリスト

- [ ] 全 10 母音文字の長/短マッピングが Python `_LONG_VOWEL_MAP` / `_SHORT_VOWEL_MAP` と一致
- [ ] 5 段階優先度の順序が Python `get_vowel_phoneme` と一致
- [ ] `O_LONG_AS_OO` チェックが長母音判定の全箇所 (4a, 4b/4c, 4e) で適用
- [ ] r+C 例外の "o" 除外が実装されている
- [ ] `FINAL_M_SHORT_WORDS` チェックが機能語チェックの後に来る
- [ ] `svCountFollowingConsonants` が母音で停止する
- [ ] マッピングに存在しない文字のフォールバック処理
- [ ] `go build ./phonemize/...` 成功

## 6. 一から作り直すとしたら

- 母音長判定の 5 段階を関数チェインではなく、判定テーブル + 優先度ソートで表現する方法もある。しかし各段階の条件が異質 (bool フラグ, リスト検索, 子音カウント) なため、手続き的な if-chain が最もシンプル。
- `svGetVowelPhoneme` のパラメータが多い (word, pos, fullWord, isStressed)。構造体にまとめる設計もあるが、Python 参照実装に合わせて関数パラメータにする方が移植しやすい。

## 7. 後続タスクへの連絡事項

- **T-M2-05 (統合):** `svGetVowelPhoneme` を呼び出す際の `isStressed` フラグは、ストレス検出 (M3 `detect_stress`) の結果と現在の音節インデックスから決定する。M3 未実装時点では暫定的に `isStressed=true` (第 1 音節) とするか、M2 レベルで簡易ストレス判定を組み込む。Python 参照実装では `_convert_word_native` が `stressed_syl` パラメータを受け取り、音節カウンタと比較している。
- **音素列内の長母音文字列**: `ɑː`, `eː` 等は 2 文字 (base + ː) だが、`MapSequence` で PUA 単一コードポイントに変換される。T-M2-05 で `MapSequence` を呼び出す前は 2 文字のまま保持すること。
- **`nFollowing == 2` と `ck` の関係:** T-M2-03 で `ck` は消費 2 文字だが、`svCountFollowingConsonants` は文字列レベルで子音を数える。`ck` は 2 文字の子音として数えられるため、直前の母音は自動的に短母音判定 (4d) される。
