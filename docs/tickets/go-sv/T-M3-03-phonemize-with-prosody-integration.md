# T-M3-03: PhonemizeWithProsody統合

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M3: 後処理 + Phonemizer統合 |
| 依存チケット | T-M3-01 (レトロフレックス同化), T-M3-02 (ストレス検出 + マーカー挿入), T-M2 (G2Pコアエンジン全体) |
| 後続チケット | T-M4 (テストスイート ~140テスト), T-M5 (マルチリンガル統合 + レジストリ) |
| 対象ファイル | `src/go/phonemize/swedish.go` |
| 推定行数 | ~170行 (`svPhonemizeWord` + `PhonemizeWithProsody` + EOS追跡 + Phonemizerインターフェース準拠) |

## 1. タスク目的とゴール

M2 (G2Pコア)、T-M3-01 (レトロフレックス)、T-M3-02 (ストレス) の全コンポーネントを統合し、`SwedishPhonemizer` の `PhonemizeWithProsody` メソッドを完成させる。テキスト入力から `*PhonemizeResult` (Tokens + Prosody + EOSToken) を返す完全なパイプラインを構築する。

**ゴール:**
- 全パイプラインの統合: 正規化→トークン化→単語ごとG2P→レトロフレックス→ストレス→PUA変換→Result組立
- `Phonemizer` インターフェース準拠 (`PhonemizeWithProsody` + `LanguageCode`)
- Prosody 構築 (A1=0, A2=stress, A3=wordPhonemeCount)
- EOS追跡 (`$`, `?`, `!`)
- `MapSequence()` による長母音PUA変換
- Python (`phonemize_swedish_with_prosody`) / Rust (`phonemize_swedish_with_prosody`) / Go既存言語 (`french.go`, `spanish.go`) と同等の出力構造

## 2. 実装する内容の詳細

### 2.1 全体パイプライン

```
テキスト入力
  │
  ▼
[1] 正規化 (M2: svNormalize)
  │  NFC + 小文字化
  ▼
[2] トークン化 (M2: svTokenize)
  │  → []svToken (Word / Punct)
  ▼
[3] トークンごとの処理ループ
  │
  ├─ Punct → 各文字をTokensに追加 + 空ProsodyInfo + EOS追跡
  │
  └─ Word → svPhonemizeWord(word) [本チケットで統合]
       │
       ├─ [3a] svDetectStress(word) → stressSyl
       ├─ [3b] ローンワード接尾辞チェック (M2: svDetectLoanwordSuffix)
       ├─ [3c] ネイティブG2P変換 (M2: svConvertWordNative)
       ├─ [3d] svApplyRetroflex(rawPhonemes) [T-M3-01]
       ├─ [3e] svInsertStressMarker(phonemes, stressSyl) [T-M3-02]
       │
       └─ 単語音素列 (ストレスマーカー付き)
            │
            ├─ Prosody構築: A1=0, A2 (stress), A3 (word phoneme count)
            └─ Tokensに追加
  │
  ▼
[4] MapSequence() で長母音→PUA変換
  │
  ▼
PhonemizeResult {Tokens, Prosody, EOSToken}
```

### 2.2 `svPhonemizeWord` — 単語レベルパイプライン統合

```go
// svPhonemizeWord runs the full G2P pipeline for a single word:
// stress detection → loanword/native G2P → retroflex → stress marker insertion.
func svPhonemizeWord(word string) []string
```

#### 内部フロー

```go
func svPhonemizeWord(word string) []string {
    if word == "" {
        return nil
    }

    // Stage 6 前半: ストレス検出
    stressSyl := svDetectStress(word)

    // Stage 2: ローンワード接尾辞チェック
    var rawPhonemes []string
    if stem, suffixPhonemes := svDetectLoanwordSuffix(word); suffixPhonemes != nil {
        // 接尾辞にストレスが吸引された場合、stem部分は非ストレス
        stemSylCount := svCountSyllables(stem)
        stemStressed := stressSyl
        if stressSyl >= stemSylCount {
            stemStressed = -1 // 接尾辞側にストレス → stemは非ストレス
        }
        stemPhonemes := svConvertWordNative([]rune(stem), word, stemStressed)
        rawPhonemes = append(stemPhonemes, suffixPhonemes...)
    } else {
        // Stage 4: ネイティブG2P変換
        rawPhonemes = svConvertWordNative([]rune(word), word, stressSyl)
    }

    // Stage 5: レトロフレックス同化 [T-M3-01]
    phonemes := svApplyRetroflex(rawPhonemes)

    // Stage 6 後半: ストレスマーカー挿入 [T-M3-02]
    phonemes = svInsertStressMarker(phonemes, stressSyl)

    return phonemes
}
```

### 2.3 `PhonemizeWithProsody` — テキストレベルパイプライン

`french.go` / `spanish.go` の既存パターンに準拠して実装する。

```go
// PhonemizeWithProsody converts Swedish text to phoneme tokens with prosody.
func (p *SwedishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
    text = svNormalize(text)  // NFC + lowercase
    tokens := svTokenize(text)

    var phs []string
    var pro []*ProsodyInfo
    needSpace := false
    eos := "$"

    for _, tok := range tokens {
        switch tok.kind {
        case svTokenPunct:
            // 各句読点文字をそのまま追加
            for _, c := range tok.text {
                ch := string(c)
                phs = append(phs, ch)
                pro = append(pro, &ProsodyInfo{})
                if c == '?' || c == '!' {
                    eos = ch
                }
            }

        case svTokenWord:
            // 単語間スペース
            if needSpace {
                phs = append(phs, " ")
                pro = append(pro, &ProsodyInfo{})
            }

            // 単語G2Pパイプライン
            wordPhonemes := svPhonemizeWord(tok.text)

            // A3: ストレスマーカーを除いた音素数
            wordPhCount := 0
            for _, ph := range wordPhonemes {
                if ph != "ˈ" && ph != "ˌ" {
                    wordPhCount++
                }
            }

            // Prosody構築 + トークン追加
            for _, ph := range wordPhonemes {
                a2 := 0
                if ph == "ˈ" {
                    a2 = 2 // primary stress
                }
                phs = append(phs, ph)
                pro = append(pro, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhCount})
            }

            needSpace = true
        }
    }

    // PUA変換 (MapSequence)
    phs = MapSequence(phs)

    return &PhonemizeResult{Tokens: phs, Prosody: pro, EOSToken: eos}, nil
}
```

### 2.4 Prosodyマッピング規則

| フィールド | 値 | 決定方法 |
|---|---|---|
| A1 | 常に 0 | スウェーデン語では未使用 (JA: accent pos, ZH: tone) |
| A2 | 0 or 2 | `"ˈ"` トークン → 2 (primary stress), それ以外 → 0 |
| A3 | int | 単語内の音素数 (`"ˈ"`, `"ˌ"` を除外してカウント) |

**句読点/スペースの Prosody**: `&ProsodyInfo{}` (全フィールド0) — Go のゼロ値。

### 2.5 EOS追跡

句読点トークン中の `?` または `!` を検出し、EOSToken を更新する。パイプライン終了時の最終値が `PhonemizeResult.EOSToken` になる。

| 入力テキスト | EOSToken |
|---|---|
| `Hej!` | `!` |
| `Vad heter du?` | `?` |
| `Jag heter Erik.` | `$` (デフォルト、`.`は更新しない) |
| `Hej! Hur mår du?` | `?` (最後の句読点) |

この動作は `french.go` / `spanish.go` と同一パターン。

### 2.6 MapSequence によるPUA変換

`MapSequence` (既存の `pua.go` で提供) は多文字IPA表記を単一PUAコードポイントに変換する。M1で登録済みのスウェーデン語長母音9エントリが対象:

| IPA表記 | PUA | 説明 |
|---|---|---|
| `iː` | U+E059 | 長i |
| `yː` | U+E05A | 長y |
| `eː` | U+E05B | 長e |
| `ɛː` | U+E05C | 長ä |
| `øː` | U+E05D | 長ö |
| `ɑː` | U+E05E | 長a |
| `oː` | U+E05F | 長å/o |
| `uː` | U+E060 | 長o (デフォルト) |
| `ʉː` | U+E061 | 長u |

`MapSequence` は `PhonemizeWithProsody` の最終ステップで呼ばれ、Prosody配列のインデックスは変わらない (1:1対応が維持される)。

### 2.7 Phonemizerインターフェース準拠

```go
// SwedishPhonemizer implements rule-based G2P for Swedish.
type SwedishPhonemizer struct{}

func NewSwedishPhonemizer() *SwedishPhonemizer     { return &SwedishPhonemizer{} }
func (p *SwedishPhonemizer) LanguageCode() string { return "sv" }
func (p *SwedishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) { ... }

// コンパイル時インターフェース準拠チェック
var _ Phonemizer = (*SwedishPhonemizer)(nil)
```

`phonemizer.go` で定義されたインターフェース:

```go
type Phonemizer interface {
    PhonemizeWithProsody(text string) (*PhonemizeResult, error)
    LanguageCode() string
}
```

### 2.8 具体的な入出力例

#### 例1: `gata` (基本ケース)

```
入力: "gata"
正規化: "gata"
トークン: [Word("gata")]
svDetectStress("gata") → 0 (デフォルト, 第1音節)
svConvertWordNative → ["ɡ", "ɑː", "t", "a"]
svApplyRetroflex → ["ɡ", "ɑː", "t", "a"] (変化なし)
svInsertStressMarker(_, 0) → ["ˈ", "ɡ", "ɑː", "t", "a"]
A3 = 4 (ˈ除外)
MapSequence → ["ˈ", "ɡ", "\uE05E", "t", "a"]  (ɑː → PUA)

Tokens:  ["ˈ", "ɡ", "\uE05E", "t", "a"]
Prosody: [{0,2,4}, {0,0,4}, {0,0,4}, {0,0,4}, {0,0,4}]
EOS: "$"
```

#### 例2: `kort hus` (レトロフレックス + 複数単語)

```
入力: "kort hus"
正規化: "kort hus"
トークン: [Word("kort"), Word("hus")]

--- kort ---
svDetectStress("kort") → 0
svConvertWordNative → ["k", "ɔ", "r", "t"]
svApplyRetroflex → ["k", "ɔ", "ʈ"]
svInsertStressMarker(_, 0) → ["ˈ", "k", "ɔ", "ʈ"]
A3 = 3

--- hus ---
svDetectStress("hus") → 0
svConvertWordNative → ["h", "ʉː", "s"]
svApplyRetroflex → ["h", "ʉː", "s"] (変化なし)
svInsertStressMarker(_, 0) → ["ˈ", "h", "ʉː", "s"]
A3 = 3

MapSequence → ["ˈ", "k", "ɔ", "ʈ", " ", "ˈ", "h", "\uE061", "s"]

Tokens:  ["ˈ", "k", "ɔ", "ʈ", " ", "ˈ", "h", "\uE061", "s"]
Prosody: [{0,2,3}, {0,0,3}, {0,0,3}, {0,0,3}, {0,0,0}, {0,2,3}, {0,0,3}, {0,0,3}, {0,0,3}]
EOS: "$"
```

#### 例3: `Vad heter du?` (機能語 + 疑問符)

```
入力: "Vad heter du?"
正規化: "vad heter du?"
トークン: [Word("vad"), Word("heter"), Word("du"), Punct("?")]

--- vad (非機能語) ---
svDetectStress("vad") → 0 (単音節)
A3 = 3 (推定)

--- heter ---
svDetectStress("heter") → 0 (デフォルト)
A3 = 4 (推定)

--- du (機能語) ---
svDetectStress("du") → -1 (機能語)
svInsertStressMarker(_, -1) → ストレスマーカーなし
A3 = 2 (推定)

--- ? (句読点) ---
EOS更新: "?" → eos = "?"

EOS: "?"
```

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 統合担当 | `svPhonemizeWord` 統合関数, `PhonemizeWithProsody` メソッド, EOS追跡ロジック, Prosody構築, `var _ Phonemizer = (*SwedishPhonemizer)(nil)` コンパイルチェック, `NewSwedishPhonemizer`, `LanguageCode` | 1 |

**合計: 1 エージェント**

本チケットは既存コンポーネント (M2 + T-M3-01 + T-M3-02) の結合であり、新規アルゴリズムの実装は少ない。`french.go` / `spanish.go` の既存パターンを踏襲するため、1名で統合可能。

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svPhonemizeWord(word string) []string` — 単語レベルのパイプライン統合
- `SwedishPhonemizer` 構造体の完成
  - `NewSwedishPhonemizer() *SwedishPhonemizer`
  - `LanguageCode() string` → `"sv"`
  - `PhonemizeWithProsody(text string) (*PhonemizeResult, error)`
- `var _ Phonemizer = (*SwedishPhonemizer)(nil)` コンパイル時チェック
- EOS追跡ロジック (`?`, `!` → EOSToken更新)
- Prosody構築 (A1=0, A2=stress, A3=wordPhonemeCount)

**含まない:**
- `unicode_detect.go` へのSV言語検出追加 (M5)
- `multilingual.go` へのSV統合 (M5)
- `synthesize.go` のレジストリ登録 (M5)
- テストファイル作成 (M4)

### 4.2 テスト項目

| # | カテゴリ | 件数 | 内容 |
|---|---------|------|------|
| 1 | Tokens/Prosody長さ一致 | 3 | 単一単語/複数単語/句読点付き |
| 2 | A1値 | 2 | 常に0であること |
| 3 | A2値 | 3 | ストレスマーカー=2, 通常音素=0, 機能語=全0 |
| 4 | A3値 | 3 | ストレスマーカー除外の正確な音素数 |
| 5 | EOS追跡 | 4 | デフォルト($), 疑問符(?), 感嘆符(!), 複数句読点 |
| 6 | PUA変換 | 3 | 長母音がPUAに変換済み, 短母音は変換なし |
| 7 | スペース挿入 | 2 | 単語間スペース, 句読点前スペースなし |
| 8 | インターフェース準拠 | 1 | `var _ Phonemizer = (*SwedishPhonemizer)(nil)` コンパイル |
| 9 | 空入力/句読点のみ | 2 | 空文字列, "..." |

### 4.3 Unitテスト

```go
func TestSvPhonemizeWithProsody_TokensProsodyLength(t *testing.T) {
    p := NewSwedishPhonemizer()
    tests := []struct {
        text string
    }{
        {"gata"},
        {"kort hus"},
        {"Hej, hur mår du?"},
    }
    for _, tt := range tests {
        t.Run(tt.text, func(t *testing.T) {
            result, err := p.PhonemizeWithProsody(tt.text)
            if err != nil {
                t.Fatalf("unexpected error: %v", err)
            }
            if len(result.Tokens) != len(result.Prosody) {
                t.Errorf("len(Tokens)=%d != len(Prosody)=%d",
                    len(result.Tokens), len(result.Prosody))
            }
        })
    }
}

func TestSvPhonemizeWithProsody_EOS(t *testing.T) {
    p := NewSwedishPhonemizer()
    tests := []struct {
        text    string
        wantEOS string
    }{
        {"hej", "$"},
        {"hej!", "!"},
        {"vad?", "?"},
        {"hej! hur?", "?"},
    }
    for _, tt := range tests {
        t.Run(tt.text, func(t *testing.T) {
            result, err := p.PhonemizeWithProsody(tt.text)
            if err != nil {
                t.Fatalf("unexpected error: %v", err)
            }
            if result.EOSToken != tt.wantEOS {
                t.Errorf("EOSToken = %q, want %q", result.EOSToken, tt.wantEOS)
            }
        })
    }
}

func TestSvPhonemizeWithProsody_Prosody(t *testing.T) {
    p := NewSwedishPhonemizer()
    result, err := p.PhonemizeWithProsody("gata")
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    // A1 は常に0
    for i, pi := range result.Prosody {
        if pi.A1 != 0 {
            t.Errorf("Prosody[%d].A1 = %d, want 0", i, pi.A1)
        }
    }

    // ˈ トークンの A2 は 2
    for i, tok := range result.Tokens {
        if tok == "ˈ" && result.Prosody[i].A2 != 2 {
            t.Errorf("stress marker Prosody[%d].A2 = %d, want 2", i, result.Prosody[i].A2)
        }
    }
}

func TestSvPhonemizeWithProsody_PUA(t *testing.T) {
    p := NewSwedishPhonemizer()
    result, err := p.PhonemizeWithProsody("gata") // ɑː → PUA U+E05E
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    // 長母音がPUAに変換されていることを確認
    hasPUA := false
    for _, tok := range result.Tokens {
        for _, r := range tok {
            if r >= 0xE000 && r <= 0xF8FF {
                hasPUA = true
            }
        }
    }
    if !hasPUA {
        t.Errorf("expected PUA codepoint in tokens for long vowel, got: %v", result.Tokens)
    }
}

func TestSvPhonemizeWithProsody_MapSequence(t *testing.T) {
    p := NewSwedishPhonemizer()
    result, err := p.PhonemizeWithProsody("hus") // ʉː → PUA U+E061
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    // MapSequence後もTokensとProsodyの長さが一致
    if len(result.Tokens) != len(result.Prosody) {
        t.Errorf("after MapSequence: len(Tokens)=%d != len(Prosody)=%d",
            len(result.Tokens), len(result.Prosody))
    }
}

// コンパイル時インターフェース準拠チェック
var _ Phonemizer = (*SwedishPhonemizer)(nil)
```

### 4.4 E2Eテスト

M4で実施する文レベルの統合テスト例:

| 入力テキスト | 検証項目 |
|---|---|
| `Hej, jag heter Erik.` | Tokens/Prosody長さ一致, "jag"が機能語(A2全0), EOS=`$` |
| `Vad heter du?` | EOS=`?`, "du"が機能語 |
| `kort barn` | ʈ含む (kort), ɳ含む (barn) |
| `station` | ˈが第2音節, ɧ含む (-tion), PUA含む (uː) |
| (空文字列) | Tokens空, Prosody空, エラーなし |

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **MapSequenceとProsodyのインデックス対応**: `MapSequence` は多文字トークンを単一PUAに変換するが、トークン数は変わらない (1:1変換)。Prosody配列のインデックスは維持される。Go既存実装 (`french.go` L475, `spanish.go` L23) と同一のパターンなので安全。
2. **EOS追跡の `.` 扱い**: Python/Rust参照実装では `.` はEOS更新しない (`$` のまま)。Go の `french.go` / `spanish.go` と同様に `?` と `!` のみ更新する。
3. **ローンワード接尾辞のストレス位置**: 接尾辞にストレスが吸引された場合、stem部分の `stemStressed` を `-1` に設定する処理が `svPhonemizeWord` 内で必要。Python/Rust参照実装と同一のロジック。
4. **`needSpace` フラグのリセット**: 句読点トークンの後に `needSpace` をリセットする必要があるか検討。既存パターン (`french.go`) では句読点後も `needSpace` は変更せず、次の Word トークンでスペースが挿入されない (句読点は前の単語に隣接)。ただし `spanish.go` では `needSpace = false` にリセットしている。**Python SV参照実装に合わせて、句読点後は `needSpace` をリセットしない** (句読点は独立トークンとして扱い、後続単語の前にスペースを挿入する) が正しい動作。

### 5.2 レビューチェックリスト

- [ ] `svPhonemizeWord` のパイプライン順序: stress検出 → ローンワード/ネイティブG2P → レトロフレックス → マーカー挿入
- [ ] `PhonemizeWithProsody` の返り値型が `(*PhonemizeResult, error)`
- [ ] `len(Tokens) == len(Prosody)` が常に成立
- [ ] `MapSequence` 呼び出しが最終ステップ (Prosody構築後)
- [ ] EOS追跡: `?` → `"?"`, `!` → `"!"`, `.` → 更新なし (デフォルト `"$"`)
- [ ] 機能語のA2が全て0 (ストレスマーカーなし)
- [ ] A3のカウントでストレスマーカー (`"ˈ"`, `"ˌ"`) を除外
- [ ] 空テキスト入力でpanic/errorしない (空のPhonemizeResult返却)
- [ ] `var _ Phonemizer = (*SwedishPhonemizer)(nil)` コンパイル通過
- [ ] `go build ./phonemize/...` 成功
- [ ] `go vet ./phonemize/...` エラーなし

## 6. 一から作り直すとしたら

- **ストリーミングパイプライン**: 現在はバッチ処理 (テキスト全体を受け取り、全トークンを処理して返す) だが、大量テキストでは文単位のストリーミングが効率的。Go のチャネルを使えば `func (p *SwedishPhonemizer) Stream(ctx context.Context, text string) <-chan PhonemizeResult` のようなAPIが可能。ただし現在の他言語実装がバッチ処理なので統一性を優先。
- **エラーハンドリングの拡充**: 現在の実装ではエラーを返すケースがほぼない (規則ベースG2Pは常に何らかの出力を生成)。将来辞書ルックアップ (I/Oエラー) を追加する場合にエラー型を活用。
- **Prosody構造体の共通化**: `A1=0` をハードコードしているが、将来スウェーデン語のtone accent (accent 1 vs accent 2) を導入する場合、A1に値を設定する拡張が必要になる。その場合は `svPhonemizeWord` がストレス情報だけでなくアクセント情報も返すように変更する。

## 7. 後続タスクへの連絡事項

- **T-M4 (テストスイート) への連絡**: `PhonemizeWithProsody` の統合テストは ~10件 (文レベル)、Prosody整合性テストは ~5件を予定。テストでは以下の不変条件を検証すること:
  1. `len(Tokens) == len(Prosody)` が常に成立
  2. 全ての `Prosody[i].A1 == 0`
  3. `Tokens[i] == "ˈ"` ↔ `Prosody[i].A2 == 2`
  4. 機能語の全Prosody要素で `A2 == 0`
  5. PUAコードポイント (0xE059-0xE061) が長母音の位置にのみ出現
- **T-M5 (マルチリンガル統合) への連絡**: `SwedishPhonemizer` は `Phonemizer` インターフェースを実装済みなので、以下の3箇所に登録するだけで統合完了:
  1. `unicode_detect.go` — SV文字/機能語検出ロジック追加
  2. `multilingual.go` — ラテン語言語リストにSV追加
  3. `synthesize.go` — `case "sv": return phonemize.NewSwedishPhonemizer(), nil`
- **CI (go-ci.yml) への連絡**: M3完了時点で `go build ./phonemize/...` が成功することを確認。テスト実行はM4でテストファイル追加後に有効化。
