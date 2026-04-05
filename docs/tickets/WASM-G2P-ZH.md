# WASM-G2P-ZH: 中国語 G2P Rust WASM 統合

> **Phase:** 4 | **ステータス:** 未着手 | **並列:** 独立開始可能
> **マイルストーン:** [wasm-g2p-implementation-milestones.md](../wasm-g2p-implementation-milestones.md#phase-4-中国語-zh--rust-wasm-統合)
> **ブランチ:** `fix/wasm-g2p-zh`

---

## 1. タスク目的とゴール

**目的:** `@piper-plus/g2p` の中国語 G2P を、文字パススルー (65行) からピンイン辞書ベース IPA 変換に置き換える。ピンイン辞書 (2.6MB) が必要なため、Rust WASM 経由で `ChinesePhonemizer` を呼び出す。

**ゴール:**
- `"你好"` → tone マーカー (tone3 PUA) 含む IPA トークン列
- `"我是学生。"` → トーンサンドヒ (T3+T3→T2+T3) 適用
- `"北京欢迎你。"` → 複数音節の正しい Initial/Final 分解 + IPA 変換
- golden test 3 件でトーンマーカー検証通過

**非ゴール:**
- 多音字の完全対応 (辞書ベースの最頻ピンイン選択のみ)
- 韻律 (prosody) の生成 (null のまま)

---

## 2. 実装する内容の詳細

### 2-1. 現状の問題

**piper-wasm 側 (`lib.rs` L229-230):**
```rust
other => Ok(Box::new(PassthroughPhonemizer::new(other))),
```
ZH は `create_phonemizer()` で専用分岐がなく `PassthroughPhonemizer` にフォールバック。

**piper-wasm/Cargo.toml:** `zh` feature 未定義。`multilingual` にも未含。

**ChinesePhonemizer のコンストラクタ:**
- `new(single_char_path, phrase_path)` — `std::fs` 依存、WASM 不可
- `from_dicts(single_dict, phrase_dict)` — HashMap 直接受け取り、**WASM で使用可能**

### 2-2. Rust 側の変更

#### A. piper-plus-g2p/chinese.rs: JSON バイト列からの初期化追加

```rust
/// WASM 向け: JSON バイト列から辞書を構築
///
/// 辞書のJSONフォーマット:
///   - pinyin_single.json: `{"19968":"yi1", "19969":"ding1,zheng4", ...}`
///     キーはコードポイント数値文字列、値はカンマ区切りピンイン
///   - pinyin_phrases.json: `{"一丁不識":[["yī"],["dīng"],["bù"],["shí"]], "一个":"yi2 ge4", ...}`
///     値はネスト配列またはスペース区切り文字列
pub fn from_json_bytes(single_json: &[u8], phrase_json: &[u8]) -> Result<Self, G2pError> {
    // pinyin_single.json: {"codepoint_str": "pinyin1,pinyin2", ...}
    // キーを u32 codepoint → char に変換、値はカンマ区切りの最初のピンインを使用
    // ※ serde_json::Value 経由でパースする (キーが数値文字列で値形式が混在するため
    //    HashMap<String, String> への直接デシリアライズは不可)
    let raw_single: HashMap<String, serde_json::Value> = serde_json::from_slice(single_json)?;
    let single_dict = Self::parse_single_entries(raw_single)?;

    // pinyin_phrases.json: {"phrase": [["py1"], ["py2"]], ...} or {"phrase": "py1 py2", ...}
    // ネスト配列をフラットな Vec<String> に変換、文字列値はスペース区切りで分割
    let raw_phrase: HashMap<String, serde_json::Value> = serde_json::from_slice(phrase_json)?;
    let phrase_dict = Self::parse_phrase_entries(raw_phrase);

    Ok(Self::from_dicts(single_dict, phrase_dict))
}
```

> **実装注意:** `parse_single_entries()` と `parse_phrase_entries()` は新規関数であり、
> 既存の `load_single_char_dict()` / `load_phrase_dict()` のパースロジック (各 30-40 行) を
> `std::fs` 非依存で移植する必要がある。具体的には:
>
> - `parse_single_entries()`: キー文字列を `u32` にパース → `char::from_u32()` で変換、
>   値が文字列ならそのまま、配列なら先頭要素を取得 (既存 `load_single_char_dict` L680-705 相当)
> - `parse_phrase_entries()`: 値が文字列ならスペース分割、配列ならフラット化
>   (既存 `load_phrase_dict` L731-755 相当)

#### B. piper-wasm/Cargo.toml: zh feature 追加

`ja` / `ja-external` パターンに倣い、`zh` (辞書バンドル) と `zh-external` (外部辞書ロード) の
2 feature を定義する。`multilingual` / `multilingual-external` にはバンドルなしの `zh-external`
を使用し、npm パッケージサイズへの影響を回避する。

```toml
[features]
zh = ["piper-plus-g2p/chinese"]           # 辞書バンドル (include_bytes)
zh-external = ["piper-plus-g2p/chinese"]  # 外部辞書ロード (setChineseDictionary)
multilingual = ["ja", "ko", "es", "fr", "pt", "sv", "zh-external"]
multilingual-external = ["ja-external", "ko", "es", "fr", "pt", "sv", "zh-external"]
```

> **注意:** 既存の `multilingual` feature は `["ja", "ko", "es", "fr", "pt", "sv"]` であり、
> `zh-external` の追加は **breaking change** となる。WASM バイナリに ZH G2P コードが含まれるため
> サイズが増加する (ただし辞書データは含まない)。`wasm-build.yml` の feature 組み合わせチェックの
> 更新も必要。

#### C. piper-wasm/src/lib.rs: ZH 分岐追加

**`zh` feature (辞書バンドル) の場合:**

辞書ファイルの現在の配置は `src/cpp/pinyin_single.json` (704 KB) と `src/cpp/pinyin_phrases.json` (1.9 MB)。
`include_bytes!` で使用するには、これらを `src/rust/piper-plus-g2p/data/` にコピーするか、
相対パスを `src/cpp/` に向ける必要がある。

```rust
#[cfg(all(feature = "zh", not(feature = "zh-external")))]
"zh" => {
    // 注意: 辞書ファイルを src/rust/piper-plus-g2p/data/ に配置するか、
    // 既存パス src/cpp/ を参照する場合は相対パスを調整すること。
    // 現時点で src/rust/piper-plus-g2p/data/ は存在しない。
    let phonemizer = ChinesePhonemizer::from_json_bytes(
        include_bytes!("../../piper-plus-g2p/data/pinyin_single.json"),
        include_bytes!("../../piper-plus-g2p/data/pinyin_phrases.json"),
    )?;
    Ok(Box::new(phonemizer))
}
```

**`zh-external` feature (外部辞書ロード) の場合:**

JA の `setJapaneseDictionary()` パターンに倣い、`setChineseDictionary()` で外部から辞書をロードする。
`multilingual` / `multilingual-external` ではこちらを使用 (npm パッケージサイズ回避)。

```rust
#[cfg(all(not(feature = "zh"), feature = "zh-external"))]
"zh" => {
    // External dict mode: start with passthrough, replaced by setChineseDictionary()
    Ok(Box::new(PassthroughPhonemizer::new("zh")))
}
```

### 2-3. 辞書バンドル方式の選択

| 方式 | サイズ | 初回ロード | npm パッケージ影響 |
|------|--------|-----------|-----------------|
| **A. `include_bytes!`** (WASM バンドル) | +2.6MB (gzip ~600KB) | 即座 | npm 1MB 上限超過の可能性 |
| **B. 外部 JSON + fetch** | 0 (WASM に含まない) | ~100-200ms | npm サイズ影響なし |
| **C. 外部 JSON + IndexedDB キャッシュ** | 0 (初回のみ fetch) | 初回 ~200ms, 2回目 ~10ms | npm サイズ影響なし |

**推奨:** Option B or C。npm パッケージの 1MB 上限 (CI `g2p-wasm-ci.yml`) を超えないため。
JA の辞書ロードパターン (`setJapaneseDictionary(bytes)`) に倣い、`setChineseDictionary()` を追加。

### 2-4. JS 側の変更

`src/wasm/g2p/src/zh/index.js` を WASM 連携版に書き換え:

```javascript
export class ChineseG2P {
    constructor(options = {}) {
        this._wasmPhonemizer = options.wasmPhonemizer || null;
        this._initialized = false;
        // フォールバック用 phonemeIdMap (WASM 未初期化時)
        this.phonemeIdMap = options.phonemeIdMap || null;
    }

    async initialize(wasmModule, dictData) {
        // dictData: { singleJson: ArrayBuffer, phraseJson: ArrayBuffer }
        this._wasmPhonemizer = new wasmModule.WasmPhonemizer(configJson);
        this._wasmPhonemizer.setChineseDictionary(dictData);
        this._initialized = true;
    }

    phonemize(text) {
        if (this._initialized) {
            // Rust WASM G2P 経由
            const result = this._wasmPhonemizer.phonemize(text, 'zh');
            return { tokens: result.tokens, prosody: result.prosody };
        }
        // フォールバック: 文字パススルー (現行動作)
        return this._fallbackPhonemize(text);
    }
}
```

### 2-5. ZH G2P の処理フロー (Rust 側、参考)

```
テキスト → CJK 検出 → 句フレーズマッチ (phrase_dict)
  → 漢字→ピンイン (single_dict) → トーン抽出
  → トーンサンドヒ (T3+T3→T2+T3, 一/不 規則)
  → Initial/Final 分離 ("zhong"→"zh","ong")
  → IPA 変換 (zh→tʂ, ong→uŋ)
  → トーンマーカー付加 (PUA tone1-tone5)
  → PUA マッピング (43 エントリ)
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| **Rust WASM エージェント** | 1 | piper-wasm Cargo.toml + lib.rs 変更、from_json_bytes 追加 |
| **JS 統合エージェント** | 1 | zh/index.js WASM 連携実装、辞書ロードパターン |
| **テストエージェント** | 1 | test-chinese.js 作成、WASM ビルド CI 検証 |

**合計: 3 エージェント** (Rust とJS を並列化)

---

## 4. 提供範囲とテスト

### スコープ

| 含む | 含まない |
|------|---------|
| ピンイン変換 (辞書ベース) | 多音字の文脈解析 |
| トーンサンドヒ (T3, 一, 不) | 韻律 (prosody) 生成 |
| Initial/Final IPA 変換 | 声調の実音声反映 (モデル依存) |
| PUA 43 エントリ | カスタム辞書 |
| WASM 未初期化時のフォールバック | — |

### Unit テスト (`test-chinese.js`)

| カテゴリ | テスト | 検証 |
|---------|--------|------|
| API | `phonemize()` 戻り値構造 | `{ tokens, prosody }` |
| API | `languageCode` | `'zh'` |
| 基本 | `"你好"` | tone マーカー含む, token_count >= 4 |
| トーンサンドヒ | `"你好"` (T3+T3) | T2+T3 に変換 |
| 複数音節 | `"北京欢迎你"` | 5 音節分解 |
| 句読点 | `"我是学生。"` | 句点処理 |
| CJK + ASCII 混在 | `"Hello你好"` | 混在テキスト |
| 空文字列 | `""` | 空配列 |
| WASM 未初期化 | フォールバック | 文字パススルー動作 |

### E2E テスト

- `IPA_OUTPUT_LANGUAGES` に `'zh'` 追加 (Phase 4 完了時に段階的に追加、WASM-G2P-TEST 参照)
- golden test 3 件でトーンマーカー検証: フィクスチャの `expected_contains` に `"tone3"` 等を含め、`assertExpectedContains` で統一的に検証 (ZH 固有ロジック不要)
- WASM ビルド CI で `--features zh` / `--features zh-external` のビルド成功確認

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| npm 1MB 上限 | 辞書バンドルで超過 | 辞書外部化 (Option B/C) |
| WASM バイナリサイズ | multilingual + zh で大幅増加 | サイズ閾値見直し (現在 64MB、十分余裕) |
| 辞書ロード遅延 | 初回利用時に ~200ms | IndexedDB キャッシュで 2 回目以降高速化 |
| Node.js テスト | WASM テストは Node.js で実行困難 | WASM テストは CI のブラウザテストに委譲、Node.js は フォールバック動作のみテスト |
| `from_json_bytes` 未実装 | 現在の Rust に存在しない | 新規実装が必要。`parse_single_entries()` / `parse_phrase_entries()` は既存 `load_single_char_dict()` / `load_phrase_dict()` のパースロジック (各 30-40 行) を `std::fs` 非依存で移植する必要がある |
| `std::fs` WASM コンパイル不可 | `chinese.rs` の `new()` が `std::fs::read_to_string()` を使用しており、`wasm32` ターゲットでコンパイルエラーとなる | `new()` を `#[cfg(not(target_arch = "wasm32"))]` でゲートし、WASM ビルドでは `from_json_bytes()` / `from_dicts()` のみを使用する設計とする。または `chinese` feature 全体を `#[cfg]` で分岐 |

### レビュー項目

- [ ] `piper-wasm/Cargo.toml` の `zh` feature 定義
- [ ] `lib.rs` の `create_phonemizer("zh")` 分岐
- [ ] 辞書バンドル方式の最終決定
- [ ] JS 側の WASM 初期化パターン (JA テンプレート準拠)
- [ ] フォールバック動作 (WASM 未初期化時) の正確性
- [ ] golden test 3 件でトーンマーカー検証
- [ ] npm パッケージサイズ 1MB 以内

---

## 6. 一から作り直すとしたら

### 全言語 Rust WASM 統一アーキテクチャ

**現在:** JA は Rust WASM、EN/KO/SV は JS 独自実装、ES/FR/PT は JS 移植予定、ZH は Rust WASM 予定。

**もし一から設計するなら:**

1. **全言語を `piper-plus-g2p` WASM で統一:**
   - `WasmPhonemizer` に全 8 言語の G2P を集約
   - JS 側は thin wrapper のみ (phonemize 呼び出し + PUA 変換)
   - **利点:** 実装の重複排除、Rust/Python との完全互換保証
   - **欠点:** ルールベース言語 (ES/FR/PT/KO/SV) は辞書不要で WASM オーバーヘッドが無駄
   - **判断:** ZH のみ WASM が妥当。ルールベース言語は JS が軽量

2. **辞書のバイナリ形式化:**

   | 形式 | サイズ | parse 速度 |
   |------|--------|-----------|
   | JSON (現在) | 2.6 MB | ~50-100ms |
   | bincode | ~0.8 MB | ~5-10ms |
   | MessagePack | ~1.2 MB | ~20-40ms |

   - JA は既に bincode を使用 (`jpreprocess` の辞書)
   - ZH も bincode 化すれば `from_serialized_dicts(&[u8])` パターンで統一可能
   - **判断:** 初期は JSON、性能問題が出たら bincode 移行

3. **WebAssembly Component Model:**
   - 各言語を独立 Component にして遅延ロード
   - `jco` (JS Component toolchain) で bridge
   - **判断:** 時期尚早。wasm-bindgen で十分

### ZH 固有の設計判断

| 判断 | 選択 | 理由 |
|------|------|------|
| 辞書バンドル | 外部 JSON (fetch + cache) | npm 1MB 上限回避 |
| Rust 変更 | `from_json_bytes()` 追加 | fs 不使用で WASM 対応 |
| JS 側 | WASM 連携 + フォールバック | WASM 未初期化時も動作 |
| 辞書形式 | JSON (初期), bincode (将来) | 既存辞書をそのまま使用 |

---

## 7. 後続タスクへの連絡事項

### Phase 5 (テスト統合) への連絡

- `IPA_OUTPUT_LANGUAGES` に `'zh'` 追加
- `g2p-wasm-ci.yml` に `test/test-chinese.js` 追加
- ZH の WASM テストは Node.js 単体では困難 (WASM バイナリが必要)
  - Node.js テスト: フォールバック動作のみ検証
  - WASM 統合テスト: `wasm-build.yml` CI で検証
- `build-wasm-reusable.yml` の `multilingual` feature に `zh` 追加必要
- `wasm-build.yml` の feature 組み合わせチェックに `--features zh` 追加

### ES/FR/PT チームへの連絡

- ZH は WASM 経由のため JS 実装パターンが異なる
- ただし `ChineseG2P` クラスの外部 API (phonemize, phonemizeWithProsody, languageCode) は共通
