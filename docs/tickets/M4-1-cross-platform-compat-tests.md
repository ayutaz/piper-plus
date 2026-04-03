# M4-1: クロスプラットフォーム互換テスト

> **マイルストーン**: M4
> **前提チケット**: M1-8, M2-8, M3-6
> **後続チケット**: M4-2
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

Python / Rust / JS の 3 プラットフォームにおける G2P 出力が一致することを、共有テストフィクスチャで保証する。全 8 言語 (JA/EN/ZH/KO/ES/FR/PT/SV) のゴールデンデータを JSON ファイルとして定義し、各プラットフォームのテストスイートがこのフィクスチャを読み込んで出力を比較する。

## 実装する内容の詳細

### 1. ゴールデンフィクスチャの作成

**ファイル**: `data/test-fixtures/g2p-golden-outputs.json`

```json
{
  "version": 1,
  "description": "Cross-platform G2P golden test outputs",
  "fixtures": [
    {
      "language": "ja",
      "input_text": "こんにちは",
      "expected_tokens": ["k", "o", "N_n", "n", "i", "ch", "i", "w", "a"],
      "expected_phoneme_ids": [1, 45, 63, ...]
    },
    {
      "language": "en",
      "input_text": "Hello world",
      "expected_tokens": ["HH", "AH0", "L", "OW1", ...],
      "expected_phoneme_ids": [1, 28, 12, ...]
    }
  ]
}
```

**ゴールデンデータの正解値は Python (piper_plus_g2p) を基準 (source of truth) として生成する。** 理由: Python が最も完全な phonemizer 実装を持ち、互換テスト (test_compat.py) で piper_train との一致が検証済みであるため。生成手順: `uv run python -c "from piper_plus_g2p import get_phonemizer; ..."` で各言語の出力を JSON に書き出す。

各言語につき 3-5 テストケースを用意:
- 基本テキスト (短文)
- 特殊文字を含むテキスト
- 空文字列 / 記号のみ

### 2. Python テスト

**ファイル**: `src/python/tests/test_g2p_golden.py` (新規)

- `g2p-golden-outputs.json` を読み込み
- `piper_plus_g2p` のエンコーダで `input_text` → `phoneme_ids` を生成
- `expected_phoneme_ids` と比較

### 3. Rust テスト

**ファイル**: `src/rust/piper-core/tests/test_g2p_golden.rs` (新規)

- `g2p-golden-outputs.json` を `serde_json` で読み込み
- `piper_plus_g2p` クレートのエンコーダで `input_text` → `phoneme_ids` を生成
- `expected_phoneme_ids` と比較

### 4. JS テスト

**ファイル**: `src/wasm/openjtalk-web/test/js/test-g2p-golden.js` (新規)

- `g2p-golden-outputs.json` を読み込み
- `@piper-plus/g2p` の `G2P.encode()` で `input_text` → `phonemeIds` を生成
- `expected_phoneme_ids` と比較

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `data/test-fixtures/g2p-golden-outputs.json` | 新規作成: 8 言語のゴールデンデータ |
| `src/python/tests/test_g2p_golden.py` | 新規作成: Python ゴールデンテスト |
| `src/rust/piper-core/tests/test_g2p_golden.rs` | 新規作成: Rust ゴールデンテスト |
| `src/wasm/openjtalk-web/test/js/test-g2p-golden.js` | 新規作成: JS ゴールデンテスト |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| フィクスチャ設計 + コーディネーター | 1 | ゴールデンデータ作成、フォーマット設計、全プラットフォームの整合性確認 |
| Python テスト担当 | 1 | Python テスト実装、ゴールデンデータ生成スクリプト |
| Rust テスト担当 | 1 | Rust テスト実装 |
| JS テスト担当 | 1 | JS テスト実装 |

## 提供範囲とテスト

### 提供範囲

- ゴールデンフィクスチャファイル (JSON)
- 3 プラットフォーム各 1 テストファイル

### テスト項目

- 全 3 プラットフォームで全 8 言語のゴールデンテストが pass すること
- ゴールデンデータが 3 プラットフォーム間で共有可能なフォーマットであること

### Unit テスト

- 各プラットフォーム:
  - 8 言語 x 3-5 テストケース = 24-40 アサーション
  - `expected_tokens` との比較 (トークン化の正当性)
  - `expected_phoneme_ids` との比較 (ID マッピングの正当性)

### E2E テスト

- CI の各プラットフォーム Job でゴールデンテストが pass すること
- ゴールデンデータの更新手順が文書化されていること

## 懸念事項とレビュー項目

### 懸念事項

1. **軽微な出力差異**: ホワイトスペースの扱い、正規化 (NFKC 等)、句読点の処理でプラットフォーム間に微妙な差異が生じる可能性がある。許容範囲を明確に定義する必要がある
2. **JA の OpenJTalk バージョン差異**: Python (pyopenjtalk-plus)、Rust (jpreprocess)、JS (OpenJTalk WASM) で OpenJTalk の内部バージョンが異なり、トークン化結果が微妙に異なる可能性がある。特に新語や固有名詞で差異が出やすい
3. **KO の G2P 差異**: Python は g2pk2、Rust/JS は独自実装で、韓国語の音素化結果が一致しない可能性がある
4. **ゴールデンデータの保守**: 言語追加やルール変更のたびにゴールデンデータの更新が必要。更新手順の自動化が望ましい

### レビュー項目

1. ゴールデンデータの各テストケースが代表的な入力をカバーしていること
2. `expected_phoneme_ids` が phoneme_id_map に基づいて正しく生成されていること
3. プラットフォーム間の差異が許容範囲内であること (差異がある場合はフィクスチャにプラットフォーム固有の expected 値を追加)
4. テストの実行が各プラットフォームの CI に統合されていること

## 一から作り直すとしたら

ゴールデンデータの生成を自動化するスクリプトを最初から用意する。「リファレンス実装 (Python) で生成 → 他プラットフォームで検証」というワークフローを CI に組み込み、リファレンス実装の変更時にゴールデンデータが自動更新される仕組みにする。

## 後続タスクへの連絡事項

- M4-2 (音声品質回帰テスト) は、このチケットで phonemeIds の一致が確認されたことを前提に、音声出力の同一性を検証する
- ゴールデンデータのフォーマット (`version: 1`) は将来の拡張に備えている。フォーマット変更時は version を上げること
- プラットフォーム固有の差異が発見された場合、フィクスチャの構造を拡張する (例: `expected_phoneme_ids_js` フィールドの追加)
