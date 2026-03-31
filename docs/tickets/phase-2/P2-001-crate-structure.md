# [P2-001] crate 構造作成

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: NFR-200
> 依存チケット: なし (Phase 2 最初のチケット)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` Rust crate のディレクトリ構造・Cargo.toml・workspace 統合を完了し、後続チケット (P2-002〜P2-005) の作業基盤を確立する。この時点では空の `lib.rs` のみで、`cargo build` が通ることをゴールとする。

### ゴール
- `src/rust/piper-g2p/` ディレクトリが作成されている
- `Cargo.toml` に feature flags (言語別コンパイル制御) が定義されている
- workspace `Cargo.toml` の `members` に `piper-g2p` が追加されている
- `piper-core` の `Cargo.toml` に `piper-g2p` への path 依存が追加されている
- `cargo build --workspace` が成功する
- `cargo build -p piper-g2p` が成功する

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/Cargo.toml` | 新規 | crate メタデータ + feature flags |
| `src/rust/piper-g2p/src/lib.rs` | 新規 | 空の crate root (doc comment のみ) |
| `src/rust/Cargo.toml` | 変更 | `members` に `"piper-g2p"` を追加 |
| `src/rust/piper-core/Cargo.toml` | 変更 | `[dependencies]` に `piper-g2p` path 依存を追加 |

### 実装手順

1. **ディレクトリ作成**
   ```bash
   mkdir -p src/rust/piper-g2p/src
   ```

2. **`piper-g2p/Cargo.toml` 作成**
   ```toml
   [package]
   name = "piper-g2p"
   version.workspace = true
   edition.workspace = true
   license.workspace = true
   authors.workspace = true
   repository.workspace = true
   homepage.workspace = true
   keywords = ["g2p", "phonemize", "tts", "ipa", "text-to-speech"]
   categories = ["text-processing", "multimedia::audio"]
   description = "Multilingual G2P (Grapheme-to-Phoneme) for TTS — 7 languages, IPA-first, no eSpeak-ng"

   [features]
   default = ["multilingual"]
   japanese = ["dep:jpreprocess"]
   naist-jdic = ["japanese", "jpreprocess/naist-jdic"]
   multilingual = ["japanese", "english", "chinese", "spanish", "french", "portuguese", "korean"]
   english = []
   chinese = []
   spanish = []
   french = []
   portuguese = []
   korean = []

   [dependencies]
   thiserror = "2"
   regex = "1"
   serde = { version = "1", features = ["derive"] }
   serde_json = "1"
   jpreprocess = { version = ">=0.9, <0.14", optional = true }

   [dev-dependencies]
   tempfile = "3"
   ```

3. **`piper-g2p/src/lib.rs` 作成**
   ```rust
   //! piper-g2p: Multilingual G2P (Grapheme-to-Phoneme) for TTS.
   //!
   //! 7 languages (JA, EN, ZH, KO, ES, FR, PT), IPA-first output,
   //! no eSpeak-ng dependency. MIT licensed.
   ```

4. **workspace `Cargo.toml` 更新**
   ```toml
   [workspace]
   members = ["piper-core", "piper-cli", "piper-python", "piper-g2p"]
   ```

5. **`piper-core/Cargo.toml` 更新**
   ```toml
   [dependencies]
   piper-g2p = { path = "../piper-g2p", default-features = false }
   ```
   注: `default-features = false` にして、piper-core 側で必要な feature のみ有効化する。piper-core の既存 `japanese` feature に `piper-g2p/japanese` を連動させる。

6. **ビルド確認**
   ```bash
   cd src/rust
   cargo build --workspace
   cargo build -p piper-g2p
   cargo build -p piper-g2p --features naist-jdic
   cargo build -p piper-g2p --no-default-features
   ```

### API / インターフェース

この時点では公開 API なし。空の `lib.rs` のみ。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | crate 作成、Cargo.toml 設定、workspace 統合 |

---

## 4. テスト計画

### 提供範囲
ビルド成功の確認のみ。

### Unit テスト
なし (空の crate)。

### E2E テスト
```bash
# 全 feature 組み合わせのビルド検証
cargo build -p piper-g2p --no-default-features
cargo build -p piper-g2p --features japanese
cargo build -p piper-g2p --features naist-jdic
cargo build -p piper-g2p --features english
cargo build -p piper-g2p --features multilingual
cargo build -p piper-g2p --all-features

# workspace 全体のビルド検証
cargo build --workspace
cargo check --workspace --all-features
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **jpreprocess バージョン範囲**: `>=0.9, <0.14` は piper-core の `0.9` ピン留めと互換性があるか。workspace 内で同一の `jpreprocess` バージョンが解決されることを `cargo tree` で確認する。
- **feature flag の連動**: piper-core 側の `japanese` feature が `piper-g2p/japanese` を有効化する設計にする必要がある。P2-004 で実装するが、ここでは piper-core への依存追加だけ行い、feature 連動は後続で設定する。
- **workspace.package 継承**: `version`, `edition`, `license` 等を workspace から継承するが、`keywords` と `categories` は piper-core と異なるため crate 個別に定義する。

### レビュー項目
- `Cargo.toml` の feature flag 名が NFR-200 の設計と一致していること
- `default = ["multilingual"]` で naist-jdic を含まないこと
- `rust-version` が workspace 設定 (1.88) から継承されること
- ライセンスが MIT であること

---

## 6. 一から作り直すとしたら

- workspace を使わず独立リポジトリ (`piper-g2p` リポジトリ) にする選択肢もある。独立リポジトリの方が crates.io での単体利用が明確になるが、piper-core との同期コストが増大する。現時点ではモノレポ内の独立 crate が最適。
- feature flag に `all-languages` と `multilingual` の 2 段階を設ける案もあるが、シンプルさ優先で `multilingual` のみとする。

---

## 7. 後続タスクへの連絡事項

- **P2-002**: `lib.rs` に `G2pError` と `PhonemeIdMap` の型定義を追加する。Cargo.toml の依存 (`thiserror`, `serde`, `serde_json`) はこのチケットで追加済み。
- **P2-003**: `Phonemizer` trait を `lib.rs` に定義する。`Send + Sync` bound を忘れないこと。
- **P2-004**: 7 言語ファイルの移動時、`src/rust/piper-g2p/src/` 配下にファイルを配置する。feature flag による `#[cfg(feature = "...")]` の条件付きコンパイルはこのチケットで Cargo.toml に定義済み。
- **P2-009**: CI ワークフローはこのチケットの crate 構造を前提とする。`working-directory: src/rust` のデフォルトパスが使えることを確認。
