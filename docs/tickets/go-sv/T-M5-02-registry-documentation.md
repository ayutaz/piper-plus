# T-M5-02: レジストリ登録 + ドキュメント更新

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M5: マルチリンガル統合 |
| 依存チケット | T-M5-01 (SV言語検出ロジック + マルチリンガル統合) |
| 後続チケット | なし (M5 最終チケット) |
| 対象ファイル | `src/go/piperplus/synthesize.go`, `src/go/README.md` |
| 推定行数 | ~5行 (本体) + ~15行 (README更新) |
| PR | #270 (`feat/go-bindings`) |
| 参照設計 | `docs/design/go-swedish-milestones.md` M5 セクション |

## 1. タスク目的とゴール

`synthesize.go` の `phonemizerForLanguage()` 関数に `case "sv"` を追加して `SwedishPhonemizer` をレジストリに登録し、`src/go/README.md` の対応言語数を6から7に更新する。

T-M5-01 で言語検出とマルチリンガルルーティングが完成した状態で、本チケットではCLI/API から `--language sv` で SV 単独推論が動作するようレジストリ接続を完了させ、ユーザ向けドキュメントを整備する。

**ゴール:**
- `--language sv` で SV 単独推論が動作する
- マルチリンガルモデルの `language_id_map` に `"sv"` が含まれる場合、自動的に `SwedishPhonemizer` が生成される
- `README.md` が7言語対応を反映する
- CI (`go-ci.yml`) 全テスト PASS

## 2. 実装する内容の詳細

### 2.1 `synthesize.go` の `phonemizerForLanguage()` に `case "sv"` 追加

現在の `phonemizerForLanguage()` は以下の言語をサポートしている:

```go
case "ja": ...
case "en": ...
case "zh": ...
case "es": return phonemize.NewSpanishPhonemizer(), nil
case "fr": return phonemize.NewFrenchPhonemizer(), nil
case "pt": return phonemize.NewPortuguesePhonemizer(), nil
default:   return nil, fmt.Errorf("unsupported language %q", lang)
```

`case "pt":` の後、`default:` の前に以下を追加する:

```go
case "sv":
    return phonemize.NewSwedishPhonemizer(), nil
```

`SwedishPhonemizer` は ES/FR/PT と同じくルールベース (外部辞書不要、無状態構造体) のため、引数なしの `NewSwedishPhonemizer()` で生成する。`dicts` パラメータは使用しない。

### 2.2 `README.md` の更新

#### 2.2.1 対応言語の更新

**変更箇所1: 概要セクション (Supported languages)**

```markdown
<!-- 変更前: -->
**Supported languages (対応言語):** Japanese (JA), English (EN), Chinese (ZH), Spanish (ES), French (FR), Portuguese (PT)

<!-- 変更後: -->
**Supported languages (対応言語):** Japanese (JA), English (EN), Chinese (ZH), Spanish (ES), French (FR), Portuguese (PT), Swedish (SV)
```

**変更箇所2: Text-to-speech 機能説明**

```markdown
<!-- 変更前: -->
- Text-to-speech with automatic phonemization for 6 languages

<!-- 変更後: -->
- Text-to-speech with automatic phonemization for 7 languages
```

**変更箇所3: CLI flags テーブル (language code)**

```markdown
<!-- 変更前: -->
| `--language` | | Language code (ja, en, zh, es, fr, pt) |

<!-- 変更後: -->
| `--language` | | Language code (ja, en, zh, es, fr, pt, sv) |
```

**変更箇所4: SynthesisOption テーブル (WithLanguage)**

```markdown
<!-- 変更前: -->
| `WithLanguage(lang string)` | `""` | Target language code (ja, en, zh, es, fr, pt). |

<!-- 変更後: -->
| `WithLanguage(lang string)` | `""` | Target language code (ja, en, zh, es, fr, pt, sv). |
```

**変更箇所5: プロジェクト構造の phonemize セクション**

```markdown
<!-- 変更前のリスト末尾に追加: -->
    swedish.go                    # Swedish phonemizer
```

#### 2.2.2 マルチリンガル例の追加 (任意)

Multilingual example セクションに SV の例を追加:

```markdown
// Swedish
result, _ := voice.Synthesize(ctx, "Hej, hur mår du idag?",
    piperplus.WithLanguage("sv"))
```

### 2.3 CI 確認

`go-ci.yml` のテストジョブで以下を確認する:

1. `go build ./...` -- `swedish.go` のコンパイル成功
2. `go test ./phonemize/ -count=1` -- SV 関連テスト PASS + 既存テスト非回帰
3. `go test ./piperplus/ -count=1` -- synthesize 関連テスト PASS
4. `go vet ./...` -- 静的解析エラーなし

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 統合完了担当者 | `synthesize.go` への `case "sv"` 追加。`README.md` の全更新箇所の反映。CI 全テスト PASS の確認。既存6言語の動作に影響がないことの回帰テスト実施 | 1 |

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `synthesize.go`: `phonemizerForLanguage()` への `case "sv"` 追加 (2行)
- `README.md`: 対応言語を6→7に更新 (5箇所)、SV 例追加 (任意)、プロジェクト構造に `swedish.go` 追加
- CI 全テスト PASS 確認

**含まない:**
- `unicode_detect.go` / `multilingual.go` の変更 (T-M5-01 で完了済み)
- `SwedishPhonemizer` 本体の実装 (M2/M3)
- テストスイートの追加 (M4)
- 新規テストファイルの作成 (本チケットでは既存テストの PASS 確認のみ)

### 4.2 テスト項目

| # | テスト対象 | 検証内容 |
|---|----------|---------|
| 1 | `phonemizerForLanguage("sv", nil)` | `SwedishPhonemizer` インスタンスが返り、エラーなし |
| 2 | `phonemizerForLanguage("ja", dicts)` | 既存 JA 動作に影響なし |
| 3 | `phonemizerForLanguage("en", dicts)` | 既存 EN 動作に影響なし |
| 4 | `phonemizerForLanguage("unknown", nil)` | `"unsupported language"` エラーが返る |
| 5 | `createMultilingualPhonemizer` with SV in `LanguageIDMap` | SV phonemizer が phonemizers マップに含まれる |
| 6 | CI: `go build ./...` | コンパイル成功 |
| 7 | CI: `go test ./...` | 全テスト PASS |
| 8 | CI: `go vet ./...` | エラーなし |

### 4.3 Unitテスト

本チケットでは新規テストファイルの作成は不要。`synthesize.go` の変更は既存の `synthesize_test.go` (存在する場合) またはCIでのビルド・テストで検証される。

`phonemizerForLanguage` のテストが既存テストに含まれていない場合は、以下のパターンで追加を検討:

```go
func TestPhonemizerForLanguage_SV(t *testing.T) {
    p, err := phonemizerForLanguage("sv", nil)
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if p == nil {
        t.Fatal("expected non-nil phonemizer")
    }
    if p.LanguageCode() != "sv" {
        t.Errorf("expected language code 'sv', got %q", p.LanguageCode())
    }
}
```

### 4.4 E2Eテスト

E2E テストはCIの `go test ./...` で全パッケージのテストが実行されることで担保される。特に以下の既存テストが非回帰であることを確認:

- `TestMultilingualPhonemizer_*` (multilingual_test.go) -- マルチリンガルルーティング
- `TestSegmentText_*` (unicode_detect_test.go) -- 言語検出
- `TestFrench*`, `TestSpanish*`, `TestPortuguese*` -- 既存ルールベース phonemizer

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念事項 | 影響度 | 緩和策 |
|---|--------|--------|--------|
| 1 | `SwedishPhonemizer` が M2/M3 で未実装の場合にコンパイルエラー | 高 | 本チケットは M3 完了後に実施。`NewSwedishPhonemizer()` が `swedish.go` に存在することが前提。M3 チェックリストの `var _ Phonemizer = (*SwedishPhonemizer)(nil)` コンパイルチェックで保証 |
| 2 | `README.md` の更新漏れ (言語コード言及箇所が分散) | 中 | 本チケットで5箇所を明示的にリストアップ。レビュー時に `grep -n "ja, en, zh, es, fr, pt"` で残存箇所がないか確認 |
| 3 | `default:` ケースの位置: `case "sv"` を `case "pt"` と `default:` の間に挿入 | 低 | Go の `switch` は `case` の順序に依存しないが、アルファベット順 (es -> fr -> pt -> sv) に配置して可読性を維持 |

### 5.2 レビューチェックリスト

- [ ] `case "sv":` が `phonemizerForLanguage()` に追加され、`phonemize.NewSwedishPhonemizer()` を返しているか
- [ ] `case "sv":` の位置が `case "pt":` の後、`default:` の前か (アルファベット順)
- [ ] `dicts` パラメータを使用していないか (SV はルールベースで外部辞書不要)
- [ ] `README.md` の5箇所全てが更新されているか
  - [ ] Supported languages 行
  - [ ] "automatic phonemization for N languages" 行
  - [ ] CLI flags テーブルの `--language` 行
  - [ ] SynthesisOption テーブルの `WithLanguage` 行
  - [ ] プロジェクト構造の phonemize セクション
- [ ] `README.md` に `swedish.go` のエントリが追加されているか
- [ ] `go build ./...` がエラーなしで完了するか
- [ ] `go test ./...` が全テスト PASS するか (T-M5-01 の SV 検出テスト含む)
- [ ] `go vet ./...` がエラーなしか
- [ ] 既存の `case "es"`, `case "fr"`, `case "pt"` に変更がないか

## 6. 一から作り直すとしたら

`synthesize.go` の言語レジストリは現在 `switch` 文によるハードコードである。もし一から作り直すなら:

1. **レジストリパターン**: `init()` で各 phonemizer が自己登録する方式 (Go のプラグインパターン) を採用できる。これにより `synthesize.go` の変更なしに新言語を追加可能になる。ただし、現在の6+1言語程度であれば `switch` 文の明示性が勝る。
2. **README 自動生成**: 対応言語リストやCLIフラグの説明を `go generate` でソースコードから自動生成する方式も考えられる。ただし、メンテナンスコストに対する効果が薄い。

現在の `switch` 文方式は ES/FR/PT の追加パターンと完全に一致しており、一貫性の観点からこのまま維持するのが最善。

## 7. 後続タスクへの連絡事項

- **M5 完了条件**: 本チケット (T-M5-02) の完了をもって M5 マイルストーンが完了となる。M5 完了条件は以下:
  - `--language sv` で SV 単独推論が動作
  - マルチリンガルモデルで SV セグメントが正しく検出・処理される
  - 既存6言語の動作に影響なし
  - README が7言語対応に更新済み
  - CI (`go-ci.yml`) 全テスト PASS
- **PR #270 マージ準備**: M1-M5 全マイルストーン完了後、PR #270 のマージレビューを実施する。マージ前に以下を最終確認:
  - 全テスト (~140件 + 既存テスト) が PASS
  - `go vet` / `golangci-lint` エラーなし
  - Python 参照実装との出力一致テスト (代表的テストケース)
- **config.json の `language_id_map`**: 7言語モデルの `config.json` では `"sv": 6` が追加される。既存6言語モデルの config.json は変更不要 (SV を含まないモデルでは `case "sv"` に到達しない)。
- **`README.md` の言語関連箇所**: 将来の言語追加時 (例: DE, KO の Go 実装) は、本チケットで更新した5箇所と同じ箇所を更新する必要がある。`grep "ja, en, zh, es, fr, pt, sv"` でリストアップ可能。
