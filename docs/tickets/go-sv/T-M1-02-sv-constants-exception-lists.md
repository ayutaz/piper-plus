# T-M1-02: SV定数・例外語リスト定義

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M1: PUA基盤 + 定数定義 |
| 依存チケット | T-M1-01 (PUA SV長母音エントリ登録) |
| 後続チケット | T-M2-01以降 (G2Pコアエンジン: 子音変換・母音長判定が定数を参照) |
| 対象ファイル | `src/go/phonemize/swedish.go` (新規作成) |
| 推定行数 | ~450行 (定数定義 + 例外語リスト10カテゴリ) |

## 1. タスク目的とゴール

スウェーデン語 G2P エンジン (`swedish.go`) の冒頭に必要な全ての定数と例外語リストを定義する。M2 以降の G2P ロジック実装が参照する基盤データであり、Python 参照実装 (`swedish.py`) の定数セクションと完全に一致させる。

**完了時の状態:**
- `swedish.go` が新規作成され、パッケージ宣言・インポート・定数セクションが定義されている
- 母音/子音セット、母音マッピング表 (長/短)、デフォルト子音マッピングが定義されている
- 例外語リスト10カテゴリが Python 参照実装と全語一致で定義されている
- `go build ./phonemize/...` と `go vet ./phonemize/...` が成功する

## 2. 実装する内容の詳細

### 2.1 ファイル構造

```go
package phonemize

// ---------------------------------------------------------------------------
// Swedish G2P constants and exception word lists
// ---------------------------------------------------------------------------
// Reference: src/python/piper_train/phonemize/swedish.py
// This file defines all constants needed by the Swedish G2P engine.
// The G2P logic itself will be added in M2/M3.
```

### 2.2 母音・子音セット

```go
var svFrontVowels = map[rune]bool{
    'e': true, 'i': true, 'y': true, 'ä': true, 'ö': true,
}

var svBackVowels = map[rune]bool{
    'a': true, 'o': true, 'u': true, 'å': true,
}

var svAllVowels = map[rune]bool{
    'a': true, 'e': true, 'i': true, 'o': true, 'u': true,
    'y': true, 'å': true, 'ä': true, 'ö': true,
}

var svConsonants = map[rune]bool{
    'b': true, 'c': true, 'd': true, 'f': true, 'g': true,
    'h': true, 'j': true, 'k': true, 'l': true, 'm': true,
    'n': true, 'p': true, 'q': true, 'r': true, 's': true,
    't': true, 'v': true, 'w': true, 'x': true, 'z': true,
}
```

### 2.3 母音マッピング表

**長母音マッピング (9エントリ):**

```go
// svLongVowelMap maps Swedish vowel letters to their long IPA realizations.
// Values are multi-character IPA strings that will be PUA-mapped by MapSequence().
var svLongVowelMap = map[rune]string{
    'a': "\u0251\u02d0", // ɑː
    'e': "e\u02d0",      // eː
    'i': "i\u02d0",      // iː
    'o': "u\u02d0",      // uː (default; /oː/ for O_LONG_AS_OO words)
    'u': "\u0289\u02d0", // ʉː
    'y': "y\u02d0",      // yː
    'å': "o\u02d0",      // oː
    'ä': "\u025b\u02d0", // ɛː
    'ö': "\u00f8\u02d0", // øː
}
```

**短母音マッピング (9エントリ):**

```go
// svShortVowelMap maps Swedish vowel letters to their short IPA realizations.
// Values are single-character IPA (no PUA needed).
var svShortVowelMap = map[rune]string{
    'a': "a",
    'e': "\u025b",  // ɛ
    'i': "\u026a",  // ɪ
    'o': "\u0254",  // ɔ
    'u': "\u0275",  // ɵ
    'y': "\u028f",  // ʏ
    'å': "\u0254",  // ɔ
    'ä': "\u025b",  // ɛ
    'ö': "\u0153",  // œ
}
```

**"o" 長母音の特殊値 (O_LONG_AS_OO 用):**

```go
// svOLongAsOOPhoneme is the long vowel for "o" in O_LONG_AS_OO words.
// Default "o" long is uː, but O_LONG_AS_OO words use oː.
const svOLongAsOOPhoneme = "o\u02d0" // oː
```

### 2.4 デフォルト子音マッピング (21エントリ)

```go
// svConsonantDefault maps single consonant letters to their default IPA output.
// Context-dependent rules (k/g + front vowel, etc.) override this in M2.
var svConsonantDefault = map[rune]string{
    'b': "b",
    'c': "k",
    'd': "d",
    'f': "f",
    'g': "\u0261", // ɡ (IPA, U+0261)
    'h': "h",
    'j': "j",
    'k': "k",
    'l': "l",
    'm': "m",
    'n': "n",
    'p': "p",
    'q': "k",
    'r': "r",
    's': "s",
    't': "t",
    'v': "v",
    'w': "v",
    'x': "ks",
    'z': "s",
}
```

### 2.5 例外語リスト (10カテゴリ)

全リストは Python 参照実装 (`swedish.py`) と完全一致。Go では `map[string]bool` で定義する。

#### 2.5.1 svHardKWords (75語)

k + 前舌母音で /k/ (hard) を保持する完全一致単語。

```go
var svHardKWords = map[string]bool{
    "backe":    true,
    "bricka":   true,
    "docka":    true,
    "dricka":   true,
    "dyker":    true,
    "dyket":    true,
    "enkel":    true,
    "ficka":    true,
    "flicka":   true,
    "fröken":   true,
    "kebab":    true,
    "kennel":   true,
    "kent":     true,
    "keps":     true,
    "kerna":    true,
    "keso":     true,
    "ketchup":  true,
    "kex":      true,
    "kibbutz":  true,
    "kick":     true,
    "kikare":   true,
    "kille":    true,
    "kilo":     true,
    "kilt":     true,
    "kimono":   true,
    "kines":    true,
    "kinesisk": true,
    "kiosk":    true,
    "kirke":    true,
    "kissa":    true,
    "kitsch":   true,
    "kiwi":     true,
    "leken":    true,
    "leker":    true,
    "lekerska": true,
    "läker":    true,
    "läket":    true,
    "märke":    true,
    "märker":   true,
    "märket":   true,
    "mörker":   true,
    "naken":    true,
    "ocker":    true,
    "onkel":    true,
    "paket":    true,
    "pojke":    true,
    "raket":    true,
    "rike":     true,
    "ryker":    true,
    "räcker":   true,
    "röker":    true,
    "röket":    true,
    "silke":    true,
    "sjunker":  true,
    "skelett":  true,
    "skicka":   true,
    "smeker":   true,
    "sockel":   true,
    "socker":   true,
    "staket":   true,
    "steker":   true,
    "steket":   true,
    "sticker":  true,
    "stryker":  true,
    "säker":    true,
    "söker":    true,
    "söket":    true,
    "tecken":   true,
    "trycke":   true,
    "tänker":   true,
    "tänket":   true,
    "vacker":   true,
    "viker":    true,
    "vinkel":   true,
    "väcker":   true,
}
```

#### 2.5.2 svHardKStems (33語)

k + 前舌母音で /k/ を保持する語根。ステムマッチ (語末1-3文字を除去してチェック) に使用。

```go
var svHardKStems = map[string]bool{
    "back":  true,
    "block": true,
    "brick": true,
    "dock":  true,
    "drick": true,
    "dyk":   true,
    "fick":  true,
    "flick": true,
    "lek":   true,
    "lock":  true,
    "läk":   true,
    "märk":  true,
    "pack":  true,
    "rock":  true,
    "ryk":   true,
    "räck":  true,
    "rök":   true,
    "sack":  true,
    "sick":  true,
    "sjunk": true,
    "skick": true,
    "smek":  true,
    "sock":  true,
    "stek":  true,
    "stick": true,
    "stryk": true,
    "sök":   true,
    "tack":  true,
    "trick": true,
    "tryck": true,
    "tänk":  true,
    "vik":   true,
    "väck":  true,
}
```

#### 2.5.3 svHardGWords (55語)

g + 前舌母音で /ɡ/ (hard) を保持する完全一致単語。

```go
var svHardGWords = map[string]bool{
    "agera":     true,
    "arrangera": true,
    "bagel":     true,
    "bageri":    true,
    "berg":      true,
    "borg":      true,
    "bygel":     true,
    "bygge":     true,
    "båge":      true,
    "dager":     true,
    "delegera":  true,
    "duger":     true,
    "engagera":  true,
    "finger":    true,
    "flygel":    true,
    "flyger":    true,
    "fogel":     true,
    "fågel":     true,
    "ge":        true,
    "gecko":     true,
    "gel":       true,
    "ger":       true,
    "hage":      true,
    "hagel":     true,
    "hunger":    true,
    "ignorera":  true,
    "intrigera": true,
    "lager":     true,
    "ligger":    true,
    "ljuger":    true,
    "läge":      true,
    "läger":     true,
    "lägger":    true,
    "mage":      true,
    "nagel":     true,
    "navigera":  true,
    "negera":    true,
    "reagera":   true,
    "regel":     true,
    "segel":     true,
    "seger":     true,
    "segregera": true,
    "spegel":    true,
    "stege":     true,
    "stiger":    true,
    "suger":     true,
    "tagel":     true,
    "tangera":   true,
    "tegel":     true,
    "tiger":     true,
    "tigger":    true,
    "tygel":     true,
    "väger":     true,
    "äger":      true,
    "ängel":     true,
}
```

#### 2.5.4 svHardGStems (23語)

g + 前舌母音で /ɡ/ を保持する語根。

```go
var svHardGStems = map[string]bool{
    "bag":  true,
    "berg": true,
    "borg": true,
    "byg":  true,
    "dag":  true,
    "drag": true,
    "dug":  true,
    "flyg": true,
    "lag":  true,
    "lig":  true,
    "ljug": true,
    "lägg": true,
    "mag":  true,
    "nag":  true,
    "reg":  true,
    "seg":  true,
    "stig": true,
    "sug":  true,
    "tag":  true,
    "tig":  true,
    "vag":  true,
    "väg":  true,
    "äg":   true,
}
```

#### 2.5.5 svOLongAsOO (30語)

"o" を /oː/ に変換する単語 (デフォルトは /uː/)。

```go
var svOLongAsOO = map[string]bool{
    "blod":     true,
    "bo":       true,
    "bror":     true,
    "dom":      true,
    "flod":     true,
    "fon":      true,
    "fot":      true,
    "god":      true,
    "ion":      true,
    "jord":     true,
    "ko":       true,
    "kol":      true,
    "kontroll": true,
    "lo":       true,
    "lov":      true,
    "mod":      true,
    "mol":      true,
    "mor":      true,
    "nod":      true,
    "ord":      true,
    "pol":      true,
    "ro":       true,
    "rod":      true,
    "roll":     true,
    "rot":      true,
    "son":      true,
    "tog":      true,
    "ton":      true,
    "tro":      true,
    "zon":      true,
}
```

#### 2.5.6 svFinalMShortWords (18語)

語末が -m で終わるが短母音を使用する単語。

```go
var svFinalMShortWords = map[string]bool{
    "dam":   true,
    "dom":   true,
    "dröm":  true,
    "dum":   true,
    "fem":   true,
    "glöm":  true,
    "gum":   true,
    "ham":   true,
    "hem":   true,
    "kam":   true,
    "lam":   true,
    "lem":   true,
    "ram":   true,
    "rum":   true,
    "som":   true,
    "stam":  true,
    "ström": true,
    "tom":   true,
}
```

#### 2.5.7 svFunctionWords (37語)

ストレスを受けない機能語。ストレス検出で -1 を返す。

```go
var svFunctionWords = map[string]bool{
    "att":  true,
    "av":   true,
    "de":   true,
    "dem":  true,
    "den":  true,
    "det":  true,
    "din":  true,
    "du":   true,
    "en":   true,
    "ett":  true,
    "från": true,
    "för":  true,
    "han":  true,
    "har":  true,
    "hon":  true,
    "hos":  true,
    "i":    true,
    "inte": true,
    "jag":  true,
    "kan":  true,
    "med":  true,
    "men":  true,
    "min":  true,
    "när":  true,
    "och":  true,
    "om":   true,
    "på":   true,
    "sig":  true,
    "sin":  true,
    "ska":  true,
    "som":  true,
    "till": true,
    "ur":   true,
    "var":  true,
    "vi":   true,
    "vill": true,
    "är":   true,
}
```

#### 2.5.8 svSKBackVowelExceptions (2語)

sk + 後舌母音で /ɧ/ を使う例外 (通常は /sk/)。

```go
var svSKBackVowelExceptions = map[string]bool{
    "människa": true,
    "marskalk": true,
}
```

#### 2.5.9 svCHExceptionsK (5語)

ch を /k/ と読む例外 (通常は /ɧ/)。

```go
var svCHExceptionsK = map[string]bool{
    "krist":   true,
    "kristus": true,
    "kron":    true,
    "kronik":  true,
    "och":     true,
}
```

#### 2.5.10 svAgeNativeWords (11語)

-age 接尾辞がフランス語ローンワードではなくスウェーデン語ネイティブの単語。ローンワード接尾辞検出から除外する。

```go
var svAgeNativeWords = map[string]bool{
    "bage":  true,
    "dage":  true,
    "drage": true,
    "frage": true,
    "hage":  true,
    "klage": true,
    "lage":  true,
    "mage":  true,
    "plage": true,
    "sage":  true,
    "tage":  true,
}
```

### 2.6 例外語リスト語数サマリ

| 変数名 | 語数 | Python参照実装の語数 | 一致 |
|---|---|---|---|
| svHardKWords | 75 | 75 | OK |
| svHardKStems | 33 | 33 | OK |
| svHardGWords | 55 | 55 | OK |
| svHardGStems | 23 | 23 | OK |
| svOLongAsOO | 30 | 30 | OK |
| svFinalMShortWords | 18 | 18 | OK |
| svFunctionWords | 37 | 37 | OK |
| svSKBackVowelExceptions | 2 | 2 | OK |
| svCHExceptionsK | 5 | 5 | OK |
| svAgeNativeWords | 11 | 11 | OK |
| **合計** | **289** | **289** | **OK** |

**注意:** マイルストーンドキュメント (`go-swedish-milestones.md`) の推定語数 (HARD_K_WORDS ~67, HARD_K_STEMS ~35 等) はチルダ付きの概数であり、Python 参照実装の正確な語数とは異なる。本チケットの語数は Python 参照実装に基づく正確な値である。

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|---|---|---|
| 実装エージェント | 1 | swedish.go 冒頭の定数セクション作成 |

データ定義のみのタスクであり、ロジックは含まない。1名で十分。ただし例外語リストの正確性検証に注意を要する。

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**スコープ内:**
- `swedish.go` の新規作成 (パッケージ宣言、定数セクションのみ)
- 母音/子音セット定義 (svFrontVowels, svBackVowels, svAllVowels, svConsonants)
- 母音マッピング表定義 (svLongVowelMap, svShortVowelMap, svOLongAsOOPhoneme)
- デフォルト子音マッピング定義 (svConsonantDefault)
- 例外語リスト10カテゴリ定義

**スコープ外:**
- G2P ロジック (子音変換、母音長判定、レトロフレックス等) -- M2/M3
- `SwedishPhonemizer` 構造体定義 -- M2
- `PhonemizeWithProsody` メソッド -- M3
- テストファイル (`swedish_test.go`) -- M4
- ストレス関連定数 (UNSTRESSED_PREFIXES, STRESS_ATTRACTING_SUFFIXES) -- M3 のスコープだが、ファイル構成の都合上このチケットで定義してもよい

### 4.2 テスト項目

| # | テスト内容 | 期待結果 |
|---|---|---|
| 1 | `go build ./phonemize/...` | コンパイル成功 |
| 2 | `go vet ./phonemize/...` | エラーなし |
| 3 | 既存テスト `go test ./phonemize/...` | 全 PASS (新ファイル追加のみで既存に影響なし) |
| 4 | svHardKWords の語数 | 75 |
| 5 | svHardKStems の語数 | 33 |
| 6 | svHardGWords の語数 | 55 |
| 7 | svHardGStems の語数 | 23 |
| 8 | svOLongAsOO の語数 | 30 |
| 9 | svFinalMShortWords の語数 | 18 |
| 10 | svFunctionWords の語数 | 37 |
| 11 | svSKBackVowelExceptions の語数 | 2 |
| 12 | svCHExceptionsK の語数 | 5 |
| 13 | svAgeNativeWords の語数 | 11 |
| 14 | svLongVowelMap の 'a' 値が `"\u0251\u02d0"` | PUA `ɑː` (0xE05E) と一致 |
| 15 | svShortVowelMap の 'a' 値が `"a"` | 短母音 |

### 4.3 Unitテスト

M4 で `swedish_test.go` に含めるが、このチケット完了時点で以下の検証を推奨:

```go
func TestSvConstantsCounts(t *testing.T) {
    tests := []struct {
        name string
        m    map[string]bool
        want int
    }{
        {"svHardKWords", svHardKWords, 75},
        {"svHardKStems", svHardKStems, 33},
        {"svHardGWords", svHardGWords, 55},
        {"svHardGStems", svHardGStems, 23},
        {"svOLongAsOO", svOLongAsOO, 30},
        {"svFinalMShortWords", svFinalMShortWords, 18},
        {"svFunctionWords", svFunctionWords, 37},
        {"svSKBackVowelExceptions", svSKBackVowelExceptions, 2},
        {"svCHExceptionsK", svCHExceptionsK, 5},
        {"svAgeNativeWords", svAgeNativeWords, 11},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            if got := len(tt.m); got != tt.want {
                t.Errorf("len(%s) = %d, want %d", tt.name, got, tt.want)
            }
        })
    }
}

func TestSvVowelMapConsistency(t *testing.T) {
    // All vowels in svAllVowels must have entries in both long and short maps
    for v := range svAllVowels {
        if _, ok := svLongVowelMap[v]; !ok {
            t.Errorf("svLongVowelMap missing vowel %q", v)
        }
        if _, ok := svShortVowelMap[v]; !ok {
            t.Errorf("svShortVowelMap missing vowel %q", v)
        }
    }
}

func TestSvLongVowelMapPUAAlignment(t *testing.T) {
    // Long vowel values must match fixedPUA keys (for PUA mapping to work)
    for vowel, ipa := range svLongVowelMap {
        if _, ok := fixedPUA[ipa]; !ok {
            // 'o' default is uː which should be in fixedPUA
            t.Errorf("svLongVowelMap[%q] = %q not in fixedPUA", string(vowel), ipa)
        }
    }
}
```

### 4.4 E2Eテスト

このチケット単体では E2E テスト不要。定数のみの定義であり、実行パスがない。M2 で G2P ロジックが追加された段階で E2E 検証を行う。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念 | 対策 |
|---|---|---|
| 1 | Python 参照実装との語数不一致 | 本チケットの全語リストは Python を直接実行して抽出した正確なデータ。レビュー時にも `PYTHONIOENCODING=utf-8 python3 -c "from ... import ...; print(sorted(...))"` で検証可能 |
| 2 | Go ソースの UTF-8 エンコーディング | スウェーデン語特有文字 (å, ä, ö) と IPA 文字 (ɡ, ɛ, ɵ 等) を含む。Go ソースは UTF-8 必須であり、既存の french.go/spanish.go が既に IPA 文字を使用しているため問題なし |
| 3 | `map[string]bool` の初期化コスト | パッケージレベル変数として定義するため、プログラム起動時に1回のみ初期化。289語は十分小さくパフォーマンス問題なし |
| 4 | 母音マッピングの IPA 文字列と PUA キーの一致 | `svLongVowelMap` の値が `fixedPUA` のキーと完全一致する必要がある。T-M1-01 で登録した PUA キーと照合すること |
| 5 | `dom`/`som` が svOLongAsOO と svFinalMShortWords の両方に存在 | Python 参照実装と同じ。`dom` は O_LONG_AS_OO (o→oː) かつ FINAL_M_SHORT (短母音)。両ルールの優先度は M2 の母音長判定ロジックで解決する (FINAL_M_SHORT が優先) |

### 5.2 レビューチェックリスト

- [ ] `package phonemize` 宣言が正しい
- [ ] 各例外語リストの語数が Python 参照実装と一致 (上記サマリ表参照)
- [ ] 各リストの全語を Python 参照実装と diff して一致を確認
- [ ] `svLongVowelMap` の全9エントリの IPA 文字列が Python の `_LONG_VOWEL_MAP` と一致
- [ ] `svShortVowelMap` の全9エントリの IPA 文字列が Python の `_SHORT_VOWEL_MAP` と一致
- [ ] `svConsonantDefault` の全21エントリが Python の `_CONSONANT_DEFAULT` と一致
- [ ] Unicode エスケープが正確 (特に `\u0261` = ɡ, `\u025b` = ɛ, `\u0289` = ʉ, `\u02d0` = ː)
- [ ] 変数名が Go 命名規則に従っている (svCamelCase, パッケージ内小文字開始)
- [ ] `go build`, `go vet` が成功
- [ ] 既存テストに影響なし

## 6. 一から作り直すとしたら

- **コード生成の検討:** 289語のリストを手動で Go に移植するのはエラーが入りやすい。Python スクリプトで `swedish.py` を読み込み `swedish.go` の定数セクションを自動生成する方法もあった。ただし、一回きりの作業であり、チケット内に全語をリストしているため、手動コピーでも正確性は確保できる。
- **型の選択:** `map[string]bool` の代わりに `map[string]struct{}` を使うとメモリ効率が若干良いが、既存の Go 実装 (french.go, spanish.go 等) が `map[string]bool` パターンを使用しているため、一貫性を優先した。
- **ストレス関連定数:** `UNSTRESSED_PREFIXES` と `STRESS_ATTRACTING_SUFFIXES` は M3 のスコープだが、この定数セクションに含めた方がファイル構成として自然かもしれない。M2/M3 実装時に判断する。

## 7. 後続タスクへの連絡事項

- **M2 担当者へ:** 例外語リストのルックアップ関数 (`isHardK()`, `isHardG()` 等) はこのチケットでは定義しない。M2 の子音変換タスクで、リストを使うルックアップ関数を実装すること。ステムマッチ (`isHardKStem()`) は語末1-3文字を除去して `svHardKStems` をチェックするロジックになる (セクション9.2 of `go-swedish-g2p-impl-plan.md` 参照)。
- **M2 担当者へ:** `svConsonantDefault` の `'x'` → `"ks"` は多文字出力。子音変換ロジックで `[]string` に展開する必要がある (例: `result = append(result, "k", "s")`)。
- **M2 担当者へ:** `dom` と `som` は `svOLongAsOO` と `svFinalMShortWords` の両方に存在する。母音長判定では `svFinalMShortWords` を先にチェックして短母音にする。Python 参照実装の `_get_vowel_phoneme()` の優先順位を参照。
- **M3 担当者へ:** ストレス関連定数 (`svUnstressedPrefixes`, `svStressAttractingSuffixes`) がこのファイルに未定義の場合は M3 で追加すること。
