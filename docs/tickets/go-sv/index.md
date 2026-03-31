# Go スウェーデン語 G2P — チケットインデックス

> **PR**: #270 (`feat/go-bindings`)
> **マイルストーン**: [`docs/design/go-swedish-milestones.md`](../../design/go-swedish-milestones.md)
> **技術設計**: [`docs/design/go-swedish-g2p-impl-plan.md`](../../design/go-swedish-g2p-impl-plan.md)

---

## 依存関係グラフ

```
M1: PUA基盤 + 定数定義
  T-M1-01 ──→ T-M1-02 ──→ T-M2-01
                              │
M2: G2Pコアエンジン           │
  T-M2-01 ──→ T-M2-02 ──┐   │
              T-M2-03 ──┤   │
              T-M2-04 ──┤   │
                        ↓   │
              T-M2-05 ←─┘   │
                  │          │
M3: 後処理 + 統合 │          │
  T-M3-01 ←──────┘          │
  T-M3-02 ←──────┘          │
                  │          │
  T-M3-03 ←── T-M3-01 + T-M3-02
      │
      ├───→ M4: テストスイート
      │       T-M4-01
      │       T-M4-02
      │
      └───→ M5: マルチリンガル統合 (M4と並行可)
              T-M5-01
              T-M5-02
```

---

## チケット一覧

### M1: PUA基盤 + 定数定義 (2チケット)

| ID | タイトル | 対象ファイル | 状態 |
|---|---|---|---|
| [T-M1-01](T-M1-01-pua-sv-registration.md) | PUA SV長母音エントリ登録 | `pua.go` | TODO |
| [T-M1-02](T-M1-02-sv-constants-exception-lists.md) | SV定数・例外語リスト定義 | `swedish.go` (新規) | TODO |

### M2: G2Pコアエンジン (5チケット)

| ID | タイトル | 対象ファイル | 状態 |
|---|---|---|---|
| [T-M2-01](T-M2-01-phonemizer-struct-normalize-tokenize.md) | SwedishPhonemizer構造体 + 正規化 + トークン化 | `swedish.go` | TODO |
| [T-M2-02](T-M2-02-loanword-suffix-detection.md) | ローンワード接尾辞検出 | `swedish.go` | TODO |
| [T-M2-03](T-M2-03-consonant-conversion.md) | 子音変換エンジン | `swedish.go` | TODO |
| [T-M2-04](T-M2-04-vowel-length-complementary-quantity.md) | 母音長判定 (Complementary Quantity) | `swedish.go` | TODO |
| [T-M2-05](T-M2-05-word-g2p-integration.md) | 単語G2P統合 | `swedish.go` | TODO |

### M3: 後処理 + Phonemizer統合 (3チケット)

| ID | タイトル | 対象ファイル | 状態 |
|---|---|---|---|
| [T-M3-01](T-M3-01-retroflex-assimilation.md) | レトロフレックス同化 | `swedish.go` | TODO |
| [T-M3-02](T-M3-02-stress-detection-insertion.md) | ストレス検出 + マーカー挿入 | `swedish.go` | TODO |
| [T-M3-03](T-M3-03-phonemize-with-prosody-integration.md) | PhonemizeWithProsody統合 | `swedish.go` | TODO |

### M4: テストスイート (2チケット)

| ID | タイトル | 対象ファイル | 状態 |
|---|---|---|---|
| [T-M4-01](T-M4-01-basic-rule-tests.md) | 基本規則テスト (~80テスト) | `swedish_test.go` (新規) | TODO |
| [T-M4-02](T-M4-02-stress-prosody-integration-tests.md) | ストレス・Prosody・統合テスト (~60テスト) | `swedish_test.go` | TODO |

### M5: マルチリンガル統合 (2チケット)

| ID | タイトル | 対象ファイル | 状態 |
|---|---|---|---|
| [T-M5-01](T-M5-01-language-detection-multilingual.md) | SV言語検出 + マルチリンガル統合 | `unicode_detect.go`, `multilingual.go` | TODO |
| [T-M5-02](T-M5-02-registry-documentation.md) | レジストリ登録 + ドキュメント更新 | `synthesize.go`, `README.md` | TODO |

---

## 統計

| 指標 | 値 |
|---|---|
| 総チケット数 | 14 |
| 新規ファイル | 2 (`swedish.go`, `swedish_test.go`) |
| 変更ファイル | 6 (`pua.go`, `unicode_detect.go`, `multilingual.go`, `synthesize.go`, `README.md`, テスト) |
| 推定総行数 | ~3,000 |
| 推定テスト数 | ~140 |
