# WASM G2P: ZH/FR/PT/ES 実装ギャップ分析

> **ステータス:** 調査完了 — 実装待ち
> **ブランチ:** `fix/wasm-zh-fr-pt-phonemizer`
> **作成日:** 2026-04-04

---

## 1. 問題概要

npm パッケージ (`piper-plus`) の WASM G2P で、**中国語 (ZH)・フランス語 (FR)・ポルトガル語 (PT)・スペイン語 (ES)** の音素化が文字レベルのパススルーのみで、実際の G2P 処理が行われていない。結果として、モデルに不正な phoneme_id 列が渡り、音声品質が著しく低下する。

**ユーザー報告:** 「css10-ja-6lang-fp16 モデルで ja/en/es は翻訳発声させても普通にしゃべるが、中国語・フランス語・ポルトガル語はちゃんと発声してくれない」

---

## 2. 現状: WASM G2P 実装レベル比較

### 2.1 行数比較

| 言語 | WASM (JS) | Rust (piper-plus-g2p) | Python (piper-plus-g2p) | 実装レベル |
|------|-----------|----------------------|------------------------|-----------|
| **JA** | 207 + 189 = **396行** | 1,203行 | (pyopenjtalk) | OpenJTalk WASM 完全実装 |
| **EN** | **636行** | 1,272行 | 427行 | 辞書 + ルールベース完全実装 |
| **SV** | **876行** | (Go: 1,218行) | — | ルールベース完全実装 |
| **KO** | **520行** | 888行 | — | Hangul分解 + IPA 完全実装 |
| **ZH** | **65行** | 1,252行 | 612行 | **文字パススルーのみ** |
| **FR** | **68行** | 1,586行 | 988行 | **文字パススルーのみ** |
| **PT** | **68行** | 1,352行 | 696行 | **文字パススルーのみ** |
| **ES** | **68行** | 1,397行 | 819行 | **文字パススルーのみ** |

### 2.2 処理パイプラインの差

#### 正常に動作する言語 (JA/EN/KO/SV)

```
テキスト → 前処理 → G2P変換(辞書/ルール) → IPA音素列 → PUAマッピング → phoneme_ids
```

#### 壊れている言語 (ZH/FR/PT/ES)

```
テキスト → (小文字化) → 1文字ずつ トークン化 → Encoder が phonemeIdMap で ID 変換 → phoneme_ids
```

> **注意:** G2P クラスの `phonemize()` はトークン化のみを行い、phoneme_id への変換は別段階の `Encoder.encode()` で実行される。Encoder は非 strict モード (デフォルト) で未知トークンを **silent-drop** する (エラーなしでスキップ)。この動作が言語間の障害程度の差を生む:
>
> - **ZH:** 漢字は `phoneme_id_map` に存在しない → **全トークンが silent-drop** → 実質空の phoneme_id 列 → 完全失敗
> - **FR/PT:** 基本ラテン文字 (b, o, n, r 等) は IPA 音素としても存在するため ID に解決される → **wrong-but-valid な ID 列** → 劣化した音声 (完全失敗ではない)
> - **ES:** スペイン語の正書法は IPA に最も近いため、パススルーでも多くの文字が正しい ID に解決 → 偶然の部分一致 → 比較的聴取可能
>
> ただし FR/PT/ES でもアクセント付き文字 (ç, é, ã 等) や言語固有文字は `phoneme_id_map` に存在せず silent-drop される。

### 2.3 現在の ZH/FR/PT/ES 実装コード (全て同一パターン)

```javascript
// 4言語とも本質的にこの処理のみ
phonemize(text) {
    const tokens = [];
    const lower = text.toLowerCase();  // ZHは小文字化なし
    for (const char of lower) {
        if (this.phonemeIdMap && this.phonemeIdMap[char]) {
            tokens.push(char);
        } else {
            tokens.push(char);  // 未知文字もそのまま通す
        }
    }
    return { tokens, prosody: new Array(tokens.length).fill(null) };
}
```

**問題点:**
- **G2P 変換がない:** テキスト→音素の変換処理が一切存在しない
- **phonemeIdMap は IPA 音素のマップ:** config.json の `phoneme_id_map` は `ɑ`, `ʃ`, `ɛ̃` 等の IPA 音素をキーとしており、`b`, `o`, `n` 等の文字は一部一致するが `j`(仏語)→`ʒ`、`ch`→`ʃ` 等の変換が欠落
- **多文字トークンが生成されない:** PUA マッピングされた音素 (tʃ, dʒ, tone1-5 等) が一切生成されない

---

## 3. 言語別: 欠落している処理の詳細

### 3.1 中国語 (ZH) — 最も深刻

| 処理 | Python/Rust | WASM (現状) | 影響度 |
|------|------------|------------|-------|
| 漢字→ピンイン変換 | pypinyin / JSON辞書 | なし | **致命的** — 音素化の前提 |
| トーン抽出 (1-5) | ピンインから自動抽出 | なし | **致命的** — 中国語は声調言語 |
| トーンサンドヒ | T3+T3→T2+T3, 一/不 | なし | 高 — 自然さに直結 |
| Initial/Final 分離 | "zhong"→("zh","ong") | なし | **致命的** — IPA変換の前提 |
| IPA 変換 | zh→tʂ, ong→uŋ 等 | なし | **致命的** |
| トーンマーカー出力 | PUA tone1-tone5 | なし | **致命的** — モデルのtone conditioning |

**例: "你好" (nǐ hǎo)**
- **Python/Rust:** `n i tone3 x a u tone3` → 正しい IPA + トーン
- **WASM:** `你 好` → phonemeIdMap に漢字がないため、Encoder が全トークンを silent-drop → 実質空の phoneme_id 列

**必要リソース:** ピンイン辞書 (JSON, ~4MB gzip前) または Rust WASM からの呼び出し

### 3.2 フランス語 (FR)

| 処理 | Python/Rust | WASM (現状) | 影響度 |
|------|------------|------------|-------|
| 鼻母音 (an→ɑ̃, on→ɔ̃, in→ɛ̃) | ルールベース | なし | **致命的** — 仏語の基本音素 |
| 黙字 (final consonants) | コンテキスト判定 | なし | 高 — 誤発音の原因 |
| 二重字 (ch→ʃ, gn→ɲ, ph→f) | パターンマッチ | なし | **致命的** |
| -er 動詞語尾 (→/e/) | 単語末尾ルール | なし | 高 |
| 母音間 s 有声化 (→z) | 位置判定 | なし | 中 |
| y_vowel (u→/y/) | PUA E01E マッピング | なし | 高 |
| ストレス (語末母音) | 自動配置 | なし | 中 |

**例: "bonjour" (bɔ̃ʒuʁ)**
- **Python/Rust:** `b ɔ̃ ʒ u ʁ` → 正しい IPA (鼻母音 + 有声摩擦音)
- **WASM:** `b o n j o u r` → 7文字個別に渡される。b/o/n/u/r は phoneme_id_map に存在するため ID 解決されるが、j は IPA /j/ (半母音) に解決され仏語の /ʒ/ ではない。鼻母音 ɔ̃ は生成されない → 劣化した音声

### 3.3 ポルトガル語 (PT)

| 処理 | Python/Rust | WASM (現状) | 影響度 |
|------|------------|------------|-------|
| 鼻母音 (ã, õ, ẽ, ĩ, ũ) | ルール+チルダ | なし | **致命的** |
| 口蓋化 (ti→tʃi, di→dʒi) | コンテキスト判定 | なし | 高 — BR特有の主要規則 |
| Coda-l 母音化 (l→w) | 音節構造判定 | なし | 高 |
| r 多型性 (介母音r→ɾ, 語頭r→ʁ) | 位置判定 | なし | 中 |
| 二重字 (nh→ɲ, lh→ʎ, ch→ʃ) | パターンマッチ | なし | **致命的** |
| 母音弱化 (語末 o→u, e→i) | ストレス判定 | なし | 中 |
| ストレス配置 | アクセント記号 + 位置規則 | なし | 中 |

**例: "Obrigado" (obɾiɡadu)**
- **Python/Rust:** `o b ɾ i ɡ a d u` → 正しい IPA (tap r + 母音弱化)
- **WASM:** `o b r i g a d o` → 文字そのまま。基本ラテン文字は ID 解決されるが、r は IPA /r/ (trill) に解決され PT の介母音間 /ɾ/ (tap) ではない。語末 o→u の弱化も欠落 → 劣化した音声

### 3.4 スペイン語 (ES)

| 処理 | Python/Rust | WASM (現状) | 影響度 |
|------|------------|------------|-------|
| 異音変化 (b→β, d→ð, g→ɣ) | コンテキスト判定 | なし | 中 |
| ñ→ɲ | 文字マッピング | なし | 高 |
| rr→r (歯茎ふるえ音) | PUA マッピング | なし | 高 |
| ll→ʎ or ʝ | 方言ルール | なし | 中 |
| qu→k, gu→g | 二重字 | なし | 高 |
| h 黙字 | 削除 | なし | 中 |
| ストレス配置 | アクセント記号 + 位置規則 | なし | 中 |

> **Note:** ES が「動く」と報告されたのは、スペイン語の正書法が IPA に最も近く、文字パススルーでも多くの文字が正しい phoneme_id に偶然一致するため。ただしアクセント付き文字 (`ó`, `é`) は phoneme_id_map に存在せず silent-drop される。また `c`→[s]/[k] の分岐、`rr`→trill の PUA 変換、`b/d/g` の異音変化等は一切処理されないため、完全な G2P ではない。

---

## 4. テストの現状

### 4.1 Golden テスト (`test-g2p-golden.js`)

```javascript
// IPA出力チェック対象: EN, KO, SV のみ
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'ko', 'sv']);
```

| 言語 | テスト内容 | 問題 |
|------|----------|------|
| JA | スキップ (WASM必要) | — |
| EN | token count + expected_contains | 適切 |
| KO | token count + expected_contains | 適切 |
| SV | token count + expected_contains | 適切 |
| **ES** | token count のみ | **IPA内容チェックなし** |
| **FR** | token count のみ | **IPA内容チェックなし** |
| **PT** | token count のみ | **IPA内容チェックなし** |
| **ZH** | `tokens.length > 0` のみ | **実質テストなし** |

### 4.2 テストフィクスチャ (`phoneme_test_cases.json`)

フィクスチャには ZH/FR/PT 用の `expected_contains` や `expected_contains_any_tone` が定義されているが、JS 側のゴールデンテストでは意図的にスキップされている。

---

## 5. 解決アプローチの選択肢

### Option A: Rust G2P を WASM 経由で呼び出し (推奨: ZH)

```
テキスト → [JS] → Rust WASM G2P → [JS] → phoneme_ids
```

- **利点:** Rust 実装 (1,252行) をそのまま再利用、Python/Rust との完全互換
- **欠点:** ピンイン辞書 (~4MB) の WASM バンドルサイズ増加
- **対象:** ZH (辞書依存のため JS 移植が困難)
- **前例:** JA は既に OpenJTalk WASM で同様のアプローチ

### Option B: JS にルールベース G2P を移植 (推奨: FR/PT/ES)

```
テキスト → [JS G2P ルール] → IPA音素列 → PUAマッピング → phoneme_ids
```

- **利点:** 外部依存なし、バンドルサイズ増加なし
- **欠点:** 移植工数 (各言語 400-900行)
- **対象:** FR/PT/ES (ルールベースで辞書不要)
- **前例:** KO (520行), SV (876行) は既にこのアプローチで実装済み

### Option C: `piper-plus-g2p` Rust クレートを WASM ビルド (将来)

```
テキスト → [piper-plus-g2p WASM] → IPA音素列 → phoneme_ids
```

- **利点:** 全言語を一括対応、Rust 実装と完全一致保証
- **欠点:** ビルドパイプライン変更、辞書バンドル、初回実装コスト大
- **対象:** 全言語

---

## 6. 推奨実装計画

### Phase 1: FR/PT/ES の JS ルールベース移植

**優先度:** 高 — 辞書不要で移植可能

| 言語 | 移植元 | 推定行数 | 主要ルール |
|------|--------|---------|-----------|
| ES | `spanish.rs` (1,397行) | ~500行 | 異音変化, rr, ñ, qu/gu, ストレス |
| FR | `french.rs` (1,586行) | ~700行 | 鼻母音, 黙字, 二重字, y_vowel, ストレス |
| PT | `portuguese.rs` (1,352行) | ~600行 | 鼻母音, 口蓋化, coda-l, r多型, ストレス |

**移植方針:**
1. Rust 実装を正規の移植元とする (Python と同等だが構造がJSに近い)
2. PUA マッピングは既存の `pua-map.js` (96エントリ) をそのまま使用
3. テストフィクスチャの `expected_contains` チェックを有効化
4. `IPA_OUTPUT_LANGUAGES` に `es`, `fr`, `pt` を追加

### Phase 2: ZH の Rust WASM 統合

**優先度:** 高 — 辞書依存のため JS 移植は非推奨

**アプローチ:**
1. `piper-plus-g2p` の中国語部分を `wasm-bindgen` でビルド
2. ピンイン辞書を WASM モジュールにバンドル
3. JA と同様の非同期初期化パターンを採用
4. トーンマーカー (tone1-5) の出力を検証

**代替案:** ピンイン辞書をJSONで配信し、JS側でルール処理を実装 (辞書サイズ ~4MB がネック)

### Phase 3: テスト強化

1. `IPA_OUTPUT_LANGUAGES` に全言語を追加
2. `expected_contains_any_tone` チェックを ZH で有効化
3. 各言語の最小テストケースを追加 (鼻母音、口蓋化等の個別ルール検証)

---

## 7. ファイルパス一覧

### WASM G2P (修正対象)

| ファイル | 行数 | 状態 |
|---------|------|------|
| `src/wasm/g2p/src/zh/index.js` | 65 | 要置換 |
| `src/wasm/g2p/src/fr/index.js` | 68 | 要置換 |
| `src/wasm/g2p/src/pt/index.js` | 68 | 要置換 |
| `src/wasm/g2p/src/es/index.js` | 68 | 要置換 |
| `src/wasm/g2p/test/test-g2p-golden.js` | 322 | テスト強化 |

### 移植元 (Rust)

| ファイル | 行数 |
|---------|------|
| `src/rust/piper-plus-g2p/src/chinese.rs` | 1,252 |
| `src/rust/piper-plus-g2p/src/french.rs` | 1,586 |
| `src/rust/piper-plus-g2p/src/portuguese.rs` | 1,352 |
| `src/rust/piper-plus-g2p/src/spanish.rs` | 1,397 |

### 参照 (正常動作している JS 実装)

| ファイル | 行数 | 方式 |
|---------|------|------|
| `src/wasm/g2p/src/ko/index.js` | 520 | Hangul分解 + IPA (Rust移植) |
| `src/wasm/g2p/src/sv/index.js` | 876 | ルールベース (Go移植) |
| `src/wasm/g2p/src/en/index.js` | 636 | 辞書 + ルール |

### 共通インフラ

| ファイル | 用途 |
|---------|------|
| `src/wasm/g2p/src/pua-map.js` | PUA マッピング定義 (96エントリ) |
| `src/wasm/g2p/src/encode.js` | phoneme_id 変換 + BOS/PAD/EOS |
| `tests/fixtures/g2p/phoneme_test_cases.json` | クロスプラットフォームテストフィクスチャ |
