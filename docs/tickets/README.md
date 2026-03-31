# piper-g2p チケット一覧

> 関連: [`g2p-milestones.md`](../design/g2p-milestones.md) (マイルストーン計画), [`g2p-package-requirements.md`](../design/g2p-package-requirements.md) (要求定義)

---

## 進捗サマリー

| Phase | チケット数 | 完了 | 進行中 | TODO | マイルストーン |
|-------|----------|------|--------|------|-------------|
| 0 (MVP) | 9 | 0 | 0 | 9 | v0.0.1, v0.1.0 |
| 1 (全言語) | 11 | 0 | 0 | 11 | v0.2.0, v1.0.0 |
| 2 (Rust) | 10 | 0 | 0 | 10 | v0.1.0, v1.0.0 |
| 3 (JS/WASM) | 8 | 0 | 0 | 8 | v0.1.0, v1.0.0 |
| **合計** | **38** | **0** | **0** | **38** | |

---

## Phase 0: MVP (Python JA+EN) — 1 週間

> 目標: `uv pip install piper-g2p[ja,en]` で IPA 音素化が動作する

| チケット | タイトル | 要求 | 依存 | ステータス |
|---------|---------|------|------|-----------|
| [P0-001](phase-0/P0-001-package-name-reservation.md) | パッケージ名予約 | — | — | TODO |
| [P0-002](phase-0/P0-002-package-structure.md) | パッケージ構造作成 | FR-006 | P0-001 | TODO |
| [P0-003](phase-0/P0-003-core-abstractions.md) | コア抽象 (ABC + ProsodyInfo + Registry) | FR-001, FR-002 | P0-002 | TODO |
| [P0-004](phase-0/P0-004-japanese-phonemizer.md) | JapanesePhonemizer (IPA 出力) | FR-003 | P0-003 | TODO |
| [P0-005](phase-0/P0-005-english-phonemizer.md) | EnglishPhonemizer (IPA 出力) | FR-004 | P0-003 | TODO |
| [P0-006](phase-0/P0-006-piper-encoder.md) | PiperEncoder (encode モジュール) | FR-005 | P0-003 | TODO |
| [P0-007](phase-0/P0-007-piper-train-compat-shim.md) | piper_train 互換シム | FR-007 | P0-004, P0-005, P0-006 | TODO |
| [P0-008](phase-0/P0-008-test-suite.md) | テストスイート | NFR-001 | P0-004〜P0-007 | TODO |
| [P0-009](phase-0/P0-009-ci-workflow.md) | CI ワークフロー | NFR-004 | P0-002, P0-008 | TODO |

**依存関係グラフ:**

```
P0-001 (名前予約)
  └── P0-002 (パッケージ構造)
        └── P0-003 (コア抽象)
              ├── P0-004 (JA) ──┐
              ├── P0-005 (EN) ──┤  ← 並列実行可能
              └── P0-006 (encode)┤
                                 └── P0-007 (互換シム)
                                       └── P0-008 (テスト)
                                             └── P0-009 (CI)
```

---

## Phase 1: 全言語展開 — 1-2 週間

> 目標: 7 言語 + MultilingualPhonemizer + カスタム辞書
> 前提: Phase 0 v0.1.0 完了

| チケット | タイトル | 要求 | 依存 | ステータス |
|---------|---------|------|------|-----------|
| [P1-001](phase-1/P1-001-chinese-phonemizer.md) | ChinesePhonemizer (pypinyin) | FR-100 | P0-003 | TODO |
| [P1-002](phase-1/P1-002-korean-phonemizer.md) | KoreanPhonemizer (g2pk2) | FR-100 | P0-003 | TODO |
| [P1-003](phase-1/P1-003-spanish-phonemizer.md) | SpanishPhonemizer (ルールベース) | FR-100 | P0-003 | TODO |
| [P1-004](phase-1/P1-004-french-phonemizer.md) | FrenchPhonemizer (ルールベース) | FR-100 | P0-003 | TODO |
| [P1-005](phase-1/P1-005-portuguese-phonemizer.md) | PortuguesePhonemizer (ルールベース) | FR-100 | P0-003 | TODO |
| [P1-006](phase-1/P1-006-multilingual-phonemizer.md) | MultilingualPhonemizer + UnicodeLanguageDetector | FR-101 | P1-001〜P1-005 | TODO |
| [P1-007](phase-1/P1-007-custom-dictionary.md) | カスタム辞書 + 入力バリデーション | FR-102 | P0-003 | TODO |
| [P1-008](phase-1/P1-008-pyproject-extras.md) | pyproject.toml extras 拡張 | FR-103 | P1-001〜P1-005 | TODO |
| [P1-009](phase-1/P1-009-documentation.md) | ドキュメント + 既知制限記載 | NFR-101 | P1-001〜P1-005 | TODO |
| [P1-010](phase-1/P1-010-test-fixtures.md) | テストフィクスチャ + 言語テスト | NFR-100 | P1-001〜P1-006 | TODO |
| [P1-011](phase-1/P1-011-api-freeze-v1.md) | API 凍結 + v1.0.0 安定版リリース | — | 全 Phase 1 | TODO |

**依存関係グラフ:**

```
P0 完了
  ├── P1-001 (ZH) ──┐
  ├── P1-002 (KO) ──┤
  ├── P1-003 (ES) ──┤  ← 5 言語並列実行可能
  ├── P1-004 (FR) ──┤
  ├── P1-005 (PT) ──┤
  ├── P1-007 (辞書) │  ← 言語と並列実行可能
  │                  ├── P1-006 (多言語)
  │                  ├── P1-008 (extras)
  │                  ├── P1-009 (docs)
  │                  └── P1-010 (テスト)
  └──────────────────────── P1-011 (v1.0.0)
```

---

## Phase 2: Rust crate — 2-3 週間

> 目標: `cargo add piper-g2p` で IPA 音素化が動作する
> 開始条件: PyPI `piper-g2p` 月間 1,000 DL 超過

| チケット | タイトル | 要求 | 依存 | ステータス |
|---------|---------|------|------|-----------|
| [P2-001](phase-2/P2-001-crate-structure.md) | crate 構造作成 | NFR-200 | — | TODO |
| [P2-002](phase-2/P2-002-g2p-error-phoneme-id-map.md) | G2pError + PhonemeIdMap 再定義 | FR-201 | P2-001 | TODO |
| [P2-003](phase-2/P2-003-phonemizer-trait.md) | Phonemizer trait (IPA-first) | FR-200 | P2-002 | TODO |
| [P2-004](phase-2/P2-004-7lang-phonemizer-move.md) | 7 言語 Phonemizer 移動 | FR-202 | P2-001〜P2-003 | TODO |
| [P2-005](phase-2/P2-005-piper-encoder.md) | PiperEncoder (PUA + ID 変換) | FR-200 | P2-001〜P2-004 | TODO |
| [P2-006](phase-2/P2-006-request-builder-rename.md) | piper-core 側 request_builder リネーム | FR-200 | P2-004, P2-005 | TODO |
| [P2-007](phase-2/P2-007-piper-core-reexport.md) | piper-core re-export | NFR-203 | P2-004, P2-005 | TODO |
| [P2-008](phase-2/P2-008-jpreprocess-compat-test.md) | jpreprocess vs pyopenjtalk 互換性テスト | FR-203 | P2-004 | TODO |
| [P2-009](phase-2/P2-009-ci-workflow.md) | CI ワークフロー | NFR-202 | P2-001, P2-004, P2-007 | TODO |
| [P2-010](phase-2/P2-010-stable-release.md) | 安定版リリース (v1.0.0) | — | 全 Phase 2 | TODO |

**依存関係グラフ:**

```
P2-001 (crate 構造)
  └── P2-002 (G2pError)
        └── P2-003 (Phonemizer trait)
              └── P2-004 (7 言語移動)
                    ├── P2-005 (PiperEncoder)
                    │     ├── P2-006 (request_builder)
                    │     └── P2-007 (re-export)
                    └── P2-008 (互換テスト)
                          └── P2-009 (CI)
                                └── P2-010 (v1.0.0)
```

---

## Phase 3: JS/WASM — 3-4 週間

> 目標: `import { G2P } from '@piper-plus/g2p'` で IPA 音素化が動作する
> 開始条件: PyPI + crates.io 合計月間 2,000 DL 超過 or ブラウザ TTS Issue 3 件以上

| チケット | タイトル | 要求 | 依存 | ステータス |
|---------|---------|------|------|-----------|
| [P3-001](phase-3/P3-001-phonemizer-separation.md) | SimpleUnifiedPhonemizer 分離 | FR-300 | — | TODO |
| [P3-002](phase-3/P3-002-openjtalk-wasm-di.md) | OpenJTalk WASM の DI 化 | FR-301 | P3-001 | TODO |
| [P3-003](phase-3/P3-003-dict-loader-separation.md) | DictLoader 分離 | FR-301 | P3-001 | TODO |
| [P3-004](phase-3/P3-004-phonemize-with-prosody.md) | phonemizeWithProsody() 追加 | FR-302 | P3-001, P3-002 | TODO |
| [P3-005](phase-3/P3-005-piper-plus-compat-layer.md) | piper-plus 互換レイヤー | NFR-301 | P3-001〜P3-004 | TODO |
| [P3-006](phase-3/P3-006-typescript-type-definitions.md) | TypeScript 型定義 | NFR-302 | P3-001, P3-004 | TODO |
| [P3-007](phase-3/P3-007-ci-workflow.md) | CI ワークフロー | NFR-300 | P3-001, P3-006 | TODO |
| [P3-008](phase-3/P3-008-stable-release.md) | 安定版リリース (v1.0.0) | — | 全 Phase 3 | TODO |

**依存関係グラフ:**

```
P3-001 (Phonemizer 分離)
  ├── P3-002 (OpenJTalk DI) ──┐
  ├── P3-003 (DictLoader) ────┤  ← 並列実行可能
  │                           ├── P3-005 (互換レイヤー)
  └── P3-004 (prosody) ──────┘
        └── P3-006 (TypeScript 型定義)
              └── P3-007 (CI)
                    └── P3-008 (v1.0.0)
```

---

## 要求トレーサビリティ

### Phase 0

| 要求 | チケット |
|------|---------|
| FR-001 (Phonemizer ABC) | P0-003 |
| FR-002 (言語レジストリ) | P0-003 |
| FR-003 (JapanesePhonemizer) | P0-004 |
| FR-004 (EnglishPhonemizer) | P0-005 |
| FR-005 (PiperEncoder) | P0-006 |
| FR-006 (pyproject.toml) | P0-002 |
| FR-007 (互換シム) | P0-007 |
| NFR-001 (テストカバレッジ) | P0-008 |
| NFR-002 (ゼロコンパイル依存) | P0-002 |
| NFR-003 (パフォーマンス) | P0-008 |
| NFR-004 (CI ワークフロー) | P0-009 |

### Phase 1

| 要求 | チケット |
|------|---------|
| FR-100 (5 言語 Phonemizer) | P1-001〜P1-005 |
| FR-101 (MultilingualPhonemizer) | P1-006 |
| FR-102 (カスタム辞書) | P1-007 |
| FR-103 (pyproject.toml extras) | P1-008 |
| NFR-100 (テストフィクスチャ) | P1-010 |
| NFR-101 (既知制限ドキュメント) | P1-009 |

### Phase 2

| 要求 | チケット |
|------|---------|
| FR-200 (Phonemizer trait + Encoder) | P2-003, P2-005, P2-006 |
| FR-201 (G2pError + PhonemeIdMap) | P2-002 |
| FR-202 (7 言語 Phonemizer 移動) | P2-004 |
| FR-203 (jpreprocess 互換性) | P2-008 |
| NFR-200 (crate 構造) | P2-001 |
| NFR-202 (CI ワークフロー) | P2-009 |
| NFR-203 (piper-core 互換) | P2-007 |

### Phase 3

| 要求 | チケット |
|------|---------|
| FR-300 (Phonemizer 分離) | P3-001 |
| FR-301 (OpenJTalk DI + DictLoader) | P3-002, P3-003 |
| FR-302 (phonemizeWithProsody) | P3-004 |
| NFR-300 (CI ワークフロー) | P3-007 |
| NFR-301 (互換レイヤー) | P3-005 |
| NFR-302 (TypeScript 型定義) | P3-006 |
