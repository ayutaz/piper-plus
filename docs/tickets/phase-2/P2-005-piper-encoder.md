# [P2-005] PiperEncoder (PUA + ID 変換)

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: FR-200
> 依存チケット: P2-001, P2-002, P2-003, P2-004
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-core/src/phonemize/phoneme_converter.rs` の G2P エンコード関数 (`tokens_to_ids()`, `prosody_to_features()`) を `piper-g2p` に移動する。推論リクエスト構築 (`build_synthesis_request()`) は piper-core に残す (P2-006 でリネーム)。これにより、IPA トークン列 -> phoneme_ids 変換が `piper-g2p` 単体で完結する。

### ゴール
- `piper_g2p::encode::tokens_to_ids()` と `piper_g2p::encode::prosody_to_features()` が公開されている
- `piper_g2p::encode::default_post_process_ids()` が公開されている (BOS/EOS/パディング挿入)
- `piper-core` の `phoneme_converter.rs` からエンコード関数が削除されている (残るのは `build_synthesis_request()` のみ)
- `build_synthesis_request()` は内部で `piper_g2p::encode::tokens_to_ids()` を呼び出すように変更されている
- 既存テストが全て通過する

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/src/encode.rs` | 新規 | `tokens_to_ids()`, `prosody_to_features()`, `default_post_process_ids()` |
| `src/rust/piper-g2p/src/lib.rs` | 変更 | `pub mod encode;` 追加 |
| `src/rust/piper-core/src/phonemize/phoneme_converter.rs` | 変更 | エンコード関数を削除、`piper_g2p::encode` を使用 |

### 実装手順

1. **`piper-g2p/src/encode.rs` 作成**
   ```rust
   //! Piper TTS 向けエンコード関数。
   //!
   //! IPA トークン列を phoneme_ids に変換する。
   //! Phonemizer trait とは独立しており、任意の IPA トークン列に対して使用可能。

   use crate::error::G2pError;
   use crate::phonemizer::ProsodyFeature;
   use crate::phonemizer::ProsodyInfo;
   use crate::types::PhonemeIdMap;

   /// IPA トークン列を phoneme ID に変換する。
   ///
   /// 各トークンを `phoneme_id_map` で引いて整数 ID 列を生成する。
   /// マッピングに存在しないトークンは `G2pError::PhonemeIdNotFound` を返す。
   pub fn tokens_to_ids(
       tokens: &[String],
       phoneme_id_map: &PhonemeIdMap,
   ) -> Result<Vec<i64>, G2pError> {
       let mut ids = Vec::with_capacity(tokens.len() * 2);
       for token in tokens {
           match phoneme_id_map.get(token) {
               Some(id_list) => ids.extend(id_list.iter().copied()),
               None => {
                   return Err(G2pError::PhonemeIdNotFound {
                       phoneme: token.clone(),
                   });
               }
           }
       }
       Ok(ids)
   }

   /// プロソディ情報列をプロソディ特徴量配列に変換する。
   ///
   /// 各 `ProsodyInfo` は `[a1, a2, a3]` に変換される。
   /// `None` は `[0, 0, 0]` になる。
   pub fn prosody_to_features(prosody: &[Option<ProsodyInfo>]) -> Vec<ProsodyFeature> {
       prosody
           .iter()
           .map(|p| match p {
               Some(info) => [info.a1, info.a2, info.a3],
               None => [0, 0, 0],
           })
           .collect()
   }

   /// BOS/EOS/パディング挿入 (EN/ZH/KO/ES/PT/FR 共通)。
   ///
   /// multilingual.rs の `default_post_process_ids()` を移動したもの。
   /// JA は独自の post_process を持つため、この関数は使用しない。
   pub fn default_post_process_ids(
       ids: Vec<i64>,
       prosody: Vec<Option<ProsodyFeature>>,
       id_map: &PhonemeIdMap,
   ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
       // BOS (^) の ID を取得
       let bos_id = id_map.get("^").and_then(|v| v.first().copied()).unwrap_or(1);
       // EOS ($) の ID を取得
       let eos_id = id_map.get("$").and_then(|v| v.first().copied()).unwrap_or(2);
       // パディング (_) の ID を取得
       let pad_id = id_map.get("_").and_then(|v| v.first().copied()).unwrap_or(0);

       let mut result_ids = Vec::with_capacity(ids.len() * 2 + 2);
       let mut result_prosody = Vec::with_capacity(ids.len() * 2 + 2);

       // BOS
       result_ids.push(bos_id);
       result_prosody.push(None);

       for (i, id) in ids.iter().enumerate() {
           // パディング挿入
           if i > 0 {
               result_ids.push(pad_id);
               result_prosody.push(None);
           }
           result_ids.push(*id);
           result_prosody.push(prosody.get(i).cloned().flatten().map(Some).unwrap_or(None));
       }

       // EOS
       result_ids.push(pad_id);
       result_prosody.push(None);
       result_ids.push(eos_id);
       result_prosody.push(None);

       (result_ids, result_prosody)
   }
   ```

2. **`piper-g2p/src/lib.rs` 更新**
   ```rust
   pub mod encode;
   pub mod error;
   pub mod phonemizer;
   pub mod types;
   // ... (P2-004 で追加された言語モジュール)
   ```

3. **`piper-core/src/phonemize/phoneme_converter.rs` の更新**
   `tokens_to_ids()` と `prosody_to_features()` を削除し、`build_synthesis_request()` 内で `piper_g2p::encode::tokens_to_ids()` を使用するように変更:
   ```rust
   // 変更前
   use crate::config::PhonemeIdMap;
   use crate::error::PiperError;

   pub fn tokens_to_ids(...) -> Result<Vec<i64>, PiperError> { ... }
   pub fn prosody_to_features(...) -> Vec<ProsodyFeature> { ... }
   pub fn build_synthesis_request(...) -> Result<SynthesisRequest, PiperError> {
       let ids = tokens_to_ids(tokens, phoneme_id_map)?;
       let features = prosody_to_features(prosody);
       ...
   }

   // 変更後
   pub fn build_synthesis_request(...) -> Result<SynthesisRequest, PiperError> {
       let ids = piper_g2p::encode::tokens_to_ids(tokens, phoneme_id_map)?;
       let features = piper_g2p::encode::prosody_to_features(prosody);
       ...
   }
   ```
   `G2pError` -> `PiperError` の変換は `From` トレイト (P2-002) により `?` 演算子で自動的に行われる。

4. **既存テストの移動**
   `phoneme_converter.rs` 内の `#[cfg(test)]` モジュール (`test_basic_token_to_id`, `test_prosody_conversion` 等) を `piper-g2p/src/encode.rs` に移動する。

### API / インターフェース

```rust
use piper_g2p::encode::{tokens_to_ids, prosody_to_features, default_post_process_ids};
use piper_g2p::PhonemeIdMap;

let phoneme_id_map: PhonemeIdMap = load_from_config()?;
let ids = tokens_to_ids(&tokens, &phoneme_id_map)?;
let features = prosody_to_features(&prosody);
let (processed_ids, processed_prosody) = default_post_process_ids(ids, features_opt, &phoneme_id_map);
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | encode モジュール作成、phoneme_converter.rs 分割、テスト移動 |

---

## 4. テスト計画

### 提供範囲
エンコード関数の単体テスト。piper-core 経由での結合テスト。

### Unit テスト

移動元 (`phoneme_converter.rs`) の既存テスト 7 件を全て移動:
- `test_basic_token_to_id`: 基本的なトークン -> ID 変換
- `test_pua_character_conversion`: PUA 文字の変換
- `test_unknown_phoneme_error`: 未知トークンのエラー
- `test_prosody_conversion`: プロソディ -> 特徴量変換
- `test_build_synthesis_request`: リクエスト構築 (piper-core 側に残す)
- `test_multi_id_mapping`: 複数 ID マッピング
- `test_empty_tokens`: 空トークン列

追加テスト:
- `test_default_post_process_ids_bos_eos`: BOS/EOS 挿入の検証
- `test_default_post_process_ids_padding`: パディング挿入の検証

### E2E テスト
```bash
cargo test -p piper-g2p --all-features
cargo test -p piper-plus  # piper-core 側のテスト (build_synthesis_request)
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **`default_post_process_ids()` のロジック正確性**: P2-004 で各言語から trait メソッドとして削除された `post_process_ids()` のロジックをここに集約する。JA は独自の post_process を持つため、この共通関数は EN/ZH/KO/ES/PT/FR 用。JA の post_process ロジックは `japanese.rs` 内の private 関数として残す。
- **型の再利用**: `tokens_to_ids()` の `PhonemeIdMap` 引数は `piper_g2p::PhonemeIdMap` 型を使用する。piper-core 側の `config::PhonemeIdMap` は P2-007 で re-export に切り替わるため、実質的に同一の型になる。ただし P2-007 完了前は 2 つの同一型定義が存在する過渡期がある。
- **`build_synthesis_request` の残留テスト**: `test_build_synthesis_request` は `SynthesisRequest` 型 (piper-core 固有) に依存するため、piper-core 側に残す。

### レビュー項目
- `tokens_to_ids()` のエラー型が `G2pError::PhonemeIdNotFound` であること
- `prosody_to_features()` の None -> `[0, 0, 0]` 変換が正しいこと
- `build_synthesis_request()` が `piper_g2p::encode` を使用していること
- 既存テストが全て通過すること

---

## 6. 一から作り直すとしたら

- `encode` モジュールを `PiperEncoder` struct として実装する案 (Python Phase 1 の `PiperEncoder` クラスに合わせて)。Rust では関数ベースの API がイディオマティックであり、state を持たない処理には struct 化のメリットが少ない。`PhonemeIdMap` を保持する struct にする場合は `encode::Encoder::new(phoneme_id_map).encode(tokens)` のような API になるが、使用側の利便性が下がるため、関数ベースを採用する。

---

## 7. 後続タスクへの連絡事項

- **P2-006**: `phoneme_converter.rs` に残った `build_synthesis_request()` を `request_builder.rs` にリネームする。この関数は内部で `piper_g2p::encode::tokens_to_ids()` を呼び出す。
- **P2-007**: piper-core の re-export に `tokens_to_ids`, `prosody_to_features` を含める。既存コードが `piper_plus::phonemize::phoneme_converter::tokens_to_ids()` で参照している場合は re-export でカバーする。
