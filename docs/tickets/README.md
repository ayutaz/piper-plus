# G2P 統一チケット一覧

> **マイルストーン**: [g2p-unification-milestones.md](../g2p-unification-milestones.md)
> **目標**: piper-plus 本体の重複 phonemizer を standalone piper-g2p に統一し、42 ファイル (~8,700 行) を削除

---

## 進捗サマリ

| マイルストーン | チケット数 | 完了 | 状態 |
|---|---|---|---|
| [M0: API ギャップ修正](#m0-piper-g2p-api-ギャップ修正) | 4 | 4/4 | 完了 |
| [M1: Python 移行](#m1-python-移行) | 8 | 1/8 | 進行中 |
| [M2: Rust 移行](#m2-rust-移行) | 8 | 0/8 | 未着手 |
| [M3: JS/WASM 移行](#m3-jswasm-移行) | 6 | 0/6 | 未着手 |
| [M4: 検証・クリーンアップ](#m4-検証クリーンアップ) | 4 | 0/4 | 未着手 |
| **合計** | **30** | **5/30** | |

---

## M0: piper-g2p API ギャップ修正

> 前提条件なし。M1/M2/M3 の全てがこれに依存する。

| ID | チケット | 見積り | リスク | 状態 |
|---|---|---|---|---|
| M0-1 | [`_get_question_type()` 戻り値修正](M0-1-fix-question-type-return.md) | 小 | 中 | 完了 |
| M0-2 | [JapanesePhonemizer custom_dict パラメータ追加](M0-2-japanese-custom-dict-param.md) | 小 | 低 | 完了 |
| M0-3 | [互換テスト拡充](M0-3-expand-compat-tests.md) | 中 | 低 | 完了 |
| M0-4 | [Rust PiperEncoder 動的 EOS 対応](M0-4-rust-dynamic-eos.md) | 中 | 中 | 完了 |

---

## M1: Python 移行

> M0 完了後に着手。M2/M3 と並行可能。

| ID | チケット | 見積り | リスク | 前提 | 状態 |
|---|---|---|---|---|---|
| M1-1 | [依存関係の追加](M1-1-add-piper-g2p-dependency.md) | 小 | 低 | M0 | 未着手 |
| M1-2 | [低リスク import 置換](M1-2-drop-in-import-replacement.md) | 小 | 低 | M1-1 | 未着手 |
| M1-3 | [ID マップ API 置換](M1-3-id-map-api-replacement.md) | 中 | 中 | M0-3, M1-1 | 未着手 |
| M1-4 | [preprocess.py リファクタ](M1-4-preprocess-pipeline-refactor.md) | 大 | **高** | M0-1, M0-2, M1-1, M1-3 | 未着手 |
| M1-5 | [tools/ スクリプト移行](M1-5-tools-scripts-migration.md) | 中 | 中 | M1-1, M1-3 | 未着手 |
| M1-6 | [dead code 削除](M1-6-dead-code-removal.md) | 小 | 低 | なし | 完了 |
| M1-7 | [旧 phonemize ディレクトリ削除](M1-7-delete-old-phonemize-dir.md) | 中 | 中 | M1-2〜M1-6 | 未着手 |
| M1-8 | [テスト・CI 対応](M1-8-test-ci-updates.md) | 中 | 中 | M1-7 | 未着手 |

---

## M2: Rust 移行

> M0-4 完了後に着手。M1/M3 と並行可能。

| ID | チケット | 見積り | リスク | 前提 | 状態 |
|---|---|---|---|---|---|
| M2-1 | [Cargo.toml features 有効化](M2-1-enable-g2p-features.md) | 小 | 低 | M0-4 | 未着手 |
| M2-2 | [adapter 層の作成](M2-2-create-adapter-layer.md) | 中 | 中 | M0-4, M2-1 | 未着手 |
| M2-3 | [voice.rs ファクトリ書き換え](M2-3-voice-factory-rewrite.md) | 中 | 中 | M2-2 | 未着手 |
| M2-4 | [phoneme_converter.rs 統合](M2-4-phoneme-converter-consolidation.md) | 小 | 低 | M2-1 | 未着手 |
| M2-5 | [MultilingualPhonemizer 統合](M2-5-multilingual-phonemizer-consolidation.md) | 中 | 中 | M2-2, M2-3 | 未着手 |
| M2-6 | [custom_dict.rs 統合](M2-6-custom-dict-consolidation.md) | 小 | 低 | M2-1 | 未着手 |
| M2-7 | [旧 phonemize ファイル削除](M2-7-delete-old-phonemize-files.md) | 中 | 中 | M2-2〜M2-6 | 未着手 |
| M2-8 | [テスト・CI 対応](M2-8-test-ci-updates.md) | 中 | 中 | M2-7 | 未着手 |

---

## M3: JS/WASM 移行

> M0 完了後に着手。M1/M2 と並行可能。

| ID | チケット | 見積り | リスク | 前提 | 状態 |
|---|---|---|---|---|---|
| M3-1 | [PiperPlus 初期化の切り替え](M3-1-piperplus-init-switch.md) | 中 | 中 | M0 | 未着手 |
| M3-2 | [_textToPhonemeIds() 統一](M3-2-unify-text-to-phoneme-ids.md) | 中 | 中 | M3-1 | 未着手 |
| M3-3 | [prosody 抽出の統合](M3-3-prosody-extraction-consolidation.md) | 小 | 低 | M3-1, M3-2 | 未着手 |
| M3-4 | [テスト更新 (11 ファイル)](M3-4-test-updates.md) | 中 | 中 | M3-1〜M3-3 | 未着手 |
| M3-5 | [deprecated コード削除](M3-5-deprecated-code-removal.md) | 中 | 中 | M3-4 | 未着手 |
| M3-6 | [CI 対応](M3-6-ci-updates.md) | 小 | 低 | M3-4, M3-5 | 未着手 |

---

## M4: 検証・クリーンアップ

> M1 + M2 + M3 全て完了後に着手。

| ID | チケット | 見積り | リスク | 前提 | 状態 |
|---|---|---|---|---|---|
| M4-1 | [クロスプラットフォーム互換テスト](M4-1-cross-platform-compat-tests.md) | 中 | 中 | M1-8, M2-8, M3-6 | 未着手 |
| M4-2 | [音声品質の回帰テスト](M4-2-audio-quality-regression.md) | 小 | 低 | M4-1 | 未着手 |
| M4-3 | [CLAUDE.md 更新](M4-3-update-claude-md.md) | 小 | 低 | M1-7, M2-7, M3-5 | 未着手 |
| M4-4 | [最終確認と削除ファイル数確認](M4-4-final-verification.md) | 小 | 低 | M4-1〜M4-3 | 未着手 |

---

## 依存関係グラフ

```
M0-1 ──┐
M0-2 ──┼──→ M1-4 (preprocess.py) ──→ M1-7 (削除) ──→ M1-8 (CI)
M0-3 ──┤                                  ↑
       │    M1-1 ──→ M1-2 ────────────────┤
       │         ──→ M1-3 ────────────────┤
       │              M1-5 ───────────────┤
       │              M1-6 ───────────────┘
       │
M0-4 ──┼──→ M2-1 ──→ M2-2 ──→ M2-3 ──→ M2-5 ──→ M2-7 (削除) ──→ M2-8 (CI)
       │         ──→ M2-4 ────────────────────────┘
       │         ──→ M2-6 ────────────────────────┘
       │
       └──→ M3-1 ──→ M3-2 ──→ M3-3 ──→ M3-4 ──→ M3-5 (削除) ──→ M3-6 (CI)

M1-8 + M2-8 + M3-6 ──→ M4-1 ──→ M4-2
                        M4-3 ──→ M4-4
```

> ※ 簡略化のため一部の依存エッジを省略。詳細は各チケットの前提/後続チケットを参照。

## エージェントチーム総計

| 役割 | 合計人数 | 担当マイルストーン |
|---|---|---|
| Python 実装者 | 4 | M0-1, M0-2, M1-2〜M1-6 |
| Rust 実装者 | 3 | M0-4, M2-2, M2-3, M2-5 |
| JS 実装者 | 2 | M3-1, M3-2, M3-3 |
| テスト作成者 | 3 | M0-3, M1-4, M3-4, M4-1 |
| CI スペシャリスト | 2 | M1-8, M2-8, M3-6 |
| レビュアー | 3 | 全チケット横断 |
| コーディネーター | 1 | M4-1 (クロスプラットフォーム) |
