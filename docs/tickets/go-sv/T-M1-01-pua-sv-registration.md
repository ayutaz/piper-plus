# T-M1-01: PUA SV長母音エントリ登録

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M1: PUA基盤 + 定数定義 |
| 依存チケット | なし (M1の最初のタスク) |
| 後続チケット | T-M1-02 (SV定数・例外語リスト定義) |
| 対象ファイル | `src/go/phonemize/pua.go` |
| 推定行数 | ~15行 (fixedPUAに9エントリ追加 + nextDynamic更新 + ResetDynamicPUA更新) |

## 1. タスク目的とゴール

スウェーデン語の9つの長母音はIPA表記が2文字 (例: `iː`, `ɑː`) であり、Piperの phoneme_id_map では1コードポイント = 1トークンの原則がある。そのためPUA (Private Use Area) に固定マッピングを登録し、多文字IPAトークンを単一コードポイントに変換できるようにする。

**完了時の状態:**
- `fixedPUA` マップに SV 長母音 9エントリ (0xE059-0xE061) が登録されている
- `nextDynamic` が 0xE064 に更新されている (0xE062-0xE063 は将来の予約枠)
- `ResetDynamicPUA()` の初期値が 0xE064 に更新されている
- 既存言語 (JA/EN/ZH/KO/ES/PT/FR) の PUA と衝突がない
- 既存テストが全て PASS する

## 2. 実装する内容の詳細

### 2.1 fixedPUA への9エントリ追加

`fixedPUA` マップの French エントリ (0xE056-0xE058) の直後に、以下の Swedish ブロックを追加する:

```go
// Swedish (0xE059-0xE061) — 9 entries (long vowels)
"iː": 0xE059,
"yː": 0xE05A,
"eː": 0xE05B,
"ɛː": 0xE05C,
"øː": 0xE05D,
"ɑː": 0xE05E,
"oː": 0xE05F,
"uː": 0xE060,
"ʉː": 0xE061,
```

**PUA割り当て全体図 (更新後):**

| 範囲 | 言語 | エントリ数 |
|---|---|---|
| 0xE000-0xE01C | Japanese | 29 |
| 0xE01D-0xE01E | Multilingual shared | 2 |
| 0xE020-0xE04A | Chinese | 43 |
| 0xE04B-0xE052 | Korean | 8 |
| 0xE054-0xE055 | Spanish/Portuguese | 2 |
| 0xE056-0xE058 | French | 3 |
| **0xE059-0xE061** | **Swedish (新規)** | **9** |
| 0xE062-0xE063 | 予約枠 | 2 |
| 0xE064+ | 動的割り当て | - |

### 2.2 nextDynamic の更新

```go
// 変更前:
nextDynamic = rune(0xE059) // Start after last fixed PUA (0xE058 = ɔ̃)

// 変更後:
nextDynamic = rune(0xE064) // Start after last fixed PUA (0xE061 = ʉː) + 2 reserved
```

### 2.3 ResetDynamicPUA() の更新

```go
// 変更前:
nextDynamic = 0xE059

// 変更後:
nextDynamic = 0xE064
```

### 2.4 9つの長母音の詳細

| IPA表記 | PUAコードポイント | Unicode表現 | 説明 |
|---|---|---|---|
| iː | 0xE059 | `"i\u02d0"` | 長i (例: fin → fiːn) |
| yː | 0xE05A | `"y\u02d0"` | 長y (例: ny → nyː) |
| eː | 0xE05B | `"e\u02d0"` | 長e (例: lek → leːk) |
| ɛː | 0xE05C | `"\u025b\u02d0"` | 長ä (例: läsa → lɛːsa) |
| øː | 0xE05D | `"\u00f8\u02d0"` | 長ö (例: döda → døːda) |
| ɑː | 0xE05E | `"\u0251\u02d0"` | 長a (例: gata → gɑːta) |
| oː | 0xE05F | `"o\u02d0"` | 長å/長o (例: son → soːn, år → oːr) |
| uː | 0xE060 | `"u\u02d0"` | 長o デフォルト (例: bok → buːk) |
| ʉː | 0xE061 | `"\u0289\u02d0"` | 長u (例: hus → hʉːs) |

**注意:** Go の fixedPUA マップキーは IPA 文字列そのもの (例: `"iː"`) であり、Unicode エスケープではない。ソースコードに直接 IPA 文字を書く。既存の French エントリ (`"ɛ̃"`, `"ɑ̃"`, `"ɔ̃"`) と同じスタイル。

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|---|---|---|
| 実装エージェント | 1 | pua.go の変更 (3箇所) |

単純な定数追加タスクのため1名で十分。

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**スコープ内:**
- `fixedPUA` マップへの SV 9エントリ追加
- `nextDynamic` 初期値の 0xE059 → 0xE064 更新
- `ResetDynamicPUA()` 内の初期値更新
- コメントの更新 (エントリ総数、Swedish セクションラベル)

**スコープ外:**
- `swedish.go` の作成 (T-M1-02)
- 既存言語の PUA エントリ変更
- テストファイルの新規作成 (既存テストの PASS 確認のみ)

### 4.2 テスト項目

| # | テスト内容 | 期待結果 |
|---|---|---|
| 1 | `go build ./phonemize/...` | コンパイル成功 |
| 2 | `go vet ./phonemize/...` | エラーなし |
| 3 | 既存テスト `go test ./phonemize/...` | 全 PASS |
| 4 | 既存テスト `go test ./piperplus/...` | 全 PASS |
| 5 | `RegisterToken("iː")` が `string(rune(0xE059))` を返す | 固定PUA解決 |
| 6 | `RegisterToken("ʉː")` が `string(rune(0xE061))` を返す | 固定PUA解決 |
| 7 | `PUAToToken(0xE059)` が `"iː"` を返す | 逆引き成功 |
| 8 | `PUAToToken(0xE061)` が `"ʉː"` を返す | 逆引き成功 |
| 9 | `DynamicPUACount()` が 0 (初期状態) | 動的割り当て未使用 |

### 4.3 Unitテスト

既存の pua 関連テストが PASS することを確認する。新規テストは T-M1-02 以降で作成するが、手動で以下を確認:

```go
// 手動確認コード (テストに追加してもよい)
func TestSvPUARegistration(t *testing.T) {
    // 9つの長母音が全て固定PUAに登録済み
    svLongVowels := map[string]rune{
        "iː": 0xE059, "yː": 0xE05A, "eː": 0xE05B,
        "ɛː": 0xE05C, "øː": 0xE05D, "ɑː": 0xE05E,
        "oː": 0xE05F, "uː": 0xE060, "ʉː": 0xE061,
    }
    for token, expectedPUA := range svLongVowels {
        result := RegisterToken(token)
        if result != string(expectedPUA) {
            t.Errorf("RegisterToken(%q) = %q, want PUA U+%04X", token, result, expectedPUA)
        }
        // 逆引き確認
        got, ok := PUAToToken(expectedPUA)
        if !ok || got != token {
            t.Errorf("PUAToToken(0x%04X) = (%q, %v), want (%q, true)", expectedPUA, got, ok, token)
        }
    }
}
```

### 4.4 E2Eテスト

このチケット単体では E2E テスト不要。M2 以降で `SwedishPhonemizer` が `MapSequence()` を呼び出す際に、PUA 変換が正しく動作することを E2E で確認する。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念 | 対策 |
|---|---|---|
| 1 | 既存言語の PUA 範囲と衝突 | 0xE053 (Korean 末尾 0xE052 の次) はスキップ済み。French 末尾は 0xE058。SV は 0xE059 開始で安全 |
| 2 | ソースコード内の IPA 文字エンコーディング | Go ソースは UTF-8 必須。既存の French エントリ (`"ɛ̃"` 等) が既に IPA 直書きなので問題なし |
| 3 | fixedPUA のキー衝突 | 長母音トークン (`iː` 等) は他言語で未使用。日本語の `i:` (ASCII コロン 0x3A) と SV の `iː` (IPA length mark U+02D0) は異なるキーなので衝突しない |
| 4 | `ResetDynamicPUA()` の更新漏れ | `nextDynamic` の初期値が2箇所 (宣言 + Reset) にあるため、両方更新する |

### 5.2 レビューチェックリスト

- [ ] `fixedPUA` に9エントリが正しいコードポイントで追加されている
- [ ] PUA コードポイントが連続している (0xE059-0xE061、間に空きなし)
- [ ] `nextDynamic` が 0xE064 に更新されている (宣言箇所)
- [ ] `ResetDynamicPUA()` 内の `nextDynamic` が 0xE064 に更新されている
- [ ] コメントが正確 ("87 entries" → "96 entries", Swedish セクションラベル)
- [ ] 日本語の `i:` (ASCII) と SV の `iː` (U+02D0) が別キーであることを確認
- [ ] `go build`, `go vet`, `go test` が全て PASS

## 6. 一から作り直すとしたら

このタスクは単純な定数追加のため、改善余地は限定的。強いて言えば:

- `nextDynamic` の初期値が2箇所に分散している設計は、定数 (`const nextDynamicInit = 0xE064`) を導入して DRY にできるが、既存パターンを維持する方が一貫性がある。変更は別 PR で検討。
- 予約枠 (0xE062-0xE063) を2つ確保しているが、今後新しい言語が追加される場合の拡張性を考えると妥当。

## 7. 後続タスクへの連絡事項

- **T-M1-02 担当者へ:** `fixedPUA` に登録されたキーは IPA 文字列そのもの (`"iː"`, `"ɑː"` 等)。`swedish.go` の母音マッピング表で生成する長母音文字列がこれらのキーと完全一致する必要がある。Python 参照実装の `_LONG_VOWEL_MAP` の値 (例: `"\u0251\u02d0"` = `ɑː`) と一致していることを確認すること。
- **M2 担当者へ:** `MapSequence()` は `RegisterToken()` を内部で呼ぶため、`fixedPUA` に登録されたトークンは自動的に PUA 変換される。追加の登録処理は不要。
- 日本語の長母音 (`a:` = ASCII コロン) と SV の長母音 (`aː` = IPA length mark U+02D0) は異なるキーで管理されている。混同しないこと。
