# M2-7: 旧 phonemize ファイル削除

> **マイルストーン**: M2
> **前提チケット**: M2-2, M2-3, M2-4, M2-5, M2-6
> **後続チケット**: M2-8, M4
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

M2-2 から M2-6 の完了により不要になった piper-core の旧 phonemize ファイル群を削除する。piper-g2p への移行が完了したモジュールのみを対象とし、piper-core 固有の機能を含むファイルは保持する。

**前提条件**: M2-2 から M2-6 が全て完了し、`cargo test` が全件パスしていること。

**ゴール**: `src/rust/piper-core/src/phonemize/` ディレクトリから旧言語別ファイルおよび統合済みモジュールが削除され、`cargo test`, `cargo clippy`, `cargo fmt` が全てパスする状態。

## 実装する内容の詳細

### 削除対象ファイル

`src/rust/piper-core/src/phonemize/` 配下:

| ファイル | 理由 |
|---------|------|
| `english.rs` | M2-3 で piper-g2p の EnglishPhonemizer に置換済み |
| `chinese.rs` | M2-3 で piper-g2p の ChinesePhonemizer に置換済み |
| `japanese.rs` | M2-3 で piper-g2p の JapanesePhonemizer に置換済み |
| `korean.rs` | M2-3 で piper-g2p の KoreanPhonemizer に置換済み |
| `spanish.rs` | M2-3 で piper-g2p の SpanishPhonemizer に置換済み |
| `french.rs` | M2-3 で piper-g2p の FrenchPhonemizer に置換済み |
| `portuguese.rs` | M2-3 で piper-g2p の PortuguesePhonemizer に置換済み |
| `swedish.rs` | M2-3 で piper-g2p の SwedishPhonemizer に置換済み |
| `custom_dict.rs` | M2-6 で piper-g2p の custom_dict に置換済み |
| `token_map.rs` | M2-4 で piper-g2p の encode モジュールに統合済み |
| `phoneme_converter.rs` | M2-4 で piper-g2p の encode モジュールに統合済み |

### 保持するファイル

| ファイル | 理由 |
|---------|------|
| `mod.rs` | adapter + Phonemizer トレイト定義を含む |
| `multilingual.rs` | M2-5 でリファクタリング済み (`default_post_process_ids()`, `PassthroughPhonemizer` を含む) |
| `adapter.rs` | M2-2 で新規作成した G2pAdapter |

### 変更手順

1. 削除前に `cargo test --workspace` が全件パスすることを確認
2. 対象 11 ファイルを削除
3. `mod.rs` から削除対象モジュールの `mod` 宣言と `pub use` を削除
4. `cargo test --workspace` が全件パスすることを確認
5. `cargo clippy --workspace` が警告なしでパスすることを確認
6. `cargo fmt --check` がパスすることを確認
7. 未使用 import が残っていないことを確認

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `english.rs`, `chinese.rs`, `japanese.rs`, `korean.rs`, `spanish.rs`, `french.rs`, `portuguese.rs`, `swedish.rs` | 削除 |
| `custom_dict.rs`, `token_map.rs`, `phoneme_converter.rs` | 削除 |
| `mod.rs` | 削除モジュールの `mod` 宣言・`pub use` を除去 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | ファイル削除、mod.rs 更新、未使用 import の除去 |
| CI 検証者 | 1 | 全テスト・clippy・fmt のパス確認 |

## 提供範囲とテスト

### 提供範囲

- 11 ファイルの削除
- `mod.rs` の更新
- 未使用 import の除去

### テスト項目

1. `cargo test --workspace` が全件パスすること
2. `cargo clippy --workspace` が警告なしでパスすること
3. `cargo fmt --check` がパスすること
4. 削除したモジュールへの参照が一切残っていないこと

### Unit テスト

- 新規テストは不要。既存テストの全件パスが確認対象
- 削除前に `grep -rn "phoneme_converter\|phonemize::english\|phonemize::chinese\|phonemize::japanese" src/rust/piper-core/tests/` で依存テストを特定し、import パスを更新または削除すること。特に `test_phoneme_converter.rs` は `phoneme_converter.rs` 削除時に破壊される可能性が高い。

### E2E テスト

- 既存の全 24 integration テストファイルがパスすること
- CLI バイナリのビルドと基本動作確認

## 懸念事項とレビュー項目

### 懸念事項

1. **参照の残存**: 削除対象ファイル内の型・関数を `pub use` で再エクスポートしている箇所が mod.rs 以外にも存在する可能性がある。削除前に `grep -r` で全参照を洗い出すこと
2. **テストファイルからの参照**: `tests/` 配下のテストファイルが削除対象モジュールを直接 import している場合、テストの更新が必要
3. **ドキュメントコメントのリンク**: `///` ドキュメントコメント内で削除対象モジュールへのリンク (`[english::EnglishPhonemizer]` 等) がある場合、リンク切れになる
4. **外部クレートからの依存**: `piper-cli` や `piper-python` が `piper-core::phonemize::english` 等を直接参照している場合、それらの更新も必要

### レビュー項目

1. 削除対象 11 ファイルが正しいこと (保持すべきファイルを誤って削除していないこと)
2. `mod.rs` から削除対象の全 `mod` 宣言と `pub use` が除去されていること
3. ワークスペース全体で未使用 import が残っていないこと
4. `cargo test`, `cargo clippy`, `cargo fmt` が全てパスすること
5. 削除により外部クレート (`piper-cli`, `piper-python`) のビルドが壊れていないこと

## 一から作り直すとしたら

piper-core に言語別 phonemizer ファイルを最初から配置せず、piper-g2p を唯一の G2P 実装として設計していれば、この削除作業は不要だった。ただし、段階的移行のために旧実装を並行維持した判断は正しく、移行中のテスト安全性が確保された。

## 後続タスクへの連絡事項

- M2-8 (テスト・CI 対応) は、このチケットの完了後に CI マトリクスが全てグリーンであることを前提とする
- M4 以降のチケットは、`src/rust/piper-core/src/phonemize/` に `mod.rs`, `adapter.rs`, `multilingual.rs` の 3 ファイルのみが存在することを前提とする
- 削除によりコード行数が大幅に減少する。コミットメッセージに削除行数を記載すること (変更の規模を明確にするため)
