# T-M3-02: ストレス検出 + マーカー挿入

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M3: 後処理 + Phonemizer統合 |
| 依存チケット | T-M2 (G2Pコアエンジン — `svCountSyllables` 等で使用する母音定数が定義済みであること), T-M3-01 (レトロフレックス同化 — パイプライン順序上、レトロフレックス後にストレスマーカー挿入) |
| 後続チケット | T-M3-03 (PhonemizeWithProsody統合) |
| 対象ファイル | `src/go/phonemize/swedish.go` |
| 推定行数 | ~150行 (`svCountSyllables` + `svDetectStress` + `svIsIPAVowel` + `svInsertStressMarker`) |

## 1. タスク目的とゴール

スウェーデン語テキストの単語に対してストレス (強勢) の音節位置を検出し、音素列の適切な位置にストレスマーカー `ˈ` (U+02C8) を挿入する3つの関数を実装する。

**ゴール:**
- `svCountSyllables(word string) int` — 母音クラスタカウントによる音節数推定
- `svDetectStress(word string) int` — 5段階優先規則によるストレス音節位置検出
- `svInsertStressMarker(phonemes []string, stressSyl int) []string` — ストレスマーカーの正確な挿入
- Python (`detect_stress`, `_count_syllables`, `_insert_stress_marker`) / Rust (`detect_stress`, `count_syllables`, `insert_stress_marker`) と同一の出力

## 2. 実装する内容の詳細

### 2.1 音節カウント: `svCountSyllables`

母音文字の連続クラスタを1音節とカウントする。結果は最低1を返す。

```go
// svCountSyllables counts syllables by counting vowel clusters in a word.
// Returns at least 1.
func svCountSyllables(word string) int {
    count := 0
    prevVowel := false
    for _, ch := range word {
        if svAllVowels[ch] { // M1で定義済みの母音集合
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

**母音集合 (M1で定義済み):** `svAllVowels = {a, e, i, o, u, y, å, ä, ö}`

| 入力 | 音節数 | 説明 |
|---|---|---|
| `hus` | 1 | 母音1つ |
| `gata` | 2 | a...a で2クラスタ |
| `station` | 2 | a...io (ioは隣接母音で1クラスタ) |
| `förståelse` | 4 | ö...å...e...e |
| `b` | 1 | 母音なし → 最低1 |

### 2.2 ストレス検出: `svDetectStress`

5段階の優先規則で主ストレスの音節位置 (0-based) を返す。`-1` はストレスなし (機能語)。

```go
// svDetectStress detects the primary stress syllable index (0-based).
// Returns -1 for function words (no stress).
func svDetectStress(word string) int
```

#### 判定フローの全パターン

```
優先度1: 機能語チェック
  ├─ word ∈ svFunctionWords → return -1
  │
  ▼
優先度2: 単音節チェック
  ├─ svCountSyllables(word) <= 1 → return 0
  │
  ▼
優先度3: ストレス吸引接尾辞チェック (18パターン、長い順)
  ├─ word が接尾辞で終わる AND len(word) > len(suffix)
  │   → return svCountSyllables(word[:stemLen])
  │     (= 接尾辞直前の音節、つまり接尾辞の先頭音節にストレス)
  │
  ▼
優先度4: 非ストレスプレフィックスチェック (5パターン)
  ├─ word が prefix で始まる AND len(word) > len(prefix)+1
  │   → return 1 (第2音節)
  │
  ▼
優先度5: デフォルト
  └─ return 0 (第1音節)
```

#### ストレス吸引接尾辞 (18個)

長い接尾辞から順にチェックする (最長一致):

```go
var svStressAttractingSuffixes = []string{
    "ssion", "tion", "sion", "itet",
    "eri", "era", "ist", "ör",
    "ment", "ans", "ens", "ell",
    "ent", "ant", "ik", "ur", "al", "ös",
}
```

| 接尾辞 | 例 | ストレス音節 |
|---|---|---|
| -tion | station (sta\|tion) | 1 (staの音節数=1) |
| -itet | universitet (univer\|sitet) | 3 |
| -eri | bageri (bag\|eri) | 1 |
| -era | reagera (reag\|era) | 2 |
| -ist | pianist (pian\|ist) | 2 |
| -ment | instrument (instru\|ment) | 2 |
| -ik | musik (mus\|ik) | 1 |

#### 非ストレスプレフィックス (5個)

```go
var svUnstressedPrefixes = []string{
    "för", "be", "ge", "er", "an",
}
```

| プレフィックス | 例 | ストレス音節 |
|---|---|---|
| för- | förstå | 1 (第2音節) |
| be- | betala | 1 |
| ge- | gestalt | 1 |
| er- | erkänna | 1 |
| an- | anmäla | 1 |

**注意:** `len(word) > len(prefix)+1` の条件により、プレフィックスだけの短い語 (例: "be") はデフォルト規則に落ちる。

#### 機能語リスト (M1で定義済み、~35語)

```
jag, du, han, hon, vi, de, dem, den, det, sig, sin, min, din,
av, i, på, för, med, om, till, från, hos, ur,
och, men, att, som, när, var, en, ett, är, har, kan, ska, vill, inte
```

#### 全パターン対応表

| 入力 | 優先度 | 返値 | 理由 |
|---|---|---|---|
| `och` | 1 (機能語) | -1 | `svFunctionWords` に含まれる |
| `att` | 1 (機能語) | -1 | 同上 |
| `hus` | 2 (単音節) | 0 | 1音節 |
| `katt` | 2 (単音節) | 0 | 1音節 |
| `station` | 3 (接尾辞 -tion) | 1 | sta=1音節 |
| `bageri` | 3 (接尾辞 -eri) | 1 | bag=1音節 |
| `musik` | 3 (接尾辞 -ik) | 1 | mus=1音節 |
| `förstå` | 4 (プレフィックス för-) | 1 | 第2音節 |
| `betala` | 4 (プレフィックス be-) | 1 | 第2音節 |
| `gata` | 5 (デフォルト) | 0 | 第1音節 |
| `flicka` | 5 (デフォルト) | 0 | 第1音節 |

### 2.3 IPA母音判定: `svIsIPAVowel`

ストレスマーカー挿入時に音素列中の母音を識別するためのヘルパー。

```go
// svIsIPAVowel checks if a phoneme string contains a vowel character.
func svIsIPAVowel(ph string) bool
```

判定対象の母音文字集合 (Python `_is_ipa_vowel` / Rust `is_ipa_vowel_str` と同一):

```
基本母音: a, e, i, o, u, y, å, ä, ö
IPA母音:  ɑ (U+0251), ɛ (U+025B), ɪ (U+026A), ɔ (U+0254),
          ʊ (U+028A), ʉ (U+0289), ʏ (U+028F), œ (U+0153),
          ø (U+00F8), ɵ (U+0275)
```

音素文字列中のいずれかのruneがこの集合に含まれれば `true` を返す。これにより長母音 (`"ɑː"`) も正しく母音と判定される。

### 2.4 ストレスマーカー挿入: `svInsertStressMarker`

レトロフレックス同化済みの音素列に対し、ストレス位置にマーカーを挿入する。

```go
// svInsertStressMarker inserts ˈ (U+02C8) before the onset of the stressed syllable.
// stressSyl < 0 means no stress (function word) → returns phonemes unchanged.
func svInsertStressMarker(phonemes []string, stressSyl int) []string
```

#### 挿入アルゴリズム

```
Step 1: ターゲット音節の最初の母音を見つける
  - 音素列を先頭から走査
  - 母音クラスタの開始をカウント (prevWasVowel で重複防止)
  - カウントが stressSyl に達したら、そのインデックスを vowelIdx とする
  - 見つからなければ → 音素列をそのまま返す

Step 2: 音節のオンセット (子音開始位置) を見つける
  - vowelIdx から後方に走査
  - 母音でない音素がある限り onsetIdx を後退
  - stressSyl == 0 の場合、onsetIdx = 0 (先頭から)

Step 3: onsetIdx の位置に "ˈ" を挿入
```

#### 挿入例

| 音素列 (レトロフレックス後) | stressSyl | 挿入位置 | 結果 |
|---|---|---|---|
| `[ɡ, ɑː, t, a]` (gata) | 0 | 0 (先頭) | `[ˈ, ɡ, ɑː, t, a]` |
| `[s, t, a, ɧ, uː, n]` (station) | 1 | 3 (ɧの前) | `[s, t, a, ˈ, ɧ, uː, n]` |
| `[b, ɑː, ɳ]` (barn) | 0 | 0 (先頭) | `[ˈ, b, ɑː, ɳ]` |
| `[ɔ, k]` (och, 機能語) | -1 | - | `[ɔ, k]` (変更なし) |

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装担当 | `svCountSyllables`, `svDetectStress`, `svIsIPAVowel`, `svInsertStressMarker` の4関数実装 + `svStressAttractingSuffixes`, `svUnstressedPrefixes` 定数定義 (M1の `svFunctionWords` は定義済み前提) | 1 |

**合計: 1 エージェント**

4関数は相互依存が直列的 (カウント→検出→判定→挿入) だが、いずれも小規模なため1名で順次実装可能。

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svCountSyllables(word string) int`
- `svDetectStress(word string) int`
- `svIsIPAVowel(ph string) bool`
- `svInsertStressMarker(phonemes []string, stressSyl int) []string`
- `svStressAttractingSuffixes` 定数 (18エントリ)
- `svUnstressedPrefixes` 定数 (5エントリ)
- IPA母音判定用の `svIPAVowelSet` 定数

**含まない:**
- `svFunctionWords` 定数 (M1で定義済み)
- `PhonemizeWithProsody` 統合 (T-M3-03)
- テストファイル作成 (M4)

### 4.2 テスト項目

| # | カテゴリ | 件数 | 内容 |
|---|---------|------|------|
| 1 | 音節カウント | 5 | 1音節/2音節/3音節/母音連続/母音なし |
| 2 | 機能語 (-1) | 3 | och, att, jag |
| 3 | 単音節 (0) | 3 | hus, katt, fin |
| 4 | 吸引接尾辞 | 4 | station(1), bageri(1), musik(1), universitet(3) |
| 5 | 非ストレスプレフィックス | 3 | förstå(1), betala(1), erkänna(1) |
| 6 | デフォルト (0) | 3 | gata(0), flicka(0), sommar(0) |
| 7 | マーカー挿入 | 5 | 第1音節/第2音節/機能語(挿入なし)/空音素列/母音見つからず |
| 8 | IPA母音判定 | 4 | 長母音/短母音/子音/ストレスマーカー |

### 4.3 Unitテスト

```go
func TestSvCountSyllables(t *testing.T) {
    tests := []struct {
        word string
        want int
    }{
        {"hus", 1},
        {"gata", 2},
        {"station", 2},     // a + io (隣接母音=1クラスタ)
        {"förståelse", 4},
        {"b", 1},            // 母音なし → 最低1
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            if got := svCountSyllables(tt.word); got != tt.want {
                t.Errorf("svCountSyllables(%q) = %d, want %d", tt.word, got, tt.want)
            }
        })
    }
}

func TestSvDetectStress(t *testing.T) {
    tests := []struct {
        word string
        want int
    }{
        // 優先度1: 機能語
        {"och", -1},
        {"att", -1},
        {"jag", -1},
        // 優先度2: 単音節
        {"hus", 0},
        {"katt", 0},
        {"fin", 0},
        // 優先度3: 吸引接尾辞
        {"station", 1},   // sta=1音節
        {"bageri", 1},     // bag=1音節
        {"musik", 1},      // mus=1音節
        // 優先度4: プレフィックス
        {"förstå", 1},
        {"betala", 1},
        // 優先度5: デフォルト
        {"gata", 0},
        {"flicka", 0},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            if got := svDetectStress(tt.word); got != tt.want {
                t.Errorf("svDetectStress(%q) = %d, want %d", tt.word, got, tt.want)
            }
        })
    }
}

func TestSvInsertStressMarker(t *testing.T) {
    tests := []struct {
        name      string
        phonemes  []string
        stressSyl int
        wantFirst string // 期待する先頭/挿入位置の音素
    }{
        {"syl0", []string{"ɡ", "ɑː", "t", "a"}, 0, "ˈ"},
        {"syl1", []string{"s", "t", "a", "ɧ", "uː", "n"}, 1, "s"}, // ˈ は index 3
        {"no stress", []string{"ɔ", "k"}, -1, "ɔ"},
        {"empty", []string{}, 0, ""},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := svInsertStressMarker(tt.phonemes, tt.stressSyl)
            if tt.wantFirst != "" && len(got) > 0 && got[0] != tt.wantFirst {
                t.Errorf("first element = %q, want %q (full: %v)", got[0], tt.wantFirst, got)
            }
        })
    }
}
```

### 4.4 E2Eテスト

E2Eテストは T-M3-03 完了後にM4で実施。代表例:

| 入力テキスト | 期待出力パターン |
|---|---|
| `hus` | `ˈ` が先頭 |
| `station` | `ˈ` が第2音節オンセット前 |
| `och` | `ˈ` なし (機能語) |
| `förstå` | `ˈ` が第2音節オンセット前 |
| `gata` | `ˈ` が先頭 |

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **音節カウントの精度**: 母音クラスタ方式は近似であり、二重母音 (`oi`, `au` 等) や外来語で実際の音節数と乖離する場合がある。Python/Rust参照実装と同じ方式を採用しており、G2P全体の精度目標 (>=95%) を達成するには十分。
2. **接尾辞チェック順序**: `svStressAttractingSuffixes` は長い接尾辞から順にチェックする必要がある (例: `ssion` は `sion` より先)。現在の定義順は長→短の暗黙順序だが、明示的にソートするか、コメントで注意喚起する。
3. **プレフィックスの `len(word) > len(prefix)+1` 条件**: この条件は `"be"` のような2文字語がプレフィックスルールに誤マッチしないための安全策。Python/Rustと同一の条件。
4. **オンセット後退の範囲**: `stressSyl == 0` のとき `onsetIdx = 0` とする特殊処理が必要。それ以外は前の母音との間の子音群がオンセットとなる。Python/Rustと同一のロジック。

### 5.2 レビューチェックリスト

- [ ] `svStressAttractingSuffixes` の18エントリが Python `STRESS_ATTRACTING_SUFFIXES` と完全一致
- [ ] `svUnstressedPrefixes` の5エントリが Python `UNSTRESSED_PREFIXES` と完全一致
- [ ] `svDetectStress` の5段階優先順序が正しい (機能語→単音節→接尾辞→プレフィックス→デフォルト)
- [ ] `svCountSyllables` が母音なし語で最低1を返す
- [ ] `svIsIPAVowel` の母音文字集合が Python `_is_ipa_vowel` / Rust `is_ipa_vowel_str` と一致
- [ ] `svInsertStressMarker` の `stressSyl < 0` で音素列を変更せず返す
- [ ] `stressSyl == 0` のとき `onsetIdx = 0` (先頭に挿入)
- [ ] 接尾辞チェックで `len(word) > len(suffix)` (接尾辞だけの語を除外)
- [ ] プレフィックスチェックで `len(word) > len(prefix)+1` (短い語を除外)
- [ ] `go vet ./phonemize/...` エラーなし

## 6. 一から作り直すとしたら

- **音節カウントの改善**: 母音クラスタ方式ではなく、onset-nucleus-coda パーサーを使えば精度が上がるが、参照実装との互換性を優先して現方式を採用。将来改善する場合はこの関数のみ差し替えれば全体に反映される。
- **接尾辞/プレフィックスの外部設定化**: 現在はハードコードだが、JSON/YAML設定ファイルから読み込む方式にすれば言語学者が直接編集可能になる。ただし Go のパッケージ初期化パターン的にはハードコードが最もシンプル。
- **ストレスマーカーの種類拡張**: 現在は一次ストレス `ˈ` のみだが、二次ストレス `ˌ` (U+02CC) への拡張も `StressLevel` 型 (Python では `IntEnum`) を導入すれば容易。Go では `iota` 定数で同様に表現可能。

## 7. 後続タスクへの連絡事項

- **T-M3-03 (PhonemizeWithProsody) への連絡**: ストレス検出とマーカー挿入は `svPhonemizeWord` 関数内で呼ばれる。パイプライン:
  1. `svDetectStress(word)` → `stressSyl`
  2. G2P変換 (ローンワード or ネイティブ)
  3. `svApplyRetroflex(rawPhonemes)` (T-M3-01)
  4. `svInsertStressMarker(phonemes, stressSyl)` (本チケット)
  T-M3-03 では `svPhonemizeWord` を統合する際にこの呼び出し順序を守ること。
- **T-M3-03 への追加連絡 (Prosody構築)**: ストレスマーカー `"ˈ"` は Prosody の A2 値に影響する。`PhonemizeWithProsody` では各音素の A2 を以下の規則で設定:
  - `"ˈ"` → A2=2 (primary stress)
  - それ以外 → A2=0
  - A3 (単語音素数) のカウントでは `"ˈ"` を除外する
- **M4 (テストスイート) への連絡**: ストレス検出のテストは ~15件を予定。特に接尾辞+プレフィックスの複合ケース (例: `förändring` = för+ändr+ing) や、接尾辞リストの境界ケースが重要。
