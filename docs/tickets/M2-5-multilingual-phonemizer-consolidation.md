# M2-5: MultilingualPhonemizer 統合

> **マイルストーン**: M2
> **前提チケット**: M2-2, M2-3
> **後続チケット**: M2-7
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`piper-core/src/phonemize/multilingual.rs` (~1000行) の MultilingualPhonemizer を piper-g2p の同等実装に置き換える。piper-core 固有の機能 (`default_post_process_ids()`, `PassthroughPhonemizer`) は piper-core 内に残す。

**ゴール**: piper-core の MultilingualPhonemizer が piper-g2p の MultilingualPhonemizer を内部で使用する状態。`UnicodeLanguageDetector`, `segment_text()` 等の重複コードが除去され、メンテナンスが piper-g2p に一元化された状態。

## 実装する内容の詳細

### 現状の構成

**piper-core**: `src/rust/piper-core/src/phonemize/multilingual.rs` (~1000行)
- `UnicodeLanguageDetector` -- Unicode ブロックベースの言語自動検出
- `segment_text()` -- テキストを言語別セグメントに分割
- `default_post_process_ids()` -- 推論固有の phoneme_ids 後処理
- `MultilingualPhonemizer` -- 言語検出 + 言語別 phonemizer 委譲
- `PassthroughPhonemizer` -- 辞書未対応時のフォールバック

**piper-g2p**: 同等の `MultilingualPhonemizer` モジュール
- `UnicodeLanguageDetector` -- 同一機能
- `segment_text()` -- 同一機能
- `MultilingualPhonemizer` -- 同一アーキテクチャ

### 変更方針

| コンポーネント | 方針 |
|--------------|------|
| `UnicodeLanguageDetector` | piper-g2p のものを使用、piper-core から削除 |
| `segment_text()` | piper-g2p のものを使用、piper-core から削除 |
| `MultilingualPhonemizer` | piper-g2p のものを使用、piper-core から削除 |
| `default_post_process_ids()` | piper-core に残す (推論固有の後処理) |
| `PassthroughPhonemizer` | piper-core に残す (piper-core 固有のフォールバック) |

### 変更手順

1. piper-core の multilingual.rs から `UnicodeLanguageDetector`, `segment_text()`, `MultilingualPhonemizer` を削除
2. 上記コンポーネントの呼び出し箇所を piper-g2p の import に置換
3. `default_post_process_ids()` を multilingual.rs に残す (または適切な新モジュールに移動)
4. `PassthroughPhonemizer` を multilingual.rs に残す
5. piper-core の MultilingualPhonemizer の初期化コード (voice.rs 等) を piper-g2p の MultilingualPhonemizer + G2pAdapter を使用するように更新

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/rust/piper-core/src/phonemize/multilingual.rs` | 大幅縮小 (~1000行 -> ~200行)、3コンポーネント削除 |
| `src/rust/piper-core/src/voice.rs` | MultilingualPhonemizer の初期化コード更新 |
| multilingual.rs を呼び出す全ファイル | import パスの変更 |

### 変更しないもの

- `default_post_process_ids()` のロジック -- 推論固有のため維持
- `PassthroughPhonemizer` -- piper-core 固有のフォールバックとして維持
- piper-g2p の MultilingualPhonemizer -- 変更不要

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust 実装者 | 1 | multilingual.rs のリファクタリング、import 置換 |
| レビュアー | 1 | 言語検出の動作一致確認、残存コンポーネントの妥当性検証 |

## 提供範囲とテスト

### 提供範囲

- `multilingual.rs` の大幅リファクタリング (3コンポーネント削除)
- voice.rs の MultilingualPhonemizer 初期化コード更新
- 呼び出し元の import パス更新

### テスト項目

1. piper-g2p の MultilingualPhonemizer が JA+EN 混合テキストを正しくセグメント化すること
2. `default_post_process_ids()` が従来と同一の結果を返すこと
3. PassthroughPhonemizer が引き続き正常に動作すること
4. 全 8 言語の言語検出が正しく動作すること

### Unit テスト

```rust
#[test]
fn test_multilingual_ja_en_mixed_text() {
    // "こんにちはHello世界" を処理し、
    // JA/EN/JA の3セグメントに分割されることを確認
}

#[test]
fn test_default_post_process_ids_unchanged() {
    // default_post_process_ids() の出力が旧実装と一致すること
}

#[test]
fn test_passthrough_phonemizer_still_works() {
    // PassthroughPhonemizer が入力テキストをそのまま返すこと
}

#[test]
fn test_language_detection_all_8_languages() {
    // 8言語の代表テキストが正しく検出されること
}
```

### E2E テスト

- マルチリンガルモデルを使用した完全推論パイプラインテスト
- JA+EN 混合テキストの推論が正しい phoneme_ids を生成すること
- 既存の integration テスト全件パス

## 懸念事項とレビュー項目

### 懸念事項

1. **PassthroughPhonemizer の移行判断**: PassthroughPhonemizer を piper-g2p に移動するか piper-core に残すかの判断。piper-core 固有の型 (PiperError 等) に依存する場合は残す方が適切
2. **スウェーデン語検出の機能語リスト**: piper-g2p の UnicodeLanguageDetector がスウェーデン語の機能語リストを十分にカバーしているか確認する。piper-core 側で追加していた機能語があれば piper-g2p にマージする必要がある
3. **default_post_process_ids() の依存関係**: この関数が piper-core の他のモジュール (engine.rs 等) から参照されている場合、移動先に注意が必要
4. **piper-g2p の MultilingualPhonemizer の API 互換性**: piper-core の MultilingualPhonemizer と同一の初期化パラメータを受け付けるか確認する
5. **スウェーデン語検出の機能語リスト差異リスク**: スウェーデン語の機能語リスト (`refine_latin_segments_for_swedish()` 内) が piper-core と piper-g2p で同一であるか diff で確認すること。差異がある場合は piper-g2p 側にマージする。

### レビュー項目

1. 削除対象の 3 コンポーネントが正しく特定されていること
2. 残存させる `default_post_process_ids()` と `PassthroughPhonemizer` の配置が適切であること
3. スウェーデン語の機能語リストが piper-g2p 側で網羅されていること
4. multilingual.rs のファイルサイズが大幅に縮小されていること (~1000行 -> ~200行)
5. 未使用 import / dead code が残っていないこと

## 一から作り直すとしたら

`default_post_process_ids()` を Phonemizer トレイトのデフォルト実装として定義し、piper-g2p と piper-core の両方で共有する設計にする。PassthroughPhonemizer は piper-g2p に配置し、言語コードだけを保持する汎用的な実装にする。これにより multilingual.rs に残す必要のあるコードがほぼなくなる。

## 後続タスクへの連絡事項

- M2-7 (旧ファイル削除) で multilingual.rs 内の削除対象コードが既に除去済みであることを確認すること。multilingual.rs 自体は削除せず、リファクタリング後の縮小版を残す
- `default_post_process_ids()` の配置先を確定し、M2-7 の作業者に共有すること
- スウェーデン語の機能語リストに差異があった場合は、M0 チケットとして piper-g2p 側の修正を先行させること
