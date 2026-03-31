# [P2-002] G2pError + PhonemeIdMap 再定義

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: FR-201
> 依存チケット: P2-001
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` crate が `piper-core` の型に一切依存しないようにするため、G2P 固有のエラー型 `G2pError` と型エイリアス `PhonemeIdMap` を `piper-g2p` 内に新規定義する。piper-core 側には `From<G2pError> for PiperError` の変換トレイトを実装し、既存コードがシームレスに `?` 演算子で G2P エラーを伝播できるようにする。

### ゴール
- `use piper_g2p::{G2pError, PhonemeIdMap}` でインポートできる
- `G2pError` は 6 バリアント (`UnsupportedLanguage`, `Phonemize`, `DictionaryLoad`, `JPreprocessInit`, `LabelParse`, `PhonemeIdNotFound`) を持つ
- `PhonemeIdMap = HashMap<String, Vec<i64>>` が `piper-g2p` で再定義されている
- `piper-core` に `impl From<G2pError> for PiperError` が実装されている
- `piper-g2p` は `piper-core` のどの型にも依存していない

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/src/error.rs` | 新規 | `G2pError` 定義 |
| `src/rust/piper-g2p/src/types.rs` | 新規 | `PhonemeIdMap` 型エイリアス |
| `src/rust/piper-g2p/src/lib.rs` | 変更 | `pub mod error; pub mod types;` + re-export |
| `src/rust/piper-core/src/error.rs` | 変更 | `impl From<G2pError> for PiperError` 追加 |

### 実装手順

1. **`piper-g2p/src/error.rs` 作成**
   ```rust
   //! G2P 固有エラー型。

   use thiserror::Error;

   /// G2P 処理で発生するエラー。
   ///
   /// `piper-core` の `PiperError` とは独立した型。
   /// `impl From<G2pError> for PiperError` により自動変換可能。
   #[derive(Error, Debug)]
   pub enum G2pError {
       #[error("unsupported language: {code}")]
       UnsupportedLanguage { code: String },

       #[error("phonemization error: {0}")]
       Phonemize(String),

       #[error("dictionary load error: {path}")]
       DictionaryLoad { path: String },

       #[error("jpreprocess initialization error: {0}")]
       JPreprocessInit(String),

       #[error("label parse error: {0}")]
       LabelParse(String),

       #[error("phoneme ID not found: {phoneme}")]
       PhonemeIdNotFound { phoneme: String },
   }
   ```

2. **`piper-g2p/src/types.rs` 作成**
   ```rust
   //! G2P 共有型定義。

   use std::collections::HashMap;

   /// 音素 -> ID のマッピング (config.json 由来)。
   ///
   /// キー: 音素トークン文字列 (1 文字、PUA 含む)
   /// 値: phoneme ID のリスト (通常 1 要素だが複数の場合あり)
   pub type PhonemeIdMap = HashMap<String, Vec<i64>>;
   ```

3. **`piper-g2p/src/lib.rs` 更新**
   ```rust
   //! piper-g2p: Multilingual G2P (Grapheme-to-Phoneme) for TTS.
   //!
   //! 7 languages (JA, EN, ZH, KO, ES, FR, PT), IPA-first output,
   //! no eSpeak-ng dependency. MIT licensed.

   pub mod error;
   pub mod types;

   pub use error::G2pError;
   pub use types::PhonemeIdMap;
   ```

4. **`piper-core/src/error.rs` に変換トレイト追加**
   ```rust
   impl From<piper_g2p::G2pError> for PiperError {
       fn from(e: piper_g2p::G2pError) -> Self {
           match e {
               piper_g2p::G2pError::UnsupportedLanguage { code } => {
                   PiperError::UnsupportedLanguage { code }
               }
               piper_g2p::G2pError::Phonemize(msg) => PiperError::Phonemize(msg),
               piper_g2p::G2pError::DictionaryLoad { path } => {
                   PiperError::DictionaryLoad { path }
               }
               piper_g2p::G2pError::JPreprocessInit(msg) => PiperError::JPreprocessInit(msg),
               piper_g2p::G2pError::LabelParse(msg) => PiperError::LabelParse(msg),
               piper_g2p::G2pError::PhonemeIdNotFound { phoneme } => {
                   PiperError::PhonemeIdNotFound { phoneme }
               }
           }
       }
   }
   ```

### API / インターフェース

```rust
// piper-g2p ユーザー向け
use piper_g2p::{G2pError, PhonemeIdMap};

// piper-core 内での自動変換
fn example() -> Result<(), PiperError> {
    let result = some_g2p_function()?;  // G2pError -> PiperError 自動変換
    Ok(())
}
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | エラー型定義、型エイリアス定義、From トレイト実装 |

---

## 4. テスト計画

### 提供範囲
型定義の正当性とエラー変換の動作確認。

### Unit テスト

```rust
// piper-g2p/src/error.rs
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_g2p_error_display() {
        let e = G2pError::UnsupportedLanguage { code: "xx".into() };
        assert!(format!("{e}").contains("xx"));
    }

    #[test]
    fn test_phoneme_id_not_found_display() {
        let e = G2pError::PhonemeIdNotFound { phoneme: "Z".into() };
        assert!(format!("{e}").contains("Z"));
    }
}

// piper-core/src/error.rs
#[test]
fn test_g2p_error_to_piper_error() {
    let g2p_err = piper_g2p::G2pError::Phonemize("test".into());
    let piper_err: PiperError = g2p_err.into();
    assert!(matches!(piper_err, PiperError::Phonemize(_)));
}
```

### E2E テスト
```bash
cargo test -p piper-g2p
cargo test -p piper-plus  # piper-core のテストが From 変換を含む
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **G2pError と PiperError のバリアント同期**: PiperError に G2P 関連のバリアントが既に 6 つある (UnsupportedLanguage, Phonemize, DictionaryLoad, JPreprocessInit, LabelParse, PhonemeIdNotFound)。G2pError はこれらと 1:1 対応させるが、将来 PiperError 側に G2P 非関連のバリアントが追加されても G2pError は影響を受けない。
- **PhonemeIdMap の重複定義**: `piper-core` の `config.rs` と `piper-g2p` の `types.rs` で同一の型が定義される。P2-007 の re-export で `piper-core::PhonemeIdMap` を `piper-g2p::PhonemeIdMap` の re-export に切り替えることで、最終的に単一定義になる。
- **所有権パターン**: `G2pError` の各バリアントは `String` を所有する。`&str` ライフタイムを避け、エラーが `'static` を満たすようにする。

### レビュー項目
- G2pError が `std::error::Error` を実装していること (`thiserror` の `#[derive(Error)]` による)
- G2pError が `Send + Sync` を満たすこと (String フィールドのみなので自動的に満たす)
- `piper-g2p` の Cargo.toml に `piper-core` への依存がないこと
- `From<G2pError> for PiperError` が全バリアントを網羅していること (`match` の exhaustive check)

---

## 6. 一から作り直すとしたら

- `G2pError` をフラットな enum ではなく、`Box<dyn std::error::Error + Send + Sync>` を内包する single-variant enum にする設計もある。拡張性は高いがパターンマッチングが使えなくなるため、現在の 6 バリアント enum が妥当。
- `PhonemeIdMap` を newtype (`struct PhonemeIdMap(HashMap<...>)`) にして型安全性を高める案もあるが、既存コードとの互換性を優先して type alias を採用する。

---

## 7. 後続タスクへの連絡事項

- **P2-003**: `Phonemizer` trait のメソッドは `Result<..., G2pError>` を返す。`G2pError` はこのチケットで定義済み。
- **P2-004**: 7 言語 Phonemizer の移動時、各ファイルの `use crate::error::PiperError` を `use crate::error::G2pError` に一括置換する。
- **P2-005**: `tokens_to_ids()` のエラーは `G2pError::PhonemeIdNotFound` を使用する。
- **P2-007**: piper-core の `PhonemeIdMap` re-export 先を `piper_g2p::PhonemeIdMap` に切り替える。`piper-core::config::PhonemeIdMap` は互換性のため残すが、内部実装は piper-g2p の型を使用する。
