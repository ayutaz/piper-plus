# Go スウェーデン語 G2P マイルストーン計画

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-31 |
| 対象 PR | #270 (`feat/go-bindings`) |
| ブランチ | `feat/go-bindings` |
| 関連文書 | `go-swedish-g2p-impl-plan.md` (技術設計), `swedish-milestones.md` (全体ロードマップ) |
| チケット | [`docs/tickets/go-sv/index.md`](../tickets/go-sv/index.md) (14チケット) |
| 位置付け | `swedish-milestones.md` Phase 2 の「M2.5 Go 実装」に相当 |

---

## 全体ロードマップ

```
M1: PUA基盤 + 定数定義
  ↓
M2: G2Pコアエンジン (子音 + 母音 + ローンワード)
  ↓
M3: 後処理 + Phonemizer統合 (レトロフレックス + ストレス + Prosody)
  ↓
M4: テストスイート (~140テスト)
  ↓
M5: マルチリンガル統合 + レジストリ + ドキュメント
```

### 依存関係

| マイルストーン | 前提 | 並行可否 |
|---|---|---|
| M1 | なし | - |
| M2 | M1 | - |
| M3 | M2 | - |
| M4 | M3 | M4のテスト作成はM2と並行可だが、実行はM3完了後 |
| M5 | M3 | M4と並行可 |

### 推定規模

| マイルストーン | 新規行数 | 変更ファイル数 |
|---|---|---|
| M1 | ~50 | 1 (pua.go) |
| M2 | ~900 | 1 (swedish.go 新規) |
| M3 | ~400 | 1 (swedish.go 追加) |
| M4 | ~1,500 | 1 (swedish_test.go 新規) |
| M5 | ~100 | 4 (unicode_detect.go, multilingual.go, synthesize.go, README.md) |
| **合計** | **~3,000** | **8** |

---

## M1: PUA基盤 + 定数定義

| 項目 | 内容 |
|------|------|
| 目標 | スウェーデン語の音素を Go PUA システムに登録し、全例外語リスト・定数を定義 |
| 成果物 | `pua.go` 変更, `swedish.go` 冒頭の定数セクション |
| 前提 | なし |
| チケット | [T-M1-01](../tickets/go-sv/T-M1-01-pua-sv-registration.md), [T-M1-02](../tickets/go-sv/T-M1-02-sv-constants-exception-lists.md) |

### タスク

| # | タスク | ファイル | 詳細 |
|---|--------|---------|------|
| 1 | SV長母音PUA登録 | `pua.go` | `fixedPUA` に9エントリ追加 (0xE059-0xE061: iː, yː, eː, ɛː, øː, ɑː, oː, uː, ʉː) |
| 2 | `nextDynamic` 更新 | `pua.go` | 0xE059 → 0xE064 (0xE062-0xE063 は予約枠) |
| 3 | 母音定数定義 | `swedish.go` | `svFrontVowels`, `svBackVowels`, `svAllVowels`, `svConsonants` |
| 4 | 母音マッピング表定義 | `swedish.go` | `svLongVowelMap`, `svShortVowelMap` (10母音 x 長短) |
| 5 | デフォルト子音マッピング | `swedish.go` | `svConsonantDefault` (16エントリ: b→b, w→v, z→s 等) |
| 6 | 例外語リスト定義 (10カテゴリ) | `swedish.go` | 下表参照 |

**例外語リスト:**

| 変数名 | 用途 | 語数 | 型 |
|---|---|---|---|
| `svHardKWords` | k+前舌母音で /k/ 保持 | ~67 | `map[string]bool` |
| `svHardKStems` | 同上 (語根) | ~35 | `map[string]bool` |
| `svHardGWords` | g+前舌母音で /ɡ/ 保持 | ~41 | `map[string]bool` |
| `svHardGStems` | 同上 (語根) | ~22 | `map[string]bool` |
| `svOLongAsOO` | "o" → /oː/ | ~30 | `map[string]bool` |
| `svFinalMShortWords` | 語末-mで短母音 | ~13 | `map[string]bool` |
| `svFunctionWords` | ストレスなし | ~35 | `map[string]bool` |
| `svSKBackVowelExceptions` | sk+後舌母音で /ɧ/ | 2 | `map[string]bool` |
| `svCHExceptionsK` | ch → /k/ | ~5 | `map[string]bool` |
| `svAgeNativeWords` | -age がネイティブ | ~9 | `map[string]bool` |

### 完了基準

- [ ] PUA 0xE059-0xE061 の9エントリが `fixedPUA` に登録済み
- [ ] `nextDynamic` が 0xE064
- [ ] 既存言語のPUAと衝突なし (既存テスト全PASS)
- [ ] 全10カテゴリの例外語リストが Python 参照実装と一致
- [ ] `go vet ./phonemize/...` がエラーなし

---

## M2: G2Pコアエンジン

| 項目 | 内容 |
|------|------|
| 目標 | テキストからIPA音素列への変換パイプラインのコア部分を実装 |
| 成果物 | `swedish.go` の正規化・トークン化・子音変換・母音長判定・ローンワード |
| 前提 | M1 |
| チケット | [T-M2-01](../tickets/go-sv/T-M2-01-phonemizer-struct-normalize-tokenize.md), [T-M2-02](../tickets/go-sv/T-M2-02-loanword-suffix-detection.md), [T-M2-03](../tickets/go-sv/T-M2-03-consonant-conversion.md), [T-M2-04](../tickets/go-sv/T-M2-04-vowel-length-complementary-quantity.md), [T-M2-05](../tickets/go-sv/T-M2-05-word-g2p-integration.md) |

### タスク

| # | タスク | 詳細 |
|---|--------|------|
| 1 | `SwedishPhonemizer` 構造体定義 | 無状態構造体, `NewSwedishPhonemizer()`, `LanguageCode() → "sv"` |
| 2 | 正規化 | NFC正規化 + 小文字化 (`strings.ToLower` + `norm.NFC`) |
| 3 | トークン化 (`svTokenize`) | テキストを単語/句読点トークンに分割。既存 FR/ES/PT と同等パターン |
| 4 | ローンワード接尾辞検出 (`svDetectLoanwordSuffix`) | 7接尾辞 (-ssion/-tion/-sion/-age/-eur/-eum/-ium) の固定音素マッピング。`svAgeNativeWords` 除外 |
| 5 | 子音変換 (`svConvertConsonant`) | 3段階優先度: 3文字→2文字→1文字パターン。sk/k/g のコンテキスト依存分岐。例外語チェック (`isHardK`, `isHardG`) |
| 6 | 母音長判定 (`svGetVowelPhoneme`) | Complementary Quantity: 非ストレス→短, 機能語→短, FINAL_M→短, 子音数カウント→長/短。"o" の O_LONG_AS_OO 例外。r+C 例外 |
| 7 | ネイティブG2P統合 (`svConvertWordNative`) | 子音変換+母音長判定を組み合わせ、単語を音素列に変換 |
| 8 | 単語G2P (`svPhonemizeWord`) | ローンワード検出 → ネイティブG2P → 音素列返却 |

### 完了基準

- [ ] 基本的な単語で正しいIPA音素列を生成
  - `gata` → `ɡ ɑː t a` (長母音)
  - `katt` → `k a t` (短母音)
  - `sked` → `ɧ eː d` (sk+前舌母音)
  - `flicka` → `f l ɪ k a` (HARD_K例外)
  - `station` → `s t a ɧ uː n` (ローンワード)
- [ ] `go build ./phonemize/...` 成功

---

## M3: 後処理 + Phonemizer統合

| 項目 | 内容 |
|------|------|
| 目標 | レトロフレックス同化・ストレス検出を追加し、`PhonemizeWithProsody` を完成 |
| 成果物 | `swedish.go` の後処理セクション + `PhonemizeWithProsody` メソッド |
| 前提 | M2 |
| チケット | [T-M3-01](../tickets/go-sv/T-M3-01-retroflex-assimilation.md), [T-M3-02](../tickets/go-sv/T-M3-02-stress-detection-insertion.md), [T-M3-03](../tickets/go-sv/T-M3-03-phonemize-with-prosody-integration.md) |

### タスク

| # | タスク | 詳細 |
|---|--------|------|
| 1 | レトロフレックス同化 (`svApplyRetroflex`) | 3状態機械 (NORMAL/R_DETECTED/CASCADING)。r+{t,d,s,n,l} → {ʈ,ɖ,ʂ,ɳ,ɭ}。rrジェミネートブロック。ɭでカスケード停止 |
| 2 | 音節カウント (`svCountSyllables`) | 母音文字数で音節推定 |
| 3 | ストレス検出 (`svDetectStress`) | 5段階優先: 機能語(-1)→単音節(0)→吸引接尾辞(N)→非ストレスプレフィックス(1)→デフォルト(0) |
| 4 | ストレスマーカー挿入 (`svInsertStressMarker`) | ストレス位置にˈ (U+02C8) 挿入 |
| 5 | Prosody構築 | A1=0, A2=ストレス有(2)/無(0), A3=単語音素数 (ストレスマーカー除外) |
| 6 | EOS追跡 | 句読点から `$`, `?`, `!` を追跡 (既存FR/ES/PTと同パターン) |
| 7 | `PhonemizeWithProsody` 統合 | トークン化→単語ごとG2P→レトロフレックス→ストレス→PUA変換→Result組立 |

### 完了基準

- [ ] レトロフレックスが正しく動作
  - `kort` → `ʈ` 含む, `barn` → `ɳ` 含む, `först` → `ʂ ʈ` (カスケード)
  - `borr` → `r r` (ジェミネートブロック)
- [ ] ストレスマーカーが正しい位置
  - `hus` → ˈ が先頭 (第1音節), `station` → ˈ が第2音節, `och` → ストレスなし
- [ ] `PhonemizeWithProsody` が `*PhonemizeResult` を返却
  - `Tokens` と `Prosody` の長さが一致
  - `MapSequence()` で長母音がPUAに変換済み
- [ ] `var _ Phonemizer = (*SwedishPhonemizer)(nil)` がコンパイル通過

---

## M4: テストスイート

| 項目 | 内容 |
|------|------|
| 目標 | ~140テストケースで全G2P規則をカバー |
| 成果物 | `swedish_test.go` |
| 前提 | M3 (実行にはM3完了が必要。テストケース作成はM2と並行可) |
| チケット | [T-M4-01](../tickets/go-sv/T-M4-01-basic-rule-tests.md), [T-M4-02](../tickets/go-sv/T-M4-02-stress-prosody-integration-tests.md) |

### タスク

| # | カテゴリ | テスト数 | 内容 |
|---|---------|---------|------|
| 1 | 基本母音 (長短) | 20 | 全10母音の長/短バリアント |
| 2 | 子音規則 (3文字/2文字) | 30 | skj/stj/sch, sk+前舌/後舌, sj, ch, tj, ng, nk, ck, gn, gj/lj/dj/hj |
| 3 | k/g 軟硬例外 | 15 | HARD_K_WORDS/STEMS, HARD_G_WORDS/STEMS のスポットチェック |
| 4 | レトロフレックス | 15 | 基本5変換 (rt/rd/rs/rn/rl) + カスケード + rrブロック + 語境界 |
| 5 | ストレス検出 | 15 | 機能語/単音節/吸引接尾辞/プレフィックス/デフォルト |
| 6 | ローンワード接尾辞 | 10 | 7接尾辞 + AGE_NATIVE除外 |
| 7 | "o" 曖昧性 | 10 | O_LONG_AS_OO リスト vs デフォルト (/uː/) |
| 8 | Prosody整合性 | 5 | len(Tokens)==len(Prosody), A1/A2/A3 値検証 |
| 9 | PUAマッピング | 10 | 9長母音のPUA変換 + MapSequence 統合 |
| 10 | 統合テスト (文レベル) | 10 | 複数単語の文、句読点含む、EOS追跡 |

### テストスタイル

既存 `french_test.go`/`spanish_test.go` に倣い、テーブル駆動テスト:

```go
func TestSvLongVowels(t *testing.T) {
    tests := []struct {
        word string
        want string  // 含まれるべきIPA
    }{
        {"gata", "ɑː"},
        {"hus", "ʉː"},
        // ...
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            // ...
        })
    }
}
```

### 完了基準

- [ ] ~140テスト全PASS
- [ ] `go test ./phonemize/ -run Swedish -count=1` 成功
- [ ] 他言語テスト (EN/JA/ZH/ES/FR/PT) に影響なし
- [ ] `go vet`, `golangci-lint` エラーなし

---

## M5: マルチリンガル統合 + レジストリ + ドキュメント

| 項目 | 内容 |
|------|------|
| 目標 | SV を Go のマルチリンガルシステムに統合し、CLI/API から利用可能にする |
| 成果物 | `unicode_detect.go`, `multilingual.go`, `synthesize.go`, `README.md` 変更 |
| 前提 | M3 (M4と並行可) |
| チケット | [T-M5-01](../tickets/go-sv/T-M5-01-language-detection-multilingual.md), [T-M5-02](../tickets/go-sv/T-M5-02-registry-documentation.md) |

### タスク

| # | タスク | ファイル | 詳細 |
|---|--------|---------|------|
| 1 | SV言語検出ロジック追加 | `unicode_detect.go` | SV特有文字 (ä, ö, å) + 機能語 (och, att, jag 等12語) でスコアリング |
| 2 | マルチリンガルPhonemizer統合 | `multilingual.go` | SV Phonemizer をラテン語言語リストに追加 |
| 3 | 言語レジストリ登録 | `synthesize.go` | `phonemizerForLanguage()` に `case "sv": return phonemize.NewSwedishPhonemizer(), nil` 追加 |
| 4 | README更新 | `src/go/README.md` | 対応言語を6→7言語に更新。SV追加の記載 |
| 5 | 言語検出テスト | `unicode_detect_test.go` | SV文字/機能語検出テスト (5-10ケース) |
| 6 | マルチリンガル統合テスト | `multilingual_test.go` | SV+他言語混在テスト (3-5ケース) |

### 完了基準

- [ ] `--language sv` で SV 単独推論が動作
- [ ] マルチリンガルモデルで SV セグメントが正しく検出・処理
- [ ] 既存6言語の動作に影響なし
- [ ] README が7言語対応に更新済み
- [ ] CI (`go-ci.yml`) 全テスト PASS

---

## チェックリスト (全体)

### M1: PUA基盤 + 定数定義
- [ ] PUA 9エントリ登録 (0xE059-0xE061)
- [ ] nextDynamic → 0xE064
- [ ] 例外語リスト 10カテゴリ定義
- [ ] 既存テスト PASS

### M2: G2Pコアエンジン
- [ ] SwedishPhonemizer 構造体
- [ ] 正規化 + トークン化
- [ ] ローンワード接尾辞検出
- [ ] 子音変換 (3文字/2文字/1文字)
- [ ] 母音長判定 (Complementary Quantity)
- [ ] 単語G2P統合

### M3: 後処理 + Phonemizer統合
- [ ] レトロフレックス同化 (3状態機械)
- [ ] ストレス検出 (5段階)
- [ ] ストレスマーカー挿入
- [ ] PhonemizeWithProsody 完成
- [ ] Phonemizer インターフェース準拠

### M4: テストスイート
- [ ] ~140テスト作成
- [ ] 全テスト PASS
- [ ] 他言語テスト非影響

### M5: マルチリンガル統合
- [ ] 言語検出 (unicode_detect.go)
- [ ] マルチリンガル統合 (multilingual.go)
- [ ] レジストリ登録 (synthesize.go)
- [ ] README 更新
- [ ] CI green
