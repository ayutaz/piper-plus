# [P2-003] Phonemizer trait (IPA-first)

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: FR-200
> 依存チケット: P2-002
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` crate のコア抽象として `Phonemizer` trait を定義する。Python Phase 1 と同様の IPA-first 方針を採用し、`phonemize()` と `phonemize_with_prosody()` の 2 メソッドのみを trait メソッドとする。現行 piper-core の Phonemizer trait から `get_phoneme_id_map()` と `post_process_ids()` を除去し、G2P とエンコードの責務を明確に分離する。

### ゴール
- `use piper_g2p::Phonemizer` で IPA-first な Phonemizer trait がインポートできる
- trait は `phonemize()` と `phonemize_with_prosody()` の 2 メソッドのみを持つ
- `Send + Sync` bound が trait に含まれる
- `ProsodyInfo` と `ProsodyFeature` が `piper-g2p` で再定義されている
- `PhonemizerRegistry` が `piper-g2p` で再定義されている
- `get_phoneme_id_map()` と `post_process_ids()` は trait に含まれない

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/src/phonemizer.rs` | 新規 | `Phonemizer` trait + `ProsodyInfo` + `ProsodyFeature` + `PhonemizerRegistry` |
| `src/rust/piper-g2p/src/lib.rs` | 変更 | `pub mod phonemizer;` + re-export 追加 |

### 実装手順

1. **`piper-g2p/src/phonemizer.rs` 作成**
   ```rust
   //! Phonemizer trait と韻律型定義。

   use std::collections::HashMap;
   use crate::error::G2pError;

   /// プロソディ情報 (言語間で共有)。
   ///
   /// 日本語: a1=アクセント核相対位置, a2=モーラ位置, a3=総モーラ数
   /// 英語:   a1=0 (未使用), a2=ストレスレベル, a3=単語内音素数
   #[derive(Debug, Clone, Copy, PartialEq, Eq)]
   pub struct ProsodyInfo {
       pub a1: i32,
       pub a2: i32,
       pub a3: i32,
   }

   /// プロソディ特徴量 (ONNX 入力用の [a1, a2, a3] 配列)。
   pub type ProsodyFeature = [i32; 3];

   /// 言語固有の IPA 音素化トレイト。
   ///
   /// IPA-first: `phonemize()` は IPA トークン列を返す。
   /// BOS/EOS/パディング/PUA エンコードは含めない。
   /// Piper TTS 固有のエンコーディングは `tokens_to_ids()` が担う。
   pub trait Phonemizer: Send + Sync {
       /// テキストを IPA トークン列 + プロソディ情報に変換する。
       ///
       /// 韻律記号 (`"#"`, `"["`, `"]"` 等) は含む。
       /// BOS (`"^"`), EOS (`"$"`) は含まない。
       /// PUA 変換は行わない (多文字トークンはそのまま返す)。
       fn phonemize_with_prosody(
           &self,
           text: &str,
       ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError>;

       /// テキストを IPA トークン列に変換する (プロソディなし)。
       ///
       /// デフォルト実装は `phonemize_with_prosody()` を呼んで
       /// プロソディ情報を捨てる。
       fn phonemize(&self, text: &str) -> Result<Vec<String>, G2pError> {
           self.phonemize_with_prosody(text).map(|(tokens, _)| tokens)
       }

       /// 言語コード ("ja", "en", "zh" 等)。
       fn language_code(&self) -> &str;

       /// テキストの主要言語を検出する。
       ///
       /// 多言語対応の phonemizer は最初の言語セグメントの言語コードを返す。
       /// デフォルト実装は `language_code()` を返す (単言語 phonemizer 用)。
       fn detect_primary_language(&self, _text: &str) -> &str {
           self.language_code()
       }
   }

   /// 言語コードから Phonemizer を取得するレジストリ。
   pub struct PhonemizerRegistry {
       registry: HashMap<String, Box<dyn Phonemizer>>,
   }

   impl PhonemizerRegistry {
       pub fn new() -> Self {
           Self {
               registry: HashMap::new(),
           }
       }

       pub fn register(&mut self, lang_code: &str, phonemizer: Box<dyn Phonemizer>) {
           self.registry.insert(lang_code.to_string(), phonemizer);
       }

       pub fn get(&self, lang_code: &str) -> Option<&dyn Phonemizer> {
           self.registry.get(lang_code).map(|p| p.as_ref())
       }

       pub fn available_languages(&self) -> Vec<&str> {
           self.registry.keys().map(|s| s.as_str()).collect()
       }
   }

   impl Default for PhonemizerRegistry {
       fn default() -> Self {
           Self::new()
       }
   }
   ```

2. **`piper-g2p/src/lib.rs` 更新**
   ```rust
   pub mod error;
   pub mod phonemizer;
   pub mod types;

   pub use error::G2pError;
   pub use phonemizer::{Phonemizer, PhonemizerRegistry, ProsodyFeature, ProsodyInfo};
   pub use types::PhonemeIdMap;
   ```

### API / インターフェース

**現行 piper-core Phonemizer trait との差分**:

| メソッド | piper-core (現行) | piper-g2p (新) | 理由 |
|---------|-------------------|---------------|------|
| `phonemize_with_prosody()` | `Result<..., PiperError>` | `Result<..., G2pError>` | エラー型分離 |
| `phonemize()` | なし | デフォルト実装 | 利便性 |
| `get_phoneme_id_map()` | trait メソッド | **削除** | エンコード責務分離 |
| `post_process_ids()` | trait メソッド | **削除** | エンコード責務分離 |
| `language_code()` | なし | 追加 | レジストリとの統合 |
| `detect_primary_language()` | trait メソッド | デフォルト実装 | 維持 |
| `Send + Sync` bound | 暗黙 (trait bound なし) | 明示的 | NFR-201 |

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | trait 定義、型定義、テスト |

---

## 4. テスト計画

### 提供範囲
trait 定義の正当性、Send + Sync の検証、PhonemizerRegistry の動作確認。

### Unit テスト

```rust
#[cfg(test)]
mod tests {
    use super::*;

    /// ダミー Phonemizer で trait の基本動作を検証
    struct DummyPhonemizer;

    impl Phonemizer for DummyPhonemizer {
        fn phonemize_with_prosody(
            &self,
            text: &str,
        ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
            let tokens: Vec<String> = text.chars().map(|c| c.to_string()).collect();
            let prosody = vec![None; tokens.len()];
            Ok((tokens, prosody))
        }

        fn language_code(&self) -> &str { "test" }
    }

    #[test]
    fn test_phonemize_default_impl() {
        let p = DummyPhonemizer;
        let tokens = p.phonemize("abc").unwrap();
        assert_eq!(tokens, vec!["a", "b", "c"]);
    }

    #[test]
    fn test_send_sync() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<DummyPhonemizer>();
        // Box<dyn Phonemizer> も Send + Sync を満たす
        fn assert_boxed_send_sync<T: Send + Sync + ?Sized>() {}
        assert_boxed_send_sync::<dyn Phonemizer>();
    }

    #[test]
    fn test_registry() {
        let mut reg = PhonemizerRegistry::new();
        reg.register("test", Box::new(DummyPhonemizer));
        assert!(reg.get("test").is_some());
        assert!(reg.get("unknown").is_none());
        assert_eq!(reg.available_languages(), vec!["test"]);
    }
}
```

### E2E テスト
```bash
cargo test -p piper-g2p
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **trait の互換性破壊**: piper-core の既存 `Phonemizer` trait とメソッドシグネチャが異なる (`G2pError` vs `PiperError`, `get_phoneme_id_map()` 削除)。P2-004 で 7 言語を移動する際に全ファイルの trait impl を更新する必要がある。P2-007 の re-export で既存コードへの影響を最小化する。
- **`language_code()` の追加**: 現行 piper-core の Phonemizer trait にはなかったメソッド。P2-004 で各言語 Phonemizer に実装する必要がある。
- **object safety**: `Phonemizer` trait は `Box<dyn Phonemizer>` で使用される。デフォルト実装のある `phonemize()` と `detect_primary_language()` は object safe (generics なし、Self を値で返さない)。

### レビュー項目
- `Send + Sync` が trait bound に明示されていること
- `phonemize()` のデフォルト実装が `phonemize_with_prosody()` に委譲していること
- `ProsodyInfo` が `Copy` を derive していること (小さい値型のため)
- `PhonemizerRegistry` が `Default` を実装していること

---

## 6. 一から作り直すとしたら

- `phonemize()` を別 trait (`SimplePhonemizer`) にして、prosody 非対応の言語で trait impl を簡略化する案。ただし trait の増加は API 複雑性に繋がるため、デフォルト実装で対応する現設計が妥当。
- `Phonemizer` trait に associated type (`type Error`) を持たせて、言語ごとにエラー型を変える設計。object safety が失われるため不採用。

---

## 7. 後続タスクへの連絡事項

- **P2-004**: 7 言語 Phonemizer を移動する際、以下の変更が必要:
  - `impl Phonemizer for XxxPhonemizer` の trait メソッドから `get_phoneme_id_map()` と `post_process_ids()` を削除
  - `fn language_code(&self) -> &str` を追加
  - 戻り値の `PiperError` を `G2pError` に変更
- **P2-005**: `tokens_to_ids()` と `prosody_to_features()` は Phonemizer trait のメソッドではなく、独立関数として `piper-g2p` に配置する。
- **P2-007**: piper-core の `ProsodyInfo`, `ProsodyFeature` は `piper_g2p` からの re-export に切り替える。
