# Go — ZH-EN Loanword 実装

> Index: [`README.md`](README.md)

## 1. 実装ファイル

| 用途 | パス |
|------|------|
| Phonemizer | `src/go/phonemize/chinese.go` (662 行) |
| Multilingual | `src/go/phonemize/multilingual.go` + `unicode_detect.go` |
| 辞書データ | `src/go/phonemize/data/zh_en_loanword.json` |
| Loanword 実装 | `src/go/phonemize/loanword.go` (新規) |
| テスト | `src/go/phonemize/chinese_test.go` (25+ 関数、500+ ケース、golden test あり) |

## 2. 現状調査

| 項目 | 状態 |
|------|------|
| pinyin → IPA 関数 | `zhSplitPinyin()` / `zhPinyinToIPA()` / `zhNormalizePinyin()` / `zhApplyToneSandhi()` |
| 公開関数 | `NewChinesePhonemizer(...)`, `PhonemizeWithProsody(...)` |
| データロード | embed なし、`map[rune]string` をプログラム的に注入 |
| Multilingual | `SegmentText` 完備 |
| ZH-EN dispatch | **❌ 未実装 (本 PR で実装)** |
| 関連実装 | **❌ 全て未実装** |

**追加 LOC 見込み**: ~300 行 (新規 `chinese_loanword.go` + `multilingual.go` 拡張)

## 3. `//go:embed` + JSON tag 戦略

**既存パターン**: 現状 `src/go/` 配下で `//go:embed` 使用例なし (全て外部ファイル参照)。`custom_dict.go` で `encoding/json` + `json:""` tag による snake_case → CamelCase mapping は確立。

**推奨ファイル構成**:

```text
src/go/phonemize/
├── data/
│   └── zh_en_loanword.json    ← Python から copy
├── loanword.go                 ← embed + struct + sync.Once
└── loanword_test.go
```

**実装スケッチ**:

```go
package phonemize

import (
    "embed"
    "encoding/json"
    "fmt"
    "sync"
)

//go:embed data/zh_en_loanword.json
var loanwordFS embed.FS

type LoanwordData struct {
    Version        int                 `json:"version"`
    Acronyms       map[string][]string `json:"acronyms"`
    Loanwords      map[string][]string `json:"loanwords"`
    LetterFallback map[string][]string `json:"letter_fallback"`
}

var (
    loanwordOnce sync.Once
    loanwordData *LoanwordData
    loanwordErr  error
)

func LoadLoanwordData() (*LoanwordData, error) {
    loanwordOnce.Do(func() {
        data, err := loanwordFS.ReadFile("data/zh_en_loanword.json")
        if err != nil {
            loanwordErr = fmt.Errorf("read embedded loanword data: %w", err)
            return
        }
        ld := &LoanwordData{}
        if err := json.Unmarshal(data, ld); err != nil {
            loanwordErr = fmt.Errorf("parse loanword JSON: %w", err)
            return
        }
        if err := ld.Validate(); err != nil {
            loanwordErr = fmt.Errorf("validate loanword data: %w", err)
            return
        }
        loanwordData = ld
    })
    return loanwordData, loanwordErr
}

func (ld *LoanwordData) Validate() error {
    if ld.Version < 1 {
        return fmt.Errorf("invalid loanword version: %d", ld.Version)
    }
    for section, m := range map[string]map[string][]string{
        "acronyms":        ld.Acronyms,
        "loanwords":       ld.Loanwords,
        "letter_fallback": ld.LetterFallback,
    } {
        for k, v := range m {
            if len(v) == 0 {
                return fmt.Errorf("'%s.%s' must be non-empty list[str]", section, k)
            }
        }
    }
    return nil
}
```

**設計判断**:

| 項目 | 採用 | 理由 |
|------|-----|------|
| `embed.FS` (vs `[]byte`) | ◯ | バイナリサイズ同等、型安全、拡張性 |
| `sync.Once` lazy load | ◯ | init() オーバーヘッド回避、エラー処理明示 |
| `json:""` snake_case tag | ◯ | 既存 `custom_dict.go` 慣例 |
| `Validate()` メソッド | ◯ | schema 整合性、早期エラー検出 |
| `fmt.Errorf("%w", err)` wrap | ◯ | 既存コード慣習、エラーチェーン |

## 4. エラーハンドリング

wrapped `error` (`fmt.Errorf("%w", ...)`):

```go
return fmt.Errorf("zh-en loanword: '%s.%s' must be list[str]: %w", section, key, err)
```

メッセージテンプレート (全ランタイム共通):

```text
{path}: '{section}.{key}' must be list[str], got {actual_type}
```

## 5. メモリ管理

package-level `sync.Once` + global var、immutable design で各 instance が参照を共有。

## 6. テスト戦略

共有 fixture (`src/go/phonemize/testdata/zh_en_loanword_matrix.json`) からロードしてサブテスト展開。

## 7. ベンチマーク

| フレーム | ファイル |
|--------|--------|
| `testing.B` | `src/go/phonemize/bench_test.go` |

## 8. カバレッジ

`go test -coverprofile` 経由で 80%+ 目標 (CI 新規追加が必要)。
