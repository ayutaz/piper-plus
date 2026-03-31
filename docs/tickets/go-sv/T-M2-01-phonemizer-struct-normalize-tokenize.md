# T-M2-01: SwedishPhonemizer構造体 + 正規化 + トークン化

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M2: G2Pコアエンジン |
| 依存チケット | M1 (PUA基盤 + 定数定義) |
| 後続チケット | T-M2-02, T-M2-03, T-M2-04 (全て本チケットの構造体・トークン化を使用) |
| 対象ファイル | `src/go/phonemize/swedish.go` (新規作成) |
| 推定行数 | ~120行 |

## 1. タスク目的とゴール

M2 の基盤として、`SwedishPhonemizer` 構造体の定義、テキスト正規化、およびトークン化を実装する。後続チケット (T-M2-02〜05) で実装する子音変換・母音長判定・ローンワード検出・単語G2P統合の全てが本チケットの成果物に依存する。

**完了時の状態:**
- `SwedishPhonemizer` 構造体が定義済みで `NewSwedishPhonemizer()` と `LanguageCode()` が使用可能
- テキスト入力を NFC 正規化 + 小文字化する関数が存在
- テキストを単語トークンと句読点トークンに分割する `svTokenize()` が動作
- `go build ./phonemize/...` が成功

## 2. 実装する内容の詳細

### 2.1 構造体定義

既存の FR/ES/PT パターンに厳密に従い、無状態構造体を定義する。

```go
// SwedishPhonemizer converts Swedish text to IPA phonemes using rule-based G2P.
type SwedishPhonemizer struct{}

func NewSwedishPhonemizer() *SwedishPhonemizer     { return &SwedishPhonemizer{} }
func (p *SwedishPhonemizer) LanguageCode() string  { return "sv" }
```

**注意:** `PhonemizeWithProsody` メソッドは T-M2-05 で実装。本チケットではスタブ (空のスライスを返す) を定義しても良い。または `PhonemizeWithProsody` の定義自体を T-M2-05 に委ねてもよい。ただしビルドを通すためには `Phonemizer` インターフェースを満たすか、インターフェース準拠チェック (`var _ Phonemizer = ...`) は M3 に持ち越す。

### 2.2 定数セット

M1 で定義済みの以下の定数を使用する (M1 の成果物として `swedish.go` 冒頭に存在しているはず):

```go
var svFrontVowels = map[rune]bool{'e': true, 'i': true, 'y': true, '\u00e4': true, '\u00f6': true}
var svBackVowels  = map[rune]bool{'a': true, 'o': true, 'u': true, '\u00e5': true}
var svAllVowels   // svFrontVowels ∪ svBackVowels
var svConsonants  = map[rune]bool{'b': true, 'c': true, ..., 'z': true}
```

本チケットで追加が必要な定数:

```go
var svPunctuation = map[rune]bool{
    '.': true, ',': true, ';': true, ':': true, '!': true, '?': true,
}
```

### 2.3 正規化関数

```go
func svNormalize(text string) string {
    // 1. strings.TrimSpace
    // 2. NFC正規化 (golang.org/x/text/unicode/norm パッケージ)
    // 3. strings.ToLower で小文字化
    // 4. strings.Fields + strings.Join で連続空白を正規化
    return norm.NFC.String(strings.ToLower(strings.TrimSpace(text)))
}
```

**依存パッケージ:** `golang.org/x/text/unicode/norm`。FR/ES/PT は `strings.ToLower` のみだが、スウェーデン語は NFC 正規化が必要 (e.g., `a` + combining `\u030a` → `\u00e5`)。`go.mod` に `golang.org/x/text` が既に含まれているか確認し、なければ追加する。ただし既存の `french.go` を確認すると NFC は明示的に行っていないため、`strings.ToLower` のみで十分な可能性も高い。Python 参照実装 (`_normalize`) が `unicodedata.normalize("NFC", ...)` を行っているため NFC を含める。

### 2.4 トークン化

Python 参照実装の `_RE_TOKEN = re.compile(r"([a-zåäöéàüáèëï]+|[,.;:!?]+)")` に対応する Go 実装。既存の FR (`frSplit`) / ES (`esTokenize`) パターンに従い、正規表現を使わず `[]rune` ベースで手書きする。

```go
type svToken struct {
    text  string
    isPun bool
}

func svTokenize(text string) []svToken {
    runes := []rune(text)
    var tokens []svToken
    i := 0
    n := len(runes)
    for i < n {
        ch := runes[i]
        // 空白はスキップ
        if unicode.IsSpace(ch) {
            i++
            continue
        }
        // 句読点
        if svPunctuation[ch] {
            tokens = append(tokens, svToken{text: string(ch), isPun: true})
            i++
            continue
        }
        // 単語: 連続するスウェーデン語文字を収集
        if svIsWordChar(ch) {
            start := i
            for i < n && svIsWordChar(runes[i]) {
                i++
            }
            tokens = append(tokens, svToken{text: string(runes[start:i]), isPun: false})
            continue
        }
        i++ // その他の文字はスキップ
    }
    return tokens
}

func svIsWordChar(ch rune) bool {
    // a-z + スウェーデン語特殊文字 (å, ä, ö) + アクセント付き文字 (é, à, ü, á, è, ë, ï)
    if ch >= 'a' && ch <= 'z' {
        return true
    }
    switch ch {
    case '\u00e5', '\u00e4', '\u00f6',           // å, ä, ö
         '\u00e9', '\u00e0', '\u00fc',           // é, à, ü
         '\u00e1', '\u00e8', '\u00eb', '\u00ef': // á, è, ë, ï
        return true
    }
    return false
}
```

**Python `_RE_TOKEN` とのマッピング:**

| Python正規表現の文字クラス | Go `svIsWordChar` のカバー |
|---|---|
| `a-z` | `ch >= 'a' && ch <= 'z'` |
| `åäö` | `\u00e5`, `\u00e4`, `\u00f6` |
| `éàüáèëï` | `\u00e9`, `\u00e0`, `\u00fc`, `\u00e1`, `\u00e8`, `\u00eb`, `\u00ef` |

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装エージェント | 構造体定義、正規化関数、トークン化関数、定数定義 | 1 |
| 2 | レビューエージェント | 既存 FR/ES/PT パターンとの整合性確認、Python 参照実装との一致検証 | 1 |

**合計: 2 エージェント**

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `SwedishPhonemizer` 構造体、`NewSwedishPhonemizer()`、`LanguageCode()`
- `svNormalize()` 関数
- `svTokenize()` 関数、`svToken` 型、`svIsWordChar()` ヘルパー
- `svPunctuation` 定数

**含まない:**
- `PhonemizeWithProsody` の完全実装 (T-M2-05)
- 子音変換 (T-M2-03)
- 母音長判定 (T-M2-04)
- ローンワード検出 (T-M2-02)
- `Phonemizer` インターフェース準拠 (`var _ Phonemizer = ...` は M3)

### 4.2 テスト項目

| # | テスト | 期待値 |
|---|--------|-------|
| 1 | `LanguageCode()` | `"sv"` |
| 2 | `svNormalize("  HÄLSA  ")` | `"hälsa"` |
| 3 | `svNormalize("Ärlig")` | `"ärlig"` |
| 4 | `svTokenize("hej, hur mår du?")` | `[{hej,F}, {",",T}, {hur,F}, {mår,F}, {du,F}, {"?",T}]` |
| 5 | `svTokenize("")` | `[]` (空) |
| 6 | `svTokenize("...")` | `[{".",T}, {".",T}, {".",T}]` |
| 7 | `svIsWordChar('å')` | `true` |
| 8 | `svIsWordChar('1')` | `false` |

### 4.3 Unitテスト

```go
func TestSvNormalize(t *testing.T) {
    tests := []struct {
        input string
        want  string
    }{
        {"  HÄLSA  ", "hälsa"},
        {"Ärlig", "ärlig"},
        {"KÖPA BRÖD", "köpa bröd"},
        {"", ""},
    }
    for _, tt := range tests {
        t.Run(tt.input, func(t *testing.T) {
            got := svNormalize(tt.input)
            if got != tt.want {
                t.Errorf("svNormalize(%q) = %q, want %q", tt.input, got, tt.want)
            }
        })
    }
}

func TestSvTokenize(t *testing.T) {
    tokens := svTokenize("hej, hur mår du?")
    // 検証: 6トークン、hej=word, ","=punct, hur=word, mår=word, du=word, "?"=punct
}
```

### 4.4 E2Eテスト

本チケット単独での E2E テストは不要。T-M2-05 完了後に単語入力→音素列出力の E2E テストが可能になる。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **NFC 正規化の必要性**: 既存の FR/ES/PT は NFC を明示的に行っていない。`golang.org/x/text/unicode/norm` への新規依存が不要であれば、`strings.ToLower` のみで十分。入力が常に NFC であると保証できるなら省略可。ただし Python 参照実装は明示的に NFC を行っているため、安全策として含めることを推奨。
2. **`svIsWordChar` のカバー範囲**: Python の `_RE_TOKEN` に含まれるアクセント付き文字 (é, à, ü, á, è, ë, ï) はスウェーデン語の外来語に出現するため含める。ただし通常のスウェーデン語テキストでは å, ä, ö のみで十分。
3. **ファイル構成**: M1 が `swedish.go` に定数を定義済みの前提。M1 が別ファイル (例: `swedish_constants.go`) に分離していた場合は調整が必要。

### 5.2 レビューチェックリスト

- [ ] `NewSwedishPhonemizer()` が無状態構造体のポインタを返す
- [ ] `LanguageCode()` が `"sv"` を返す
- [ ] `svNormalize` が NFC + lowercase を適用 (Python `_normalize` と同等)
- [ ] `svTokenize` が FR `frSplit` / ES `esTokenize` と同等のパターン
- [ ] `svIsWordChar` が Python `_RE_TOKEN` の文字クラスをカバー
- [ ] `svPunctuation` が Python `PUNCTUATION = set(",.;:!?")` と一致
- [ ] `go build ./phonemize/...` 成功
- [ ] `go vet ./phonemize/...` エラーなし

## 6. 一から作り直すとしたら

- FR/ES/PT のトークン化は各自でパターンが微妙に異なるが、共通の `latinTokenize()` ユーティリティを導入すれば重複コードを減らせた可能性がある。しかし各言語固有の文字セットの違いがあるため、現状の言語別実装は妥当。
- `svIsWordChar` の文字リストを `map[rune]bool` にすれば switch-case よりも拡張性が高いが、パフォーマンスは switch の方が良い。エントリ数が少ない (10文字) ため switch で問題ない。

## 7. 後続タスクへの連絡事項

- **T-M2-02 (ローンワード):** `svTokenize` が返す `svToken.text` (小文字化済み) をそのまま使える。
- **T-M2-03 (子音変換):** `svIsWordChar` と `svAllVowels` / `svConsonants` (M1 定義) を子音判定に使用。`svFrontVowels` / `svBackVowels` は M1 で定義済みの前提。
- **T-M2-04 (母音長判定):** 正規化済みテキストの母音文字は全て小文字であることが保証される。
- **T-M2-05 (統合):** `svTokenize` の戻り値 `[]svToken` を iterate して単語ごとに G2P を適用する。`svNormalize` は `PhonemizeWithProsody` の冒頭で呼び出す。
