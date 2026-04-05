# WASM G2P: ZH/FR/PT/ES 実装マイルストーン

> **前提ドキュメント:** [wasm-g2p-zh-fr-pt-gap-analysis.md](./wasm-g2p-zh-fr-pt-gap-analysis.md)
> **ブランチ:** `fix/wasm-zh-fr-pt-phonemizer`
> **作成日:** 2026-04-05

---

## チケット一覧

| チケット | Phase | ステータス | 詳細 |
|---------|-------|----------|------|
| [WASM-G2P-ES](./tickets/WASM-G2P-ES.md) | 1 | 未着手 | ES Rust→JS移植 (~600行) |
| [WASM-G2P-FR](./tickets/WASM-G2P-FR.md) | 2 | 未着手 | FR Rust→JS移植 (~680行) |
| [WASM-G2P-PT](./tickets/WASM-G2P-PT.md) | 3 | 未着手 | PT Rust→JS移植 (~600行) + BR後処理 |
| [WASM-G2P-ZH](./tickets/WASM-G2P-ZH.md) | 4 | 未着手 | ZH Rust WASM統合 + 辞書2.6MB |
| [WASM-G2P-TEST](./tickets/WASM-G2P-TEST.md) | 5 | 未着手 | golden test全言語対応 + CI統合 |

---

## 全体方針

- **ES/FR/PT:** Rust 実装を JS にルールベース移植（KO/SV と同じアプローチ）
- **ZH:** ピンイン辞書 (2.6MB) が必要なため、Rust WASM 経由で呼び出し
- **並列化:** ES/FR/PT は互いに独立しており、3エージェント同時並行可能
- **移植元:** `src/rust/piper-plus-g2p/src/{spanish,french,portuguese,chinese}.rs`
- **移植先テンプレート:** `src/wasm/g2p/src/{ko,sv}/index.js` の構造に従う

### 共通インターフェース (全言語共通)

```javascript
export class {Language}G2P {
    constructor(options = {})
    get languageCode()              // → 'es' | 'fr' | 'pt' | 'zh'
    setPhonemeIdMap(phonemeIdMap)    // config.json の phoneme_id_map を設定
    phonemize(text)                 // → { tokens: string[], prosody: null[] }
    phonemizeWithProsody(text)      // → { tokens: string[], prosody: (ProsodyInfo|null)[] }
}
```

### PUA マッピング (既存 `pua-map.js` に定義済み)

| 言語 | PUA エントリ数 | 主要トークン |
|------|--------------|------------|
| ES | 3 | rr (E01D), tʃ (E054), dʒ (E055) |
| FR | 3 + 1共有 | ɛ̃ (E056), ɑ̃ (E057), ɔ̃ (E058), y_vowel (E01E, 共有) |
| PT | 0 | (ES/FR の PUA を共有: tʃ, dʒ, 鼻母音は precomposed Unicode) |
| ZH | 43 | tone1-5, aspirated, affricates, diphthongs |

---

## Phase 1: スペイン語 (ES) — JS ルールベース移植

### 概要

| 項目 | 値 |
|------|-----|
| 移植元 | `src/rust/piper-plus-g2p/src/spanish.rs` (1,397行) |
| 推定JS行数 | ~500-600行 |
| 難易度 | 中 |
| 依存 | なし（ルールベース、外部辞書不要） |
| 並列可能 | Phase 2, 3 と同時実行可能 |

### タスク一覧

#### 1-1. テキスト正規化・トークン化

**対象ファイル:** `src/wasm/g2p/src/es/index.js`

移植する関数:
- `normalize()` — Unicode NFD 結合文字の正規化、句読点処理
- `to_lower_sp()` — スペイン語固有の小文字変換 (ñ, ü 保持)
- `collapse_combiners()` — 結合アクセント記号の処理
- `tokenize()` — 単語/句読点の分離
- `is_spanish_alpha()`, `is_punctuation()` — 文字分類

**受け入れ基準:**
- `"¿Cómo estás?"` → 3 トークン (`¿cómo`, `estás`, `?`) に分割
- NFD 形式のアクセント文字が正しく正規化される

#### 1-2. 音節分割・ストレス検出

移植する関数:
- `segment_graphemes()` — グラフェム分割 (ch, ll, rr 等の二重字認識)
- `find_syllable_boundaries()` — 音節境界検出
- `get_stressed_syllable()` — ストレス位置決定
- `find_accent_index()` — アクセント記号によるストレス位置
- `is_strong_vowel()`, `is_weak_vowel()` — 二重母音判定
- `has_stress_accent()` — アクセント記号判定
- `is_inseparable()` — 分離不可能な子音クラスタ (pr, bl, tr 等)

**受け入れ基準:**
- `"perro"` → 2 音節 (`pe`, `rro`), ストレス = 第1音節
- `"español"` → 3 音節, ストレス = 最終音節 (アクセント記号)

#### 1-3. G2P ルール・IPA 変換

移植する関数:
- `g2p_word()` — 単語のグラフェム→IPA変換 (主要ロジック)
  - `b/v` → [β] (母音間), [b] (その他)
  - `d` → [ð] (母音間), [d] (その他)
  - `g` → [ɣ] (母音間), [ɡ] (その他)
  - `c` → [θ]/[s] (e/i 前), [k] (その他)
  - `g` → [x] (e/i 前), [ɡ] (その他)
  - `j` → [x]
  - `ñ` → [ɲ]
  - `ll` → [ʝ]
  - `rr` → PUA rr (E01D)
  - `qu` → [k], `gu` → [ɡ] (e/i 前)
  - `h` → 黙字 (削除)
- `insert_stress_marker()` — ˈ マーカー挿入
- `phoneme_count_for_unit()` — 音素数カウント
- `map_sequence()` — PUA マッピング適用

**受け入れ基準:**
- `"hola"` → `["ˈ", "o", "l", "a"]` (フィクスチャ exact match)
- `"perro grande"` → rr PUA トークン含む
- `"¿Cómo estás?"` → ストレスマーカー、逆疑問符号含む

#### 1-4. テスト追加

**対象ファイル:** `src/wasm/g2p/test/test-spanish.js` (新規作成)

- フィクスチャ golden テスト: `IPA_OUTPUT_LANGUAGES` に `'es'` 追加
- 個別ルールテスト: 異音変化 (b→β, d→ð, g→ɣ), rr, ñ→ɲ, qu/gu, h 黙字
- ストレステスト: アクセント記号, 位置規則
- エッジケース: 数字、記号、空文字列

**受け入れ基準:**
- `test-g2p-golden.js` の ES ケース 3 件が `expected_contains` チェックを通過
- 個別テスト 30+ ケース (KO: 91, SV: 67 を参考)

---

## Phase 2: フランス語 (FR) — JS ルールベース移植

### 概要

| 項目 | 値 |
|------|-----|
| 移植元 | `src/rust/piper-plus-g2p/src/french.rs` (1,586行) |
| 推定JS行数 | ~600-750行 |
| 難易度 | 高 (最も複雑なルール体系) |
| 依存 | なし（ルールベース、外部辞書不要） |
| 並列可能 | Phase 1, 3 と同時実行可能 |

### タスク一覧

#### 2-1. テキスト正規化・単語分割

**対象ファイル:** `src/wasm/g2p/src/fr/index.js`

移植する関数:
- `normalize()` — テキスト正規化
- `collapse_nfd()` — NFD 結合文字処理
- `to_lower_fr()` — フランス語小文字変換 (ç, é, è, ê, ë 等保持)
- `normalize_apostrophes()` — アポストロフィ正規化 (l', d', j' 等)
- `split_words()` — 単語分割 (エリジオン、ハイフン処理)

**受け入れ基準:**
- `"l'homme"` → エリジオン付き単語として処理
- `"Comment allez-vous?"` → ハイフン単語の正しい分割

#### 2-2. 鼻母音・二重字処理

移植する関数 (全て `convert_word()` 内のサブロジック):
- 鼻母音ルール:
  - `an/am/en/em` → ɑ̃ (PUA E057)
  - `in/im/yn/ym` → ɛ̃ (PUA E056)
  - `on/om` → ɔ̃ (PUA E058)
  - `un/um` → ɛ̃
- 二重字ルール:
  - `ch` → ʃ, `gn` → ɲ, `ph` → f, `th` → t, `qu` → k
- 母音二重字:
  - `ou` → u, `au/eau` → o, `oi` → wa, `ai/ei` → ɛ, `eu` → ø/œ

**受け入れ基準:**
- `"bonjour"` → `b ɔ̃ ʒ u ʁ` (鼻母音 + 後部歯茎摩擦音)
- `"français"` → ɑ̃ (PUA E057) 含む
- `"chambre"` → ʃ 含む

#### 2-3. 黙字・語尾・特殊ルール

移植する関数 (全て `convert_word()` 内):
- 黙字末尾子音: d, g, h, m, n, p, s, t, x, z
- `-er` 動詞語尾 → /e/ (多音節), /ɛʁ/ (単音節)
- `-tion` → /sjɔ̃/
- `-ille/-eille/-ouille/-aille` パターン
- `is_ille_as_il()`, `is_er_as_ehr()` — 例外辞書
- 母音間 `s` 有声化 → /z/
- `y_vowel` (u→/y/) — PUA E01E
- `is_front_vowel_for_cg()` — c/g の前舌母音ルール

**受け入れ基準:**
- `"parler"` → 末尾 /e/, `"mer"` → 末尾 /ɛʁ/
- `"maison"` → 母音間 s → z
- `"tu"` → y_vowel (PUA E01E)

#### 2-4. ストレス処理・シーケンスマッピング

移植する関数:
- ストレス: フランス語は語末ストレス (固定)
- `count_vowels()` — 母音数カウント
- `is_vowel_phoneme()` — IPA 母音判定
- `map_sequence()` — PUA マッピング適用

**受け入れ基準:**
- ストレスマーカーが語末母音前に挿入される

#### 2-5. テスト追加

**対象ファイル:** `src/wasm/g2p/test/test-french.js` (新規作成)

- フィクスチャ golden テスト: `IPA_OUTPUT_LANGUAGES` に `'fr'` 追加
- 個別ルールテスト: 鼻母音 3種, 黙字, -er 語尾, -ille パターン, 母音間 s
- エッジケース: エリジオン (l', d'), ハイフン語
- 例外辞書テスト: ville, mille (ille-as-il), mer, fer (er-as-ehr)

**受け入れ基準:**
- golden テスト FR 3 件が `expected_contains` チェック通過
- 個別テスト 40+ ケース

---

## Phase 3: ポルトガル語 (PT) — JS ルールベース移植

### 概要

| 項目 | 値 |
|------|-----|
| 移植元 | `src/rust/piper-plus-g2p/src/portuguese.rs` (1,352行) |
| 推定JS行数 | ~500-650行 |
| 難易度 | 高 (BR方言の後処理が複雑) |
| 依存 | なし（ルールベース、外部辞書不要） |
| 並列可能 | Phase 1, 2 と同時実行可能 |

### タスク一覧

#### 3-1. テキスト正規化・トークン化

**対象ファイル:** `src/wasm/g2p/src/pt/index.js`

移植する関数:
- `normalize()` — テキスト正規化
- `collapse_nfd_combining_accents()` — NFD 結合アクセント処理
- `to_lower()` — 小文字変換 (ã, õ, ç 等保持)
- `tokenize()` — 単語/句読点分離
- `is_word_char()`, `is_punctuation()` — 文字分類

**受け入れ基準:**
- アクセント付き文字 (á, é, ã, õ) が正しく保持される
- NFD 形式の入力が正規化される

#### 3-2. 鼻母音・二重字処理

移植する関数:
- 鼻母音:
  - チルダ: `ã, õ` → そのまま (precomposed Unicode)
  - 母音 + n/m + 子音 → 鼻母音 (`nasal_of()`)
  - `ẽ, ĩ, ũ` — 追加の鼻母音
- 二重字:
  - `nh` → ɲ, `lh` → ʎ, `ch` → ʃ
  - `rr` → ʁ, `ss` → s
  - `sc` (e/i 前) → s
  - `qu` (e/i 前) → k, (a/o 前) → kw
- `remove_duplicate_nasal_coda()` — 鼻母音後の鼻音子音削除 (`"bom"` → b õ, not b õ m)

**受け入れ基準:**
- `"Bom dia"` → 鼻母音 õ 含む
- `"senhor"` → ɲ 含む
- `"chuva"` → ʃ 含む

#### 3-3. ブラジルポルトガル語 (BR) 後処理

移植する関数:
- `apply_br_postprocessing()` — BR方言の後処理統合
  - t/d 口蓋化: `ti` → tʃi (PUA E054), `di` → dʒi (PUA E055)
  - Coda-l 母音化: 音節末 l → w (`apply_coda_l_vocalization()`)
  - r 多型性: 介母音 r → ɾ, 語頭/語末 r → ʁ
- 母音弱化: 無強勢語末 `o` → u, `e` → i
- `is_intervocalic()` — 母音間位置判定

**受け入れ基準:**
- `"tipo"` → tʃ (PUA E054) 含む
- `"Brasil"` → 末尾 l → w
- `"caro"` → 介母音 r → ɾ, `"rato"` → 語頭 r → ʁ

#### 3-4. ストレス検出

移植する関数:
- `find_stress_position()` — ストレス位置検出
  - アクセント記号優先 (á, é, í, ó, ú, â, ê, ô)
  - 位置規則: 末尾 a/e/o/am/em → 次末, 末尾子音/i/u → 末尾
- `count_vowel_groups()` — 母音群カウント (音節数推定)
- `is_stress_accent()`, `is_circumflex()`, `is_tilde()` — アクセント種別判定

**受け入れ基準:**
- `"olá"` → 最終音節ストレス (アクセント記号)
- `"Obrigado"` → 次末音節ストレス (位置規則)

#### 3-5. テスト追加

**対象ファイル:** `src/wasm/g2p/test/test-portuguese.js` (新規作成)

- フィクスチャ golden テスト: `IPA_OUTPUT_LANGUAGES` に `'pt'` 追加
- 個別ルールテスト: 鼻母音, 口蓋化, coda-l, r多型性, 母音弱化
- BR後処理テスト: ti→tʃi, di→dʒi, l→w
- ストレステスト: アクセント記号, 位置規則

**受け入れ基準:**
- golden テスト PT 3 件が `expected_contains` チェック通過
- 個別テスト 35+ ケース

---

## Phase 4: 中国語 (ZH) — Rust WASM 統合

### 概要

| 項目 | 値 |
|------|-----|
| 移植元 | `src/rust/piper-plus-g2p/src/chinese.rs` (1,252行) |
| 辞書サイズ | `pinyin_single.json` (688KB) + `pinyin_phrases.json` (1.9MB) = 2.6MB |
| 難易度 | 極高 (辞書バンドル + WASM 統合) |
| 依存 | Phase 1-3 完了後が望ましい (テスト基盤の安定化) |

### アプローチ選択

#### Option A: Rust WASM 経由 (推奨)

既存の `src/rust/piper-wasm/` に ZH G2P が feature flag で組み込まれている。
`WasmPhonemizer.phonemize()` が内部で `ChinesePhonemizer` を呼び出す構造。

**利点:**
- Rust 実装 (1,252行) をそのまま使用、Python/Rust との完全互換保証
- `piper-wasm` の既存インフラ (`wasm-bindgen`, feature flags) を活用
- JA と同じ非同期初期化パターン

**欠点:**
- WASM バイナリサイズ増加 (辞書 2.6MB + コード)
- 初回ロード時間の増加

#### Option B: JS 移植 + JSON 辞書配信

ピンイン辞書を JSON で配信し、JS 側でルール処理を実装。

**利点:**
- WASM ビルド不要
- 辞書を遅延ロード可能

**欠点:**
- 辞書 2.6MB の配信管理
- Rust 実装 (22関数) の JS 移植コスト
- Python/Rust との出力一致検証コスト

### タスク一覧 (Option A: Rust WASM)

#### 4-1. piper-wasm ZH feature の WASM ビルド検証

**対象ファイル:**
- `src/rust/piper-wasm/Cargo.toml` — `zh` feature が既に定義済みか確認
- `.github/workflows/wasm-build.yml` — ZH 含むビルドマトリックス確認

**作業:**
- `wasm-pack build` で `zh` feature 有効時のビルド成功を確認
- 辞書データの WASM バンドル方法を決定 (include_bytes! vs 外部ロード)
- バンドルサイズ測定

**受け入れ基準:**
- `wasm-pack build --features zh` が成功
- 生成 WASM バイナリサイズを記録

#### 4-2. JS 側 ChineseG2P の WASM 連携実装

**対象ファイル:** `src/wasm/g2p/src/zh/index.js`

**作業:**
- JA の `JapaneseG2P` パターンを参考に非同期初期化を実装
- `WasmPhonemizer` の `phonemize()` を呼び出し
- トーンマーカー (tone1-5) の PUA 変換を確認
- フォールバック: WASM 未初期化時は現行の文字パススルー

**受け入れ基準:**
- `"你好"` → tone マーカー含む IPA トークン列
- `"北京欢迎你。"` → 複数音節の正しい処理
- `"我是学生。"` → トーンサンドヒ (T3+T3→T2+T3) 適用

#### 4-3. 辞書配信方式の決定・実装

**選択肢:**
1. WASM にバンドル (`include_bytes!`) — シンプルだがサイズ増
2. 外部 JSON として IndexedDB キャッシュ — JA 辞書と同じパターン
3. gzip 圧縮 JSON を CDN 配信 — 最小初回ロード

**受け入れ基準:**
- 辞書ロード方式が決定・実装され、初期化が成功する
- npm パッケージサイズが CI の 1MB 上限に収まる方式 (辞書外部化が必要な可能性)

#### 4-4. テスト追加

**対象ファイル:**
- `src/wasm/g2p/test/test-g2p-golden.js` — ZH テストの `tokens.length > 0` を拡張
- `src/wasm/g2p/test/test-chinese.js` (新規) — 個別テスト

**受け入れ基準:**
- golden テスト ZH 3 件でトーンマーカー検証 (`expected_contains_any_tone`)
- 個別テスト: ピンイン変換, トーンサンドヒ, 句読点処理
- `IPA_OUTPUT_LANGUAGES` に `'zh'` 追加

---

## Phase 5: テスト基盤・CI 統合

### 概要

Phase 1-4 の横断的なテスト強化と CI 統合。各 Phase のテスト追加と並行して進める。

### タスク一覧

#### 5-1. golden テスト強化

**対象ファイル:** `src/wasm/g2p/test/test-g2p-golden.js`

**作業:**
- `IPA_OUTPUT_LANGUAGES` を `new Set(['en', 'ko', 'sv', 'es', 'fr', 'pt', 'zh'])` に拡張
- ZH の `tokens.length > 0` テストを `assertTokenCountMin` + `assertExpectedContains` に変更
- ES/FR/PT の `expected_contains` チェックを有効化

#### 5-2. テストフィクスチャ拡充

**対象ファイル:** `tests/fixtures/g2p/phoneme_test_cases.json`

**作業:**
- ES/FR/PT に `expected_tokens` (exact match) ケースを追加 (ES: "hola" が既にある)
- ZH に `expected_tokens` ケースを追加 (WASM 完成後)
- 各言語の重要ルールをカバーするケースを追加 (鼻母音, 口蓋化, トーンサンドヒ等)

#### 5-3. CI ワークフロー更新

**対象ファイル:** `.github/workflows/g2p-wasm-ci.yml`

**作業:**
- 新規テストファイル (`test-spanish.js`, `test-french.js`, `test-portuguese.js`, `test-chinese.js`) を `node --test` コマンドに追加
- ZH WASM ビルドが CI で動作することを確認
- npm パッケージサイズチェック (1MB 上限) が ZH 辞書外部化後も通ることを確認

---

## 依存関係・並列化マップ

```
Phase 1 (ES) ──┐
Phase 2 (FR) ──┼── Phase 5 (テスト統合)
Phase 3 (PT) ──┘         │
                          │
Phase 4 (ZH) ────────────┘
```

- **Phase 1, 2, 3 は完全に並列実行可能** — 3エージェント同時割り当て推奨
- **Phase 4 は独立して開始可能**だが、Phase 5 の前に完了が望ましい
- **Phase 5 は Phase 1-4 の各完了に応じて段階的に進行**

---

## エージェント割り当て指針

### エージェントへの指示テンプレート

各エージェントに以下を渡す:

1. **移植元ファイル:** `src/rust/piper-plus-g2p/src/{language}.rs`
2. **移植先ファイル:** `src/wasm/g2p/src/{lang}/index.js` (上書き)
3. **参照実装:** `src/wasm/g2p/src/ko/index.js` (KO) or `src/wasm/g2p/src/sv/index.js` (SV)
4. **PUA マップ:** `src/wasm/g2p/src/pua-map.js`
5. **テストフィクスチャ:** `tests/fixtures/g2p/phoneme_test_cases.json`
6. **ギャップ分析:** `docs/wasm-g2p-zh-fr-pt-gap-analysis.md`

### 作業ブランチ戦略

```
fix/wasm-zh-fr-pt-phonemizer (ベース)
├── fix/wasm-g2p-es  ← エージェント A
├── fix/wasm-g2p-fr  ← エージェント B
├── fix/wasm-g2p-pt  ← エージェント C
└── fix/wasm-g2p-zh  ← エージェント D (Phase 4)
```

各エージェントは独立ブランチで作業し、完了後にベースブランチにマージ。

---

## 受け入れ基準 (全体)

| 基準 | 条件 |
|------|------|
| ES/FR/PT が IPA 出力 | 文字パススルーではなく、Rust/Python と同等の IPA トークン列を生成 |
| ZH がトーンマーカー出力 | tone1-5 PUA トークンが音節ごとに生成される |
| golden テスト全通過 | `test-g2p-golden.js` の全言語で `expected_contains` チェック通過 |
| 個別テスト追加 | 各言語 30+ テストケース |
| CI グリーン | `g2p-wasm-ci.yml` が 3 OS で通過 |
| npm サイズ上限 | パッケージサイズ 1MB 以内 (ZH 辞書は外部化) |
| Rust/Python 互換 | 同一入力に対して同等の phoneme_id 列を生成 (tolerance: token count ±10%) |

---

## 一から作り直すとしたら — Phase 横断の設計再考

各 Phase の個別チケットにも「一から作り直し」セクションがあるが、ここではプロジェクト全体の設計判断を振り返る。

### 判断 1: 言語ごとに独立 JS vs 全言語 Rust WASM 統一

**現在の方針:** ES/FR/PT は JS 移植、ZH は Rust WASM。

**もし一から設計するなら:**

| アプローチ | 利点 | 欠点 |
|-----------|------|------|
| (A) 現方針 (ハイブリッド) | ルールベース言語は軽量JS、辞書依存言語のみWASM | 2つの実装パスを維持 |
| (B) 全言語 Rust WASM | 実装の一元管理、Rust/Python完全互換 | ルールベース言語にWASMオーバーヘッド、バンドルサイズ大 |
| (C) 全言語 JS 移植 | WASM依存なし、最軽量 | ZH辞書2.6MBのJS管理が複雑 |

**結論:** (A) が最適。KO (520行JS) / SV (876行JS) の実績から、ルールベース言語のJS移植は実用的。ZHのみ辞書サイズの問題でWASMが妥当。

### 判断 2: ラテン系共通基盤の設計タイミング

**現在の方針:** ES を先行実装し、FR/PT 移植時に共通部分を抽出。

**もし一から設計するなら:**
- `latin-common.js` を先に設計し、NFD/NFC正規化・テキストトークナイズ・母音/子音判定の共通インターフェースを定義
- ただし音節分割・ストレス規則・異音規則は言語固有のため、共通化は限定的
- **結論:** premature abstraction 回避のため、ES 先行 → FR/PT で抽出の方針を維持。共通化対象は `collapseCombiningAccents()` と `tokenize()` 程度

### 判断 3: テスト戦略

**現在の方針:** 手動テストケース + Rust テスト移植。

**もし一から設計するなら:**
1. **golden test 自動生成:** Rust G2P の出力をキャプチャして `expected_tokens` を自動生成
2. **Property-based testing:** ランダムテキスト → G2P → 構造検証
3. **クロスプラットフォーム diff CI:** Rust/Python/JS の 3 実装を同一入力で比較

**結論:** Phase 5 完了後に golden test 自動生成を導入検討。初期は手動テストで品質保証

### 判断 4: 辞書形式

**現在の方針:** ZH は JSON (2.6MB)、外部 fetch + キャッシュ。

**もし一から設計するなら:**
- bincode 形式 (~0.8MB) で JA と統一
- `from_serialized_dicts(&[u8])` パターン
- **結論:** 初期は JSON、性能問題が出たら bincode 移行
