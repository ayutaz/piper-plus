# WASM-G2P-ES: スペイン語 G2P JS ルールベース移植

> **Phase:** 1 | **ステータス:** 未着手 | **並列:** Phase 2, 3 と同時実行可能
> **マイルストーン:** [wasm-g2p-implementation-milestones.md](../wasm-g2p-implementation-milestones.md#phase-1-スペイン語-es--js-ルールベース移植)
> **ブランチ:** `fix/wasm-g2p-es`

---

## 1. タスク目的とゴール

**目的:** npm パッケージ `@piper-plus/g2p` のスペイン語 G2P を、文字パススルー (68行) からルールベース IPA 変換 (~600行) に置き換える。

**ゴール:**
- `"hola"` → `["ˈ", "o", "l", "a"]` (golden test exact match)
- `"perro grande"` → PUA rr (`\uE01D`) トークン含む IPA 列
- Rust/Python 実装と同等の phoneme_id 列を生成
- golden test 3件 + 個別テスト 30+ 件が全通過

**非ゴール:**
- liaison/elision 処理 (Python 固有機能、Rust にもない)
- 方言対応 (Rioplatense 等)

---

## 2. 実装する内容の詳細

### 2-1. テキスト正規化・トークン化

| 移植元関数 (Rust) | JS関数名 (案) | 行数目安 |
|------------------|-------------|---------|
| `collapse_combiners(cps)` | `collapseCombiningAccents(cps)` | ~30 |
| `normalize(text)` | `normalize(text)` | ~15 |
| `to_lower_sp(c)` | `toLowerSp(c)` | ~20 |
| `tokenize(cps)` | `tokenize(cps)` | ~25 |
| `is_spanish_alpha(c)`, `is_punctuation(c)` | 同名 | ~15 |

Unicode NFD 結合文字 (U+0301 acute, U+0303 tilde, U+0308 diaeresis) を NFC に正規化。

### 2-2. 書記素分割・音節分割・ストレス

| 移植元関数 (Rust) | JS関数名 (案) | 行数目安 |
|------------------|-------------|---------|
| `segment_graphemes(word)` | `segmentGraphemes(word)` | ~80 |
| `find_syllable_boundaries(units)` | `findSyllableBoundaries(units)` | ~60 |
| `get_stressed_syllable(word, units, boundaries)` | `getStressedSyllable(...)` | ~40 |
| `is_inseparable(c1, c2)` | `isInseparable(c1, c2)` | ~10 |

二重字認識: ch, ll, rr, qu, gu, sc, xc。
ストレス3規則: (1) アクセント記号 → その音節, (2) 母音/n/s 末尾 → 次末, (3) その他 → 最終。
機能語 28語 (`UNSTRESSED_FUNCTION_WORDS`) はストレス除外。

### 2-3. G2P 変換コア

| ルール | 入力例 | 出力 | PUA |
|--------|--------|------|-----|
| seseo (c/z) | `"cena"`, `"zapato"` | s | — |
| ch affricate | `"chico"` | tʃ | E054 |
| ll yeismo | `"calle"` | ʝ | — |
| rr trill | `"perro"` | rr | E01D |
| 語頭 r | `"rosa"` | rr | E01D |
| ñ palatal | `"niño"` | ɲ | — |
| b/v 異音 | `"lobo"` (母音間) | β | — |
| d 異音 | `"todo"` (母音間) | ð | — |
| g 異音 | `"lago"` (母音間) | ɣ | — |
| qu → k | `"queso"` | k | — |
| gu + e/i | `"guerra"` | ɡ (u無音) | — |
| j, g+e/i | `"jota"`, `"gente"` | x | — |
| h 黙字 | `"hola"` | (削除) | — |
| ストレス | `"teléfono"` | ˈ 挿入 | — |

**移植元:** `g2p_word()` (Rust L584-871, ~290行) → JS `g2pWord()` (~200行)

### 2-4. PUA マッピング・出力

`map_sequence()` で multi-char IPA → PUA 変換。ES で使用する PUA:
- `rr` → `\uE01D` (pua-map.js に定義済み)
- `tʃ` → `\uE054` (pua-map.js に定義済み)

### クラス構造 (KO/SV テンプレートに従う)

```javascript
// PUA + IPA 定数
const PUA_RR = '\uE01D';
const PUA_TCH = '\uE054';
const IPA_BETA = '\u03B2';
// ... (8個)

// ヘルパー関数群 (~300行)
function normalize(text) { ... }
function tokenize(cps) { ... }
function segmentGraphemes(word) { ... }
function findSyllableBoundaries(units) { ... }
function getStressedSyllable(...) { ... }
function g2pWord(word) { ... }
function insertStressMarker(...) { ... }
function mapSequence(tokens) { ... }

// export クラス (~50行)
export class SpanishG2P {
    constructor(options = {})
    get languageCode() { return 'es'; }
    phonemize(text) { ... }
    phonemizeWithProsody(text) { ... }
}
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| **実装エージェント** | 1 | `es/index.js` のフル実装 (Rust → JS 移植) |
| **テストエージェント** | 1 | `test-spanish.js` 作成 + golden test 更新 |

**合計: 2エージェント** (実装とテストを並列化可能。実装が API 構造テスト完了後、テストエージェントがルールテストを追加)

**各エージェントへの提供物:**
- 移植元: `src/rust/piper-plus-g2p/src/spanish.rs` (1,397行)
- 移植先: `src/wasm/g2p/src/es/index.js` (上書き)
- テンプレート: `src/wasm/g2p/src/ko/index.js` (クラス構造), `src/wasm/g2p/src/sv/index.js` (ルール処理参考)
- PUA定義: `src/wasm/g2p/src/pua-map.js`
- テストテンプレート: `src/wasm/g2p/test/test-korean.js`
- フィクスチャ: `tests/fixtures/g2p/phoneme_test_cases.json`

---

## 4. 提供範囲とテスト

### スコープ

| 含む | 含まない |
|------|---------|
| 全 G2P ルール (seseo, yeismo, 異音, 二重字) | liaison / elision |
| ストレス検出 (3規則 + 機能語除外) | 方言分岐 (Rioplatense) |
| PUA マッピング (rr, tʃ) | prosody A1/A2/A3 (ES は null) |
| NFD/NFC 正規化 | 数字→テキスト変換 |

### Unit テスト (`test-spanish.js`)

Rust の 27 テストケースを移植:

| カテゴリ | テストケース | 検証内容 |
|---------|------------|---------|
| API | `phonemize()` 戻り値構造 | `{ tokens, prosody }` |
| API | `languageCode` | `'es'` |
| 基本 | `"hola"` exact match | `["ˈ", "o", "l", "a"]` |
| seseo | `"cena"`, `"zapato"` | `s` 含む, `z` なし |
| affricate | `"chico"` | PUA `\uE054` 含む |
| yeismo | `"calle"` | `ʝ` 含む |
| trill | `"perro"`, `"rosa"` | PUA `\uE01D` 含む |
| palatal | `"niño"` | `ɲ` 含む |
| 異音 | `"lobo"`, `"todo"`, `"lago"` | β, ð, ɣ 含む |
| ストレス | `"casa"` (次末), `"ciudad"` (最終) | ˈ 位置 |
| 機能語 | `"el"`, `"de"` | ˈ なし |
| qu/gu | `"queso"`, `"guerra"` | k, ɡ |
| j/g+ei | `"jota"`, `"gente"` | x 含む |
| h 黙字 | `"hola"` | h なし |
| NFD | `"HOLA"` | 小文字正規化 |
| b/v 語頭 | `"vino"` | `b` (stop) |
| nasal+b | `"hambre"` | `b` (stop, not β) |
| 複文 | `"Buenos dias amigo"` | 複数語処理 |
| 空文字列 | `""` | 空配列 |
| sc | `"piscina"` | 単一 `s` |

### E2E テスト

- golden test (`test-g2p-golden.js`): `IPA_OUTPUT_LANGUAGES` に `'es'` 追加
- フィクスチャ 3 件の `expected_contains` チェック有効化
- `"hola"` の `expected_tokens` exact match 有効化

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| NFD 正規化の不完全 | macOS が NFD を生成する場合がある | `collapseCombiningAccents()` で全結合マーク対応 |
| 二重母音 vs ヒアトゥスの判定 | 音節分割で誤判定 → ストレス位置ずれ | Rust テストの全ケースを移植して検証 |
| `x` の処理 | 位置依存 (語頭 `ks`, 語中 `ks`) | Rust と同一ルールを移植 |
| ˈ 挿入位置 | 多音節語で音素数カウントずれ | `phonemeCountForUnit()` を正確に移植 |

### レビュー項目

- [ ] Rust テスト 27 件と JS テストの 1:1 対応確認
- [ ] PUA マッピング (rr→E01D, tʃ→E054) の正確性
- [ ] 機能語リスト 28 語の完全移植
- [ ] `segment_graphemes()` の二重字リスト完全移植 (ch, ll, rr, qu, gu, sc, xc)
- [ ] `is_inseparable()` の子音クラスタ 13 組の完全移植
- [ ] golden test `"hola"` の exact match 通過

---

## 6. 一から作り直すとしたら

### アーキテクチャ再考

**現在の方針:** 言語ごとに独立した JS ファイル (ko/index.js, sv/index.js, es/index.js)。

**もし一から設計するなら:**

1. **ラテン系共通基盤 (`latin-common.js`) の先行設計:**
   - ES/FR/PT で共通する処理: NFD/NFC 正規化, テキストトークナイズ (Word/Punct 分割), 母音/子音分類の基底セット
   - ただし音節分割・ストレス規則・異音規則は言語固有のため、共通化は正規化+トークナイザ程度に留める
   - **判断:** ES を単独でフル実装し、FR/PT 移植時に共通部分を抽出する方が安全 (premature abstraction 回避)

2. **テスト駆動開発 (TDD):**
   - 最初に golden test 3 件 + API 構造テスト 3 件を書く
   - 次に `"hola"` exact match を通すための最小実装
   - その後 Rust テスト 27 件を段階的に追加しながら実装を拡充
   - **利点:** 各ルールの追加が回帰テストで保護される

3. **Rust → JS 自動トランスパイル:**
   - LLM 支援で Rust 1,100 行 → JS ~600 行の変換は可能だが、手動レビュー必須
   - KO/SV の移植実績でパターンが確立されているため、手動移植の方が品質管理しやすい
   - **判断:** 手動移植推奨

### 設計判断の記録

| 判断 | 選択 | 理由 |
|------|------|------|
| 共通基盤 | ES 単独先行 | premature abstraction 回避。FR/PT 後で抽出 |
| 開発手法 | TDD | 回帰テスト保護。golden test → 個別ルール の順 |
| 移植方法 | 手動 (Rust 参照) | パターン確立済み、品質管理容易 |
| PUA 処理 | 既存 pua-map.js 使用 | 変更不要 |

---

## 7. 後続タスクへの連絡事項

### Phase 2 (FR), Phase 3 (PT) への連絡

- **ES で確立した JS クラス構造** (`constructor`, `phonemize`, `phonemizeWithProsody`, `languageCode`) を FR/PT でも踏襲すること
- **NFD/NFC 正規化** (`collapseCombiningAccents`) は ES/FR/PT で同一ロジック。ES 実装を参考にコピーまたは共通化
- **テスト構造** (`test-spanish.js`) を FR/PT のテストテンプレートとして使用可能
- **機能語リスト** は言語固有。ES の `UNSTRESSED_FUNCTION_WORDS` パターンを参考に FR/PT でも定義

### Phase 5 (テスト統合) への連絡

- `test-g2p-golden.js` の `IPA_OUTPUT_LANGUAGES` に `'es'` を追加する必要あり
- `g2p-wasm-ci.yml` のテスト実行コマンドに `test/test-spanish.js` を追加
- ES exact match テストケース `"hola"` が通過することを確認
