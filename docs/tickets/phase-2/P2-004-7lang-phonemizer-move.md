# [P2-004] 7 言語 Phonemizer 移動

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: FR-202
> 依存チケット: P2-001, P2-002, P2-003
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-core/src/phonemize/` にある 7 言語の Phonemizer 実装、PUA トークンマップ、カスタム辞書、多言語 Phonemizer を `piper-g2p/src/` に移動する。移動に伴い、各ファイルのエラー型を `PiperError` から `G2pError` に変更し、`get_phoneme_id_map()` / `post_process_ids()` を trait 実装から除去する。

### ゴール
- `piper-g2p/src/` に以下のファイルが配置されている: `japanese.rs`, `english.rs`, `chinese.rs`, `korean.rs`, `spanish.rs`, `french.rs`, `portuguese.rs`, `multilingual.rs`, `token_map.rs`, `custom_dict.rs`
- 全 Phonemizer が `piper_g2p::Phonemizer` trait を実装し、エラー型は `G2pError`
- JA は `#[cfg(feature = "japanese")]` で条件付きコンパイル
- PUA トークンマップ (87 エントリ) が `piper-g2p` に含まれる
- カスタム辞書 (JSON v1.0/v2.0) が `piper-g2p` に含まれる
- `MultilingualPhonemizer` と `UnicodeLanguageDetector` が `piper-g2p` に含まれる
- `piper-core/src/phonemize/` のこれらのファイルは削除される (P2-007 の re-export で後方互換性を維持)

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/src/japanese.rs` | 新規 (移動) | JapanesePhonemizer |
| `src/rust/piper-g2p/src/english.rs` | 新規 (移動) | EnglishPhonemizer |
| `src/rust/piper-g2p/src/chinese.rs` | 新規 (移動) | ChinesePhonemizer |
| `src/rust/piper-g2p/src/korean.rs` | 新規 (移動) | KoreanPhonemizer |
| `src/rust/piper-g2p/src/spanish.rs` | 新規 (移動) | SpanishPhonemizer |
| `src/rust/piper-g2p/src/french.rs` | 新規 (移動) | FrenchPhonemizer |
| `src/rust/piper-g2p/src/portuguese.rs` | 新規 (移動) | PortuguesePhonemizer |
| `src/rust/piper-g2p/src/multilingual.rs` | 新規 (移動) | MultilingualPhonemizer + UnicodeLanguageDetector |
| `src/rust/piper-g2p/src/token_map.rs` | 新規 (移動) | PUA トークンマップ (87 エントリ) |
| `src/rust/piper-g2p/src/custom_dict.rs` | 新規 (移動) | カスタム辞書 (JSON v1.0/v2.0) |
| `src/rust/piper-g2p/src/lib.rs` | 変更 | 全モジュール宣言 + re-export |
| `src/rust/piper-core/src/phonemize/*.rs` | 削除 | 移動元ファイル削除 (mod.rs は P2-007 で re-export 用に残す) |

### 実装手順

1. **ファイル移動** (git mv で履歴保持)
   ```bash
   cd src/rust
   # 7 言語 + multilingual + token_map + custom_dict
   git mv piper-core/src/phonemize/japanese.rs piper-g2p/src/japanese.rs
   git mv piper-core/src/phonemize/english.rs piper-g2p/src/english.rs
   git mv piper-core/src/phonemize/chinese.rs piper-g2p/src/chinese.rs
   git mv piper-core/src/phonemize/korean.rs piper-g2p/src/korean.rs
   git mv piper-core/src/phonemize/spanish.rs piper-g2p/src/spanish.rs
   git mv piper-core/src/phonemize/french.rs piper-g2p/src/french.rs
   git mv piper-core/src/phonemize/portuguese.rs piper-g2p/src/portuguese.rs
   git mv piper-core/src/phonemize/multilingual.rs piper-g2p/src/multilingual.rs
   git mv piper-core/src/phonemize/token_map.rs piper-g2p/src/token_map.rs
   git mv piper-core/src/phonemize/custom_dict.rs piper-g2p/src/custom_dict.rs
   ```

2. **各ファイルの `use` パス変更** (全ファイル共通)
   ```rust
   // 変更前
   use crate::config::PhonemeIdMap;
   use crate::error::PiperError;
   use super::{Phonemizer, ProsodyFeature, ProsodyInfo};

   // 変更後
   use crate::error::G2pError;
   use crate::phonemizer::{Phonemizer, ProsodyFeature, ProsodyInfo};
   use crate::types::PhonemeIdMap;
   ```

3. **trait impl の変更** (全 7 言語 + multilingual 共通)
   ```rust
   // 変更前
   impl Phonemizer for XxxPhonemizer {
       fn phonemize_with_prosody(&self, text: &str)
           -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> { ... }
       fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> { ... }
       fn post_process_ids(&self, ids: Vec<i64>, ...) -> (...) { ... }
   }

   // 変更後
   impl Phonemizer for XxxPhonemizer {
       fn phonemize_with_prosody(&self, text: &str)
           -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> { ... }
       fn language_code(&self) -> &str { "xx" }
   }
   ```
   `get_phoneme_id_map()` と `post_process_ids()` のロジックは一旦各ファイル内に private 関数として残す (P2-005 で PiperEncoder に統合予定)。

4. **custom_dict.rs のエラー型変更**
   ```rust
   // 変更前: PiperError::DictionaryLoad
   // 変更後: G2pError::DictionaryLoad
   ```

5. **multilingual.rs の `default_post_process_ids()` 処理**
   `default_post_process_ids()` は EN/ZH/KO/ES/PT/FR の `post_process_ids()` から呼ばれていた。trait からは削除されるが、関数自体は `piper-g2p` 内の public 関数として残す (P2-005 の PiperEncoder が利用するため)。

6. **feature flag による条件付きコンパイル**
   ```rust
   // piper-g2p/src/lib.rs
   #[cfg(feature = "japanese")]
   pub mod japanese;
   #[cfg(feature = "english")]
   pub mod english;
   #[cfg(feature = "chinese")]
   pub mod chinese;
   #[cfg(feature = "korean")]
   pub mod korean;
   #[cfg(feature = "spanish")]
   pub mod spanish;
   #[cfg(feature = "french")]
   pub mod french;
   #[cfg(feature = "portuguese")]
   pub mod portuguese;
   pub mod multilingual;
   pub mod token_map;
   pub mod custom_dict;
   ```

7. **英語 CMU 辞書データファイルの移動**
   `english.rs` が参照する `cmudict_data.json` (組み込みデータ) の `include_str!` パスを更新する。

### API / インターフェース

```rust
use piper_g2p::japanese::JapanesePhonemizer;
use piper_g2p::english::EnglishPhonemizer;
use piper_g2p::multilingual::MultilingualPhonemizer;
use piper_g2p::token_map::{token_to_pua, FIXED_PUA_MAP};
use piper_g2p::custom_dict::CustomDictionary;

let ja = JapanesePhonemizer::new()?;  // naist-jdic feature 必要
let (tokens, prosody) = ja.phonemize_with_prosody("こんにちは")?;
// tokens: ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a", ...]
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 2 | ファイル移動 + use パス変更 (1名)、trait impl 更新 + テスト修正 (1名) |

---

## 4. テスト計画

### 提供範囲
移動後の全 Phonemizer の動作確認。既存テストの移動・修正。

### Unit テスト
各言語ファイルの既存 `#[cfg(test)]` テストを移動し、`use` パスを修正する。

- JA: 栗原法韻律マーカー、N 音素変異 4 パターン、疑問詞マーカー
- EN: ARPAbet-to-IPA 変換、機能語ストレス除去、OOV 形態素フォールバック
- ZH: ピンイン変換、声調マーカー
- KO: 韓国語音韻規則
- ES: ルールベース変換
- FR: 鼻母音、リエゾン
- PT: ルールベース変換
- multilingual: UnicodeLanguageDetector、セグメント分割、コードスイッチング
- token_map: 87 エントリ一致、衝突なし
- custom_dict: JSON v1.0/v2.0 ロード、longest-match-first

### E2E テスト
```bash
# 全言語のテスト実行
cargo test -p piper-g2p --all-features

# 個別言語
cargo test -p piper-g2p --features japanese
cargo test -p piper-g2p --features english
cargo test -p piper-g2p --no-default-features --features chinese

# feature なしでもコンパイル可能
cargo build -p piper-g2p --no-default-features
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **git mv による差分の大きさ**: 12 ファイル x 数百 LOC = 大量の差分が発生する。PR レビューの負荷が高い。ファイル移動のコミットと内容変更のコミットを分離することでレビューしやすくする。
- **`include_str!` パスの更新**: `english.rs` の CMU 辞書 JSON は `include_str!("../../data/cmudict_data.json")` のような相対パスで参照されている可能性がある。ファイル移動後にパスが壊れないか確認が必要。
- **`default_post_process_ids()` の扱い**: この関数は trait メソッドではなくなるが、piper-core の request_builder (P2-006) から呼ばれる。`piper-g2p` の pub 関数として残すか、P2-005 の PiperEncoder に統合するかを決める必要がある。本チケットでは pub 関数として残し、P2-005/P2-006 で最終配置を決定する。
- **EN OOV が無音になる既知制限 (KL-200)**: 移動時にこの制限は変わらない。CMUdict 未収録語は引き続き無音になる。doc comment に既知制限として明記する。

### レビュー項目
- 全ファイルの `use crate::error::PiperError` が `G2pError` に変更されていること
- `get_phoneme_id_map()` と `post_process_ids()` が trait impl から除去されていること
- `language_code()` が全 7 言語 + multilingual で正しく実装されていること
- JA の `#[cfg(feature = "japanese")]` が正しく適用されていること
- PUA トークンマップが 87 エントリで Python 実装と完全一致すること
- `cargo test -p piper-g2p --all-features` が全テスト通過すること

---

## 6. 一から作り直すとしたら

- 各言語を独立 crate (`piper-g2p-ja`, `piper-g2p-en`, ...) にして feature flag の代わりに crate 分離で制御する案。メンテナンスコストが増大するため、feature flag 方式が妥当。
- `english.rs` の CMU 辞書 JSON をバイナリクレートとして分離し、`piper-g2p-cmudict` として公開する案。辞書サイズ (~1.5MB) は crate.io の 10MB 制限内に収まるため、現状は `include_str!` 組み込みで十分。

---

## 7. 後続タスクへの連絡事項

- **P2-005**: `tokens_to_ids()` と `prosody_to_features()` はこのチケットでは移動しない (`phoneme_converter.rs` に残る)。P2-005 で piper-g2p に移動する。
- **P2-006**: `build_synthesis_request()` も同様にこのチケットでは移動しない。P2-006 で piper-core 側のリネームを行う。
- **P2-007**: piper-core の `src/phonemize/mod.rs` はこのチケットで言語ファイルの `pub mod` 宣言を削除する。P2-007 で `pub use piper_g2p::*;` による re-export に差し替える。
- **P2-008**: jpreprocess 互換性テストは `piper-g2p` の `japanese.rs` を対象とする。このチケットで移動済みであることが前提。
