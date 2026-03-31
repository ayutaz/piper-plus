# スウェーデン語対応 ドキュメント体系

## 文書一覧

| # | 文書 | ファイル | 内容 |
|---|------|---------|------|
| 1 | **調査レポート** | `swedish-g2p-research.md` | 既存OSS評価 (Epitran 31%, espeak-ng 70%), データ資源, 実装方式比較 |
| 2 | **設計書** | `swedish-g2p-design.md` | 全課題の解決方針, 疑似コード, 処理フロー |
| 3 | **NST辞書統合設計** | `nst-dictionary-integration.md` | 辞書構造分析, SAMPA→IPA変換, ティア戦略 |
| 4 | **要求定義書** | `swedish-requirements.md` | スコープ, 機能/非機能要件, 受入テスト, 制約/リスク |
| 5 | **要件定義: 辞書統合** | `swedish-fr01-fr02-spec.md` | FR-01 辞書ルックアップ, FR-02 SAMPA→IPA変換ツール |
| 6 | **要件定義: G2P規則** | `swedish-g2p-impl-spec.md` | FR-03a〜g 全規則の詳細仕様, データテーブル, 疑似コード |
| 7 | **要件定義: 統合** | `swedish-requirements-FR04-FR06.md` | FR-04 音素インベントリ, FR-05 ABC準拠, FR-06 マルチリンガル |
| 8 | **要件定義: テスト** | `swedish-test-spec.md` | FR-07 110テストケース, パイプライントレース, CI仕様 |

## 文書間の関係

```
調査レポート (research)
  ↓ 発見事項
設計書 (design) ← NST辞書統合設計 (nst-dictionary)
  ↓ 設計方針
要求定義書 (requirements)
  ↓ 要件分解
要件定義書 (4文書)
  ├── FR-01/02: 辞書統合 (fr01-fr02-spec)
  ├── FR-03: G2P規則 (impl-spec)
  ├── FR-04/05/06: 統合 (FR04-FR06)
  └── FR-07: テスト (test-spec)
```

## テストケース数

| 文書 | テスト数 |
|------|---------|
| FR-01/02 (辞書) | 66 |
| FR-03 (G2P規則) | ~145 |
| FR-04/05/06 (統合) | 33 |
| FR-07 (メインテスト) | 110 |
| **合計** | **~354** |

※ 重複あり。FR-07の110テストが最終的な受入テストスイート。他はユニットテスト仕様。

## 成果物サマリー

### 新規ファイル (5)

| ファイル | 推定行数 | 内容 |
|---------|---------|------|
| `phonemize/swedish.py` | ~900-1100 | SwedishPhonemizer + 全G2P規則 |
| `phonemize/sv_id_map.py` | ~50 | SWEDISH_PHONEMES |
| `tools/convert_nst_dictionary.py` | ~200 | SAMPA→IPA変換CLI |
| `test/test_swedish_phonemizer.py` | ~500 | 110+ テストケース |
| (generated) `sv_dict_core.json` | - | 238K語辞書 |

### 変更ファイル (4)

| ファイル | 変更内容 |
|---------|---------|
| `phonemize/registry.py` | sv 登録 (+7行) |
| `phonemize/multilingual.py` | _latin_languages に sv (+1行) |
| `phonemize/multilingual_id_map.py` | LANGUAGE_PHONEMES sv 登録 (+8行) |
| `phonemize/token_mapper.py` | PUA 9個追加 + _PUA_START 更新 (+12行) |
