# Go スウェーデン語 G2P 実装計画

> **対象 PR**: #270 (`feat/go-bindings`)
> **参照**: `docs/design/swedish-g2p-impl-spec.md` (全プラットフォーム共通仕様)
> **作成日**: 2026-03-31

---

## 1. 概要

最新の dev ブランチ (PR #297) により、スウェーデン語 G2P が Python/C#/Rust/C++/npm の全プラットフォームに実装済み。Go 側のみ未実装のため、既存の Go 言語実装パターンに従い移植する。

### 対応状況

| プラットフォーム | 実装行数 | テスト数 | 状態 |
|---|---|---|---|
| Python | 1,257行 | 129+ | 完了 (参照実装) |
| Rust | 2,819行 | 91 | 完了 |
| C# | 1,182行 | 39+ | 完了 |
| C++ | 1,087行 | 26 | 完了 |
| npm | 言語検出のみ | 385行 | 完了 |
| **Go** | **0行** | **0** | **未実装** |

---

## 2. アーキテクチャ

### 2.1 パイプライン (全プラットフォーム共通)

```
テキスト入力
  │
  ▼
[Stage 1] 正規化 — NFC + 小文字化
  │
  ▼
[Stage 2] トークン化 — 単語/句読点に分割
  │
  ▼
[Stage 3] ストレス検出 — 音節位置の決定
  │
  ▼
[Stage 4] G2P変換 (単語ごと)
  │  ├─ ローンワード接尾辞検出 → 接尾辞は固定音素
  │  ├─ 子音変換 (3文字→2文字→1文字の優先度)
  │  └─ 母音長判定 (Complementary Quantity)
  │
  ▼
[Stage 5] レトロフレックス同化 — r+{t,d,s,n,l} → 反舌音
  │
  ▼
[Stage 6] ストレスマーカー挿入 — ˈ (U+02C8)
  │
  ▼
[Stage 7] PUA マッピング — MapSequence() で多文字→単一コードポイント
  │
  ▼
PhonemizeResult {Tokens, Prosody, EOSToken}
```

### 2.2 Go 側のインターフェース準拠

```go
// 既存インターフェース (phonemizer.go)
type Phonemizer interface {
    PhonemizeWithProsody(text string) (*PhonemizeResult, error)
    LanguageCode() string
}

// SwedishPhonemizer が実装すべきもの
type SwedishPhonemizer struct{}

func NewSwedishPhonemizer() *SwedishPhonemizer
func (p *SwedishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error)
func (p *SwedishPhonemizer) LanguageCode() string  // → "sv"
```

### 2.3 Prosody マッピング

| フィールド | 値 | 説明 |
|---|---|---|
| A1 | 常に 0 | スウェーデン語では未使用 |
| A2 | 0 or 2 | 0=非ストレス, 2=主ストレス |
| A3 | int | 単語内の音素数 (ストレスマーカー除外) |

---

## 3. 音素インベントリ

### 3.1 スウェーデン語固有音素 (19個)

#### 単一コードポイント (10個, PUA不要)

| 音素 | Unicode | 説明 |
|---|---|---|
| ɖ | U+0256 | 反舌有声破裂音 (rd) |
| ʈ | U+0288 | 反舌無声破裂音 (rt) |
| ɳ | U+0273 | 反舌鼻音 (rn) |
| ɭ | U+026D | 反舌側面音 (rl) |
| ɧ | U+0267 | sj音 (無声背口蓋摩擦音) |
| ɵ | U+0275 | 半狭中舌円唇母音 (短u) |
| ʏ | U+028F | 準狭前舌円唇母音 (短y) |
| œ | U+0153 | 半広前舌円唇母音 (短ö) |
| ɑ | U+0251 | 広後舌非円唇母音 (短a系) |
| ø | U+00F8 | 半狭前舌円唇母音 (短ö系) |

#### 長母音 (9個, PUA必須)

| 音素 | PUA | IPA表記 |
|---|---|---|
| iː | 0xE059 | 長i |
| yː | 0xE05A | 長y |
| eː | 0xE05B | 長e |
| ɛː | 0xE05C | 長ä |
| øː | 0xE05D | 長ö |
| ɑː | 0xE05E | 長a |
| oː | 0xE05F | 長å/長o |
| uː | 0xE060 | 長o (デフォルト) |
| ʉː | 0xE061 | 長u |

### 3.2 PUA 割り当て全体図

```
0xE000-0xE01C  Japanese (29)
0xE01D-0xE01E  Multilingual shared (2): rr, y_vowel
0xE020-0xE04A  Chinese (43)
0xE04B-0xE052  Korean (8)
0xE054-0xE055  Spanish/Portuguese (2): tʃ, dʒ
0xE056-0xE058  French (3): ɛ̃, ɑ̃, ɔ̃
0xE059-0xE061  Swedish (9): iː, yː, eː, ɛː, øː, ɑː, oː, uː, ʉː  ← 新規追加
0xE062-0xE063  予約枠
0xE064+        動的割り当て (nextDynamic)
```

---

## 4. 子音変換規則

### 4.1 3文字パターン (最優先)

| パターン | 出力 | 備考 |
|---|---|---|
| skj | ɧ | sj音 |
| stj | ɧ | sj音 |
| sch | ɧ | sj音 |
| sng | s + n | ngの分離 |
| ckj | ɕ | tj音 |

### 4.2 2文字パターン

| パターン | 出力 | 条件 |
|---|---|---|
| sk | ɧ | 次が前舌母音 (e,i,y,ä,ö) |
| sk | s + k | 次が後舌母音/子音/語末 |
| sk | ɧ | SK_BACK_VOWEL_EXCEPTIONS (människa, marskalk) |
| sj | ɧ | 常に |
| sh | ɧ | 外来語 |
| ch | ɧ | デフォルト |
| ch | k | CH_EXCEPTIONS_K (och, kristus等) |
| ph | f | 外来語 |
| th | t | 外来語 |
| tj | ɕ | 常に |
| kj | ɕ | 常に |
| gn | ɡ + n | 語頭 |
| gn | ŋ + n | 語中 |
| ng | ŋ | 常に |
| nk | ŋ + k | 常に |
| ck | k | ジェミネート (母音は短) |
| gj | j | 語頭のみ |
| lj | j | 語頭のみ |
| dj | j | 語頭のみ |
| hj | j | 語頭のみ |

### 4.3 1文字パターン (コンテキスト依存)

**k + 前舌母音:**
- デフォルト → ɕ (soft)
- HARD_K_WORDS/HARD_K_STEMS に該当 → k (hard)

**g + 前舌母音:**
- デフォルト → j (soft)
- HARD_G_WORDS/HARD_G_STEMS に該当 → ɡ (hard)

**その他:**
| 文字 | 出力 | 条件 |
|---|---|---|
| c + {e,i} | s | |
| c + その他 | k | |
| x | k + s | |
| g (ASCII) | ɡ (U+0261) | IPA標準化 |

### 4.4 デフォルト子音マッピング

```
b→b, d→d, f→f, h→h, j→j, l→l, m→m,
n→n, p→p, r→r, s→s, t→t, v→v, w→v, z→s
```

---

## 5. 母音長判定 (Complementary Quantity)

### 5.1 判定フロー (優先順)

```
1. 非ストレス音節 → 短母音
2. 機能語 (FUNCTION_WORDS) → 短母音
3. FINAL_M_SHORT_WORDS に該当 → 短母音
4. 後続子音数カウント:
   a. 語末 (子音0個) → 長母音
   b. r + 語末 → 長母音
   c. r + 単一子音 (ただし "o" 除外) → 長母音
   d. 子音2個以上 (ジェミネート/クラスタ) → 短母音
   e. 単一子音 → 長母音
```

### 5.2 母音マッピング表

| 文字 | 長母音 | 短母音 |
|---|---|---|
| a | ɑː (0xE05E) | a |
| e | eː (0xE05B) | ɛ (U+025B) |
| i | iː (0xE059) | ɪ (U+026A) |
| o (デフォルト) | uː (0xE060) | ɔ (U+0254) |
| o (O_LONG_AS_OO) | oː (0xE05F) | ɔ (U+0254) |
| u | ʉː (0xE061) | ɵ (U+0275) |
| y | yː (0xE05A) | ʏ (U+028F) |
| å | oː (0xE05F) | ɔ (U+0254) |
| ä | ɛː (0xE05C) | ɛ (U+025B) |
| ö | øː (0xE05D) | œ (U+0153) |

---

## 6. レトロフレックス同化

### 6.1 状態機械

```
状態: NORMAL, R_DETECTED, CASCADING

遷移表:
  NORMAL      + "r"              → R_DETECTED (rを保留)
  R_DETECTED  + "r"              → NORMAL (rr = ジェミネート, 同化なし)
  R_DETECTED  + {t,d,s,n,l}     → CASCADING (反舌音に変換)
  R_DETECTED  + その他           → NORMAL (保留した r を出力)
  CASCADING   + {t,d,s,n} (ɭ以外) → CASCADING (伝播継続)
  CASCADING   + l               → NORMAL (ɭ に変換, 伝播停止)
  CASCADING   + その他           → NORMAL (伝播停止)
```

### 6.2 変換マップ

| 入力 | 出力 | Unicode | 伝播 |
|---|---|---|---|
| t | ʈ | U+0288 | Yes |
| d | ɖ | U+0256 | Yes |
| s | ʂ | U+0282 | Yes |
| n | ɳ | U+0273 | Yes |
| l | ɭ | U+026D | **No (停止)** |

### 6.3 例

```
"kort"  → k + ɔ + ʈ         (r+t → ʈ)
"barn"  → b + ɑː + ɳ        (r+n → ɳ)
"först" → f + øː + ʂ + ʈ    (r+s → ʂ, カスケード: s+t → ʈ)
"karl"  → k + ɑː + ɭ        (r+l → ɭ, カスケード停止)
"borr"  → b + ɔ + r + r     (rr = ジェミネート, 同化なし)
```

---

## 7. ストレス検出

### 7.1 判定フロー

```go
func detectStress(word string) int {
    // 1. 機能語 → -1 (ストレスなし)
    if functionWords[word] { return -1 }

    // 2. 単音節 → 0
    if countSyllables(word) <= 1 { return 0 }

    // 3. ストレス吸引接尾辞 → 接尾辞直前の音節
    for _, suffix := range stressAttractingSuffixes {
        if strings.HasSuffix(word, suffix) {
            return countSyllables(stemPart)
        }
    }

    // 4. 非ストレスプレフィックス → 音節1
    for _, prefix := range unstressedPrefixes {
        if strings.HasPrefix(word, prefix) { return 1 }
    }

    // 5. デフォルト → 0
    return 0
}
```

### 7.2 ストレス吸引接尾辞 (18個)

```
ssion, tion, sion, itet, eri, era, ist, ör,
ment, ans, ens, ell, ent, ant, ik, ur, al, ös
```

### 7.3 非ストレスプレフィックス (5個)

```
för, be, ge, er, an
```

---

## 8. ローンワード接尾辞

| 接尾辞 | 固定音素 | 例 |
|---|---|---|
| -ssion | ɧ + uː + n | passion → pas + ɧuːn |
| -tion | ɧ + uː + n | station → sta + ɧuːn |
| -sion | ɧ + uː + n | vision → vi + ɧuːn |
| -age | ɑː + ɧ | garage → gar + ɑːɧ |
| -eur | øː + r | friseur → fris + øːr |
| -eum | eː + ɵ + m | museum → mus + eːɵm |
| -ium | ɪ + ɵ + m | stadium → stad + ɪɵm |

**注意:** AGE_NATIVE_WORDS (bage, lage, sage, mage, hage, tage等) はローンワード扱いしない。

---

## 9. 例外語リスト

### 9.1 一覧

| リスト名 | 用途 | 語数 |
|---|---|---|
| HARD_K_WORDS | k+前舌母音で /k/ を保持 | ~67 |
| HARD_K_STEMS | 同上 (語根形式) | ~35 |
| HARD_G_WORDS | g+前舌母音で /ɡ/ を保持 | ~41 |
| HARD_G_STEMS | 同上 (語根形式) | ~22 |
| O_LONG_AS_OO | "o" → /oː/ (デフォルトは /uː/) | ~30 |
| FINAL_M_SHORT_WORDS | 語末-mでも短母音 | ~13 |
| FUNCTION_WORDS | ストレスなし | ~35 |
| SK_BACK_VOWEL_EXCEPTIONS | sk+後舌母音で /ɧ/ | 2 |
| CH_EXCEPTIONS_K | ch → /k/ | ~5 |
| AGE_NATIVE_WORDS | -age がネイティブ扱い | ~9 |

### 9.2 Go実装方針

Python の `frozenset` / Rust の `LazyLock<HashSet>` に相当する Go のパターン:

```go
// パッケージレベル変数で初期化 (Go は init() 不要)
var hardKWords = map[string]bool{
    "flicka": true, "pojke": true, "socker": true,
    // ...
}

// ステムチェック
func isHardKStem(word string) bool {
    runes := []rune(word)
    for suffixLen := 3; suffixLen >= 1; suffixLen-- {
        if len(runes) > suffixLen {
            stem := string(runes[:len(runes)-suffixLen])
            if hardKStems[stem] { return true }
        }
    }
    return false
}
```

---

## 10. 言語検出 (unicode_detect.go 拡張)

### 10.1 スウェーデン語検出指標

**文字指標:**
- ä, ö, å (小文字/大文字) → +1 スコア

**機能語指標 (12語):**
```
och, att, jag, det, inte, han, hon, som, ska, med, aldrig, alltid
```

**判定:** スコア >= 1 でスウェーデン語と判定

### 10.2 Go実装

既存の `unicode_detect.go` の `SegmentText()` / ラテン語検出ロジックに sv スコアリングを追加。

---

## 11. 変更対象ファイル

### 11.1 新規作成

| ファイル | 行数 (推定) | 内容 |
|---|---|---|
| `src/go/phonemize/swedish.go` | 1,200-1,500 | G2Pエンジン本体 |
| `src/go/phonemize/swedish_test.go` | 1,500-2,000 | テストスイート |

### 11.2 既存ファイル変更

| ファイル | 変更内容 |
|---|---|
| `src/go/phonemize/pua.go` | SV 9エントリ追加 (0xE059-0xE061), nextDynamic → 0xE064 |
| `src/go/phonemize/unicode_detect.go` | SV文字/機能語検出追加 |
| `src/go/phonemize/multilingual.go` | SV phonemizer 統合 |
| `src/go/piperplus/synthesize.go` | `case "sv":` 追加 |

### 11.3 ドキュメント更新

| ファイル | 変更内容 |
|---|---|
| `src/go/README.md` | 7言語対応に更新 |

---

## 12. テスト計画

### 12.1 テストカテゴリ

| カテゴリ | テスト数 (目標) | 内容 |
|---|---|---|
| 基本母音 (長短) | 20 | 全10母音 × 長短 |
| 子音規則 | 30 | 3文字/2文字/1文字パターン |
| k/g 軟硬例外 | 15 | HARD_K/HARD_G リスト検証 |
| レトロフレックス | 15 | 基本5変換 + カスケード + ジェミネート |
| ストレス検出 | 15 | 機能語/接尾辞/プレフィックス/デフォルト |
| ローンワード接尾辞 | 10 | 7接尾辞 + AGE_NATIVE例外 |
| "o" 曖昧性 | 10 | O_LONG_AS_OO リスト |
| Prosody 整合性 | 5 | tokens.len == prosody.len, A1/A2/A3 |
| PUA マッピング | 10 | 9長母音 + MapSequence |
| 統合テスト | 10 | 文レベルの E2E |
| **合計** | **~140** | |

### 12.2 代表的テストケース (他プラットフォームと共通)

```go
// 長母音
{"gata", "ˈɡɑːta"},     // 長a → ɑː
{"hus", "ˈhʉːs"},       // 長u → ʉː
{"fin", "ˈfiːn"},        // 長i → iː

// 短母音
{"katt", "ˈkat"},        // ダブル子音 → 短
{"fest", "ˈfɛst"},       // クラスタ → 短

// 子音規則
{"sked", "ˈɧeːd"},      // sk+e → ɧ
{"skola", "ˈskuːla"},    // sk+o → sk
{"köp", contains "ɕ"},   // k+ö → ɕ (soft)
{"flicka", contains "k"}, // HARD_K例外
{"sjuk", contains "ɧ"},  // sj → ɧ

// レトロフレックス
{"kort", contains "ʈ"},  // r+t → ʈ
{"barn", contains "ɳ"},  // r+n → ɳ
{"först", contains "ʂ"}, // r+s → ʂ (+ カスケード)

// "o" 曖昧性
{"son", contains "oː"},  // O_LONG_AS_OO
{"sol", contains "uː"},  // デフォルト
```

---

## 13. 実装方針

### 13.1 参照実装の優先度

1. **Python** (`swedish.py`) — 正規の参照実装、全規則の出典
2. **Rust** (`swedish.rs`) — 型安全な実装の参考
3. **Go既存言語** (`french.go`, `spanish.go`) — Go固有のパターン準拠

### 13.2 Go実装スタイル

既存の Go ルールベース phonemizer (FR/ES/PT) に従い:

- 無状態構造体 (`SwedishPhonemizer struct{}`)
- パッケージレベル `map[string]bool` で例外語リスト
- `[]rune` ベースの文字操作
- テーブル駆動テスト
- `MapSequence()` による PUA 変換

### 13.3 実装順序

```
1. pua.go        — SV PUAエントリ追加 (前提条件)
2. swedish.go    — G2Pエンジン本体
   2a. 定数・例外語リスト
   2b. トークン化
   2c. 子音変換
   2d. 母音長判定
   2e. レトロフレックス同化
   2f. ストレス検出・挿入
   2g. PhonemizeWithProsody 統合
3. swedish_test.go — テストスイート
4. unicode_detect.go — SV言語検出追加
5. multilingual.go — SV統合
6. synthesize.go — レジストリ登録
7. README.md — ドキュメント更新
```
