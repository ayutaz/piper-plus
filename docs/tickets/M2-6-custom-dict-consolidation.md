# M2-6: custom_dict.rs 統合

> **マイルストーン**: M2
> **前提チケット**: M2-1
> **後続チケット**: M2-7
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`piper-core/src/phonemize/custom_dict.rs` を削除し、piper-g2p の同等モジュールに置き換える。両者の API はほぼ同一であり、piper-g2p 側に 10MB ファイルサイズ上限が追加されている点が唯一の差異。

**ゴール**: piper-core から custom_dict.rs が削除され、カスタム辞書機能が piper-g2p 経由で提供される状態。エラー変換は既存の `From<G2pError> for PiperError` 実装を利用する。

## 実装する内容の詳細

### 現状の構成

**piper-core**: `src/rust/piper-core/src/phonemize/custom_dict.rs`
- `CustomDict::load()` -- JSON v1.0/v2.0 + TSV 形式の辞書ファイル読み込み
- `CustomDict::apply_to_text()` -- テキストに辞書エントリを適用

**piper-g2p**: 同等の `custom_dict` モジュール
- 同一 API + 10MB ファイルサイズ上限

### API 互換性の事前確認

実装前に以下のメソッドシグネチャを比較確認:
- `new()`, `load_dictionary(&mut self, path: &Path)`, `apply_to_text(&self, text: &str) -> String`, `add_word()`, `get_pronunciation()`

差異がある場合はアダプタを追加する。エラー型は `From<G2pError> for PiperError` で変換。

### 変更手順

1. piper-core 内の `CustomDict` 呼び出し箇所を全て洗い出す
2. 各呼び出し箇所の import を `piper_plus_g2p::custom_dict::CustomDict` に置換
3. エラー変換が既存の `From<G2pError> for PiperError` で処理されることを確認
4. `custom_dict.rs` を削除
5. `mod.rs` から `custom_dict` モジュールの登録を削除

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/rust/piper-core/src/phonemize/custom_dict.rs` | 削除 |
| `src/rust/piper-core/src/phonemize/mod.rs` | custom_dict モジュール登録の削除 |
| custom_dict を呼び出す全ファイル (voice.rs 等) | import パスの変更 |
| CLI 関連 (piper-cli) | import パスの変更 (該当する場合) |

### 変更しないもの

- カスタム辞書の JSON v1.0/v2.0 フォーマット -- 互換性維持
- TSV フォーマット -- 互換性維持
- piper-g2p の custom_dict モジュール -- 変更不要
- `From<G2pError> for PiperError` 実装 -- 既存のまま使用

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | import 置換、ファイル削除、テスト更新 |

## 提供範囲とテスト

### 提供範囲

- `custom_dict.rs` の削除
- 呼び出し元の import パス更新

### テスト項目

1. piper-g2p の `CustomDict::load()` が JSON v1.0/v2.0 を正しく読み込むこと
2. piper-g2p の `CustomDict::load()` が TSV 形式を正しく読み込むこと
3. `apply_to_text()` が従来と同一の結果を返すこと
4. エラー変換が正しく動作すること
5. 10MB を超えるファイルが適切にエラーになること

### Unit テスト

```rust
#[test]
fn test_load_json_v1_dict() {
    // JSON v1.0 形式の辞書を piper-g2p 経由で読み込み、
    // エントリが正しくパースされることを確認
}

#[test]
fn test_load_json_v2_dict() {
    // JSON v2.0 形式の辞書を piper-g2p 経由で読み込み、
    // エントリが正しくパースされることを確認
}

#[test]
fn test_load_tsv_dict() {
    // TSV 形式の辞書を piper-g2p 経由で読み込み、
    // エントリが正しくパースされることを確認
}

#[test]
fn test_apply_to_text_same_result() {
    // apply_to_text() の結果が旧実装と同一であることを確認
}

#[test]
fn test_error_conversion_g2p_to_piper() {
    // G2pError が PiperError に正しく変換されることを確認
}
```

### E2E テスト

- 既存の `test_custom_dict_integration.rs` が全件パスすること
- CLI の `--custom-dict` オプションが正常に動作すること

## 懸念事項とレビュー項目

### 懸念事項

1. **10MB ファイルサイズ上限**: piper-g2p 側に追加された 10MB 上限が、一部のユーザーにとって制約になる可能性がある。大規模な辞書ファイルを使用しているユーザーがいる場合、上限を引き上げるか設定可能にする必要がある。リリースノートに上限追加を明記すること
2. **CLI との結合点**: `piper-cli` が `custom_dict` を直接 import している場合、CLI 側の import パスも更新が必要。`piper-cli/src/main.rs` を確認すること

### レビュー項目

1. `custom_dict.rs` の全呼び出し箇所が洗い出されていること
2. piper-g2p の `CustomDict` API が piper-core の旧 API と互換であること
3. エラー変換で情報が失われていないこと
4. 10MB 上限の影響範囲が評価されていること
5. 既存の integration テスト (`test_custom_dict_integration.rs`) がパスすること

## 一から作り直すとしたら

カスタム辞書機能を最初から piper-g2p にのみ配置し、piper-core には辞書ファイルパスの受け渡しロジックのみを実装する。ファイルサイズ上限は設定可能にし、デフォルト 10MB、環境変数で変更可能にする。

## 後続タスクへの連絡事項

- M2-7 (旧ファイル削除) の対象に `custom_dict.rs` が含まれることを確認すること
- 10MB 上限について、ユーザー向けドキュメントへの記載が必要な場合は別チケットで対応すること
- `test_custom_dict_integration.rs` のテストが piper-g2p 経由でもパスすることを M2-8 で最終確認すること
