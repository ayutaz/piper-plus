# [P2-006] piper-core 側 request_builder リネーム

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: FR-200
> 依存チケット: P2-004, P2-005
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
P2-005 で `tokens_to_ids()` / `prosody_to_features()` が piper-g2p に移動した後、piper-core の `phoneme_converter.rs` に残った `build_synthesis_request()` を `request_builder.rs` にリネームする。これにより、「G2P エンコード」は piper-g2p、「推論リクエスト構築」は piper-core という責務分離が命名にも反映される。

### ゴール
- `piper-core/src/phonemize/phoneme_converter.rs` が `piper-core/src/phonemize/request_builder.rs` にリネームされている
- `mod.rs` の `pub mod phoneme_converter;` が `pub mod request_builder;` に変更されている
- `build_synthesis_request()` の public API パスが `phonemize::request_builder::build_synthesis_request()` になっている
- piper-cli と piper-python のコンパイルがゼロ変更で通る (直接参照していない場合)、または最小限の `use` パス変更で通る

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-core/src/phonemize/phoneme_converter.rs` | リネーム | -> `request_builder.rs` |
| `src/rust/piper-core/src/phonemize/mod.rs` | 変更 | `pub mod phoneme_converter` -> `pub mod request_builder` |
| `src/rust/piper-core/src/phonemize/mod.rs` | 変更 | 後方互換のため `pub use request_builder as phoneme_converter;` を追加 (暫定) |
| `src/rust/piper-core/src/**/*.rs` | 変更 | `phoneme_converter::build_synthesis_request` の参照パスを更新 |

### 実装手順

1. **ファイルリネーム**
   ```bash
   cd src/rust
   git mv piper-core/src/phonemize/phoneme_converter.rs \
          piper-core/src/phonemize/request_builder.rs
   ```

2. **`mod.rs` の更新**
   ```rust
   // 変更前
   pub mod phoneme_converter;

   // 変更後
   pub mod request_builder;
   /// 後方互換エイリアス (P2-010 v1.0.0 で削除予定)
   #[deprecated(since = "0.2.0", note = "use request_builder instead")]
   pub use request_builder as phoneme_converter;
   ```

3. **`request_builder.rs` 内の doc comment 更新**
   ```rust
   //! Synthesis request builder.
   //!
   //! Builds `SynthesisRequest` structs ready for ONNX inference.
   //! Phoneme token-to-ID conversion is delegated to `piper_g2p::encode`.
   ```

4. **内部参照の更新**
   `piper-core` 内で `phonemize::phoneme_converter::build_synthesis_request` を参照している箇所を検索し、`phonemize::request_builder::build_synthesis_request` に変更する。

5. **piper-cli / piper-python の影響確認**
   ```bash
   # 参照箇所の検索
   grep -r "phoneme_converter" src/rust/piper-cli/
   grep -r "phoneme_converter" src/rust/piper-python/
   ```
   直接参照がある場合は `use` パスを更新する。後方互換エイリアスがあるため、更新しなくてもコンパイルは通る。

### API / インターフェース

```rust
// 新しいパス (推奨)
use piper_plus::phonemize::request_builder::build_synthesis_request;

// 後方互換パス (deprecated)
use piper_plus::phonemize::phoneme_converter::build_synthesis_request;
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | リネーム、参照パス更新、後方互換エイリアス設定 |

---

## 4. テスト計画

### 提供範囲
リネーム後のビルド成功と既存テストの通過確認。

### Unit テスト
`request_builder.rs` に残る `build_synthesis_request()` のテスト:
- `test_build_synthesis_request`: P2-005 で piper-core 側に残したテスト

### E2E テスト
```bash
# workspace 全体のビルド (piper-cli, piper-python 含む)
cargo build --workspace
cargo test --workspace

# deprecated 警告の確認 (後方互換エイリアス経由のアクセス)
cargo build --workspace 2>&1 | grep "deprecated"
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **後方互換エイリアスの lifetime**: `pub use request_builder as phoneme_converter;` を v1.0.0 (P2-010) まで残す。`#[deprecated]` 属性を付けることで利用者に移行を促す。
- **外部 crate からの参照**: piper-core を依存している外部コードが `phonemize::phoneme_converter` パスを使用している可能性がある。後方互換エイリアスでカバーするが、semver 的には breaking change に該当するため、minor バージョンの前に変更する (v0.x.y は breaking change 許容)。
- **`build_synthesis_request()` の関数シグネチャ**: P2-005 で内部実装が `piper_g2p::encode::tokens_to_ids()` を呼ぶように変更されているが、公開 API (関数シグネチャ) は変更しない。

### レビュー項目
- `git mv` で履歴が保持されていること
- `mod.rs` の後方互換エイリアスに `#[deprecated]` が付いていること
- `build_synthesis_request()` の関数シグネチャが変更されていないこと
- `cargo build --workspace` がゼロエラーで通ること

---

## 6. 一から作り直すとしたら

- `request_builder` を独立モジュールではなく `engine.rs` に統合する案。`build_synthesis_request()` は `SynthesisRequest` を構築する唯一の関数であり、`engine.rs` の impl ブロック内のメソッドにする方が自然かもしれない。ただし、phonemize モジュール内に残すことで G2P -> エンコード -> リクエスト構築の流れが明確になるため、現設計を維持する。

---

## 7. 後続タスクへの連絡事項

- **P2-007**: piper-core の re-export 設定時、`request_builder` は re-export の対象外 (piper-core 固有のモジュールであり piper-g2p の公開 API ではない)。
- **P2-010**: v1.0.0 リリース時に後方互換エイリアス (`pub use request_builder as phoneme_converter`) を削除する。CHANGELOG に breaking change として記載する。
