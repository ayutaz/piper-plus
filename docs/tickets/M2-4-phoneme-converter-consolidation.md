# M2-4: phoneme_converter.rs 統合

> **マイルストーン**: M2
> **前提チケット**: M2-1
> **後続チケット**: M2-7
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`piper-core/src/phonemize/phoneme_converter.rs` に含まれる `tokens_to_ids()` と `prosody_to_features()` を piper-g2p の `piper_g2p::encode` モジュールに統合し、重複コードを削除する。

piper-core と piper-g2p の両方に同一機能の `tokens_to_ids()` と `prosody_to_features()` が存在しており、メンテナンスコストが二重になっている。piper-g2p 側の実装を正とし、piper-core 側を削除する。

`build_synthesis_request()` は piper-core 固有の型 (`SynthesisRequest`) を使用するため、piper-core 内に残す (voice.rs または新規モジュールに移動)。

**ゴール**: piper-core の phoneme_converter.rs を削除し、`tokens_to_ids()` と `prosody_to_features()` の呼び出しが piper-g2p 経由になった状態。`build_synthesis_request()` は piper-core 内の適切な場所に移動。

## 実装する内容の詳細

### 現状の構成

**piper-core**: `src/rust/piper-core/src/phonemize/phoneme_converter.rs`
- `tokens_to_ids()` -- トークン列を phoneme_ids に変換
- `prosody_to_features()` -- A1/A2/A3 prosody 値を特徴量テンソルに変換
- `build_synthesis_request()` -- phoneme_ids + prosody_features から SynthesisRequest を構築

**piper-g2p**: `piper_g2p::encode` モジュール
- `tokens_to_ids()` -- 同一機能
- `prosody_to_features()` -- 同一機能

### 変更手順

1. piper-core 内の `tokens_to_ids()` 呼び出しを `piper_g2p::encode::tokens_to_ids()` に置換
2. piper-core 内の `prosody_to_features()` 呼び出しを `piper_g2p::encode::prosody_to_features()` に置換
3. `build_synthesis_request()` を voice.rs (または新規 `synthesis.rs` モジュール) に移動
4. `phoneme_converter.rs` を削除
5. `mod.rs` から `phoneme_converter` モジュールの登録を削除

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/rust/piper-core/src/phonemize/phoneme_converter.rs` | 削除 |
| `src/rust/piper-core/src/phonemize/mod.rs` | phoneme_converter モジュール登録の削除 |
| `src/rust/piper-core/src/voice.rs` | import パスの変更、`build_synthesis_request()` の移動先 |
| phoneme_converter を呼び出す全ファイル | import パスの変更 |

### 変更しないもの

- `build_synthesis_request()` のロジック -- 移動のみ、実装変更なし
- `SynthesisRequest` 構造体 -- piper-core 固有のため変更不要
- piper-g2p の `encode` モジュール -- 変更不要

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | import 置換、ファイル移動・削除、テスト更新 |

## 提供範囲とテスト

### 提供範囲

- `phoneme_converter.rs` の削除
- `build_synthesis_request()` の移動
- 呼び出し元の import パス更新

### テスト項目

1. piper-g2p の `tokens_to_ids()` が piper-core の旧実装と同一結果を返すこと
2. piper-g2p の `prosody_to_features()` が piper-core の旧実装と同一結果を返すこと
3. `build_synthesis_request()` が移動後も正しく動作すること

### Unit テスト

```rust
#[test]
fn test_tokens_to_ids_from_g2p_matches_old() {
    // piper-g2p の tokens_to_ids() で変換した結果が
    // 旧 piper-core の tokens_to_ids() と同一であることを確認
}

#[test]
fn test_prosody_to_features_from_g2p_matches_old() {
    // piper-g2p の prosody_to_features() で変換した結果が
    // 旧 piper-core の prosody_to_features() と同一であることを確認
}

#[test]
fn test_build_synthesis_request_after_move() {
    // 移動後の build_synthesis_request() が正しく SynthesisRequest を構築すること
}
```

### E2E テスト

- 既存の推論パイプラインテストが全てパスすること
- `tokens_to_ids` -> `build_synthesis_request` -> `synthesize` のフルパスが動作すること

## 懸念事項とレビュー項目

### 懸念事項

1. **SynthesisRequest の構築**: `build_synthesis_request()` は piper-core の `SynthesisRequest` 型に依存する。この関数を piper-g2p に移動することはできないため、piper-core 内の適切な場所に配置する必要がある。voice.rs が最も自然な配置先だが、ファイルサイズが大きくなる場合は `synthesis.rs` 等の新規モジュールを検討する
2. **API の微妙な差異**: piper-g2p と piper-core の `tokens_to_ids()` が完全に同一の引数・戻り値型であることを事前に確認すること。型の違い (例: `&[String]` vs `&[&str]`) がある場合はラッパーが必要
3. **関数シグネチャの互換性検証**: `tokens_to_ids()` と `prosody_to_features()` の引数型・戻り値型が piper-core 版と piper-g2p 版で完全一致するか、実装前に比較確認すること。型が異なる場合は薄いラッパーが必要。

### レビュー項目

1. `phoneme_converter.rs` の全関数の呼び出し箇所が洗い出されていること
2. piper-g2p の `tokens_to_ids()` / `prosody_to_features()` と旧実装の引数・戻り値型が一致すること
3. `build_synthesis_request()` の移動先が適切であること
4. 未使用 import が残っていないこと

## 一から作り直すとしたら

`tokens_to_ids()` と `prosody_to_features()` を最初から piper-g2p にのみ配置し、piper-core はそれを呼び出す設計にしていれば重複は発生しなかった。encode/decode のロジックは G2P パッケージの責務として明確に分離すべきだった。

## 後続タスクへの連絡事項

- M2-7 (旧ファイル削除) の対象に `phoneme_converter.rs` が含まれることを確認すること
- `build_synthesis_request()` の移動先 (voice.rs or synthesis.rs) を確定したら共有すること
- import パスの変更が他の M2 チケットの作業と競合する可能性があるため、マージ順序に注意すること
