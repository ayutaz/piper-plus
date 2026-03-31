# T-M3-01: レトロフレックス同化

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M3: 後処理 + Phonemizer統合 |
| 依存チケット | T-M2 (G2Pコアエンジン完了 — `svConvertWordNative`, `svPhonemizeWord` が動作すること) |
| 後続チケット | T-M3-02 (ストレス検出 + マーカー挿入), T-M3-03 (PhonemizeWithProsody統合) |
| 対象ファイル | `src/go/phonemize/swedish.go` |
| 推定行数 | ~80行 (関数本体 + 定数 + ヘルパー) |

## 1. タスク目的とゴール

M2で生成された単語レベルの音素列に対し、レトロフレックス同化 (retroflex assimilation) の後処理を適用する関数 `svApplyRetroflex` を実装する。

スウェーデン語では `r` の直後に `{t, d, s, n, l}` が来ると反舌音に同化し、さらに `{ʈ, ɖ, ʂ, ɳ}` は後続子音にカスケード伝播する。このルールは単語内の音素列を入力として受け取り、同化適用済みの音素列を返す。

**ゴール:**
- 3状態機械 (NORMAL / R_DETECTED / CASCADING) による正確な同化処理
- `rr` ジェミネートのブロック (同化なし)
- `ɭ` でのカスケード停止
- Python (`swedish.py:apply_retroflex`) / Rust (`swedish.rs:apply_retroflex`) と同一の出力

## 2. 実装する内容の詳細

### 2.1 レトロフレックス変換マップ

| 入力音素 | 出力音素 | Unicode | カスケード伝播 |
|---|---|---|---|
| `t` | `ʈ` | U+0288 | Yes (継続) |
| `d` | `ɖ` | U+0256 | Yes (継続) |
| `s` | `ʂ` | U+0282 | Yes (継続) |
| `n` | `ɳ` | U+0273 | Yes (継続) |
| `l` | `ɭ` | U+026D | **No (停止)** |

Go定数として定義:

```go
var svRetroflexMap = map[string]string{
    "t": "\u0288", // ʈ
    "d": "\u0256", // ɖ
    "s": "\u0282", // ʂ
    "n": "\u0273", // ɳ
    "l": "\u026d", // ɭ
}

var svPropagatingRetroflexes = map[string]bool{
    "\u0288": true, // ʈ
    "\u0256": true, // ɖ
    "\u0282": true, // ʂ
    "\u0273": true, // ɳ
    // ɭ (U+026D) は含まない — カスケード停止
}
```

### 2.2 状態機械の遷移表

```
状態           + 入力              → 遷移先         出力動作
─────────────────────────────────────────────────────────────────
NORMAL         + "r"               → R_DETECTED     (何も出力しない、rを保留)
NORMAL         + その他            → NORMAL         入力をそのまま出力

R_DETECTED     + "r"               → NORMAL         "r", "r" を出力 (ジェミネートブロック)
R_DETECTED     + {t,d,s,n}         → CASCADING      変換後の反舌音を出力
R_DETECTED     + "l"               → NORMAL         "ɭ" を出力 (カスケード停止)
R_DETECTED     + その他            → NORMAL         保留した "r" + 入力を出力

CASCADING      + {t,d,s,n}         → CASCADING      変換後の反舌音を出力 (伝播継続)
CASCADING      + "l"               → NORMAL         "ɭ" を出力 (カスケード停止)
CASCADING      + その他            → NORMAL         入力をそのまま出力 (伝播停止)
```

**終端処理:** ループ終了時に `state == R_DETECTED` なら保留中の `"r"` を出力する。

### 2.3 状態機械の図

```
                    "r"
            ┌──────────────┐
            │              ▼
        ┌───────┐     ┌───────────┐
        │NORMAL │     │R_DETECTED │
        └───┬───┘     └─────┬─────┘
            ▲               │
            │  その他/rr    │ {t,d,s,n} → 反舌音
            │  ┌────────────┘
            │  │   "l" → ɭ
            │  ▼
        ┌─────────┐
        │CASCADING│──── {t,d,s,n} → 反舌音 (自己遷移)
        └─────────┘
            │ "l" → ɭ / その他 → NORMAL
            ▼
          NORMAL
```

### 2.4 関数シグネチャ

```go
// svApplyRetroflex applies retroflex assimilation to a phoneme sequence.
// r + {t,d,s,n,l} → {ʈ,ɖ,ʂ,ɳ,ɭ}.
// Geminate rr blocks assimilation.
// Cascade: {ʈ,ɖ,ʂ,ɳ} propagate; ɭ stops.
func svApplyRetroflex(phonemes []string) []string
```

### 2.5 疑似コード

```go
func svApplyRetroflex(phonemes []string) []string {
    result := make([]string, 0, len(phonemes))
    state := stateNormal // iota定数: stateNormal, stateRDetected, stateCascading

    for _, ph := range phonemes {
        switch state {
        case stateNormal:
            if ph == "r" {
                state = stateRDetected
            } else {
                result = append(result, ph)
            }

        case stateRDetected:
            if ph == "r" {
                // ジェミネートブロック
                result = append(result, "r", "r")
                state = stateNormal
            } else if retro, ok := svRetroflexMap[ph]; ok {
                result = append(result, retro)
                if svPropagatingRetroflexes[retro] {
                    state = stateCascading
                } else {
                    state = stateNormal // ɭ停止
                }
            } else {
                // r + 非同化対象
                result = append(result, "r", ph)
                state = stateNormal
            }

        case stateCascading:
            if retro, ok := svRetroflexMap[ph]; ok {
                result = append(result, retro)
                if !svPropagatingRetroflexes[retro] {
                    state = stateNormal // ɭ停止
                }
            } else {
                result = append(result, ph)
                state = stateNormal
            }
        }
    }

    // 終端フラッシュ
    if state == stateRDetected {
        result = append(result, "r")
    }
    return result
}
```

### 2.6 具体例

| 入力単語 | G2P出力 (M2) | レトロフレックス後 | 説明 |
|---|---|---|---|
| kort | `k ɔ r t` | `k ɔ ʈ` | r+t → ʈ |
| barn | `b ɑː r n` | `b ɑː ɳ` | r+n → ɳ |
| karl | `k ɑː r l` | `k ɑː ɭ` | r+l → ɭ (停止) |
| borr | `b ɔ r r` | `b ɔ r r` | rr ジェミネートブロック |
| forst | `f ɔ r s t` | `f ɔ ʂ ʈ` | r+s → ʂ, カスケード s→t → ʈ |
| karl+s | `k ɑː r l s` | `k ɑː ɭ s` | ɭ でカスケード停止、s は変換されない |
| bar | `b ɑː r` | `b ɑː r` | 語末 r は変換なし (終端フラッシュ) |

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 実装担当 | `svRetroflexMap`, `svPropagatingRetroflexes` 定数定義, `svApplyRetroflex` 関数実装, 状態定数 (iota) 定義 | 1 |

**合計: 1 エージェント**

このタスクはスコープが小さく (~80行)、依存関係も単純 (M2の出力音素列を入力として受け取る) なため、1名で十分。

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `svRetroflexMap` 定数 (5エントリ)
- `svPropagatingRetroflexes` 定数 (4エントリ)
- 状態定数 (`stateNormal`, `stateRDetected`, `stateCascading`)
- `svApplyRetroflex(phonemes []string) []string` 関数

**含まない:**
- ストレス検出/マーカー挿入 (T-M3-02)
- `PhonemizeWithProsody` 統合 (T-M3-03)
- テストファイル作成 (M4)

### 4.2 テスト項目

| # | カテゴリ | 件数 | 内容 |
|---|---------|------|------|
| 1 | 基本5変換 | 5 | r+t→ʈ, r+d→ɖ, r+s→ʂ, r+n→ɳ, r+l→ɭ |
| 2 | ジェミネートブロック | 2 | rr→r+r, 語中rrの前後保全 |
| 3 | カスケード伝播 | 3 | r+s+t→ʂ+ʈ, r+n+d→ɳ+ɖ, r+t+s→ʈ+ʂ |
| 4 | ɭ停止 | 2 | r+l+t→ɭ+t (tは変換されない), r+l+s→ɭ+s |
| 5 | 非同化対象 | 2 | r+a→r+a, r+k→r+k |
| 6 | 終端フラッシュ | 1 | 末尾r→r出力 |
| 7 | 空入力/rなし | 2 | []→[], [a,b,c]→[a,b,c] |

### 4.3 Unitテスト

```go
func TestSvApplyRetroflex(t *testing.T) {
    tests := []struct {
        name   string
        input  []string
        want   []string
    }{
        {"r+t", []string{"k", "ɔ", "r", "t"}, []string{"k", "ɔ", "ʈ"}},
        {"r+d", []string{"b", "ɑː", "r", "d"}, []string{"b", "ɑː", "ɖ"}},
        {"r+s", []string{"f", "øː", "r", "s"}, []string{"f", "øː", "ʂ"}},
        {"r+n", []string{"b", "ɑː", "r", "n"}, []string{"b", "ɑː", "ɳ"}},
        {"r+l", []string{"k", "ɑː", "r", "l"}, []string{"k", "ɑː", "ɭ"}},
        {"rr geminate", []string{"b", "ɔ", "r", "r"}, []string{"b", "ɔ", "r", "r"}},
        {"cascade r+s+t", []string{"f", "ɔ", "r", "s", "t"}, []string{"f", "ɔ", "ʂ", "ʈ"}},
        {"ɭ stops cascade", []string{"r", "l", "t"}, []string{"ɭ", "t"}},
        {"r+vowel", []string{"r", "a"}, []string{"r", "a"}},
        {"trailing r", []string{"b", "ɑː", "r"}, []string{"b", "ɑː", "r"}},
        {"empty", []string{}, []string{}},
        {"no r", []string{"a", "b", "c"}, []string{"a", "b", "c"}},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := svApplyRetroflex(tt.input)
            if !slices.Equal(got, tt.want) {
                t.Errorf("svApplyRetroflex(%v) = %v, want %v", tt.input, got, tt.want)
            }
        })
    }
}
```

### 4.4 E2Eテスト

E2Eテストは T-M3-03 完了後にM4で実施。代表例:

| 入力テキスト | 期待: 含む音素 |
|---|---|
| `kort` | `ʈ` (r+t同化) |
| `barn` | `ɳ` (r+n同化) |
| `först` | `ʂ` かつ `ʈ` (カスケード) |
| `borr` | `r r` (ジェミネート) |

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **語境界での同化**: 現在の実装は単語内のみ適用。Python/Rust参照実装も同様に単語内のみ。語間レトロフレックス (cross-word) は将来課題。
2. **多文字音素の扱い**: M2の出力が `[]string` の各要素として1音素を保持する前提。長母音は `"ɑː"` のように1要素。レトロフレックスマップのキーは全て単一文字音素 (`"t"`, `"d"` 等) なので衝突しない。
3. **カスケード深度の理論上限**: 実用上 r+C+C+C のような3連鎖が最大 (`först` = r+s+t)。無限ループのリスクはない (カスケード対象が5子音に限定され、いずれも入力を消費する)。

### 5.2 レビューチェックリスト

- [ ] `svRetroflexMap` の5エントリが Python `RETROFLEX_MAP` と一致
- [ ] `svPropagatingRetroflexes` の4エントリが Python `PROPAGATING_RETROFLEXES` と一致 (ɭ 除外)
- [ ] 状態機械が3状態 (NORMAL/R_DETECTED/CASCADING) で遷移表通り
- [ ] `rr` ジェミネートが NORMAL に正しく戻る (R_DETECTED + "r" → 2つの "r" 出力)
- [ ] `ɭ` でカスケードが停止する (CASCADING + "l" → NORMAL)
- [ ] 終端 `r` がフラッシュされる (state == R_DETECTED のまま終了 → "r" 出力)
- [ ] 空スライス入力で panic しない
- [ ] `go vet ./phonemize/...` エラーなし

## 6. 一から作り直すとしたら

この関数は状態機械のパターンが明確で、Python/Rust両方の参照実装が安定しているため、大きな設計変更は不要。強いて言えば:

- **状態を構造体メソッドにする**: 現在の関数型アプローチ (ローカル変数 `state`) で十分だが、将来 cross-word 同化を追加する場合は `retroflexProcessor` 構造体に状態を持たせ、`Feed(phoneme)` / `Flush()` メソッドで段階的に処理するストリーミングパターンが有用。
- **マップキーを `rune` にする**: 現在は `string` キーだが、レトロフレックス対象は全て単一文字なので `rune` キーにすればアロケーションを削減できる。ただし Go の既存パターン (`french.go` 等) が `string` ベースなので統一性を優先。

## 7. 後続タスクへの連絡事項

- **T-M3-02 (ストレス検出) への連絡**: `svApplyRetroflex` はストレス検出よりも**前**に呼ばれる。パイプライン順序: G2P → レトロフレックス → ストレス検出 → ストレスマーカー挿入。ストレス検出は正規化テキスト (`word string`) に対して行われるため、レトロフレックスの出力には依存しない。
- **T-M3-03 (PhonemizeWithProsody) への連絡**: `svApplyRetroflex` の呼び出し位置は `phonemize_word` 関数内で、Stage 5 として `svConvertWordNative` の出力に適用される。T-M3-03 では `svPhonemizeWord` 内部で既に呼び出し済みの結果を受け取る形になる。
- **M4 (テストスイート) への連絡**: レトロフレックスのテストは ~15件を予定。カスケード深度2 (`först` パターン) と ɭ停止の検証が重要。
