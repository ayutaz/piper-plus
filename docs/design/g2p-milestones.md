# piper-g2p マイルストーン計画

> 作成日: 2026-03-31
> 関連: `g2p-package-requirements.md` (要件定義), `g2p-standalone-package.md` (調査レポート), `g2p-technical-investigation.md` (技術調査)
> チケット: [`docs/tickets/README.md`](../tickets/README.md) (全チケット一覧)

---

## 全体ロードマップ

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3
(1週)       (1-2週)      (需要検証後)   (需要に応じて)
Python      Python       Rust          JS/WASM
JA+EN       全7言語      piper-g2p     @piper-plus/g2p
v0.1.0      v0.2.0→1.0   v0.1.0→1.0    v0.1.0→1.0
```

**設計方針**: IPA-first、エンコード分離、Phonemizer ABC は 2 メソッドのみ
**対象外**: C# (DotNetG2P 既存)、ニューラル G2P

---

## Phase 0: MVP (Python JA+EN)

**目標**: `uv pip install piper-g2p[ja,en]` で IPA 音素化が動作する
**期間**: 1 週間

### v0.0.1 — パッケージ名予約

| タスク | 完了条件 | チケット |
|-------|---------|---------|
| PyPI に `piper-g2p` v0.0.1 placeholder を publish | `uv pip install piper-g2p` が成功 | [P0-001](../tickets/phase-0/P0-001-package-name-reservation.md) |
| crates.io に `piper-g2p` v0.0.1 placeholder を publish | `cargo add piper-g2p` が成功 | [P0-001](../tickets/phase-0/P0-001-package-name-reservation.md) |
| npm に `@piper-plus/g2p` v0.0.1 placeholder を publish | `npm info @piper-plus/g2p` が成功 | [P0-001](../tickets/phase-0/P0-001-package-name-reservation.md) |

### v0.1.0 — MVP リリース

| # | タスク | 対応要求 | 完了条件 | チケット |
|---|-------|---------|---------|---------|
| 1 | パッケージ構造作成 (`piper_g2p/`) | FR-006 | `src/python/g2p/pyproject.toml` が存在し `uv build` 成功 | [P0-002](../tickets/phase-0/P0-002-package-structure.md) |
| 2 | Phonemizer ABC + ProsodyInfo | FR-001 | `from piper_g2p import Phonemizer, ProsodyInfo` が動作 | [P0-003](../tickets/phase-0/P0-003-core-abstractions.md) |
| 3 | 言語レジストリ | FR-002 | `get_phonemizer("ja")` / `available_languages()` が動作 | [P0-003](../tickets/phase-0/P0-003-core-abstractions.md) |
| 4 | JapanesePhonemizer (IPA 出力) | FR-003 | `phonemize("こんにちは")` が BOS/EOS/PUA なしの IPA トークン列を返す | [P0-004](../tickets/phase-0/P0-004-japanese-phonemizer.md) |
| 5 | EnglishPhonemizer (IPA 出力) | FR-004 | `phonemize("Hello world")` が IPA トークン列を返す | [P0-005](../tickets/phase-0/P0-005-english-phonemizer.md) |
| 6 | PiperEncoder (encode モジュール) | FR-005 | `encoder.encode(tokens)` が BOS/PAD/EOS 付き phoneme_ids を返す | [P0-006](../tickets/phase-0/P0-006-piper-encoder.md) |
| 7 | piper_train 互換シム | FR-007 | 既存テストが変更なしで pass | [P0-007](../tickets/phase-0/P0-007-piper-train-compat-shim.md) |
| 8 | テスト (JA 10+, EN 6+, encode 8+, 互換 4+) | NFR-001 | `uv run pytest` 成功、カバレッジ 90%+ | [P0-008](../tickets/phase-0/P0-008-test-suite.md) |
| 9 | CI ワークフロー | NFR-004 | 3 OS x 2 Python で green | [P0-009](../tickets/phase-0/P0-009-ci-workflow.md) |

**完了判定**: 全タスク完了、`uv run pytest` green、piper_train 既存テスト pass

---

## Phase 1: 全言語展開

**目標**: 7 言語 + MultilingualPhonemizer + カスタム辞書
**期間**: 1-2 週間
**前提**: Phase 0 v0.1.0 完了

### v0.2.0 — ベータ公開

| # | タスク | 対応要求 | 完了条件 | チケット |
|---|-------|---------|---------|---------|
| 1 | ChinesePhonemizer (pypinyin) | FR-100 | `phonemize("你好")` が声調サンドヒ適用済み IPA を返す | [P1-001](../tickets/phase-1/P1-001-chinese-phonemizer.md) |
| 2 | KoreanPhonemizer (g2pk2) | FR-100 | `phonemize("안녕하세요")` が音韻規則適用済み IPA を返す | [P1-002](../tickets/phase-1/P1-002-korean-phonemizer.md) |
| 3 | SpanishPhonemizer (ルールベース) | FR-100 | `phonemize("Hola mundo")` が IPA を返す | [P1-003](../tickets/phase-1/P1-003-spanish-phonemizer.md) |
| 4 | FrenchPhonemizer (ルールベース) | FR-100 | `phonemize("Bonjour")` が鼻母音含む IPA を返す | [P1-004](../tickets/phase-1/P1-004-french-phonemizer.md) |
| 5 | PortuguesePhonemizer (ルールベース) | FR-100 | `phonemize("Olá")` が BR-PT 規則適用済み IPA を返す | [P1-005](../tickets/phase-1/P1-005-portuguese-phonemizer.md) |
| 6 | MultilingualPhonemizer + UnicodeLanguageDetector | FR-101 | `get_phonemizer("ja-en-zh")` で混在テキストを処理可能 | [P1-006](../tickets/phase-1/P1-006-multilingual-phonemizer.md) |
| 7 | カスタム辞書 + 入力バリデーション | FR-102 | JSON v1.0/v2.0 ロード、10MB 制限、パストラバーサル拒否 | [P1-007](../tickets/phase-1/P1-007-custom-dictionary.md) |
| 8 | pyproject.toml extras (zh, ko, all) | FR-103 | `uv pip install piper-g2p[all]` で全言語インストール | [P1-008](../tickets/phase-1/P1-008-pyproject-extras.md) |
| 9 | 既知制限を docstring + README に記載 | NFR-101 | ZH/KO/FR/PT/ES の制限がドキュメント化 | [P1-009](../tickets/phase-1/P1-009-documentation.md) |
| 10 | 共通テストフィクスチャ JSON (7 言語 x 2+) | NFR-100 | `tests/fixtures/g2p/phoneme_test_cases.json` が存在 | [P1-010](../tickets/phase-1/P1-010-test-fixtures.md) |
| 11 | 各言語テスト追加 | NFR-100 | 全言語のテストが pass | [P1-010](../tickets/phase-1/P1-010-test-fixtures.md) |

**完了判定**: `uv pip install piper-g2p[all]` で 7 言語動作、テスト green、PyPI v0.2.0 公開

### v1.0.0 — 安定版リリース

| # | タスク | 完了条件 | チケット |
|---|-------|---------|---------|
| 1 | ユーザーフィードバック反映 | v0.2.0 の Issue を triage し重要なものを修正 | [P1-011](../tickets/phase-1/P1-011-api-freeze-v1.md) |
| 2 | API 凍結 | `phonemize()` / `phonemize_with_prosody()` / `PiperEncoder` の API を確定 | [P1-011](../tickets/phase-1/P1-011-api-freeze-v1.md) |
| 3 | piper_train 互換シムに DeprecationWarning 追加 | `from piper_train.phonemize import ...` で warning | [P1-011](../tickets/phase-1/P1-011-api-freeze-v1.md) |
| 4 | README + API ドキュメント整備 | PyPI ページに使用例・言語一覧・既知制限が記載 | [P1-011](../tickets/phase-1/P1-011-api-freeze-v1.md) |
| 5 | TTS フレームワーク統合ガイド | VITS / Fish Speech への組み込み例をドキュメント化 | [P1-011](../tickets/phase-1/P1-011-api-freeze-v1.md) |

**完了判定**: API 安定、ドキュメント完備、PyPI v1.0.0 公開

---

## Phase 2: Rust crate

**目標**: `cargo add piper-g2p` で IPA 音素化が動作
**期間**: 2-3 週間
**開始条件**: PyPI `piper-g2p` 月間 1,000 DL 超過

### v0.1.0 — ベータ公開

| # | タスク | 対応要求 | 完了条件 | チケット |
|---|-------|---------|---------|---------|
| 1 | crate 構造作成 (`src/rust/piper-g2p/`) | NFR-200 | workspace member 追加、`cargo build` 成功 | [P2-001](../tickets/phase-2/P2-001-crate-structure.md) |
| 2 | G2pError + PhonemeIdMap 再定義 | FR-201 | `PiperError` 非依存、`From<G2pError> for PiperError` 変換可能 | [P2-002](../tickets/phase-2/P2-002-g2p-error-phoneme-id-map.md) |
| 3 | Phonemizer trait (IPA-first) | FR-200 | `phonemize_with_prosody()` が IPA トークン列を返す | [P2-003](../tickets/phase-2/P2-003-phonemizer-trait.md) |
| 4 | 7 言語 Phonemizer 移動 | FR-202 | feature flags で言語別コンパイル制御 | [P2-004](../tickets/phase-2/P2-004-7lang-phonemizer-move.md) |
| 5 | PiperEncoder (PUA + ID 変換) | FR-200 | `tokens_to_ids()` / `prosody_to_features()` が動作 | [P2-005](../tickets/phase-2/P2-005-piper-encoder.md) |
| 6 | piper-core 側 `request_builder` リネーム | FR-200 | `build_synthesis_request()` が piper-core に残る | [P2-006](../tickets/phase-2/P2-006-request-builder-rename.md) |
| 7 | piper-core re-export | NFR-203 | 既存の piper-cli / piper-python が変更なしでコンパイル | [P2-007](../tickets/phase-2/P2-007-piper-core-reexport.md) |
| 8 | jpreprocess vs pyopenjtalk 互換性テスト | FR-203 | 共通テストフィクスチャで JA の phoneme 列が一致 | [P2-008](../tickets/phase-2/P2-008-jpreprocess-compat-test.md) |
| 9 | CI ワークフロー (3 OS x stable) | NFR-202 | タグ `rust-g2p-v*` で crates.io publish | [P2-009](../tickets/phase-2/P2-009-ci-workflow.md) |

**既知制限**:
- 英語 OOV が無音になる (CMUdict 未収録語の LSTM 推測なし)
- jpreprocess と pyopenjtalk でフルコンテキストラベルが微妙に異なる可能性

### v1.0.0 — 安定版リリース

| # | タスク | 完了条件 | チケット |
|---|-------|---------|---------|
| 1 | ユーザーフィードバック反映 | v0.1.0 の Issue を修正 | [P2-010](../tickets/phase-2/P2-010-stable-release.md) |
| 2 | `#![deny(missing_docs)]` | 全 pub アイテムに doc comment | [P2-010](../tickets/phase-2/P2-010-stable-release.md) |
| 3 | crate ドキュメントにクイックスタート例 | `cargo doc` で生成されるドキュメントに使用例 | [P2-010](../tickets/phase-2/P2-010-stable-release.md) |

---

## Phase 3: JS/WASM

**目標**: `import { G2P } from '@piper-plus/g2p'` で IPA 音素化が動作
**期間**: 3-4 週間
**開始条件**: PyPI + crates.io 合計月間 2,000 DL 超過 or ブラウザ TTS Issue 3 件以上

### v0.1.0 — ベータ公開

| # | タスク | 対応要求 | 完了条件 | チケット |
|---|-------|---------|---------|---------|
| 1 | SimpleUnifiedPhonemizer 分離 | FR-300 | onnxruntime-web 非依存で動作 | [P3-001](../tickets/phase-3/P3-001-phonemizer-separation.md) |
| 2 | OpenJTalk WASM の DI 化 | FR-301 | コンストラクタで openjtalkModule を注入可能 | [P3-002](../tickets/phase-3/P3-002-openjtalk-wasm-di.md) |
| 3 | DictLoader 分離 | FR-301 | IndexedDB キャッシュ + SHA-256 検証が独立動作 | [P3-003](../tickets/phase-3/P3-003-dict-loader-separation.md) |
| 4 | phonemizeWithProsody() 追加 | FR-302 | A1/A2/A3 を ProsodyInfo として返す | [P3-004](../tickets/phase-3/P3-004-phonemize-with-prosody.md) |
| 5 | piper-plus 互換レイヤー | NFR-301 | 既存の PiperPlus API に破壊的変更なし | [P3-005](../tickets/phase-3/P3-005-piper-plus-compat-layer.md) |
| 6 | TypeScript 型定義 | NFR-302 | `tsc --noEmit` エラーなし | [P3-006](../tickets/phase-3/P3-006-typescript-type-definitions.md) |
| 7 | CI ワークフロー (3 OS x Node 18/20/22) | NFR-300 | タグ `wasm-g2p-v*` で npm publish | [P3-007](../tickets/phase-3/P3-007-ci-workflow.md) |

### v1.0.0 — 安定版リリース

| # | タスク | 完了条件 | チケット |
|---|-------|---------|---------|
| 1 | ユーザーフィードバック反映 | v0.1.0 の Issue を修正 | [P3-008](../tickets/phase-3/P3-008-stable-release.md) |
| 2 | Tree-shaking 対応 | subpath exports で未使用言語がバンドルから除外 | [P3-008](../tickets/phase-3/P3-008-stable-release.md) |
| 3 | バンドルサイズ検証 | JA なし < 30KB gzip、JA 込み < 430KB gzip | [P3-008](../tickets/phase-3/P3-008-stable-release.md) |

---

## バージョニング

SemVer 2.0.0 採用。**MAJOR 同期は廃止**、PUA compat バージョンで互換管理。

```
piper-g2p (Python) v1.2.0  [pua-compat: 1]
piper-g2p (Rust)   v1.0.3  [pua-compat: 1]  ← 同一 = 互換
@piper-plus/g2p    v1.1.0  [pua-compat: 1]  ← 同一 = 互換
```

| 変更 | バージョン | PUA compat |
|------|-----------|-----------|
| PUA エントリ削除・変更 | 不問 | +1 (全パッケージ同時) |
| PUA エントリ追加 | MINOR | 変更なし |
| API 破壊的変更 | MAJOR | 変更なし |
| バグ修正 | PATCH | 変更なし |

---

## 需要検証基準

| 指標 | Phase 2 開始 | Phase 3 開始 |
|------|------------|------------|
| PyPI 月間 DL | > 1,000 | > 1,000 |
| crates.io 月間 DL | - | > 1,000 (合計 2,000) |
| GitHub Star | 参考 | 参考 |
| ブラウザ TTS Issue | - | >= 3 |
| 計測方法 | pypistats.org | pypistats.org + crates.io API |

---

## CI/CD タグ戦略

| Phase | タグパターン | レジストリ | ツール |
|-------|------------|-----------|--------|
| 0-1 | `python-g2p-v*` | PyPI | `uv build && uv publish` |
| 2 | `rust-g2p-v*` | crates.io | `cargo publish -p piper-g2p` |
| 3 | `wasm-g2p-v*` | npm | `npm publish --provenance --access public` |
