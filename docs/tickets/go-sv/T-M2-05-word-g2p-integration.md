# T-M2-05: 単語G2P統合

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M2: G2Pコアエンジン |
| 依存チケット | T-M2-01 (構造体 + トークン化), T-M2-02 (ローンワード), T-M2-03 (子音変換), T-M2-04 (母音長判定) |
| 後続チケット | M3 (レトロフレックス同化 + ストレス検出 + PhonemizeWithProsody 統合) |
| 対象ファイル | `src/go/phonemize/swedish.go` (追記) |
| 推定行数 | ~150行 |

## 1. タスク目的とゴール

T-M2-02〜04 で実装した個別関数を組み合わせ、単語テキストから IPA 音素列を生成する統合パイプラインを完成させる。本チケットは M2 の最終チケットであり、M3 で追加されるレトロフレックス同化・ストレスマーカー挿入の手前までをカバーする。

**完了時の状態:**
- `svConvertWordNative()` が子音変換 + 母音長判定を組み合わせて単語全体を音素列に変換
- `svPhonemizeWord()` がローンワード検出 → ネイティブ G2P のパイプラインを実行
- 代表的な単語で正しい IPA 音素列を生成 (M3 のレトロフレックス・ストレスは未適用)
- `go build ./phonemize/...` が成功

## 2. 実装する内容の詳細

### 2.1 ネイティブ G2P 統合ループ (svConvertWordNative)

文字を左から右へ走査し、母音なら `svGetVowelPhoneme` (T-M2-04)、子音なら `svConvertConsonant` (T-M2-03) を呼び出す。

```go
// svConvertWordNative converts a word using native Swedish G2P rules.
// Processes characters left-to-right, applying consonant rules and
// vowel length (Complementary Quantity).
// Parameters:
//   - word: the word string (normalized, lowercase)
//   - fullWord: complete word for exception list lookup
//   - stressedSyl: index of stressed syllable (0-based, -1 for no stress)
func svConvertWordNative(word string, fullWord string, stressedSyl int) []string {
    runes := []rune(word)
    n := len(runes)
    var phonemes []string
    pos := 0
    sylCount := 0
    prevWasVowel := false

    for pos < n {
        ch := runes[pos]

        if svAllVowels[ch] {
            if !prevWasVowel {
                isStressed := sylCount == stressedSyl && stressedSyl >= 0
                vowel := svGetVowelPhoneme(runes, pos, fullWord, isStressed)
                phonemes = append(phonemes, vowel)
                sylCount++
            } else {
                // 連続母音 (スウェーデン語では稀): 短母音として処理
                vowel := svShortVowelMap[ch]
                phonemes = append(phonemes, vowel)
            }
            prevWasVowel = true
            pos++

        } else if svConsonants[ch] {
            prevWasVowel = false
            ipaList, consumed := svConvertConsonant(word, pos, fullWord)
            phonemes = append(phonemes, ipaList...)
            pos += consumed

        } else {
            // 未知文字: スキップ
            prevWasVowel = false
            pos++
        }
    }

    return phonemes
}
```

**Python 参照実装との対応:** `_convert_word_native(word, full_word, stressed_syl)`

**重要ポイント:**
- `sylCount` は母音クラスタ (連続母音) を 1 音節としてカウント (`prevWasVowel` フラグ)
- `svConvertConsonant` は `(word string, pos int, fullWord string)` を受け取るため、`word` は string のまま渡す (内部で `[]rune` 変換)
- `svGetVowelPhoneme` は `(word []rune, pos int, fullWord string, isStressed bool)` を受け取る

### 2.2 ストレス判定の暫定対応

M3 で `detectStress()` (5段階優先度) が実装されるが、M2 時点では以下の簡易版を使用する。

```go
// svSimpleStress は M2 時点の簡易ストレス判定。
// M3 で本格的な detectStress() に置き換えられる。
func svSimpleStress(word string) int {
    if svFunctionWords[word] {
        return -1  // ストレスなし
    }
    return 0  // デフォルト: 第1音節
}
```

**注意:** この簡易版は M3 で `detectStress()` に完全置換される。多音節語のストレス吸引接尾辞 (`-tion` 等) や非ストレスプレフィックス (`för-` 等) は M3 で対応。

### 2.3 音節カウント関数

M3 のストレス検出でも使用されるため、ここで実装する。

```go
// svCountSyllables counts syllables by counting vowel clusters.
func svCountSyllables(word string) int {
    count := 0
    prevVowel := false
    for _, ch := range word {
        if svAllVowels[ch] {
            if !prevVowel {
                count++
            }
            prevVowel = true
        } else {
            prevVowel = false
        }
    }
    if count == 0 {
        return 1
    }
    return count
}
```

Python 参照: `_count_syllables(word)`

### 2.4 単語G2Pパイプライン (svPhonemizeWord)

```go
// svPhonemizeWord is the full G2P pipeline for a single word.
// Pipeline:
//   1. Stress detection (simplified in M2, full in M3)
//   2. Loanword suffix detection
//   3. Native G2P conversion
//   Note: Retroflex assimilation and stress marker insertion are added in M3.
func svPhonemizeWord(word string) []string {
    if word == "" {
        return nil
    }

    // 1. ストレス検出
    stressedSyl := svSimpleStress(word)

    // 2. ローンワード接尾辞チェック
    stem, suffixPhonemes, found := svDetectLoanwordSuffix(word)
    if found {
        // ステムの音節数計算 → ステム内のストレス位置調整
        stemSylCount := svCountSyllables(stem)
        stemStress := stressedSyl
        if stressedSyl >= stemSylCount {
            stemStress = -1  // ストレスは接尾辞側にある → ステムは非ストレス
        }
        // ステム部分のみネイティブ G2P
        stemPhonemes := svConvertWordNative(stem, word, stemStress)
        // ステム + 接尾辞音素を結合
        return append(stemPhonemes, suffixPhonemes...)
    }

    // 3. ネイティブ G2P
    return svConvertWordNative(word, word, stressedSyl)
}
```

**Python 参照実装との対応:** `_phonemize_word(word)`

### 2.5 パイプラインフロー図

```
svPhonemizeWord("station")
  │
  ├─ svSimpleStress("station") → 0 (M2簡易版, M3で→1に修正)
  │
  ├─ svDetectLoanwordSuffix("station")
  │    → ("sta", [ɧ, uː, n], true)
  │
  ├─ svCountSyllables("sta") → 1
  │    stressedSyl=0 < stemSylCount=1 → stemStress=0
  │
  ├─ svConvertWordNative("sta", "station", 0)
  │    → [s, t, ɑː]
  │
  └─ result: [s, t, ɑː, ɧ, uː, n]
     (M3 でレトロフレックス + ストレスマーカー追加後: [ˈs, t, ɑː, ɧ, uː, n])
```

```
svPhonemizeWord("gata")
  │
  ├─ svSimpleStress("gata") → 0
  │
  ├─ svDetectLoanwordSuffix("gata") → not found
  │
  ├─ svConvertWordNative("gata", "gata", 0)
  │    pos=0: g → svConvertConsonant → [ɡ], 1
  │    pos=1: a → svGetVowelPhoneme(stressed, 1 following C) → ɑː
  │    pos=2: t → svConvertConsonant → [t], 1
  │    pos=3: a → svGetVowelPhoneme(unstressed) → a
  │
  └─ result: [ɡ, ɑː, t, a]
```

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装エージェント | `svConvertWordNative` 統合ループ、`svPhonemizeWord` パイプライン、`svSimpleStress`、`svCountSyllables` | 1 |
| 2 | テストエージェント | 代表的単語のE2Eテスト、ローンワード統合テスト、エッジケーステスト | 1 |
| 3 | レビューエージェント | Python参照実装とのパイプライン一致検証、T-M2-02〜04との連携確認 | 1 |

**合計: 3 エージェント**

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svConvertWordNative()` 関数 (子音+母音の統合ループ)
- `svPhonemizeWord()` 関数 (ローンワード→ネイティブ G2P パイプライン)
- `svSimpleStress()` 関数 (M2 暫定版)
- `svCountSyllables()` 関数

**含まない:**
- `PhonemizeWithProsody` メソッド (M3 で実装)
- レトロフレックス同化 (M3)
- ストレスマーカー挿入 (M3)
- 完全な `detectStress()` (M3)
- `Phonemizer` インターフェース準拠 (M3)
- PUA マッピング (`MapSequence`) の呼び出し (M3)

### 4.2 テスト項目

**基本単語 (子音+母音統合):**

| # | 入力 | 期待音素列 | 備考 |
|---|------|----------|------|
| 1 | `gata` | ɡ ɑː t a | 長母音 + 非ストレス末尾 |
| 2 | `katt` | k a t | 短母音 (tt→1消費+前の子音カウント) |
| 3 | `hus` | h ʉː s | 長u |
| 4 | `sol` | s uː l | デフォルト長o |
| 5 | `son` | s oː n | O_LONG_AS_OO |
| 6 | `fin` | f iː n | 長i |
| 7 | `by` | b yː | 語末長y |
| 8 | `öl` | øː l | 長ö |

**子音規則統合:**

| # | 入力 | 期待に含む音素 | 備考 |
|---|------|-------------|------|
| 9 | `sked` | ɧ eː d | sk+前舌母音 |
| 10 | `skola` | s k uː l a | sk+後舌母音 |
| 11 | `köp` | ɕ øː p | soft k |
| 12 | `flicka` | f l ɪ k a | hard k (HARD_K_WORDS) |
| 13 | `sjuk` | ɧ ʉː k | sj |
| 14 | `tjugo` | ɕ ʉː ɡ uː | tj (M2簡易ストレスでは2つ目のuも長になる可能性あり) |
| 15 | `kung` | k ɵ ŋ | ng + 短u |

**ローンワード統合:**

| # | 入力 | 期待音素列 | 備考 |
|---|------|----------|------|
| 16 | `station` | s t ɑː ɧ uː n | -tion ローンワード |
| 17 | `passion` | p a ɧ uː n | -ssion ローンワード |
| 18 | `garage` | ɡ ɑː r ɑː ɧ | -age ローンワード |
| 19 | `museum` | m ʉː s eː ɵ m | -eum ローンワード |
| 20 | `mage` | m ɑː ɡ ɛ | AGE_NATIVE (ローンワードでない) |

**エッジケース:**

| # | 入力 | 期待 | 備考 |
|---|------|------|------|
| 21 | `""` | nil | 空文字列 |
| 22 | `"a"` | [ɑː] | 単一母音 (語末→長) |
| 23 | `"t"` | [t] | 単一子音 |
| 24 | `"och"` | [ɔ, k] | 機能語 + ch例外 (全母音短) |

### 4.3 Unitテスト

```go
func TestSvPhonemizeWord(t *testing.T) {
    tests := []struct {
        word string
        want []string
    }{
        {"gata", []string{"\u0261", "\u0251\u02d0", "t", "a"}},
        {"katt", []string{"k", "a", "t"}},
        {"hus", []string{"h", "\u0289\u02d0", "s"}},
        {"son", []string{"s", "o\u02d0", "n"}},
        {"sked", []string{"\u0267", "e\u02d0", "d"}},
        {"flicka", []string{"f", "l", "\u026a", "k", "a"}},
        {"station", []string{"s", "t", "\u0251\u02d0", "\u0267", "u\u02d0", "n"}},
        {"mage", []string{"m", "\u0251\u02d0", "\u0261", "\u025b"}},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            got := svPhonemizeWord(tt.word)
            if len(got) != len(tt.want) {
                t.Fatalf("svPhonemizeWord(%q) = %v (len %d), want %v (len %d)",
                    tt.word, got, len(got), tt.want, len(tt.want))
            }
            for i := range tt.want {
                if got[i] != tt.want[i] {
                    t.Errorf("[%d] = %q, want %q", i, got[i], tt.want[i])
                }
            }
        })
    }
}

func TestSvConvertWordNative(t *testing.T) {
    // svPhonemizeWord 経由でない直接テスト
    got := svConvertWordNative("gata", "gata", 0)
    // ɡ ɑː t a
    if len(got) != 4 {
        t.Fatalf("len = %d, want 4", len(got))
    }
}

func TestSvCountSyllables(t *testing.T) {
    tests := []struct {
        word string
        want int
    }{
        {"gata", 2},
        {"katt", 1},
        {"station", 2},
        {"universitet", 5},
        {"t", 1},  // min 1
        {"", 1},   // min 1
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            got := svCountSyllables(tt.word)
            if got != tt.want {
                t.Errorf("svCountSyllables(%q) = %d, want %d", tt.word, got, tt.want)
            }
        })
    }
}
```

### 4.4 E2Eテスト

M2 完了基準として、以下の代表ケースで正しい音素列を生成:

```go
func TestSvM2CompletionCriteria(t *testing.T) {
    // マイルストーンドキュメントの完了基準から
    tests := []struct {
        word    string
        wantPh  string // 含まれるべき部分文字列 (IPA)
    }{
        {"gata", "\u0251\u02d0"},    // ɑː (長母音)
        {"katt", "a"},               // 短母音 (tt)
        {"sked", "\u0267"},          // ɧ (sk+前舌母音)
        {"flicka", "k"},             // hard k
        {"station", "\u0267"},       // ɧ (ローンワード -tion)
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            got := svPhonemizeWord(tt.word)
            joined := strings.Join(got, "")
            if !strings.Contains(joined, tt.wantPh) {
                t.Errorf("svPhonemizeWord(%q) = %v, want containing %q", tt.word, got, tt.wantPh)
            }
        })
    }
}
```

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **`svConvertConsonant` への `string` vs `[]rune` 渡し**: `svConvertWordNative` は `[]rune` でループを回すが、`svConvertConsonant` は `string` と `int pos` を受け取る設計 (T-M2-03)。`string` のインデックスはバイト位置であり、`[]rune` のインデックスとずれる。解決策: (a) `svConvertConsonant` も `[]rune` を受け取るように変更、(b) ルーン位置からバイト位置への変換関数を用意。(a) を推奨。T-M2-03 の実装時に `[]rune` ベースにすることを連携。
2. **M2 簡易ストレスの限界**: `svSimpleStress` は第 1 音節をストレスとするため、多音節語のストレス位置が不正確。`station` のストレスは本来第 2 音節 (-tion) だが、M2 では第 1 音節 (sta) にストレスがかかる。これにより母音長判定が一部不正確になるが、M3 で修正される。
3. **ローンワードステムのストレス調整**: `svPhonemizeWord` でローンワードのステム部分のストレス位置を調整するロジックが、M2 簡易ストレスでは十分に機能しない可能性がある。M3 の `detectStress` がストレス吸引接尾辞を考慮するため、M3 統合後にローンワードのストレス処理を最終検証する必要がある。
4. **`katt` の `tt` 処理**: `svConvertConsonant` は `t` を 1 文字消費で `["t"]` を返す。`tt` は 2 回の `t` 呼び出しになるが、`svCountFollowingConsonants` は `tt` を 2 子音としてカウントするため、直前の母音は正しく短母音になる。ただし出力に `t` が 2 回出現する。Python 参照実装も同じ動作 (ジェミネートの音素的実現は `ck` のような特殊パターンのみ)。

### 5.2 レビューチェックリスト

- [ ] `svConvertWordNative` が左→右走査で母音/子音を正しく振り分け
- [ ] 音節カウンタ (`sylCount`) が母音クラスタを 1 音節としてカウント
- [ ] `svPhonemizeWord` のローンワードパイプラインが正しい: stem G2P + suffix phonemes
- [ ] ローンワードステムのストレス位置調整が Python `_phonemize_word` と一致
- [ ] `svCountSyllables` が最小値 1 を返す (子音のみの「単語」)
- [ ] 空文字列入力で nil/空スライスを返す
- [ ] M2 完了基準の 5 単語テストが全て PASS
- [ ] `go build ./phonemize/...` 成功
- [ ] `go vet ./phonemize/...` エラーなし

## 6. 一から作り直すとしたら

- `svConvertWordNative` のループは Python 参照実装の直訳。Go らしくするなら、母音処理と子音処理をそれぞれメソッドに分離し、`svWordConverter` 構造体に状態 (pos, sylCount, prevWasVowel) を持たせる設計もある。しかし Python との 1:1 対応を維持する方が移植の正確性が高いため、手続き的アプローチが妥当。
- M2 時点で暫定 `svSimpleStress` を入れるか、ストレス関連を全て M3 に持ち越すかは判断が分かれる。前者の方が M2 単体でのテストがしやすいため採用した。

## 7. 後続タスクへの連絡事項

- **M3 (レトロフレックス):** `svPhonemizeWord` の戻り値 (音素列) を `svApplyRetroflex()` に渡す。レトロフレックスは単語内でのみ適用 (単語境界を跨がない)。M3 で `svPhonemizeWord` の最後に `apply_retroflex` 呼び出しを追加する。
- **M3 (ストレス):** `svSimpleStress` を `detectStress` に置き換える。`svPhonemizeWord` 内の呼び出し箇所を差し替えるだけで済む設計。
- **M3 (ストレスマーカー):** `svPhonemizeWord` の戻り値 (レトロフレックス適用済み) に `_insert_stress_marker()` を適用。
- **M3 (PhonemizeWithProsody):** `svTokenize` (T-M2-01) でテキストをトークン化 → 単語ごとに `svPhonemizeWord` → Prosody 情報を構築 → `MapSequence` → `PhonemizeResult` を返却。FR/ES/PT の `PhonemizeWithProsody` パターンに従う。
- **パラメータの `[]rune` 統一**: T-M2-03 (`svConvertConsonant`) と T-M2-04 (`svGetVowelPhoneme`) で `string` と `[]rune` が混在している可能性がある。本チケットの統合ループで不整合が見つかった場合は、T-M2-03/04 の関数シグネチャを `[]rune` に統一する修正を行う。
