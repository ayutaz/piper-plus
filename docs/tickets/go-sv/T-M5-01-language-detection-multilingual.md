# T-M5-01: SV言語検出ロジック + マルチリンガル統合

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M5: マルチリンガル統合 |
| 依存チケット | M3 (後処理 + Phonemizer統合) |
| 後続チケット | T-M5-02 (レジストリ登録 + ドキュメント更新) |
| 対象ファイル | `src/go/phonemize/unicode_detect.go`, `src/go/phonemize/multilingual.go`, `src/go/phonemize/unicode_detect_test.go`, `src/go/phonemize/multilingual_test.go` |
| 推定行数 | ~60行 (本体) + ~120行 (テスト) |
| PR | #270 (`feat/go-bindings`) |
| 参照設計 | `docs/design/go-swedish-g2p-impl-plan.md` セクション10 |
| Python参照実装 | `src/python/piper_train/phonemize/multilingual.py` (`_SWEDISH_CHARS`, `_SWEDISH_FUNCTION_WORDS`, `_refine_latin_segments_for_swedish`) |

## 1. タスク目的とゴール

Go の `UnicodeLanguageDetector` にスウェーデン語 (SV) の検出ロジックを追加し、`MultilingualPhonemizer` のラテン語言語リストに SV を統合する。これにより、マルチリンガルモデルで SV テキストが自動検出され、正しい phonemizer にルーティングされるようにする。

現在の Go 実装では、ラテン文字は全て `defaultLatinLanguage` (通常 EN) として処理される。SV が言語セットに含まれる場合、ラテン文字セグメント内のスウェーデン語特有指標 (文字 + 機能語) をスコアリングして SV を識別する必要がある。

**ゴール:**
- `en-sv` や `ja-en-sv` 等の言語セットで、SV テキストが正しく検出される
- 既存6言語 (JA/EN/ZH/ES/FR/PT) の検出動作に影響なし
- Python 参照実装 (`_refine_latin_segments_for_swedish`) と同等のスコアリングロジック

## 2. 実装する内容の詳細

### 2.1 `unicode_detect.go` への SV 検出追加

#### 2.1.1 SV 特有文字セット

Python の `_SWEDISH_CHARS` に対応する Go 定数を追加する。

```go
// svChars contains Swedish-specific characters not used by EN/ES/PT/FR.
// Used for word-level Swedish detection within Latin segments.
var svChars = map[rune]bool{
    '\u00e4': true, // ä
    '\u00f6': true, // ö
    '\u00c4': true, // Ä
    '\u00d6': true, // Ö
    '\u00e5': true, // å
    '\u00c5': true, // Å
}
```

**文字指標の詳細:**
- `ä` (U+00E4) / `Ä` (U+00C4) -- ドイツ語でも使用されるが、piper-plus には DE が未登録のため SV 指標として安全
- `ö` (U+00F6) / `Ö` (U+00D6) -- 同上
- `å` (U+00E5) / `Å` (U+00C5) -- DA/NO と共有だが、piper-plus に DA/NO は未登録のため安全

#### 2.1.2 SV 機能語リスト (12語)

Python 参照実装では45語の大規模な `_SWEDISH_FUNCTION_WORDS` セットを持つが、Go 実装設計 (セクション10) ではEN/ES/PT/FR と誤判定しない高頻度12語に絞る。

```go
// svFunctionWords contains highly distinctive Swedish function words
// that do not appear in EN/ES/PT/FR. Used for word-level disambiguation.
var svFunctionWords = map[string]bool{
    "och":    true, // and (EN: and, ES: y, FR: et, PT: e)
    "att":    true, // to/that
    "jag":    true, // I (first person pronoun)
    "det":    true, // it/that (also Danish, but DA not in piper-plus)
    "inte":   true, // not
    "han":    true, // he
    "hon":    true, // she
    "som":    true, // who/which/as
    "ska":    true, // shall/will
    "med":    true, // with
    "aldrig": true, // never
    "alltid": true, // always
}
```

#### 2.1.3 `UnicodeLanguageDetector` 構造体への SV フィールド追加

```go
type UnicodeLanguageDetector struct {
    languages            map[string]bool
    defaultLatinLanguage string
    hasJA, hasZH, hasKO  bool
    hasSV                bool   // 新規追加
    detectSwedish        bool   // 新規追加: hasSV && len(latinLanguages) >= 2
}
```

`NewUnicodeLanguageDetector` で以下の初期化を追加:

```go
hasSV := langSet["sv"]
// Count Latin-script languages for Swedish detection
latinLangs := 0
for _, l := range []string{"en", "es", "pt", "fr", "sv"} {
    if langSet[l] { latinLangs++ }
}
detectSwedish := hasSV && latinLangs >= 2
```

#### 2.1.4 `SegmentText` への後処理パス追加

Python の `_refine_latin_segments_for_swedish` に相当する後処理を `SegmentText` 関数に追加する。`detectSwedish` が有効な場合、セグメント結果に対してスウェーデン語指標のスコアリングを実行する。

```go
// SegmentText 末尾に追加:
if detector.detectSwedish {
    segments = refineLatinSegmentsForSwedish(segments, detector)
}
```

`refineLatinSegmentsForSwedish` 関数:

```go
func refineLatinSegmentsForSwedish(segments []LangSegment, d *UnicodeLanguageDetector) []LangSegment {
    if d.defaultLatinLanguage == "sv" {
        return segments // SV がデフォルトなら再分類不要
    }
    result := make([]LangSegment, 0, len(segments))
    for _, seg := range segments {
        if seg.Language != d.defaultLatinLanguage {
            result = append(result, seg)
            continue
        }
        // ラテン語セグメント内の SV 指標をスコアリング
        svScore := 0
        for _, word := range strings.Fields(seg.Text) {
            wordLower := strings.ToLower(strings.Trim(word, ".,;:!?"))
            if wordLower == "" { continue }
            // SV 特有文字チェック
            hasSvChar := false
            for _, r := range wordLower {
                if svChars[r] { hasSvChar = true; break }
            }
            if hasSvChar {
                svScore++
            } else if svFunctionWords[wordLower] {
                svScore++
            }
        }
        if svScore >= 1 {
            result = append(result, LangSegment{Language: "sv", Text: seg.Text})
        } else {
            result = append(result, seg)
        }
    }
    return result
}
```

### 2.2 `multilingual.go` への SV 追加

#### 2.2.1 `DefaultLatinLanguage` 関数の更新

`DefaultLatinLanguage` のラテン語優先順リストに `"sv"` を追加する。Python 参照の `_detect_default_latin` と同様、SV は末尾 (最低優先度)。

```go
// 変更前:
for _, preferred := range []string{"en", "es", "fr", "pt"} {

// 変更後:
for _, preferred := range []string{"en", "es", "fr", "pt", "sv"} {
```

これにより `en-sv` では EN がデフォルト (SV は後処理で検出)、`ja-sv` では SV がデフォルトラテン言語になる。

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | 検出ロジック実装者 | `unicode_detect.go` への SV 検出追加 (`svChars`, `svFunctionWords`, `hasSV`/`detectSwedish` フィールド, `refineLatinSegmentsForSwedish` 関数)。Python 参照実装との等価性確認 | 1 |
| 2 | 統合テスト担当者 | `multilingual.go` の `DefaultLatinLanguage` 更新。`unicode_detect_test.go` に SV 検出テスト 5-10 件追加。`multilingual_test.go` に SV 統合テスト 3-5 件追加。既存テストの非回帰確認 | 1 |

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**含む:**
- `unicode_detect.go`: SV 特有文字・機能語定数、構造体フィールド追加、`refineLatinSegmentsForSwedish` 後処理
- `multilingual.go`: `DefaultLatinLanguage` 優先順リストへの SV 追加
- `unicode_detect_test.go`: SV 検出テスト 5-10 件
- `multilingual_test.go`: SV マルチリンガル統合テスト 3-5 件

**含まない:**
- `synthesize.go` のレジストリ登録 (T-M5-02)
- `README.md` 更新 (T-M5-02)
- `SwedishPhonemizer` 本体の実装 (M2/M3)
- テストモデルの言語設定変更

### 4.2 テスト項目

| # | カテゴリ | 件数 | 内容 |
|---|---------|------|------|
| 1 | SV 特有文字検出 | 3 | ä/ö/å を含むテキストが SV として検出される |
| 2 | SV 機能語検出 | 3 | 機能語 (och, att, jag 等) を含むテキストが SV として検出される |
| 3 | 非 SV ラテンの非干渉 | 2 | SV 指標がないラテンテキストがデフォルト言語のまま |
| 4 | detectSwedish 無効化 | 1 | SV が言語セットにない場合、後処理が実行されない |
| 5 | DefaultLatinLanguage | 1 | `ja-sv` で SV がデフォルトラテン言語 |
| 6 | マルチリンガル SV ルーティング | 3-5 | mock phonemizer で SV セグメントが正しくルーティング |

### 4.3 Unitテスト

**`unicode_detect_test.go` に追加 (5-10 件):**

```go
// T1: ä/ö/å を含むテキストが SV として検出される
func TestSegmentText_SwedishCharsDetected(t *testing.T) {
    d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
    segs := SegmentText("Jag är glad", d)
    // "är" contains ä -> sv_score >= 1 -> segment is SV
    if len(segs) != 1 { t.Fatalf(...) }
    if segs[0].Language != "sv" { t.Errorf(...) }
}

// T2: 機能語のみで SV 検出
func TestSegmentText_SwedishFunctionWords(t *testing.T) {
    d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
    segs := SegmentText("jag och hon", d)
    if len(segs) != 1 { t.Fatalf(...) }
    if segs[0].Language != "sv" { t.Errorf(...) }
}

// T3: SV 指標なしのラテンテキスト -> EN のまま
func TestSegmentText_NoSwedishIndicators(t *testing.T) {
    d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
    segs := SegmentText("hello world", d)
    if len(segs) != 1 { t.Fatalf(...) }
    if segs[0].Language != "en" { t.Errorf(...) }
}

// T4: SV が言語セットにない場合は後処理なし
func TestSegmentText_NoSVInLanguages(t *testing.T) {
    d := NewUnicodeLanguageDetector([]string{"en", "fr"}, "en")
    segs := SegmentText("Jag är glad", d) // ä はラテン拡張 -> EN
    if len(segs) != 1 { t.Fatalf(...) }
    if segs[0].Language != "en" { t.Errorf(...) }
}

// T5: ja-sv でラテン文字が SV にルーティング
func TestSegmentText_JaSvLatinGoesToSv(t *testing.T) {
    d := NewUnicodeLanguageDetector([]string{"ja", "sv"}, "sv")
    segs := SegmentText("こんにちはhej", d)
    if len(segs) != 2 { t.Fatalf(...) }
    if segs[0].Language != "ja" { t.Errorf(...) }
    if segs[1].Language != "sv" { t.Errorf(...) }
}

// T6: å 文字で SV 検出
func TestSegmentText_SwedishRingA(t *testing.T) {
    d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
    segs := SegmentText("Det är en bra dag", d)
    if len(segs) != 1 { t.Fatalf(...) }
    if segs[0].Language != "sv" { t.Errorf(...) }
}

// T7: DefaultLatinLanguage で ja-sv は SV がデフォルト
func TestDefaultLatinLanguage_JaSv(t *testing.T) {
    got := DefaultLatinLanguage([]string{"ja", "sv"})
    if got != "sv" { t.Errorf("expected sv, got %q", got) }
}

// T8: DefaultLatinLanguage で en-sv は EN が優先
func TestDefaultLatinLanguage_EnSv(t *testing.T) {
    got := DefaultLatinLanguage([]string{"en", "sv"})
    if got != "en" { t.Errorf("expected en, got %q", got) }
}
```

### 4.4 E2Eテスト

**`multilingual_test.go` に追加 (3-5 件):**

```go
// E2E-1: SV テキストが SV mock phonemizer にルーティングされる
func TestMultilingualPhonemizer_SwedishRouting(t *testing.T) {
    mp := newTestMultilingualPhonemizer(
        []string{"en", "sv"},
        "en",
        map[string]*mockPhonemizer{
            "en": {lang: "en", tokens: []string{"^", "h", "$"}},
            "sv": {lang: "sv", tokens: []string{"^", "s", "v", "$"}},
        },
    )
    // "Jag är glad" has ä -> SV detected
    result, err := mp.PhonemizeWithProsody("Jag är glad")
    // SV mock returns ["s", "v"] (BOS/EOS stripped)
    // -> result.Tokens should be ["s", "v"]
}

// E2E-2: JA + SV 混在テキスト
func TestMultilingualPhonemizer_JaSvMixed(t *testing.T) {
    mp := newTestMultilingualPhonemizer(
        []string{"ja", "sv"},
        "sv",
        map[string]*mockPhonemizer{
            "ja": {lang: "ja", tokens: []string{"^", "a", "$"}},
            "sv": {lang: "sv", tokens: []string{"^", "b", "$"}},
        },
    )
    result, err := mp.PhonemizeWithProsody("こんにちは Hej")
    // JA segment: ["a"], SV segment: ["b"]
    // -> result.Tokens should be ["a", "b"]
}

// E2E-3: SV 指標なしのラテンテキスト -> EN にルーティング
func TestMultilingualPhonemizer_LatinDefaultsToEnNotSv(t *testing.T) {
    mp := newTestMultilingualPhonemizer(
        []string{"en", "sv"},
        "en",
        map[string]*mockPhonemizer{
            "en": {lang: "en", tokens: []string{"^", "e", "$"}},
            "sv": {lang: "sv", tokens: []string{"^", "s", "$"}},
        },
    )
    result, err := mp.PhonemizeWithProsody("hello world")
    // No SV indicators -> EN
    // -> result.Tokens should be ["e"]
}

// E2E-4: 7言語セット (ja-en-zh-es-fr-pt-sv) で SV 検出が動作
func TestMultilingualPhonemizer_7LangSvDetection(t *testing.T) {
    // SV テキストが SV にルーティングされることを確認
    // 他の6言語には影響なし
}
```

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念事項 | 影響度 | 緩和策 |
|---|--------|--------|--------|
| 1 | EN-SV 誤検出: SV 機能語が EN テキストに偶発的に含まれる場合 (例: "det" は英語の detective の略語にも使われる) | 中 | 12語の機能語リストは他言語との衝突リスクが低い語に厳選済み。`svScore >= 1` の閾値は Python 参照と同一。過剰検出より未検出のほうが安全 (EN fallback として動作するため) |
| 2 | セグメント再分類のパフォーマンス: `refineLatinSegmentsForSwedish` が全ラテンセグメントを再走査する | 低 | O(n) のテキスト走査 + O(1) のハッシュセットルックアップ。TTS の推論時間 (~100ms) に対して無視できるオーバーヘッド |
| 3 | `detectSwedish` が SV 単独言語セットで不要に有効化される | 低 | `detectSwedish = hasSV && latinLangs >= 2` の条件で、SV のみの場合は `defaultLatinLanguage == "sv"` となり `refineLatinSegmentsForSwedish` 冒頭の早期リターンで処理されない |
| 4 | Python 参照との機能語リスト差異: Python は45語、Go は12語 | 低 | Go 設計では高頻度かつ他言語と非衝突の12語に絞る方針。検出漏れは EN fallback として許容される。必要に応じてリスト拡張可能 |
| 5 | `strings.Fields` でのトークン分割がフランス語アポストロフィ ("l'homme") で不正確 | 低 | SV テキストでアポストロフィは稀。FR テキストが SV として誤検出されるリスクは FR 機能語が svFunctionWords に含まれないため無し |

### 5.2 レビューチェックリスト

- [ ] `svChars` の6文字 (ä/ö/å の大文字小文字) が Python `_SWEDISH_CHARS` と一致するか
- [ ] `svFunctionWords` の12語が Python `_SWEDISH_FUNCTION_WORDS` のサブセットであり、EN/ES/PT/FR の一般語と衝突しないか
- [ ] `refineLatinSegmentsForSwedish` の `svScore >= 1` 閾値が Python 参照と一致するか
- [ ] `detectSwedish` の有効化条件 (`hasSV && latinLangs >= 2`) が Python の `self._detect_swedish = self._has_sv and len(self._latin_languages) >= 2` と等価か
- [ ] `defaultLatinLanguage == "sv"` の場合に早期リターンして再分類しないか (Python: `if default == "sv": return segments`)
- [ ] `DefaultLatinLanguage` の優先順 `["en", "es", "fr", "pt", "sv"]` が Python 参照の `_detect_default_latin` と一致するか
- [ ] 既存テスト (`TestJapaneseTextSingleSegment`, `TestEnglishTextSingleSegment`, `TestMixedEnglishJapanese` 等) が全て PASS するか
- [ ] `go vet ./phonemize/...` がエラーなしか
- [ ] `strings` パッケージの import が `unicode_detect.go` に追加されているか (既に import 済みなら不要)

## 6. 一から作り直すとしたら

現在の設計は Python 参照の「セグメント後に後処理で再分類」パターンに忠実に従っている。もし一から作り直すなら:

1. **文字レベル検出への統合**: `DetectChar` でラテン拡張文字 (ä/ö/å) を直接 SV として返す方式も検討できる。ただし、これは EN テキスト中の偶発的なダイアクリティック (例: "naïve", "café") で誤検出を引き起こすため、現在の「セグメント後の単語レベル再分類」のほうが安全。
2. **機能語リストの外部化**: 12語のハードコード以外に、設定ファイルからのカスタマイズ可能性も考えられる。ただし、現時点では piper-plus の言語セットが固定のため、過度な柔軟性は不要。
3. **N-gram ベース検出**: 文字 N-gram による言語識別はより堅牢だが、TTS のユースケースでは入力テキストが短く明確な場合が多いため、簡易スコアリングで十分。

## 7. 後続タスクへの連絡事項

- **T-M5-02 への引き継ぎ**: `unicode_detect.go` と `multilingual.go` の変更が完了したら、T-M5-02 で `synthesize.go` のレジストリ登録と `README.md` の更新を行う。T-M5-02 は本チケット完了後に着手可能。
- **`detectSwedish` フラグの存在**: `UnicodeLanguageDetector` に `hasSV` と `detectSwedish` フィールドが追加されるため、将来の言語追加時 (例: DE, DA, NO) にはラテン語検出ロジックの見直しが必要になる可能性がある。
- **テストの mock パターン**: `multilingual_test.go` の `mockPhonemizer` パターンを SV テストでも使用する。`SwedishPhonemizer` の実ルーティングテストは M4 テストスイートで網羅する。
- **`strings` パッケージ**: `refineLatinSegmentsForSwedish` で `strings.Fields` と `strings.ToLower` と `strings.Trim` を使用する。`unicode_detect.go` に `strings` import が未追加の場合は追加が必要。
