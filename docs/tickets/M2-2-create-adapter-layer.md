# M2-2: adapter 層の作成

> **マイルストーン**: M2
> **前提チケット**: M0-4, M2-1
> **後続チケット**: M2-3, M2-5
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/rust/piper-core/src/phonemize/adapter.rs` を新規作成し、piper-g2p の `Box<dyn piper_plus_g2p::Phonemizer>` を piper-core の Phonemizer トレイトでラップする `G2pAdapter` 構造体を実装する。

piper-core の Phonemizer トレイトと piper-g2p の Phonemizer トレイトはインターフェースが異なるため、adapter パターンで橋渡しする。これにより、piper-core の既存コードは piper-g2p の実装詳細を意識することなく、統一的な Phonemizer インターフェースを使用できる。

**ゴール**: G2pAdapter が piper-core の Phonemizer トレイトを正しく実装し、piper-g2p の全言語 Phonemizer を piper-core 内で使用可能にする。

## 実装する内容の詳細

### 新規ファイル

**ファイル**: `src/rust/piper-core/src/phonemize/adapter.rs`

### G2pAdapter 構造体

```rust
pub struct G2pAdapter {
    inner: Box<dyn piper_plus_g2p::Phonemizer>,
}
```

### Phonemizer トレイト実装

piper-core の Phonemizer トレイトの各メソッドを以下のように実装する:

| メソッド | 実装方針 |
|---------|---------|
| `phonemize_with_prosody()` | `inner` に委譲 + エラー型変換 (`G2pError` -> `PiperError`) |
| `get_phoneme_id_map()` | 常に `None` を返す (piper-core の全 phonemizer が `None` を返す設計) |
| `post_process_ids()` | `inner` の `default_post_process_ids()` に委譲 |
| `language_code()` | `inner` に委譲 |

### 日本語 adapter の特殊処理

日本語 Phonemizer は `post_process_ids()` で特殊な EOS 処理 (動的 EOS) が必要なため、以下のいずれかで対応する:

- **案 A**: `G2pAdapter` 内で `language_code() == "ja"` を判定し、`post_process_ids()` を no-op にする (EOS 処理は piper-g2p 側の `phonemize_with_prosody()` で完了済み)
- **案 B**: `G2pJapaneseAdapter` を別途定義し、`post_process_ids()` をオーバーライドする

実装時に piper-g2p 側の日本語 EOS 処理の実装を確認し、適切な案を選択する。

### エラー型変換

```rust
impl From<piper_plus_g2p::G2pError> for PiperError {
    fn from(e: piper_plus_g2p::G2pError) -> Self {
        PiperError::PhonemizeError(e.to_string())
    }
}
```

既存の `From<G2pError> for PiperError` 実装がある場合はそれを利用する。

### 変更しないもの

- piper-core の Phonemizer トレイト定義 -- 変更不要
- piper-g2p のソースコード -- 変更不要
- 既存の言語別 phonemizer (english.rs 等) -- M2-7 まで残存

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust 実装者 | 1 | G2pAdapter の設計・実装、テスト作成 |
| レビュアー | 1 | トレイト整合性の検証、エラー変換の妥当性確認 |

## 提供範囲とテスト

### 提供範囲

- `src/rust/piper-core/src/phonemize/adapter.rs` (新規)
- `src/rust/piper-core/src/phonemize/mod.rs` (adapter モジュールの追加)

### テスト項目

1. G2pAdapter が piper-core の Phonemizer トレイトを実装していること
2. 各トレイトメソッドが正しく委譲されること
3. エラー型変換が正しく行われること
4. 日本語 adapter の `post_process_ids()` が正しく動作すること

### Unit テスト

```rust
#[cfg(test)]
mod tests {
    // モック Phonemizer を使用した G2pAdapter のテスト
    fn test_adapter_phonemize_with_prosody() { ... }
    fn test_adapter_get_phoneme_id_map_returns_none() { ... }
    fn test_adapter_post_process_ids_delegates() { ... }
    fn test_adapter_language_code_delegates() { ... }
    fn test_adapter_error_conversion() { ... }
    fn test_japanese_adapter_post_process_ids() { ... }
}
```

### E2E テスト

- G2pAdapter 経由で日本語テキスト「こんにちは」を音素化し、期待される phoneme_ids が返ることを確認
- G2pAdapter 経由で英語テキスト "Hello" を音素化し、期待される phoneme_ids が返ることを確認

## 懸念事項とレビュー項目

### 懸念事項

1. **エラー型変換の情報損失**: `G2pError` -> `PiperError` の変換で元のエラー情報 (スタックトレース等) が失われる可能性がある。`PiperError` に十分な情報を保持する設計が必要
2. **日本語の動的 EOS**: piper-g2p 側の日本語 Phonemizer が EOS を出力に含めるか否かで adapter の `post_process_ids()` の実装が変わる。piper-g2p の実装を事前に確認すること
3. **trait object の制約**: `Box<dyn piper_plus_g2p::Phonemizer>` が `Send + Sync` を満たすかの確認。マルチスレッド環境 (推論サーバー等) で問題になる可能性
4. **Send+Sync bounds の全言語検証**: `Box<dyn piper_plus_g2p::Phonemizer>` が Send+Sync を満たすことを全言語モジュールで確認すること。piper-g2p の Phonemizer trait は `Send + Sync` を要求しているが、各言語実装が内部状態で non-Send 型を使っていないか検証が必要。
5. **パフォーマンスオーバーヘッド**: adapter 層による間接呼び出しのコスト。音素化は推論パイプライン全体の中では軽量な処理のため、実質的な影響はないと予想

### レビュー項目

1. piper-core の Phonemizer トレイトの全メソッドが正しく実装されていること
2. エラー型変換で情報が十分に保持されていること
3. 日本語 adapter の `post_process_ids()` が正しい方式 (案 A or B) で実装されていること
4. `Send + Sync` の要件を満たしていること
5. adapter.rs が `mod.rs` に正しく登録されていること

## 一から作り直すとしたら

piper-core と piper-g2p の Phonemizer トレイトを最初から統一設計していれば、adapter 層は不要だった。具体的には:

- `get_phoneme_id_map()` を Phonemizer トレイトから除外し、別のトレイトに分離する
- `post_process_ids()` のデフォルト実装を共通トレイトに定義する
- エラー型を共通化する

ただし、piper-g2p を独立パッケージとして設計する以上、piper-core 固有の型 (SynthesisRequest 等) への依存は避けるべきであり、adapter パターンは妥当な選択である。

## 後続タスクへの連絡事項

- M2-3 (voice.rs ファクトリ書き換え) は G2pAdapter のコンストラクタを使用して phonemizer を生成する。コンストラクタの API (`G2pAdapter::new(inner)`) を確定させて共有すること
- M2-5 (MultilingualPhonemizer 統合) は G2pAdapter を内部で使用する可能性がある。adapter の公開インターフェースを確定させること
- 日本語 adapter の `post_process_ids()` の最終的な実装方式 (案 A or B) を共有すること
