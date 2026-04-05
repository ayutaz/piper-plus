# WASM-G2P-TEST: テスト基盤・CI 統合

> **Phase:** 5 | **ステータス:** 未着手 | **依存:** Phase 1-4 の各完了に応じて段階的に進行
> **マイルストーン:** [wasm-g2p-implementation-milestones.md](../wasm-g2p-implementation-milestones.md#phase-5-テスト基盤ci-統合)
> **ブランチ:** `fix/wasm-zh-fr-pt-phonemizer` (ベースブランチ)

---

## 1. タスク目的とゴール

**目的:** Phase 1-4 で実装された ES/FR/PT/ZH の G2P を、既存テスト基盤 (408テスト, 3 OS CI) に統合し、クロスプラットフォーム品質を保証する。

**ゴール:**
- golden test (`test-g2p-golden.js`) が全 8 言語で `expected_contains` チェック通過
- 各言語の個別テストファイル (test-spanish.js 等) が CI で実行
- npm パッケージサイズ 1MB 以内
- ZH WASM ビルドが CI グリーン

**非ゴール:**
- ブラウザ E2E テスト (別チケット)
- パフォーマンスベンチマーク

---

## 2. 実装する内容の詳細

### 2-1. golden テスト強化 (`test-g2p-golden.js`)

**現在:**
```javascript
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'ko', 'sv']);
```

**変更方針:** 一括更新ではなく、各 Phase 完了と同期して言語を段階的に追加する。
各 Phase のマージ時に対応する言語を追加し、未実装言語の IPA チェックが誤って有効化されることを防止する。

```javascript
// Phase 1 (ES) 完了後
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'ko', 'sv', 'es']);
// Phase 2 (FR) 完了後
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'ko', 'sv', 'es', 'fr']);
// Phase 3 (PT) 完了後
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'ko', 'sv', 'es', 'fr', 'pt']);
// Phase 4 (ZH) 完了後 — 最終形
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'ko', 'sv', 'es', 'fr', 'pt', 'zh']);
```

**ZH テストの強化:**

ZH 固有のトーンマーカー検証ロジックを追加するのではなく、フィクスチャの `expected_contains` に
トーン PUA トークンを含めることで、既存の `assertExpectedContains` で統一的に処理する。

```javascript
// 現在: tokens.length > 0 のみ
// 変更後: 他言語と同一のテストパターンを使用 (ZH 固有ロジック不要)
describe('G2P golden: Chinese', () => {
    const g2p = new ChineseG2P();
    for (const c of casesFor('zh')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
            // トーン検証は expected_contains にトークンを含めることで対応
            // 例: expected_contains: ["tone3"] → assertExpectedContains が検証
        });
    }
});
```

### 2-2. テストフィクスチャ拡充 (`phoneme_test_cases.json`)

**追加するテストケース:**

| 言語 | input | 新規 assertion |
|------|-------|---------------|
| es | `"niño"` | `expected_contains: ["ɲ"]` |
| es | `"Buenos días"` | `expected_contains: ["β"]` (異音) |
| fr | `"lune"` | `expected_contains: ["y_vowel"]` (PUA E01E) |
| fr | `"maison"` | `expected_contains: ["z"]` (母音間 s) |
| pt | `"tipo"` | `expected_contains: ["tʃ"]` (PUA E054) |
| pt | `"caro"` | `expected_contains: ["ɾ"]` (tap r) |
| zh | `"中国"` | `expected_contains: ["tone3"]` (PUA トーンマーカー、`assertExpectedContains` で統一検証) |

### 2-3. CI ワークフロー更新 (`g2p-wasm-ci.yml`)

**テスト実行コマンドの更新:**
```bash
node --test test/test-encode.js test/test-english.js test/test-g2p.js \
  test/test-languages.js test/test-detect.js test/test-pua-map.js \
  test/test-swedish.js test/test-korean.js test/test-custom-dict.js \
  test/test-strict-mode.js \
  test/test-spanish.js test/test-french.js test/test-portuguese.js \
  test/test-chinese.js
```

**WASM ビルド CI (`build-wasm-reusable.yml`):**
- `multilingual` feature に `zh` 追加
- feature 組み合わせチェックに `--features zh` 追加

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| **テスト統合エージェント** | 1 | golden test 強化、CI 更新、フィクスチャ拡充 |

**合計: 1 エージェント** (Phase 1-4 の各テストエージェントと連携)

---

## 4. 提供範囲とテスト

### 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/wasm/g2p/test/test-g2p-golden.js` | IPA_OUTPUT_LANGUAGES 拡張、ZH テスト強化 |
| `tests/fixtures/g2p/phoneme_test_cases.json` | テストケース追加 (7+件) |
| `.github/workflows/g2p-wasm-ci.yml` | テスト実行コマンドに 4 ファイル追加 |
| `.github/workflows/build-wasm-reusable.yml` | multilingual に zh 追加 |
| `.github/workflows/wasm-build.yml` | feature 組み合わせに zh 追加 |

### 統合テスト項目

| テスト | 条件 |
|--------|------|
| golden test 全通過 | 8 言語 28 ケース |
| 個別テスト全通過 | ES 30+ / FR 40+ / PT 35+ / ZH 10+ |
| CI 3 OS グリーン | Ubuntu / macOS / Windows |
| npm サイズ上限 | < 1MB |
| WASM ビルド成功 | multilingual (zh 含む) |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| ZH WASM テスト | Node.js で WASM 実行困難 | フォールバック動作のみ Node.js テスト、WASM は CI ブラウザテスト |
| テストケース間の干渉 | 言語検出の誤判定 | テストケースごとに言語を明示指定 |
| npm サイズ超過 | ZH 辞書バンドルで 1MB 超過 | 辞書外部化 (Phase 4 で対応済みの前提) |

### レビュー項目

- [ ] `IPA_OUTPUT_LANGUAGES` の段階的更新 (各 Phase 完了と同期)
- [ ] ZH のトーン検証が `expected_contains` + `assertExpectedContains` で統一されていること
- [ ] CI テストコマンドに 4 新規テストファイル含む
- [ ] WASM ビルド CI の feature flag 更新
- [ ] npm サイズチェック通過

---

## 6. 一から作り直すとしたら

### テスト戦略の再設計

**現在:** 手動テストケース (28件) + 言語別個別テスト。

**もし一から設計するなら:**

1. **自動生成 golden テスト:**
   - Rust/Python G2P で全テストケースを実行し、出力を自動キャプチャ
   - `expected_tokens` を自動生成してフィクスチャに保存
   - JS 実装はこの golden output との exact match で検証
   - **利点:** テストケース追加が容易、手動の expected 値計算不要
   - **判断:** Phase 5 完了後に導入検討

2. **Property-based テスト (fuzzing):**
   - ランダムテキスト生成 → G2P → 構造検証 (BOS/EOS 存在、空トークンなし等)
   - 言語固有の不変条件: ES なら「ˈ は母音の前にのみ出現」等
   - **判断:** 個別テスト充実後の追加施策として検討

3. **クロスプラットフォーム出力差分ツール:**
   ```bash
   # 同一入力を Rust/Python/JS で処理し、出力を比較
   uv run python -m piper_plus_g2p --lang es "hola"
   cargo run -p piper-plus-g2p -- --lang es "hola"
   node -e "import('@piper-plus/g2p/es').then(m => console.log(m.phonemize('hola')))"
   ```
   - diff ツールで 3 実装の出力を自動比較
   - **判断:** CI に組み込む価値あり。Phase 5 拡張として検討

---

## 7. 後続タスクへの連絡事項

### 全チームへの連絡

- Phase 5 は Phase 1-4 の各完了に応じて段階的に進行
- 各言語チームは個別テストファイル (test-spanish.js 等) を作成した上で、Phase 5 エージェントに以下を連絡:
  1. テストファイル名
  2. テストケース数
  3. golden test で有効化すべきチェック
  4. 特殊な CI 要件 (ZH の WASM ビルド等)

### マージ順序

1. Phase 1-3 (ES/FR/PT) → 各ブランチから `fix/wasm-zh-fr-pt-phonemizer` にマージ
2. Phase 5 の golden test + CI 更新を適用
3. Phase 4 (ZH) → WASM ビルド変更を含むためマージ後に CI 検証
4. 最終的に `fix/wasm-zh-fr-pt-phonemizer` → `dev` にマージ
