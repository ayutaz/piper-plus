# T-M2-03: 子音変換エンジン

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M2: G2Pコアエンジン |
| 依存チケット | T-M2-01 (構造体 + トークン化), M1 (定数定義: 例外語リスト, 子音マッピング) |
| 後続チケット | T-M2-05 (単語G2P統合で `svConvertConsonant` を呼び出す) |
| 対象ファイル | `src/go/phonemize/swedish.go` (追記) |
| 推定行数 | ~250行 |

## 1. タスク目的とゴール

スウェーデン語の子音変換は 3 段階の最長一致優先度で動作する。3 文字パターン (5 個) → 2 文字パターン (~20 個) → 1 文字パターン (コンテキスト依存分岐含む) を左から右へ走査し、各位置で最長マッチする規則を適用する。k/g の軟硬分岐では例外語リストと語幹チェックが必要。

**完了時の状態:**
- `svConvertConsonant()` が全子音パターンを正しく変換
- `isHardK()` / `isHardG()` が例外語・語幹チェックを実装
- Python 参照実装 `_convert_consonant()` と同等の動作

## 2. 実装する内容の詳細

### 2.1 関数シグネチャ

```go
// svConvertConsonant converts consonant(s) starting at pos in word.
// Returns (ipaPhonemes, charsConsumed).
// fullWord is the complete word (for exception list lookup).
func svConvertConsonant(word string, pos int, fullWord string) ([]string, int)
```

Python 参照: `_convert_consonant(word, pos, full_word) -> tuple[list[str], int]`

### 2.2 3文字パターン (最優先, 5個)

| # | パターン | 出力 | Unicode |
|---|---------|------|---------|
| 1 | `skj` | ɧ | `["\u0267"]` |
| 2 | `stj` | ɧ | `["\u0267"]` |
| 3 | `sch` | ɧ | `["\u0267"]` |
| 4 | `sng` | s + n | `["s", "n"]` |
| 5 | `ckj` | ɕ | `["\u0255"]` |

```go
if remaining >= 3 {
    tri := string(runes[pos : pos+3])
    switch tri {
    case "skj":
        return []string{"\u0267"}, 3
    case "stj":
        return []string{"\u0267"}, 3
    case "sch":
        return []string{"\u0267"}, 3
    case "sng":
        return []string{"s", "n"}, 3
    case "ckj":
        return []string{"\u0255"}, 3
    }
}
```

### 2.3 2文字パターン (~20個)

| # | パターン | 出力 | 条件 |
|---|---------|------|------|
| 1 | `sk` | ɧ `["\u0267"]` | 次文字が前舌母音 (e,i,y,ä,ö) かつ `svSKBackVowelExceptions` でない |
| 2 | `sk` | s + k `["s","k"]` | 次文字が後舌母音 / 子音 / 語末 |
| 3 | `sk` | ɧ `["\u0267"]` | `svSKBackVowelExceptions` に該当 (människa, marskalk) |
| 4 | `sj` | ɧ `["\u0267"]` | 常に |
| 5 | `sh` | ɧ `["\u0267"]` | 常に (外来語) |
| 6 | `ch` | ɧ `["\u0267"]` | デフォルト |
| 7 | `ch` | k `["k"]` | `svCHExceptionsK` に該当 (och, kristus, krist, kron, kronik) |
| 8 | `ph` | f `["f"]` | 常に (外来語) |
| 9 | `th` | t `["t"]` | 常に (外来語) |
| 10 | `tj` | ɕ `["\u0255"]` | 常に |
| 11 | `kj` | ɕ `["\u0255"]` | 常に |
| 12 | `gn` | ɡ + n `["\u0261","n"]` | 語頭 (pos == 0) |
| 13 | `gn` | ŋ + n `["\u014b","n"]` | 語中 (pos > 0) |
| 14 | `ng` | ŋ `["\u014b"]` | 常に |
| 15 | `nk` | ŋ + k `["\u014b","k"]` | 常に |
| 16 | `ck` | k `["k"]` | 常に (ジェミネートマーカー) |
| 17 | `gj` | j `["j"]` | 語頭のみ (pos == 0) |
| 18 | `lj` | j `["j"]` | 語頭のみ (pos == 0) |
| 19 | `dj` | j `["j"]` | 語頭のみ (pos == 0) |
| 20 | `hj` | j `["j"]` | 語頭のみ (pos == 0) |

**`sk` のコンテキスト依存ロジック:**

```go
if di == "sk" {
    if remaining >= 3 {
        nextCh := runes[pos+2]
        if svFrontVowels[nextCh] && !svSKBackVowelExceptions[fullWord] {
            return []string{"\u0267"}, 2  // ɧ
        }
    }
    // sk + 後舌母音 / 子音 / 語末 → /sk/
    // ただし例外語チェック
    if svSKBackVowelExceptions[fullWord] {
        return []string{"\u0267"}, 2
    }
    return []string{"s", "k"}, 2
}
```

**`gj`/`lj`/`dj`/`hj` 語頭限定の注意:** Python 参照実装では語頭でない場合はフォールスルーし、1 文字パターンで処理される。Go でも同様に、`pos == 0` でない場合は 2 文字パターンをスキップする。

### 2.4 1文字パターン (コンテキスト依存)

**k + 前舌母音:**

```go
if ch == 'k' && pos+1 < n && svFrontVowels[runes[pos+1]] {
    if isHardK(fullWord) {
        return []string{"k"}, 1
    }
    return []string{"\u0255"}, 1  // ɕ (soft k)
}
```

**g + 前舌母音:**

```go
if ch == 'g' && pos+1 < n && svFrontVowels[runes[pos+1]] {
    if isHardG(fullWord) {
        return []string{"\u0261"}, 1  // ɡ (hard g)
    }
    return []string{"j"}, 1  // soft g
}
```

**g + その他 (後舌母音 / 子音 / 語末):**

```go
if ch == 'g' {
    return []string{"\u0261"}, 1  // ɡ
}
```

**c + 前舌母音 (e, i):**

```go
if ch == 'c' && pos+1 < n && (runes[pos+1] == 'e' || runes[pos+1] == 'i') {
    return []string{"s"}, 1
}
if ch == 'c' {
    return []string{"k"}, 1
}
```

**x → k + s:**

```go
if ch == 'x' {
    return []string{"k", "s"}, 1
}
```

**デフォルト子音マッピング (M1 で定義済み):**

```go
// svConsonantDefault (M1 定義)
var svConsonantDefault = map[rune]string{
    'b': "b", 'd': "d", 'f': "f", 'h': "h", 'j': "j",
    'l': "l", 'm': "m", 'n': "n", 'p': "p", 'r': "r",
    's': "s", 't': "t", 'v': "v", 'w': "v", 'z': "s",
}
```

```go
if ipa, ok := svConsonantDefault[ch]; ok {
    return []string{ipa}, 1
}
// 未知の子音: そのまま出力
return []string{string(ch)}, 1
```

### 2.5 例外語チェック関数

```go
// isHardK checks if k in this word is hard /k/ before a front vowel.
func isHardK(word string) bool {
    if svHardKWords[word] {
        return true
    }
    // 形態論ヒューリスティック: 語尾を1-3文字剥がして語幹辞書と照合
    runes := []rune(word)
    for suffixLen := 3; suffixLen >= 1; suffixLen-- {
        if len(runes) > suffixLen {
            stem := string(runes[:len(runes)-suffixLen])
            if svHardKStems[stem] {
                return true
            }
        }
    }
    return false
}

// isHardG checks if g in this word is hard /ɡ/ before a front vowel.
func isHardG(word string) bool {
    if svHardGWords[word] {
        return true
    }
    // -era verb heuristic: -era/-erar/-erade は通常ハード g
    if strings.HasSuffix(word, "era") || strings.HasSuffix(word, "erar") || strings.HasSuffix(word, "erade") {
        return true
    }
    runes := []rune(word)
    for suffixLen := 3; suffixLen >= 1; suffixLen-- {
        if len(runes) > suffixLen {
            stem := string(runes[:len(runes)-suffixLen])
            if svHardGStems[stem] {
                return true
            }
        }
    }
    return false
}
```

**Python 参照実装との対応:**

| Python | Go |
|---|---|
| `_is_hard_k(word)` | `isHardK(word string) bool` |
| `_is_hard_g(word)` | `isHardG(word string) bool` |
| `word in HARD_K_WORDS` | `svHardKWords[word]` |
| `stem in HARD_K_STEMS` | `svHardKStems[stem]` |
| `word.endswith(("era", "erar", "erade"))` | `strings.HasSuffix(word, "era") \|\| ...` |

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装エージェント | `svConvertConsonant` の 3 段階パターンマッチ、k/g 分岐、デフォルト処理 | 1 |
| 2 | 例外語エージェント | `isHardK` / `isHardG` の実装、語幹ストリッピングロジック、`-era` ヒューリスティック | 1 |
| 3 | レビューエージェント | Python 参照実装との全パターン照合、エッジケース検証 | 1 |

**合計: 3 エージェント**

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svConvertConsonant()` 関数 (3 段階優先度)
- `isHardK()` / `isHardG()` 例外語チェック関数
- 2 文字パターンの全コンテキスト依存分岐 (sk, ch, gn, gj/lj/dj/hj)
- 1 文字パターンの k/g 軟硬分岐、c/x 特殊処理

**含まない:**
- 母音処理 (T-M2-04)
- 例外語リスト自体の定義 (M1 で定義済み)
- レトロフレックス同化 (M3)
- 子音変換結果と母音結果の統合 (T-M2-05)

### 4.2 テスト項目

**3 文字パターン:**

| # | テスト | 入力 (word, pos) | 期待出力 | 期待消費 |
|---|--------|-----------------|---------|---------|
| 1 | skj | `("skjorta", 0)` | `["ɧ"]` | 3 |
| 2 | stj | `("stjärna", 0)` | `["ɧ"]` | 3 |
| 3 | sch | `("schema", 0)` | `["ɧ"]` | 3 |
| 4 | sng | `("sng...", 0)` | `["s","n"]` | 3 |
| 5 | ckj | `("ackja", 2)` | `["ɕ"]` | 3 |

**2 文字パターン:**

| # | テスト | 入力 | 期待出力 | 備考 |
|---|--------|------|---------|------|
| 6 | sk+前舌母音 | `("sked", 0)` | `["ɧ"]`, 2 | sk+e → ɧ |
| 7 | sk+後舌母音 | `("skola", 0)` | `["s","k"]`, 2 | sk+o → sk |
| 8 | sk+例外 | `("människa", 4)` fullWord=`"människa"` | `["ɧ"]`, 2 | SK_BACK_VOWEL_EXCEPTIONS |
| 9 | sj | `("sjuk", 0)` | `["ɧ"]`, 2 | |
| 10 | ch デフォルト | `("chans", 0)` | `["ɧ"]`, 2 | |
| 11 | ch 例外 | `("och", 0)` fullWord=`"och"` | `["k"]`, 2 | CH_EXCEPTIONS_K |
| 12 | tj | `("tjugo", 0)` | `["ɕ"]`, 2 | |
| 13 | ng | `("kung", 2)` | `["ŋ"]`, 2 | |
| 14 | nk | `("tänka", 2)` | `["ŋ","k"]`, 2 | |
| 15 | ck | `("flicka", 3)` | `["k"]`, 2 | |
| 16 | gn 語頭 | `("gnaga", 0)` | `["ɡ","n"]`, 2 | |
| 17 | gn 語中 | `("vagn", 2)` | `["ŋ","n"]`, 2 | |
| 18 | gj 語頭 | `("gjord", 0)` | `["j"]`, 2 | |
| 19 | lj 語頭 | `("ljus", 0)` | `["j"]`, 2 | |

**1 文字パターン (k/g 分岐):**

| # | テスト | 入力 | 期待出力 | 備考 |
|---|--------|------|---------|------|
| 20 | k+前舌母音 (soft) | `("köp", 0)` fullWord=`"köp"` | `["ɕ"]`, 1 | |
| 21 | k+前舌母音 (hard) | `("flicka", 4)` fullWord=`"flicka"` | `["k"]`, 1 | HARD_K_WORDS |
| 22 | k+後舌母音 | `("katt", 0)` | デフォルト `"k"`, 1 | |
| 23 | g+前舌母音 (soft) | `("göra", 0)` fullWord=`"göra"` | `["j"]`, 1 | |
| 24 | g+前舌母音 (hard) | `("ge", 0)` fullWord=`"ge"` | `["ɡ"]`, 1 | HARD_G_WORDS |
| 25 | c+e | `("center", 0)` | `["s"]`, 1 | |
| 26 | c+a | `("cafe", 0)` | `["k"]`, 1 | |
| 27 | x | `("extra", 1)` | `["k","s"]`, 1 | |

**例外語チェック:**

| # | テスト | 関数 | 入力 | 期待 |
|---|--------|------|------|------|
| 28 | HARD_K_WORDS 完全一致 | `isHardK` | `"flicka"` | `true` |
| 29 | HARD_K_STEMS 語幹 | `isHardK` | `"leker"` | `true` (stem `lek`) |
| 30 | 非ハードK | `isHardK` | `"köp"` | `false` |
| 31 | HARD_G_WORDS 完全一致 | `isHardG` | `"ge"` | `true` |
| 32 | -era ヒューリスティック | `isHardG` | `"navigera"` | `true` |
| 33 | HARD_G_STEMS 語幹 | `isHardG` | `"lägger"` | `true` (stem `lägg`) |
| 34 | 非ハードG | `isHardG` | `"göra"` | `false` |

### 4.3 Unitテスト

```go
func TestSvConvertConsonant_ThreeChar(t *testing.T) {
    tests := []struct {
        word     string
        pos      int
        fullWord string
        wantPh   []string
        wantN    int
    }{
        {"skjorta", 0, "skjorta", []string{"\u0267"}, 3},
        {"stjärna", 0, "stjärna", []string{"\u0267"}, 3},
        {"schema", 0, "schema", []string{"\u0267"}, 3},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            ph, n := svConvertConsonant(tt.word, tt.pos, tt.fullWord)
            // 検証
        })
    }
}

func TestIsHardK(t *testing.T) {
    tests := []struct {
        word string
        want bool
    }{
        {"flicka", true},
        {"leker", true},   // stem "lek"
        {"köp", false},
        {"keps", true},    // HARD_K_WORDS
        {"socker", true},  // HARD_K_WORDS
    }
    // ...
}
```

### 4.4 E2Eテスト

本チケット単独での E2E テストは不要。T-M2-05 で `sked` → `ɧ eː d` (子音+母音の統合) をテストする。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **`[]rune` vs `string` のインデックス**: `svConvertConsonant` は `string` と `int pos` を受け取るが、スウェーデン語特殊文字 (å, ä, ö) はマルチバイト。`[]rune` に変換してからインデックスアクセスすること。Python は文字列を直接インデックスできるが、Go では `runes := []rune(word)` が必須。
2. **`gj`/`lj`/`dj`/`hj` のフォールスルー**: 語頭でない場合に 2 文字パターンがスキップされ、1 文字パターンに入る。`g` は前舌母音コンテキストで軟化し得るので、フォールスルー先の処理が正しいか確認が必要。
3. **`sk` + `SK_BACK_VOWEL_EXCEPTIONS` の優先度**: `människa` は `sk` の後に `a` (後舌母音) が来るが例外的に `/ɧ/` になる。通常の sk+後舌母音 = `/sk/` のルートより先に例外チェックが入ること。Python 参照実装のロジックでは前舌母音チェック分岐の中で例外チェックを行っているが、Go 実装では `svSKBackVowelExceptions` チェックを別途追加する必要がある。

### 5.2 レビューチェックリスト

- [ ] 3 文字パターン 5 個が全て実装されている
- [ ] 2 文字パターン ~20 個が全て実装されている
- [ ] `sk` の 3 分岐 (前舌母音/後舌母音/例外) が正しい
- [ ] `ch` の例外チェック (`svCHExceptionsK`) が動作
- [ ] `gn` の語頭/語中分岐が正しい
- [ ] `gj`/`lj`/`dj`/`hj` が語頭のみで動作 (語中ではフォールスルー)
- [ ] k/g 軟硬分岐が `svFrontVowels` をチェック
- [ ] `isHardK` の語幹チェック (1-3 文字剥がし) が Python と一致
- [ ] `isHardG` の `-era` ヒューリスティックが実装されている
- [ ] `c+e/i → s`, `c+other → k` が正しい
- [ ] `x → k+s` が消費文字数 1 (2 ではない)
- [ ] 全出力の Unicode コードポイントが Python 参照実装と一致
- [ ] `go build ./phonemize/...` 成功

## 6. 一から作り直すとしたら

- Python 参照実装の `_convert_consonant` は `if`-`if`-`if` の長い関数 (~130行) で、Go でも同じ構造になる。テーブル駆動にできれば可読性が上がるが、各パターンの条件が異なる (pos==0, コンテキスト母音, 例外語) ため手続き的な if-chain が妥当。
- `isHardK` / `isHardG` の語幹チェックは 1-3 文字剥がしの固定長ヒューリスティックだが、接尾辞リストを指定できるようにすればより柔軟。ただし Python 参照実装に合わせて同じアプローチにする。

## 7. 後続タスクへの連絡事項

- **T-M2-05 (統合):** `svConvertConsonant` は `([]string, int)` を返す。統合ループでは `pos += consumed` で進めること。
- **M3 (レトロフレックス):** `svConvertConsonant` の出力に `"r"` が含まれる場合、後続の `"t"`, `"d"`, `"s"`, `"n"`, `"l"` と合わせてレトロフレックスに変換する。子音変換の段階では `"r"` はそのまま出力される。
- **`ck` の母音長への影響:** `ck` は消費 2 文字で `["k"]` を返すが、直前の母音は短母音になる。これは T-M2-04 (母音長判定) の `_count_following_consonants` で `ck` が 2 子音としてカウントされることで自動的に処理される。ただし `svConvertConsonant` が 2 文字を消費するため、統合ループの文字位置管理に注意。
- **`fullWord` パラメータ**: 例外語チェック (`isHardK`, `isHardG`, `svSKBackVowelExceptions`, `svCHExceptionsK`) は完全な単語で照合する。ローンワードのステム部分のみが渡された場合は例外語にマッチしない可能性があるが、Python 参照実装も同じ動作なので許容。
