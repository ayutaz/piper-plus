# M2-3: voice.rs ファクトリ書き換え

> **マイルストーン**: M2
> **前提チケット**: M2-2
> **後続チケット**: M2-7
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/rust/piper-core/src/voice.rs` の `create_language_phonemizer()` ファクトリ関数を書き換え、piper-core 内蔵の言語別 phonemizer ではなく piper-g2p のコンストラクタ + G2pAdapter でラップした phonemizer を返すようにする。

**ゴール**: `Voice::new()` がマルチリンガル config を含む全てのケースで正常に動作し、音素化パイプラインが piper-g2p ベースに切り替わった状態。

## 実装する内容の詳細

### 変更箇所

**ファイル**: `src/rust/piper-core/src/voice.rs`

**注意**: 行番号は調査時点の参照値。実装時は以下で最新位置を確認:
- `grep -n "fn create_phonemizer\|fn create_language_phonemizer\|fn create_japanese_phonemizer\|fn create_english_phonemizer\|fn create_chinese_phonemizer" src/rust/piper-core/src/voice.rs`

### コンストラクタマッピング

`create_language_phonemizer()` 内の各言語のコンストラクタを以下のように書き換える:

| 言語 | 現在のコンストラクタ | 新しいコンストラクタ (piper-g2p) |
|------|--------------------|---------------------------------|
| ja | `JapanesePhonemizer::new(dict_path)` | `piper_plus_g2p::JapanesePhonemizer::new_bundled()` |
| en | `EnglishPhonemizer::new(dict_path)` | `piper_plus_g2p::EnglishPhonemizer::new_with_dict(&path)` |
| zh | `ChinesePhonemizer::new()` | `piper_plus_g2p::ChinesePhonemizer::new(&single, &phrases)` |
| es | `SpanishPhonemizer::new()` | `piper_plus_g2p::SpanishPhonemizer::new()` |
| fr | `FrenchPhonemizer::new()` | `piper_plus_g2p::FrenchPhonemizer::new()` |
| pt | `PortuguesePhonemizer::new()` | `piper_plus_g2p::PortuguesePhonemizer::new()` |
| ko | `KoreanPhonemizer::new()` | `piper_plus_g2p::KoreanPhonemizer::new()` |
| sv | `SwedishPhonemizer::new()` | `piper_plus_g2p::SwedishPhonemizer::new()` |

各コンストラクタの戻り値を `G2pAdapter::new()` でラップして返す。

### PassthroughPhonemizer フォールバック

辞書が見つからない場合等のフォールバックとして `PassthroughPhonemizer` を引き続き使用する。この phonemizer は piper-core 固有のものであり、piper-g2p には移行しない。

```rust
// 辞書パスが無効な場合のフォールバック例
match piper_plus_g2p::EnglishPhonemizer::new_with_dict(&path) {
    Ok(p) => Box::new(G2pAdapter::new(Box::new(p))),
    Err(_) => Box::new(PassthroughPhonemizer::new("en")),
}
```

### 変更しないもの

- `Voice::new()` の公開 API -- 変更不要
- `Voice` 構造体のフィールド -- 変更不要
- 推論パイプライン (`synthesize()` 等) -- phonemizer の内部実装が変わるだけ
- `PassthroughPhonemizer` -- piper-core に残存

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust 実装者 | 1 | voice.rs のファクトリ書き換え、各言語のコンストラクタ対応 |
| レビュアー | 1 | コンストラクタマッピングの正確性、フォールバックロジックの検証 |

## 提供範囲とテスト

### 提供範囲

- `src/rust/piper-core/src/voice.rs` の `create_language_phonemizer()` 書き換え

### テスト項目

1. 各言語で `create_language_phonemizer()` が正しい phonemizer を返すこと
2. フォールバック (PassthroughPhonemizer) が適切に動作すること
3. `Voice::new()` がマルチリンガル config で正常に動作すること

### Unit テスト

```rust
#[test]
fn test_factory_creates_japanese_phonemizer() { ... }
#[test]
fn test_factory_creates_english_phonemizer() { ... }
#[test]
fn test_factory_creates_chinese_phonemizer() { ... }
#[test]
fn test_factory_creates_spanish_phonemizer() { ... }
#[test]
fn test_factory_creates_french_phonemizer() { ... }
#[test]
fn test_factory_creates_portuguese_phonemizer() { ... }
#[test]
fn test_factory_creates_korean_phonemizer() { ... }
#[test]
fn test_factory_creates_swedish_phonemizer() { ... }
#[test]
fn test_factory_fallback_to_passthrough() { ... }
```

### E2E テスト

- `Voice::new()` に 6 言語マルチリンガル config を渡し、各言語のテキストを音素化して phoneme_ids が返ることを確認
- 既存の integration テスト (`tests/` 配下) が全てパスすること

## 懸念事項とレビュー項目

### 懸念事項

1. **中国語辞書パスの解決ロジック**: `piper_plus_g2p::ChinesePhonemizer::new(&single, &phrases)` は辞書ファイルのパスを要求する。現在の piper-core が辞書パスをどのように解決しているかを確認し、同等のロジックを維持する必要がある
2. **日本語辞書バンドリング**: `new_bundled()` は naist-jdic をバイナリに埋め込む。feature gate (`naist-jdic`) が無効の場合の動作を確認すること
3. **英語辞書パスの互換性**: piper-g2p の `new_with_dict(&path)` が期待する辞書フォーマットが piper-core の現行辞書と互換であることを確認する
4. **エラーハンドリングの変更**: 各コンストラクタのエラー型が変わるため、呼び出し元のエラーハンドリングが正しく動作するか確認する
5. **Error type mismatch**: piper-g2p コンストラクタは `Result<_, G2pError>` を返す。既存の `From<G2pError> for PiperError` 変換が全エラーバリアントをカバーしているか確認すること。

### レビュー項目

1. 全 8 言語のコンストラクタマッピングが正しいこと
2. PassthroughPhonemizer フォールバックが全言語で適切に設定されていること
3. 辞書パス解決ロジックが現行と同等であること
4. エラーメッセージが有用であること (辞書が見つからない場合等)
5. `Voice::new()` の公開 API が変更されていないこと

## 一から作り直すとしたら

`create_language_phonemizer()` をレジストリパターンで実装し、言語コードに基づいて自動的に適切な phonemizer を選択する設計にする。piper-g2p が `get_phonemizer(lang_code)` のようなファクトリ関数を公開し、piper-core はそれを呼ぶだけにすれば、voice.rs のファクトリロジックを大幅に簡素化できる。

## 後続タスクへの連絡事項

- M2-7 (旧ファイル削除) は、このチケットの完了後に voice.rs が旧 phonemizer (english.rs 等) を参照していないことが前提
- voice.rs から旧 phonemizer モジュールへの `use` 文が全て除去されていることを確認して共有すること
- 辞書パス解決ロジックに変更がある場合は、M2-8 (テスト・CI) に影響するため共有すること
