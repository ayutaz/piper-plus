# TICKET-02: Go ZH-EN Code-Switching 実装

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-02 |
| **マイルストーン** | Phase 2 (Day 4-5) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §2.2 / §4.1 G1-G5 / §8.10 (`//go:embed` + sync.Once) |
| **ステータス** | 📝 Draft |
| **依存元** | なし (TICKET-01 とは独立並列可) |
| **依存先** | TICKET-06 (CI Sync) |
| **追加 LOC** | ~355 (`chinese_loanword.go` 120 + `chinese.go` 100 + `multilingual.go` 50 + テスト 80 + embed 5) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: Go ランタイム (`src/go/phonemize/`) に ZH-EN code-switching を実装する。Python 実装と byte-for-byte 一致する出力を返す。

**ゴール**:
- `PhonemizeEmbeddedEnglish(text string, data *LoanwordData) []string` が公開関数として動作する。
- `MultilingualPhonemizer` が `[zh, en, *]` パターンを自動 dispatch する。
- `data/zh_en_loanword.json` を `//go:embed` で同梱、`sync.Once` でロード。
- Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件が Python と同一の IPA 列を返す。
- 既存の純中国語経路の性能劣化が **<5%**。
- `go test ./...` の追加実行時間が **<1 秒**。

---

## 2. 実装する内容の詳細

### G1. `chinese_loanword.go` 新規 (Loanword struct + load)

設計書 §8.10 のスケッチを採用。場所: `src/go/phonemize/chinese_loanword.go`。

```go
package phonemize

import (
    "embed"
    "encoding/json"
    "fmt"
    "strings"
    "sync"
    "unicode"
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

func LoadLoanwordData() (*LoanwordData, error) { /* §8.10 参照 */ }

func (ld *LoanwordData) Validate() error {
    // section と key を含むエラー文言で Python と一致させる
    // f"{path}: '{section}.{key}' must be list[str]"
}
```

**Schema validation**: 値が `[]string` でないものを検出して `fmt.Errorf("data/zh_en_loanword.json: '%s.%s' must be list[str], got %v", section, key, value)` を返す。Python の文言と完全一致。

### G2. `chinese.go` の `PhonemizeEmbeddedEnglish` 関数追加

```go
func (cp *ChinesePhonemizer) PhonemizeEmbeddedEnglish(
    text string,
    data *LoanwordData,
) []string {
    var result []string
    for _, raw := range tokenizeEnglishWords(text) {
        stripped := stripTrailingPunctuation(raw)
        if syllables := lookup(stripped, data); syllables != nil {
            for _, syl := range syllables {
                pinyinSplit := zhSplitPinyin(syl)
                ipa := zhPinyinToIPA(pinyinSplit)
                result = append(result, ipa...)
            }
        }
    }
    return result
}
```

**Lookup 優先度** (Python と一致):
1. `data.Loanwords[stripped]` — case-sensitive
2. `data.Acronyms[strings.ToUpper(stripped)]`
3. `data.LetterFallback[strings.ToUpper(string(ch))]` — char-by-char、`unicode.IsDigit(ch)` は drop

### G3. `multilingual.go` dispatch 追加

```go
for i, segment := range segments {
    if segment.Lang == "en" && hasZh {
        prevIsZh := i > 0 && segments[i-1].Lang == "zh"
        nextIsZh := i+1 < len(segments) && segments[i+1].Lang == "zh"
        if prevIsZh || nextIsZh {
            tokens := chinesePhonemizer.PhonemizeEmbeddedEnglish(
                segment.Text, loanwordData,
            )
            result = append(result, tokens...)
            continue
        }
    }
    // 既存の英語経路
    result = append(result, englishPhonemizer.Phonemize(segment.Text)...)
}
```

### G4. `//go:embed` で JSON 埋め込み

`src/go/phonemize/data/zh_en_loanword.json` を Python source からコピー。`go:embed` ディレクティブで static asset として bundle。`go build -tags wasm` でも動作確認。

### G5. テスト追加

#### Unit テスト (`chinese_loanword_test.go`)

| テスト名 | 内容 |
|---------|------|
| `TestPhonemizeEmbeddedEnglish_AcronymGPS` | `GPS` → tone marker 含む IPA 列 |
| `TestPhonemizeEmbeddedEnglish_LoanwordPython` | `Python` (case-sensitive) → `pai4-sen1` 相当 |
| `TestPhonemizeEmbeddedEnglish_ChatGPT` | `ChatGPT` → 5 syllable |
| `TestPhonemizeEmbeddedEnglish_LetterFallback` | `ZZ` → letter_fallback 2 回 |
| `TestPhonemizeEmbeddedEnglish_Empty` | `""` → `[]` |
| `TestLookupPriority_LoanwordBeatsAcronym` | override で loanword 優先 |
| `TestLookupPriority_AcronymBeatsFallback` | override で acronym 優先 |
| `TestCaseSensitivity_PythonVsPYTHON` | case sensitivity |
| `TestPunctuation_TrailingComma` | `GPS,` `GPS.` `GPS` 等価 |
| `TestMultiSegment_TwoEmbeddedEn` | `ChatGPT 和 Python` |
| `TestDigits_Z2Z9EqualsZZ` | digits drop |
| `TestAcronymWithDigits_MP3` | `MP3` 直接ヒット |
| `TestLoadLoanwordData_OnceOnly` | `sync.Once` で 2 回呼んでも同じ pointer |
| `TestValidate_InvalidSchema` | `[]int` を渡すと `Validate()` がエラー |
| `TestEmbedConsistency` | `loanwordFS.ReadFile` の bytes が Python source と一致 |

#### Integration テスト (`multilingual_test.go` 拡張)

| テスト名 | 内容 |
|---------|------|
| `TestZhEnZhPattern` | `请打开 GPS 系统` |
| `TestZhEnPattern_IssueExample` | `请打开 GPS` |
| `TestEnZhPattern` | `Hello 世界` |
| `TestPureZhUnaffected` | regression |
| `TestPureEnUsesG2pEn` | regression |
| `TestIssueExamplePython` | `我喜欢用 Python 写代码` |
| `TestIssueExampleChatGPT` | `让我用 ChatGPT 写代码` |
| `TestJsonMatchesPythonSource` | `data/zh_en_loanword.json` の SHA256 が Python source と一致 |

#### Golden test 拡張 (`testdata/zh_en_golden.txt`)

既存 `testdata/` 構造を踏襲、Python 出力と完全一致する IPA 列を golden として保存し、`go test -update` で更新可能にする。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 責任 |
|------|------|-----|
| **Phase Lead** | 1 | チケット統括、TICKET-01 (Rust) との設計同期確認、Lead 引き継ぎ |
| **Go Dev** | 1 | G1-G4 実装、`embed.FS` + `sync.Once` パターン、`zhSplitPinyin` / `zhPinyinToIPA` の再利用 |
| **QA / Test** | 1 | G5 テスト 23 件、golden test 更新、性能ベンチ |

**並列化**: Dev と QA は同時着手可能。Dev が G1-G2 完了次第、QA がテスト着手 (G3 完了を待たない)。

**コミット推奨**:
- `feat(go): G1+G4 chinese_loanword.go と embed JSON を追加`
- `feat(go): G2+G3 PhonemizeEmbeddedEnglish と multilingual dispatch`
- `test(go): G5 ZH-EN テスト追加`

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- Go module `github.com/ayutaz/piper-plus/src/go/phonemize` の公開 API:
  - `LoadLoanwordData() (*LoanwordData, error)`
  - `(*ChinesePhonemizer).PhonemizeEmbeddedEnglish(text string, data *LoanwordData) []string`
  - `(*MultilingualPhonemizer).Phonemize(text string) []string` (内部 dispatch 拡張)
- `src/go/cmd/piper-plus/` CLI が中国語混在テキストを正しく扱えること
- `data/zh_en_loanword.json` の embed

### Out of scope

- gRPC / プラグイン API
- 別言語ペア (JA-EN, KO-EN)
- Go module versioning (TICKET-07 で実施)

### テスト項目 (設計書 §4.3 統一マトリックス全件)

最低 **23 テスト**を追加。golden file による回帰検出を組み合わせる。

---

## 5. Unit テスト

セクション 2 G5 の Unit テスト 15 件を実装。Go の慣習として `*_test.go` ファイルに配置。Table-driven テストパターンを採用 (`tests := []struct{...}{}` で網羅)。

```go
func TestPhonemizeEmbeddedEnglish_LookupPriority(t *testing.T) {
    cases := []struct {
        name     string
        input    string
        override *LoanwordData
        expected []string
    }{
        {"loanword_beats_acronym", "GPS",
            customData("loanwords:{GPS:[xxx]}", "acronyms:{GPS:[yyy]}"),
            wantLoanwordOutput},
        {"acronym_beats_fallback", "BBC", defaultData(), wantBBC},
        // ...
    }
    for _, c := range cases {
        t.Run(c.name, func(t *testing.T) {
            got := cp.PhonemizeEmbeddedEnglish(c.input, c.override)
            require.Equal(t, c.expected, got)
        })
    }
}
```

---

## 6. E2E テスト

`go run ./cmd/piper-plus` で Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件を音素 dump し、Python (`piper-plus`) の出力と byte 一致させる。

```bash
go run ./cmd/piper-plus \
  --model multilingual-test-medium.onnx \
  --text "请打开 GPS" \
  --language zh-en \
  --output-phonemes phonemes_go.json

diff phonemes_python.json phonemes_go.json  # 期待: 差分ゼロ
```

E2E ケース 3 件 + 純中国語 1 件 + 純英語 1 件 (regression) = 計 5 ケース。

---

## 7. 実装に関する懸念事項

### 懸念 1: `go:embed` のパス制約
- **影響**: `//go:embed data/zh_en_loanword.json` は **同一パッケージ配下** にしか配置できない。
- **緩和**: `src/go/phonemize/data/` を新規作成、`chinese_loanword.go` と同じパッケージに置く。
- **責任**: Go Dev。

### 懸念 2: `sync.Once` のエラー伝播
- **影響**: 1 回目の load でエラーが起きると、以降は永遠に同じエラーを返す (再試行不可)。
- **緩和**: 設計書 §8.9 と整合。default loanword なので欠損は build 時にしか起こらず、ランタイムで再試行が必要なケースなし。`override` 指定時は別 API (`LoadLoanwordDataFromPath(path string)`) を提供して `sync.Once` をバイパス。
- **責任**: Go Dev。

### 懸念 3: `unicode.IsDigit` の Unicode 範囲
- **影響**: ASCII 0-9 以外 (例: 全角数字 ７) を drop しない可能性。
- **緩和**: Python 実装は `str.isdigit()` 使用 (Unicode 全般)。Go では `unicode.IsDigit` を使い、Python と一致する。fixture テストで全角数字ケースを 1 件追加。
- **責任**: QA。

### 懸念 4: `go:embed` の build tag 衝突
- **影響**: `+build wasm` などの build tag を付けるとファイル除外され embed FS が空になる可能性。
- **緩和**: 本機能は build tag を付けない (全 platform で有効)。`go test -tags wasm` でも通ることを CI で確認。
- **責任**: Go Dev。

### 懸念 5: golden test の更新フロー
- **影響**: Python 出力が変わると Go の golden が腐る。
- **緩和**: TICKET-06 で CI に **「Python と Go の golden が一致するか」** チェックを追加。`go test -update` での golden 更新は手動 PR 必須。
- **責任**: QA + DevOps (TICKET-06)。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] `LoanwordData` の field tag が snake_case (`json:"acronyms"` 等)
- [ ] `sync.Once` で 2 回目以降は `loanwordData` をそのまま返す
- [ ] `Validate()` のエラー文言が Python と一致 (`'%s.%s' must be list[str]`)
- [ ] `PhonemizeEmbeddedEnglish` のシグネチャが `(text string, data *LoanwordData) []string` で固定
- [ ] dispatch 条件 `[zh,en,*]` / `[en,zh]` / `[zh,en,zh]` が Python と一致
- [ ] tokenize 時 trailing punctuation を strip (`strings.TrimRight`)
- [ ] digits を `letter_fallback` で drop (`unicode.IsDigit`)
- [ ] 既存 PUA mapping (`pua-contract.toml` 0xE020-0xE04A) と整合
- [ ] `loanwordFS.ReadFile` が Python source と byte 一致
- [ ] table-driven テストで 15 件以上 unit カバー
- [ ] `golangci-lint` 警告ゼロ
- [ ] `go test -race ./...` で race condition 検出ゼロ

### ドキュメントレビュー

- [ ] `src/go/phonemize/README.md` (もしくは `src/go/README.md`) に ZH-EN 例追加
- [ ] `src/go/CHANGELOG.md` に "added: ZH-EN code-switching" 一行
- [ ] godoc コメントを公開 API 全てに付与

---

## 9. 一から作り直すとしたら

> **前提**: v1.0.0 (major bump) を対象。本 PR は §8.11 通り **module の minor タグ** で進める。

### 9.0 思想

| # | 原則 | 説明 |
|---|------|------|
| 1 | **PUA 出力 byte 一致** | 既存学習済みモデルの PUA 0xE020-0xE04A を絶対変えない。 |
| 2 | **Default-on, opt-out 可** | `WithZhEnDispatch(false)` で off。default は on。 |
| 3 | **Graceful failure** | default 欠損 → warning + 空辞書、override 欠損 → error。 |
| 4 | **Single source of truth** | Python JSON が canonical、Go は consumer。 |
| 5 | **`embed.FS` で同梱必須** | 実行時 I/O ゼロ、deploy artifact 単一化。 |
| 6 | **Functional options pattern** | builder ではなく Go の慣習に合わせる。 |
| 7 | **クロス言語 fixture** | `tests/fixtures/g2p/zh_en_loanword_matrix.json` を **CI sync で `testdata/` に複製** (Go の testdata 慣習を尊重)。 |
| 8 | **Rust 設計を Go に直輸入しない** | crate 分離 / proc-macro / phf は Rust 慣習。Go では package 集約 / `embed.FS` / `init()` を選ぶ。 |

### 9.1 データ層

**Go 文化的注記**: `embed.FS` (Go 1.16+) は **データ同梱の de facto 標準**。`go:generate` は protobuf / stringer / mockgen など **型・コードの派生**専用で、JSON → map のような単純展開には使わない。Rust の `phf` を Go に直輸入する必要はない (思想 #8)。

**現状の判断**: 131 entries では `embed.FS` + `sync.Once` で十分。10,000 超えても `init()` 内 eager parse で p99 < 100μs を満たすため、code-gen は基本不要。

| 採用パス | トリガー | 実装 |
|---------|---------|------|
| `embed.FS + sync.Once` (現行案) | エントリ数 < 10,000 | G1 のまま、lazy load |
| `embed.FS + init()` eager parse | エントリ数 ≥ 10,000 OR cold start p99 < 100μs 要件 | `init()` で 1 回 `json.Unmarshal` → package 変数 `loanwordData *LoanwordData` に格納。lazy 不要、`sync.Once` 不要、`map[string][]string` の hash lookup は O(1) |
| `go:generate` で静的 map 生成 | **採用しない** (Go 慣習に逆行) | — |

### 9.2 API 層

```go
// Functional options pattern (Go 慣習)。variadic 追加なので SemVer 互換。
phonemizer, err := phonemize.NewChinesePhonemizer(
    singleCharDict, phraseDict,
    phonemize.WithZhEnDispatch(true),
    phonemize.WithLoanwordSource(LoanwordSourceDefault{}),
    // or phonemize.WithLoanwordSource(LoanwordSourceFile{Path: "custom.json"}),
)
```

**現行 API 互換戦略** (Go の variadic は **SemVer non-breaking**):

| 現行 (v0.x) | 互換戦略 |
|------------|---------|
| `NewChinesePhonemizer(sc, ph)` | **そのまま残す** (variadic 末尾に `opts ...Option` 追加で互換) |
| `LoadLoanwordData()` | 互換 alias として残す。内部で `LoadLoanwordDataWithOptions()` に転送 |

- error 型は `type LoanwordError struct { Path, Section, Key, Expected string }`、`Error()` で Python と同一書式。
- `errors.Is` 対応のため sentinel error (`ErrLoanwordSchema`, `ErrLoanwordIO`) を併用。
- `LoanwordSource` は **sealed type pattern** (Go 慣習): `type LoanwordSource interface { isLoanwordSource() }`、`LoanwordSourceDefault{}` と `LoanwordSourceFile{Path string}` の 2 variant。private method `isLoanwordSource()` で外部実装を封じる。`*string` で nil 許容するパターンは型安全性が低く採用しない。

### 9.3 Dispatcher

**Day 1 (本 PR)**: 現行の `prevIsZh / nextIsZh` 直書きで OK。

**v1.0.0**: pattern table を `var patterns = []CodeSwitchPattern{...}` で declarative 化。JA-EN / KO-EN を追加するときに table 1 行追加で済む。

### 9.4 Module 構成

```
src/go/phonemize/
├── chinese.go                    (既存)
├── chinese_loanword.go           (新規 - 本 PR)
├── chinese_loanword_test.go      (新規 - 本 PR)
├── data/
│   └── zh_en_loanword.json       (新規 - 本 PR)
├── multilingual.go               (拡張 - 本 PR)
└── testdata/
    ├── zh_en_golden.txt          (新規 - 本 PR)
    └── zh_en_matrix.json         (TICKET-06 でクロス言語 fixture を導入)
```

**Sub-package 化はしない**: Rust の crate 分離 (`piper-plus-g2p` / `piper-core`) は依存解決のためだが、Go の sub-package は import path 増加と公開面拡大のコストのみで、ZH-EN 1 機能のために切る必要はない。既存 `chinese.go` (662 行) / `japanese.go` / `korean.go` も同一 `phonemize` package に収まっており、慣習的に正しい。本当に分離が必要なら `internal/loanword/` (外部 import 不可) を選択するが、現状では **同一 package 内で lowercase の未公開 helper を使う** だけで十分。

### 9.5 Failure mode

| ケース | 動作 | エラー型 |
|-------|------|---------|
| default JSON 欠損 (build 時) | **build error** (`go:embed` がエラー) | — |
| override path で file 欠損 | `error` 返却 | `wraps ErrLoanwordIO` |
| schema 違反 | `error` 返却 | `wraps ErrLoanwordSchema`、Python と同文言 |
| JSON parse error (override) | `error` 返却 | `wraps ErrLoanwordParse` |
| `WithZhEnDispatch(false)` | EnglishPhonemizer 経路、loanword は touch しない | — |
| **v1.0.0 拡張**: override hot reload | `ReloadLoanwordData(source LoanwordSource) error` で `atomic.Pointer[LoanwordData]` を差し替え | lock-free、`sync.Once` をバイパス |

`sync.Once` は default 経路のみで使用。override 経路は `atomic.Pointer[LoanwordData]` (Go 1.19+) でマップ風に hot reload 可能にし、永続エラー問題を回避。

### 9.6 i18n 拡張パス

| Phase | 内容 | Go 側変更 |
|-------|------|----------|
| Phase 1 (本 PR) | ZH-EN | `data/zh_en_loanword.json` 1 個 |
| Phase 2 | JA-EN / KO-EN | `data/{ja_en, ko_en}_loanword.json` 追加 + pattern table 拡張 |
| Phase 3 | 任意ペア | `LoanwordRegistry.Register(src, tgt, data)` |

### 9.7 テスト戦略

- **Table-driven test** が Go 慣習。`tests := []struct{name, input, expected}{}` で網羅。
- **Golden file** 更新は `-update` フラグで明示的に。
- **Cross-runtime fixture の運用**: Go の `testdata/` 慣習 (package-local、build から除外) と `tests/fixtures/` (repo-wide) は両立しないため、TICKET-06 の CI sync で **`tests/fixtures/g2p/zh_en_loanword_matrix.json` → `src/go/phonemize/testdata/zh_en_loanword_matrix.json` へ byte-for-byte コピー**する。Go test 側は `os.ReadFile("testdata/...")` で読む。**Symlink は採用しない** (Windows 環境で挙動不安定)。
- `go test -race ./...` で race detection を CI で必須化。

### 9.8 Observability

`log/slog` は **既に `chinese.go` / `multilingual.go` 等で使用中** (`go.mod` は `go 1.26`)。本 PR では新 logger は導入せず、既存 `slog.Debug` / `slog.Warn` を踏襲する。

ログ位置 3 箇所:
- `slog.Debug("loanword hit", "token", tok, "syllables", syl)` — case-sensitive loanword
- `slog.Debug("acronym hit", "token", tok, "uppercase", up, "syllables", syl)` — uppercase acronym
- `slog.Debug("fallback hit", "token", tok, "char", ch, "syllables", syl)` — letter_fallback

`PIPER_DEBUG_ZH_EN=1` env var の扱い: `slog.SetDefault` で **global logger を破壊しない**。代わりに **package-private logger 変数** (`var loanwordLogger *slog.Logger`) を `init()` で env var に応じて初期化。デフォルトは `slog.Default()` 継承、env var ありで `slog.LevelDebug` 固定の handler を差し込む。

---

## 10. 後続タスクへの連絡内容

### TICKET-06 (CI Sync) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **JSON 配置パス** | `src/go/phonemize/data/zh_en_loanword.json` |
| **比較対象** | Python source `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` と byte 一致 |
| **Validation 確認** | `LoadLoanwordData()` を CI で 1 回呼んで `Validate()` を通過確認 |
| **Race detection** | `go test -race ./...` を CI に追加 |

### TICKET-07 (Docs) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **README 追加** | `src/go/README.md` (もしくは `src/go/phonemize/README.md`) に ZH-EN 例 |
| **CHANGELOG** | `[Unreleased]` に "Added: ZH-EN code-switching" |
| **godoc** | `pkg.go.dev` で公開 API が表示されるよう doc comment 必須 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §2.2 / §4.1 G1-G5 / §8.10 から派生、TICKET-01 と整合) |
