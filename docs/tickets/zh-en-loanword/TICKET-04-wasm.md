# TICKET-04: JS/WASM ZH-EN Code-Switching 実装

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-04 |
| **マイルストーン** | Phase 4 (Day 9) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §2.4 / §4.1 W2-W5 / §8.4 (二層 FFI) / §8.22 (WASM size 最適化) |
| **ステータス** | 📝 Draft |
| **依存元** | **TICKET-01 (Rust)** ✱ Rust 完了が前提 (W1) |
| **依存先** | TICKET-06 (CI Sync), TICKET-07 (Docs) |
| **追加 LOC** | ~250 (Rust FFI 30 + JS ラッパ 80 + TS型 20 + テスト 120) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: WASM ビルド (`piper-wasm`) と JS パッケージ (`@piper-plus/g2p`) で ZH-EN code-switching を有効化。Rust 側 (TICKET-01) の `phonemize_embedded_english` を WASM 経由で呼ぶ薄ラッパを JS に追加する。

**ゴール**:
- `setChineseLoanwordData(json: Uint8Array | LoanwordData)` が WASM 経由で動作。
- `ChineseG2P.phonemize()` が `[zh, en, *]` を自動 dispatch (内部で Rust 側 dispatcher 呼出)。
- `data/zh_en_loanword.json` を JS 側に bundle (WASM サイズ +0)。
- Issue [#384](https://github.com/ayutaz/issues/384) 例 3 件が Python と同一 IPA 列。
- npm package size < **1 MB** (CI 既存ガード遵守、現状 684 KB → 想定 ~700 KB)。
- WASM サイズ増分 < **+25 KB** (見込 +8-12 KB)。
- TypeScript 型定義が完備、`@piper-plus/g2p` 利用者が IDE 補完を受けられる。

---

## 2. 実装する内容の詳細

設計書 §8.4 で確定済みの **案 B (JS 側 bundle + Rust 注入)** を採用。

### W1. Rust 側完了確認 (前提条件)

TICKET-01 で `piper-plus-g2p::ChinesePhonemizer::phonemize_embedded_english` と `setChineseLoanwordData` 用の内部 setter (`set_loanword_data`) が完成していることを確認。失敗時は本チケット blocked。

### W2. Rust に `setChineseLoanwordData()` FFI 追加

`src/rust/piper-wasm/src/lib.rs` に追加:

```rust
#[wasm_bindgen(js_name = setChineseLoanwordData)]
pub fn set_chinese_loanword_data(
    &mut self,
    loanword_json: &[u8],
) -> Result<(), JsValue> {
    let data = serde_json::from_slice::<LoanwordData>(loanword_json)
        .map_err(|e| JsValue::from_str(&format!("CONFIG_PARSE_ERROR: {e}")))?;
    LoanwordData::validate(&data)
        .map_err(|e| JsValue::from_str(&format!("VALIDATION_ERROR: {e}")))?;
    self.chinese_phonemizer.set_loanword_data(Arc::new(data));
    Ok(())
}
```

**feature gate** (`src/rust/piper-wasm/Cargo.toml`、現状の `default = []` を維持):

```toml
[features]
default = []
multilingual = ["ja", "zh", "ko", "es", "fr", "pt", "sv"]
# 注意: multilingual には zh-en を含めない (既存利用者へ非影響)
zh-en = ["zh", "piper-plus-g2p/zh-en-loanword"]   # ZH 単独の opt-in 機能
```

ZH-EN を必要とするアプリは明示的に `features = ["multilingual", "zh-en"]` を指定する。**default opt-in セットには含めない** (1 MB CI ガード保護のため)。

### W3. JS 側 `ChineseG2P` に薄ラッパ追加

`src/wasm/g2p/src/zh/index.js` 拡張:

```javascript
import loanwordData from '../../data/zh_en_loanword.json' with { type: 'json' };

class ChineseG2P {
    constructor(wasmPhonemizer) {
        this._wasmPhonemizer = wasmPhonemizer;
        this._loanwordData = loanwordData;  // JS 側 bundle (default)
        this._enableZhEnDispatch = true;
    }

    setLoanwordData(data) {
        this._loanwordData = data;
        if (this._wasmPhonemizer) {
            const bytes = new TextEncoder().encode(JSON.stringify(data));
            this._wasmPhonemizer.setChineseLoanwordData(bytes);
        }
    }

    setZhEnDispatch(enabled) {
        this._enableZhEnDispatch = enabled;
        if (this._wasmPhonemizer) {
            this._wasmPhonemizer.setZhEnDispatch(enabled);
        }
    }
}
```

**重要**: WASM 初期化直後に **default loanword を自動注入**するブートストラップを `index.js` の `init()` に追加。利用者が `setLoanwordData` を呼び忘れても動作するように。

### W4. TypeScript 型定義更新

`src/wasm/g2p/types/index.d.ts` に追加:

```typescript
export interface LoanwordData {
    version: number;
    acronyms: Record<string, string[]>;
    loanwords: Record<string, string[]>;
    letter_fallback: Record<string, string[]>;
}

export class ChineseG2P {
    /** Override default loanword data (JSON object 直接指定可能) */
    setLoanwordData(data: LoanwordData): void;
    /** Enable/disable ZH-EN code-switching dispatch (default: true) */
    setZhEnDispatch(enabled: boolean): void;
    /** Convert Chinese (with optional embedded English) to IPA tokens */
    phonemize(text: string): string[];
}
```

### W5. テスト追加 (`test/test-chinese.js` 拡張)

`node:test` フレームワークを継続使用。

#### Unit テスト

| テスト名 | 内容 |
|---------|------|
| `chinese: setLoanwordData accepts default JSON` | デフォルトデータの set + 動作確認 |
| `chinese: setLoanwordData with custom override` | 任意データで override |
| `chinese: GPS via embedded English` | acronym ヒット |
| `chinese: Python via embedded English` | loanword ヒット (case-sensitive) |
| `chinese: ChatGPT 5 syllables` | 5 syllable |
| `chinese: ZZ via letter_fallback` | fallback 2 回 |
| `chinese: empty string returns empty array` | edge case |
| `chinese: lookup priority loanword > acronym (override)` | priority 確認 |
| `chinese: punctuation trailing comma equivalent` | `GPS,` 等価 |
| `chinese: digits dropped (Z2Z9 == ZZ)` | digit drop |
| `chinese: setZhEnDispatch(false) skips dispatch` | opt-out 動作 |
| `chinese: invalid JSON throws CONFIG_PARSE_ERROR` | error string 確認 |
| `chinese: invalid schema throws VALIDATION_ERROR` | schema validation |
| `multilingual: zh-en-zh pattern (请打开 GPS 系统)` | dispatch |
| `multilingual: zh-en pattern (请打开 GPS)` | Issue 例 1 |
| `multilingual: en-zh pattern (Hello 世界)` | en at start |
| `multilingual: pure zh unchanged (regression)` | regression |
| `multilingual: pure en uses english (regression)` | regression |
| `issue example: 我喜欢用 Python 写代码` | Issue 例 2 |
| `issue example: 让我用 ChatGPT 写代码` | Issue 例 3 |
| `bundled JSON SHA256 matches Python source` | byte 一致確認 |

合計 **21 テスト**。

#### E2E テスト (browser smoke)

`test/test-chinese-browser.html` で puppeteer 経由でも動作確認。Node.js (`node:test`) と browser 両方で通る。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 責任 |
|------|------|-----|
| **Phase Lead** | 1 | TICKET-01 (Rust) 完了確認、後工程 (TICKET-06/07) への引き継ぎ |
| **WASM Dev** | 1 | W2 Rust FFI 追加、`piper-wasm` 再ビルド、`pkg/` 出力検証 |
| **JS Dev** | 1 | W3 JS ラッパ、W4 TS 型、`@piper-plus/g2p` パッケージ更新 |
| **QA / Test** | 1 | W5 テスト 21 件、bundle size 計測、Python source との SHA256 比較 |

**並列化**: TICKET-01 完了後、W2 / W3 / W4 を並列着手可能。W5 は W2-W4 完了後。

**コミット推奨**:
- `feat(wasm): W2 setChineseLoanwordData FFI 追加 + zh-en feature gate`
- `feat(wasm): W3+W4 JS ラッパと TypeScript 型定義`
- `test(wasm): W5 ZH-EN テスト追加 (21 件)`

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- `piper-wasm` の wasm-bindgen 公開関数 `setChineseLoanwordData(bytes)`, `setZhEnDispatch(bool)`
- `@piper-plus/g2p` の `ChineseG2P.setLoanwordData(data)`, `setZhEnDispatch(enabled)`
- `data/zh_en_loanword.json` を JS bundle (`src/wasm/g2p/data/zh_en_loanword.json`)
- TypeScript 型定義 `index.d.ts` 拡張
- feature gate `zh-en` (Cargo)

### Out of scope

- WASM SIMD 最適化 (将来 PR)
- npm publish (TICKET-07)
- browser-only / Deno-only 限定機能

### テスト項目

設計書 §4.3 統一テストマトリックスを JS で全件カバー。bundle size + WASM size を CI で検証。

---

## 5. Unit テスト

セクション 2 W5 の 21 件を `node:test` で実装。Table-driven 風に書く:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';

const cases = [
    { name: 'GPS via acronym', input: 'GPS', expectedSyllables: 4 },
    { name: 'Python via loanword', input: 'Python', expectedSyllables: 2 },
    // ...
];

for (const c of cases) {
    test(`chinese: ${c.name}`, async () => {
        const tokens = await chinese.phonemizeEmbeddedEnglish(c.input);
        // tone marker 個数で syllable 数を逆算
        const toneCount = tokens.filter(t => /[-]/.test(t)).length;
        assert.equal(toneCount, c.expectedSyllables);
    });
}
```

`tests/fixtures/g2p/zh_en_loanword_matrix.json` (TICKET-06 で導入) を読んで全件回す。

---

## 6. E2E テスト

### 環境別

| 環境 | フレームワーク | 確認内容 |
|------|--------------|---------|
| Node.js | `node:test` | unit 21 件 + Issue 例 3 件 |
| Browser | `puppeteer` (既存 webui-test.yml 活用) | WASM 初期化 + Issue 例 1 件 (smoke) |
| CDN | `cdn-test.yml` (既存) | unpkg / jsdelivr で `import` 経由 |

### Issue 例 3 件 byte 一致

```javascript
// 注意: MultilingualG2P クラスは未存在。既存 G2P factory + 言語別 class、
// または v1.0.0 で createMultilingualG2P() async builder を新設 (§9.2)。
import { G2P } from '@piper-plus/g2p';
import expectedFromPython from './fixtures/python_phonemes.json' with { type: 'json' };

const g2p = await G2P.create({ languages: ['zh', 'en'], zhEnDispatch: true });
const tokens = await g2p.phonemize('请打开 GPS');
assert.deepEqual(tokens, expectedFromPython.gps_open);
```

---

## 7. 実装に関する懸念事項

### 懸念 1: TICKET-01 (Rust) との同時開発
- **影響**: Rust 側の `set_loanword_data` 内部 setter が確定しないと WASM bindings 書けない。
- **緩和**: TICKET-01 R1 で setter のシグネチャを早期確定。WASM Dev が Rust API を受け取る形でモック実装可能。
- **責任**: Phase Lead。

### 懸念 2: JSON import の Node.js 互換性
- **影響**: `import json from './data.json' with { type: 'json' }` は Node.js 22+ 必須 (旧 `assert` 構文は deprecated)。
- **緩和**: 現状 `engines.node: ">=24.0.0"` で対応済。CDN 利用時は CDN 配信側の JSON loader 対応に依存 (所見 6 参照)。
- **責任**: JS Dev。

### 懸念 3: WASM bundle size 増分
- **影響**: 1 MB CI ガードに対し +25 KB は許容範囲だが、複数機能追加で逼迫の可能性。
- **緩和**: `zh-en` feature gate で除外可能。CI で `wasm-opt -Os` 適用後のサイズを計測、>1 MB で fail。
- **責任**: WASM Dev + DevOps (TICKET-06)。

### 懸念 4: WASM 初期化時の自動注入タイミング
- **影響**: WASM `init()` 完了前に `setChineseLoanwordData` を呼ぶと panic、並行 builder 呼出で二重 init。
- **緩和**: **single-flight pattern** を採用。Module-level の `_wasmInitPromise` で重複起動を抑制、init 失敗時は `null` 化で retry 可能。詳細は §9.2。
- **責任**: JS Dev。

### 懸念 5: TextEncoder の availability
- **影響**: 一部の古い Node.js / Deno で `TextEncoder` が global にない。
- **緩和**: 現状 Node.js 18+ で global 使用可能。Deno は標準対応。`util.TextEncoder` フォールバック不要。
- **責任**: JS Dev。

### 懸念 6: feature gate `zh-en` を default-on にした場合のサイズ影響
- **影響**: 全利用者にデフォルトで +12 KB。
- **緩和**: 設計書 §8.22 で確定済 (default on)。size 制約が厳しいユーザーは `default-features = false` で除外。
- **責任**: WASM Dev。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] `setChineseLoanwordData` の error string が `CONFIG_PARSE_ERROR:` / `VALIDATION_ERROR:` prefix
- [ ] `LoanwordData` の TypeScript interface が `index.d.ts` に export 済
- [ ] `ChineseG2P.setLoanwordData(data: LoanwordData)` の引数型が一致
- [ ] WASM init 後に default loanword の自動注入が走る
- [ ] `setZhEnDispatch(false)` で英語経路に fallback
- [ ] feature gate `zh-en` が `Cargo.toml` で default 入り
- [ ] `wasm-pack build --release --features zh-en` で size < 1 MB
- [ ] JSON bundle 後の SHA256 が Python source と一致
- [ ] `node test/test-chinese.js` 全件 PASS
- [ ] puppeteer browser test 1 件 PASS
- [ ] `tsc --noEmit` で型エラーゼロ

### ドキュメントレビュー

- [ ] `src/wasm/g2p/README.md` に ZH-EN 例 + ブラウザ usage
- [ ] `src/wasm/g2p/CHANGELOG.md` に "added: setChineseLoanwordData / setZhEnDispatch"
- [ ] TypeScript 型定義の JSDoc コメント (`/** */`) を全公開 API に付与

---

## 9. 一から作り直すとしたら

> **前提**: v1.0.0 (`@piper-plus/g2p` 1.0.0) を対象。本 PR は §8.11 通り **0.7.0** (minor bump)。

### 9.0 思想

| # | 原則 | 説明 |
|---|------|------|
| 1 | **PUA 出力 byte 一致** | 既存学習済みモデル PUA 0xE020-0xE04A を絶対変えない。 |
| 2 | **`zh-en` feature は opt-in 維持** | Cargo `default = []` を維持、`features = ["multilingual", "zh-en"]` 明示。1 MB CI ガード保護。runtime 側は `setZhEnDispatch(false)` で control。 |
| 3 | **Graceful failure** | WASM init 失敗 → reject Promise、JSON parse 失敗 → string error。 |
| 4 | **Single source of truth** | Python JSON が canonical、JS は consumer。 |
| 5 | **二層 FFI で WASM-thin** | データは JS 側 bundle、ロジックは Rust 側。WASM サイズ +0。 |
| 6 | **TypeScript 型定義 first-class** (手書き) | 公開 API の型は `types/index.d.ts` で **手書き** 完備。Rust struct との同期は CI sync test で担保 (`schemars::schema_for!` ↔ `.d.ts`)。wasm-bindgen 自動生成 `.d.ts` は internal only。 |
| 7 | **Browser / Node.js / Deno 全対応** | Node.js 22+ (現状 `engines.node: ">=24.0.0"`)、`with { type: 'json' }` 構文 (旧 `assert` は deprecated)、import-attributes proposal Stage 4。 |
| 8 | **Single-flight WASM init** | 並行 builder 呼出を 1 度の init に集約、失敗時 retry 可能。詳細 §9.2。 |

### 9.1 データ層

**現状の判断**: §8.4 の **案 B (JS 側 bundle + Rust 注入)** がベスト。WASM サイズ +0、bundler の JSON tree-shaking で最適化済。

| 採用パス | トリガー | 実装 |
|---------|---------|------|
| 案 A: Rust `include_bytes!` | WASM のみで完結したいケース | bundle +5KB、再ビルド必要 |
| **案 B: JS bundle + Rust 注入** (現行案) | 一般 | W3 のまま |
| 案 C: `fetch()` で外部取得 | CDN 利用、サイズ厳しい | オフライン NG、不採用 |

**Import 構文**: `import x from './data/x.json' with { type: 'json' }` (import-attributes Stage 4)。旧 `assert { type: 'json' }` は Node.js 22+ で deprecated warning、Deno 1.46+ も同様。

**CDN 配信時の JSON loader 戦略** (jsdelivr / unpkg / Skypack):

| パターン | bundler | jsdelivr | unpkg | Deno |
|---------|---------|---------|-------|------|
| A. `import x from './data/x.json' with { type: 'json' }` | ✓ | ✓ | △ MIME 依存 / Safari < 18 で fail | ✓ |
| B. `await fetch(new URL('./data/x.json', import.meta.url)).then(r => r.json())` | ✓ | ✓ | ✓ | ✓ |

**Day 1**: A (現行 W3 案)、CDN テスト (`cdn-test.yml`) で smoke 通過確認。失敗頻発時は v1.0.0 で B にフォールバック。

**v1.0.0 候補プラン**:
- **A**: 同期 import + JSON 定数化 (`const loanwordData = { ... }` を build script で生成)。bundler 最適化確実、CDN 解決安定。
- **B**: `with { type: 'json' }` 維持。差分なし。
- **C**: Dynamic import (`await import(...)` ＋ `with { type: 'json' }`)。tree-shake 期待、bundler 設定要。

推奨: B 維持を Day 1、A への移行は v1.0.0 で検討。

### 9.2 API 層

**Single-flight pattern で WASM init の race / 二重初期化を防ぐ**:

```typescript
// builder pattern + single-flight init
let _wasmInitPromise: Promise<WasmModule> | null = null;
function getWasm(): Promise<WasmModule> {
    if (!_wasmInitPromise) {
        _wasmInitPromise = init().catch((e) => {
            _wasmInitPromise = null;  // retry 可能化
            throw new PiperG2PError('WASM_INIT_ERROR', e);
        });
    }
    return _wasmInitPromise;
}

export async function createMultilingualG2P(opts: G2POptions): Promise<MultilingualG2P> {
    const wasm = await getWasm();          // 並行 builder でも 1 回のみ init
    const phonemizer = new Phonemizer(wasm);
    if (opts.loanwordData === 'default' || opts.loanwordData === undefined) {
        phonemizer.setLoanwordData(defaultLoanwordData);  // bundle
    } else if (opts.loanwordData instanceof URL) {
        const data = await fetch(opts.loanwordData).then(r => r.json());
        phonemizer.setLoanwordData(data);
    } else {
        phonemizer.setLoanwordData(opts.loanwordData);
    }
    return phonemizer;
}
```

これで:
1. 並行 builder 呼出 → 同じ Promise 共有 (single-flight)
2. init 失敗時 → `_wasmInitPromise = null` で retry 可能
3. URL / object / 'default' の 3 形式統一

- error: `class PiperG2PError extends Error` の subclass を `CONFIG_PARSE_ERROR` / `VALIDATION_ERROR` / `WASM_INIT_ERROR` で discriminate。
- 現行 `setLoanwordData(data)` は v1.0.0 で `set` ではなく構築時引数のみに変更 (immutable)。
- **`MultilingualG2P` クラスは現状未存在**。本 PR は既存 `G2P` factory を拡張、v1.0.0 で `createMultilingualG2P()` を新設して旧 API は deprecated alias 化。

### 9.3 Dispatcher

**Day 1 (本 PR)**: Rust 側 dispatcher を使用、JS 側はそれをラップするだけ。

**v1.0.0**: 変更なし (Rust 側 pattern table 化が走れば自動で恩恵)。

### 9.4 Package 構成

```
src/wasm/
├── g2p/                                  (npm: @piper-plus/g2p)
│   ├── data/
│   │   └── zh_en_loanword.json           (JS bundle 対象)
│   ├── src/
│   │   ├── zh/index.js                   (ChineseG2P)
│   │   ├── multilingual/index.js
│   │   └── index.js                      (entry)
│   ├── types/index.d.ts                  (TypeScript)
│   └── test/
│       ├── test-chinese.js               (node:test)
│       └── test-chinese-browser.html     (puppeteer)
├── openjtalk-web/                        (既存)
└── ../rust/piper-wasm/                   (Rust → WASM ビルド)
```

### 9.5 Failure mode

| ケース | 動作 | エラー |
|-------|------|--------|
| WASM init 失敗 | `Promise.reject`、`_wasmInitPromise=null` で retry 可能 | `WASM_INIT_ERROR` |
| `setChineseLoanwordData` で JSON parse 失敗 | throw Error | `CONFIG_PARSE_ERROR: ...` |
| schema 違反 | throw Error | `VALIDATION_ERROR: ...` |
| `setZhEnDispatch(false)` | dispatch 無効、英語経路 | — |
| default JSON bundle 欠損 | build error (bundler) | — |

### 9.5b 優先順位ルール (loanword data 解決順)

constructor / builder で data を解決する順序:

```
1. 利用者が init 後に setLoanwordData(data) を明示呼び出し → 必ず勝つ
2. constructor option { loanwordData: ... } 渡し (v1.0.0 builder)
3. JS bundle の default `data/zh_en_loanword.json` (auto-inject)
```

**Auto-inject タイミング**:
- WASM `init()` 完了の Promise の then で実行
- 利用者の `setLoanwordData` 呼出は init Promise を await した後にのみ可能 (init 前は内部キューに積む)

```javascript
async function initChineseG2P(wasm) {
    await wasm.ready;
    const g2p = new ChineseG2P(wasm);
    g2p.setLoanwordData(loanwordData);  // step 3: bundle default 注入
    return g2p;  // ここから利用者が override 可能
}
```

constructor は同期、auto-inject は async なので分離する。利用者は `await G2P.create()` の戻り値に対してのみ `setLoanwordData` を呼べる。

### 9.6 i18n 拡張パス

| Phase | 内容 | 必要な変更 |
|-------|------|-----------|
| Phase 1 (本 PR) | ZH-EN | `data/zh_en_loanword.json` 1 個 |
| Phase 2 | JA-EN / KO-EN | `data/{ja_en, ko_en}_loanword.json` 追加 + JS API `setLoanwordData(pair, data)` |
| Phase 3 | 任意ペア | `LoanwordRegistry.register(src, tgt, data)` |

### 9.7 テスト戦略

- **`node:test`** (Node.js 18+) で unit 21 件、parameterized loop。
- **`puppeteer`** で browser smoke 1 件 (既存 `webui-test.yml` 流用)。
- **CDN test** (unpkg / jsdelivr) で `cdn-test.yml` (既存) 通過確認。
- **Cross-runtime fixture** (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) を CI sync で `src/wasm/g2p/test/fixtures/` にコピー (TICKET-06)。
- **bundle size 検証**: `wasm-pack build` 後の `pkg/*.wasm` サイズと `npm pack` の tarball サイズを CI で計測、閾値超で fail。

### 9.8 Observability

**設計原則**: programmatic API を優先、env var / localStorage は fallback。

- **Programmatic API (推奨)**: `setDebug(enabled: boolean)` メソッドで制御。
- **Node.js**: `PIPER_DEBUG_ZH_EN=1` env var を読む (process 起動時)。
- **Browser**: `localStorage.PIPER_DEBUG_ZH_EN==='1'` を読む。ただし **production 警告**を出す:

```javascript
if (typeof localStorage !== 'undefined' && localStorage.PIPER_DEBUG_ZH_EN === '1') {
    console.warn('[piper-plus] DEBUG enabled via localStorage. ' +
                 'Disable in production. Use setDebug(true) instead.');
}
```

**Privacy**: debug 出力には **入力テキストを log しない** (prefix のみ: `[zh-en hit] loanword[idx=2]`)。利用者テキストの fingerprinting / 第三者スクリプトからの読取り防止。

- Rust/WASM 側: `web-sys::console::debug_1(...)` で出力。env var は WASM 内取得不可、`setDebug(enabled)` API 経由のみ。

### 9.9 SemVer 戦略

| 変更 | impact |
|------|-------|
| `setChineseLoanwordData` / `setZhEnDispatch` 追加 | **non-breaking** (新メソッド、既存破壊なし) |
| TypeScript 型定義拡張 | **non-breaking** (interface 拡張のみ) |
| feature gate `zh-en` を **opt-in 維持** (`default = []`) | **non-breaking** (既存ユーザーへ無影響) |
| `multilingual` meta-feature を変えない (zh-en を含めない) | **non-breaking** |
| v1.0.0 で `setLoanwordData` 削除 (immutable builder のみ) | **breaking** → major bump |
| v1.0.0 で `MultilingualG2P` 新クラス追加 | **non-breaking** (既存 `G2P` factory は alias 維持) |

---

## 10. 後続タスクへの連絡内容

### TICKET-06 (CI Sync) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **JSON 配置パス** | `src/wasm/g2p/data/zh_en_loanword.json` |
| **比較対象** | Python source `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` と byte 一致 |
| **WASM size 検証** | `wasm-pack build --release` 後 `pkg/*.wasm` < 25 KB 増 |
| **npm package size** | `npm pack` 後 < 1 MB (既存ガード) |
| **CDN smoke** | unpkg / jsdelivr で `import` 動作確認 |

### TICKET-07 (Docs) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **README 追加** | `src/wasm/g2p/README.md` に ZH-EN 例 (browser + Node.js) |
| **CHANGELOG** | `[Unreleased]` に "Added: setChineseLoanwordData, setZhEnDispatch" |
| **TypeScript JSDoc** | `index.d.ts` の `/** */` を完備、`tsc --declaration` で生成可能に |
| **npm release notes** | publish 時 description に ZH-EN 追加 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §2.4 / §4.1 W2-W5 / §8.4 / §8.22 から派生) |
