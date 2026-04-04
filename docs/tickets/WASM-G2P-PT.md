# WASM-G2P-PT: ポルトガル語 G2P JS ルールベース移植

> **Phase:** 3 | **ステータス:** 未着手 | **並列:** Phase 1, 2 と同時実行可能
> **マイルストーン:** [wasm-g2p-implementation-milestones.md](../wasm-g2p-implementation-milestones.md#phase-3-ポルトガル語-pt--js-ルールベース移植)
> **ブランチ:** `fix/wasm-g2p-pt`

---

## 1. タスク目的とゴール

**目的:** `@piper-plus/g2p` のポルトガル語 G2P を、文字パススルー (68行) からルールベース IPA 変換 (~600行) に置き換える。BR (ブラジル) 方言対応。

**ゴール:**
- `"Bom dia"` → 鼻母音 õ + 口蓋化 dʒ (PUA E055) 含む IPA 列
- `"Brasil"` → coda-l 母音化 (l → w)
- `"tipo"` → 口蓋化 tʃ (PUA E054)
- golden test 3 件 + 個別テスト 35+ 件が全通過

**非ゴール:**
- PT-PT (ヨーロッパポルトガル語) 対応
- 母音調和・前強勢中母音上昇

---

## 2. 実装する内容の詳細

### 2-1. テキスト正規化・トークン化 (~60行)

| 移植元関数 (Rust) | JS関数名 | 概要 |
|------------------|---------|------|
| `collapse_nfd_combining_accents(cps)` | `collapseNfdAccents(cps)` | 6種結合マーク (acute, grave, circumflex, tilde, diaeresis, cedilla) |
| `to_lower(c)` | `toLower(c)` | ASCII + Latin-1 小文字化 |
| `normalize(text)` | `normalize(text)` | NFC + lowercase + 空白圧縮 |
| `tokenize(cps)` | `tokenize(cps)` | Word/Punct 分割 |

### 2-2. convert_word() コア (~250行)

Rust `convert_word()` (L555-811, ~260行) の線形スキャナ。

#### マルチ文字シーケンス

| パターン | 出力 | 備考 |
|---------|------|------|
| `nh` | ɲ | palatal nasal |
| `lh` | ʎ | palatal lateral |
| `ch` | ʃ | — |
| `rr` | ʁ | uvular (単一化) |
| `ss` | s | 単一化 |
| `sc` + soft vowel | s | 2文字消費 |
| `qu` + soft vowel | k (u 無音) | — |
| `qu` + other | kw | — |
| `gu` + soft vowel | ɡ (u 無音) | — |
| `ou` | o | BR 還元 |

#### 子音ルール

| 子音 | ルール |
|------|--------|
| `r` (介母音間) | → ɾ (tap) |
| `r` (その他) | → ʁ (uvular) |
| `s` (介母音間) | → z |
| `s` (その他) | → s |
| `x` (語頭/子音後) | → ʃ |
| `x` (介母音間) | → z |
| `c` + soft vowel | → s |
| `ç` | → s |
| `g` + soft vowel | → ʒ |
| `j` | → ʒ |
| `h` | 黙字 |

#### 母音ルール

| 母音 | ルール |
|------|--------|
| tilde (ã, õ) | → 鼻母音 (NFC precomposed: ã=U+00E3, õ=U+00F5) |
| 母音 + n/m + (語末/子音) | → 鼻母音 + n/m 吸収 (nh 前は除外) |
| acute (á, é, í, ó, ú) | → 開母音 (e→ɛ, o→ɔ, 他は base) |
| circumflex (â, ê, ô) | → 閉母音 (base) |
| その他 | → base |

### 2-3. BR 後処理パイプライン (~100行)

`process_word()` で順次適用する 3 段階:

```
convert_word() → removeDuplicateNasalCoda() → applyCodaLVocalization() → applyBrPostprocessing()
```

#### Stage 1: `removeDuplicateNasalCoda()`
- 鼻母音 + n/m の重複除去
- 例: "bom" → b õ (not b õ m)

#### Stage 2: `applyCodaLVocalization()`
- 音節末 l → w (語末/子音前/句読点前)
- 例: "Brasil" → b ɾ a z i **w**, "alto" → a **w** t u
- PUA affricate (E054, E055) も子音として認識

#### Stage 3: `applyBrPostprocessing()`
- 語範囲単位で処理 (`findWordRanges()`)
- 非ストレス語末 `e` + 先行 `t` → PUA tʃ (E054) + i
- 非ストレス語末 `e` + 先行 `d` → PUA dʒ (E055) + i
- 非ストレス語末 `e` (一般) → i
- 非ストレス語末 `o` → u

### 2-4. ストレス検出 (~40行)

| 関数 | 概要 |
|------|------|
| `findStressPosition(word)` | アクセント記号優先、なければ語尾規則 |
| `countVowelGroups(word)` | qu/gu + ou 考慮の音節数推定 |

ストレス位置規則:
- アクセント記号あり → その母音
- 末尾 a/e/o/am/em/ens → 次末 (paroxytone)
- 末尾子音 (s除く)/i/u → 最終 (oxytone)

### 2-5. PUA マッピング

| トークン | PUA | 用途 |
|---------|-----|------|
| tʃ (`t\u0283`) | `\uE054` | BR 口蓋化 ti → tʃi |
| dʒ (`d\u0292`) | `\uE055` | BR 口蓋化 di → dʒi |

PT の鼻母音 (ã, ẽ, ĩ, õ, ũ) は NFC precomposed Unicode で、PUA マッピング不要。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| **実装エージェント** | 1 | `pt/index.js` フル実装 (convert_word + BR後処理) |
| **テストエージェント** | 1 | `test-portuguese.js` 作成 + Rust 18 テスト移植 |

**合計: 2 エージェント**

---

## 4. 提供範囲とテスト

### Unit テスト (`test-portuguese.js`)

Rust 18 テストケースの移植:

| カテゴリ | テスト | 検証 |
|---------|--------|------|
| 鼻母音 | `"bom"` | õ (U+00F5) |
| coda-l | `"Brasil"` | l → w |
| 口蓋化 | `"tia"` → tʃ, `"dia"` → dʒ | PUA E054, E055 |
| r 多型 | `"caro"` → ɾ, `"rato"` → ʁ | tap vs uvular |
| lh/nh | `"filho"` → ʎ, `"junho"` → ɲ | palatal |
| ストレス | `"café"` (最終), `"casa"` (次末) | ˈ 位置 |
| 母音弱化 | `"grande"` → 末尾 e→i | BR 後処理 |
| 母音弱化 | `"gato"` → 末尾 o→u | BR 後処理 |
| ç | `"coração"` | s |
| rr | `"carro"` | ʁ (単一化) |
| qu | `"quero"` (k), `"quando"` (kw) | 軟母音判定 |
| 介母音間 s | `"casa"` | z |
| ss | `"passo"` | s (単一化) |
| prosody | length match | tokens.length === prosody.length |
| NFD | 結合アクセント正規化 | NFC 出力 |
| 複文 | `"Bom dia, como você está?"` | 複数語処理 |

### E2E テスト

- `IPA_OUTPUT_LANGUAGES` に `'pt'` 追加
- golden test 3 件の `expected_contains` 有効化

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| BR 後処理の語範囲判定 | スペース区切りの語境界でストレス index がずれる | `findWordRanges()` のオフセット計算を正確に |
| 鼻母音 + nh ガード | `"manhã"` で nh 前の a が鼻母音化しない | nh ダイグラフチェックを鼻母音判定前に実行 |
| coda-l の位置判定 | PUA affricate を子音として認識する必要 | `isIpaConsonant()` に PUA E054/E055 を含める |
| ストレス index と後処理の連動 | 後処理で phoneme 挿入/削除するとストレス位置がずれる | Rust と同じ固定 index 方式を維持 |

### レビュー項目

- [ ] BR 後処理 3 段階の順序が Rust と一致
- [ ] 鼻母音 5種 (ã, ẽ, ĩ, õ, ũ) の precomposed Unicode 出力
- [ ] PUA 2 種 (E054 tʃ, E055 dʒ) の正確な出力
- [ ] r 多型性: 介母音間 ɾ vs その他 ʁ
- [ ] coda-l 母音化: 語末/子音前の l → w
- [ ] ストレス位置: アクセント記号 + 語尾規則
- [ ] golden test 3 件通過

---

## 6. 一から作り直すとしたら

### BR 後処理パイプラインの設計

**現在の Rust 実装:** 3 関数を順次適用。各関数は `&mut Vec<char>` を in-place 変更。

**もし一から設計するなら:**

1. **Composable パイプライン (推奨):**
   ```javascript
   // 各ステップを独立 export して個別テスト可能に
   export function removeDuplicateNasalCoda(phonemes) { ... }
   export function applyCodaLVocalization(phonemes) { ... }
   export function applyBrPostprocessing(phonemes, stressIdx) { ... }
   ```
   - Rust は `&mut` で in-place 変更だが、JS では新配列返却の方が immutable で安全
   - 各ステップの入出力をテストで個別検証可能

2. **PT-PT 拡張を見据えた方言パラメータ:**
   ```javascript
   class PortugueseG2P {
       constructor({ dialect = 'br' } = {}) {
           this.dialect = dialect;
           this.postProcessors = dialect === 'br'
               ? [removeDuplicateNasalCoda, applyCodaLVocalization, applyBrPostprocessing]
               : [removeDuplicateNasalCoda]; // PT-PT: coda-l/口蓋化なし
       }
   }
   ```
   - `convert_word()` 内の ti→tʃ ルールも方言パラメータで分岐可能に
   - **判断:** constructor に `dialect` オプションを用意するが、初期実装は BR のみ

3. **r 多型性の位置判定:**
   - 現在: grapheme-level `isIntervocalic()` (前後が母音文字か)
   - 代替: 音素列での後処理 (phoneme-level intervocalic check)
   - **判断:** Rust と同じ grapheme-level を維持。rr/nh/lh は先にマッチされるため、r 単独の介母音間判定に到達するケースでは grapheme-level で十分正確

4. **FR との鼻母音共通化:**
   - PT: 「母音 → n/m 吸収チェック → 鼻母音」パターン
   - FR: 「an/am → 直接鼻母音トークン」パターン (2文字消費)
   - 共通化可能: `isNasalContext(word, i)` 判定関数のみ
   - **判断:** 共通化は最小限に留める。マッピング自体は言語固有

---

## 7. 後続タスクへの連絡事項

### Phase 5 (テスト統合) への連絡

- `IPA_OUTPUT_LANGUAGES` に `'pt'` 追加
- `g2p-wasm-ci.yml` に `test/test-portuguese.js` 追加
- PT の鼻母音は NFC precomposed (ã=U+00E3 等) であり、FR の PUA (E056-E058) とは異なる形式であることに注意
- PUA E054/E055 は ES と共有

### ES/FR チームへの連絡

- NFD/NFC 正規化は ES/FR/PT で同一パターン。先に完成した実装をコピー可能
- `tokenize()` も同一パターン (Word/Punct 分割、alpha 判定のみ言語固有)
- テスト構造 (`test-spanish.js`, `test-french.js`) をテンプレートとして使用
