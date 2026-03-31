# [P2-007] piper-core re-export

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: NFR-203
> 依存チケット: P2-004, P2-005
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
piper-core の `phonemize` モジュールを `piper-g2p` からの re-export に切り替え、既存の piper-cli / piper-python がゼロ変更でコンパイルできる後方互換性を維持する。piper-core を使うダウンストリームコードは、`piper_g2p` を直接依存に追加しなくても、従来通り `piper_plus::phonemize::*` でアクセスできる。

### ゴール
- `piper-core/src/phonemize/mod.rs` が `pub use piper_g2p::*;` で主要型と trait を re-export している
- `piper_plus::Phonemizer`, `piper_plus::ProsodyInfo`, `piper_plus::ProsodyFeature`, `piper_plus::PhonemeIdMap` が従来通り使用できる
- `piper_plus::phonemize::japanese::JapanesePhonemizer` 等の言語別 Phonemizer パスが引き続き有効
- `piper-cli` と `piper-python` のソースコードに変更が不要
- `cargo build --workspace` が成功する

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-core/src/phonemize/mod.rs` | 全面書き換え | re-export 中心のモジュールに変更 |
| `src/rust/piper-core/src/lib.rs` | 変更 | re-export パスの更新 |
| `src/rust/piper-core/src/config.rs` | 変更 | `PhonemeIdMap` を `piper_g2p` からの re-export に切り替え |
| `src/rust/piper-core/Cargo.toml` | 変更 | `piper-g2p` 依存の feature 連動設定 |

### 実装手順

1. **`piper-core/Cargo.toml` の feature 連動**
   ```toml
   [features]
   default = ["naist-jdic", "dict-download"]
   japanese = ["dep:jpreprocess", "piper-g2p/japanese"]
   naist-jdic = ["japanese", "jpreprocess/naist-jdic", "piper-g2p/naist-jdic"]
   # ... (他の feature)

   [dependencies]
   piper-g2p = { path = "../piper-g2p", default-features = false, features = ["multilingual"] }
   ```
   piper-core の `japanese` feature が有効になると `piper-g2p/japanese` も有効になる。

2. **`piper-core/src/phonemize/mod.rs` の re-export**
   ```rust
   //! Phonemizer trait, language registry, and language-specific implementations.
   //!
   //! This module re-exports from `piper_g2p` for backward compatibility.
   //! New code should depend on `piper_g2p` directly.

   // --- Core types (re-export from piper_g2p) ---
   pub use piper_g2p::phonemizer::{Phonemizer, PhonemizerRegistry, ProsodyFeature, ProsodyInfo};
   pub use piper_g2p::error::G2pError;
   pub use piper_g2p::types::PhonemeIdMap;
   pub use piper_g2p::encode;

   // --- Language modules (re-export) ---
   #[cfg(feature = "japanese")]
   pub use piper_g2p::japanese;
   pub use piper_g2p::english;
   pub use piper_g2p::chinese;
   pub use piper_g2p::korean;
   pub use piper_g2p::spanish;
   pub use piper_g2p::french;
   pub use piper_g2p::portuguese;
   pub use piper_g2p::multilingual;
   pub use piper_g2p::token_map;
   pub use piper_g2p::custom_dict;

   // --- piper-core specific (remains here) ---
   pub mod request_builder;
   ```

3. **`piper-core/src/lib.rs` の re-export 更新**
   ```rust
   // 変更前
   pub use config::{PhonemeIdMap, PhonemeType, VoiceConfig};
   pub use phonemize::{ProsodyFeature, ProsodyInfo};

   // 変更後
   pub use piper_g2p::{PhonemeIdMap, ProsodyFeature, ProsodyInfo};
   pub use config::{PhonemeType, VoiceConfig};
   ```

4. **`piper-core/src/config.rs` の更新**
   ```rust
   // 変更前
   pub type PhonemeIdMap = HashMap<String, Vec<i64>>;

   // 変更後
   pub use piper_g2p::PhonemeIdMap;
   ```

5. **ビルド検証**
   ```bash
   cargo build --workspace
   cargo test --workspace
   # piper-cli / piper-python が変更なしでコンパイルされることを確認
   ```

### API / インターフェース

**re-export マッピング**:

| 既存パス (piper-core) | re-export 元 (piper-g2p) |
|----------------------|--------------------------|
| `piper_plus::Phonemizer` | `piper_g2p::Phonemizer` |
| `piper_plus::ProsodyInfo` | `piper_g2p::ProsodyInfo` |
| `piper_plus::ProsodyFeature` | `piper_g2p::ProsodyFeature` |
| `piper_plus::PhonemeIdMap` | `piper_g2p::PhonemeIdMap` |
| `piper_plus::phonemize::japanese::*` | `piper_g2p::japanese::*` |
| `piper_plus::phonemize::english::*` | `piper_g2p::english::*` |
| `piper_plus::phonemize::token_map::*` | `piper_g2p::token_map::*` |

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | re-export 設定、feature 連動、ビルド検証 |

---

## 4. テスト計画

### 提供範囲
後方互換性の検証。既存テストのゼロ変更通過。

### Unit テスト
新規テストは不要。既存テストが全て通過すれば re-export が正しいことの証明になる。

追加検証テスト:
```rust
// piper-core/tests/test_reexport.rs
#[test]
fn test_phonemizer_reexport() {
    // piper-core 経由のパスでアクセスできることを検証
    use piper_plus::phonemize::Phonemizer;
    use piper_plus::phonemize::ProsodyInfo;
    use piper_plus::phonemize::PhonemeIdMap;
    use piper_plus::PhonemeIdMap as TopLevelPhonemeIdMap;

    // 同一型であることを検証
    let _map: PhonemeIdMap = std::collections::HashMap::new();
    let _map2: TopLevelPhonemeIdMap = _map;
}
```

### E2E テスト
```bash
# 最重要: workspace 全体のビルドとテスト
cargo build --workspace
cargo test --workspace

# feature 組み合わせ
cargo build -p piper-plus --no-default-features
cargo build -p piper-plus --features japanese
cargo build -p piper-plus --all-features
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **feature flag の連動の複雑さ**: piper-core の `japanese` feature が `piper-g2p/japanese` を有効化し、さらに `piper-g2p/japanese` が `dep:jpreprocess` を有効化する。3 段階の連動が正しく動作するか `cargo tree --features japanese` で検証する。
- **重複依存の排除**: piper-core と piper-g2p の両方が `jpreprocess` に依存する。workspace 内で同一バージョンに解決されることを確認する。piper-core の direct dependency から `jpreprocess` を外し、piper-g2p 経由のみにするのが理想だが、piper-core の他モジュール (dictionary_manager 等) が直接参照している場合は残す必要がある。
- **`Phonemizer` trait の衝突**: piper-core 内で `use piper_g2p::Phonemizer` と旧 `use crate::phonemize::Phonemizer` が同一の trait を指すことを型システムが認識するか。re-export により同一パスになるため衝突は発生しないが、トランジション中は両方の import が共存する可能性がある。

### レビュー項目
- piper-cli のソースコードに変更がないこと
- piper-python のソースコードに変更がないこと
- `cargo build --workspace` がゼロエラーで通ること
- `cargo test --workspace` が全テスト通過すること
- `PhonemeIdMap` が piper-core と piper-g2p で同一の型であること

---

## 6. 一から作り直すとしたら

- piper-core を piper-g2p の re-export ではなく、piper-g2p を optional 依存にして facade パターンで統合する案。piper-core を使うユーザーが G2P 不要の場合 (JSONL 入力のみ) に依存を減らせる。ただし、現在の piper-core ユーザーの大半が G2P を使用しているため、re-export 方式が実用的。

---

## 7. 後続タスクへの連絡事項

- **P2-008**: jpreprocess 互換性テストは `piper-g2p` を直接依存として実行する。piper-core 経由の re-export テストは本チケットでカバー済み。
- **P2-009**: CI ワークフローで piper-g2p 単体と workspace 全体の両方をテストする。re-export の正常動作は workspace テストで検証される。
- **P2-010**: v1.0.0 リリース時に、piper-core からの re-export を「推奨されない使い方」として doc comment で案内し、`piper-g2p` 直接依存を推奨する。
