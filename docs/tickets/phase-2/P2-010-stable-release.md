# [P2-010] 安定版リリース (v1.0.0)

> Phase: 2 (Rust crate)
> マイルストーン: v1.0.0
> 対応要求: NFR-203
> 依存チケット: P2-001〜P2-009 全て
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
v0.1.0 リリース後のユーザーフィードバックを反映し、API を安定化させた v1.0.0 をリリースする。`#![deny(missing_docs)]` による全 pub アイテムのドキュメント化、crate レベルのクイックスタート例、CHANGELOG の整備を行い、crates.io での安定版として公開する。

### ゴール
- `#![deny(missing_docs)]` が `lib.rs` に設定されている
- 全 `pub` アイテム (trait, struct, enum, fn, type alias, const) に doc comment が付与されている
- crate レベルの doc comment にクイックスタート例が含まれる
- ユーザーフィードバック (GitHub Issues) からの改善が反映されている
- `CHANGELOG.md` に v0.1.0 -> v1.0.0 の変更が記録されている
- P2-006 の後方互換エイリアス (`phoneme_converter`) が削除されている
- crates.io に `piper-g2p` v1.0.0 が publish されている

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/src/lib.rs` | 変更 | `#![deny(missing_docs)]` + クイックスタート例 |
| `src/rust/piper-g2p/src/*.rs` | 変更 | 全 pub アイテムに doc comment 追加 |
| `src/rust/piper-g2p/Cargo.toml` | 変更 | `version = "1.0.0"` |
| `src/rust/piper-g2p/CHANGELOG.md` | 新規 | リリースノート |
| `src/rust/piper-core/src/phonemize/mod.rs` | 変更 | 後方互換エイリアス削除 |

### 実装手順

1. **`#![deny(missing_docs)]` の設定**
   ```rust
   // src/rust/piper-g2p/src/lib.rs
   #![deny(missing_docs)]

   //! # piper-g2p
   //!
   //! Multilingual G2P (Grapheme-to-Phoneme) for TTS.
   //!
   //! 7 languages (JA, EN, ZH, KO, ES, FR, PT), IPA-first output,
   //! no eSpeak-ng dependency. MIT / Apache-2.0 dual licensed.
   //!
   //! ## Quick start
   //!
   //! ```rust
   //! use piper_g2p::{Phonemizer, PhonemizerRegistry};
   //! use piper_g2p::english::EnglishPhonemizer;
   //!
   //! let en = EnglishPhonemizer::new();
   //! let tokens = en.phonemize("Hello world").unwrap();
   //! // tokens: ["h", "ʌ", "ˈ", "l", "oʊ", " ", "ˈ", "w", "ɜː", "l", "d"]
   //! ```
   //!
   //! ## Feature flags
   //!
   //! | Feature | Description |
   //! |---------|-------------|
   //! | `multilingual` (default) | All 7 languages |
   //! | `japanese` | Japanese (requires jpreprocess) |
   //! | `naist-jdic` | Japanese with bundled NAIST-JDIC dictionary |
   //! | `english` | English (CMU dictionary) |
   //! | `chinese` | Chinese (pinyin-based) |
   //! | `korean` | Korean (jamo decomposition) |
   //! | `spanish` | Spanish (rule-based) |
   //! | `french` | French (rule-based) |
   //! | `portuguese` | Portuguese (rule-based) |
   //!
   //! ## Known limitations
   //!
   //! - **English OOV**: Words not in the CMU dictionary produce no output.
   //!   Use custom dictionaries for proper nouns and neologisms.
   //! - **jpreprocess vs pyopenjtalk**: Minor differences in fullcontext
   //!   labels may exist (especially for numbers and symbols).
   ```

2. **全 pub アイテムの doc comment 確認**
   ```bash
   # missing_docs を有効にしてコンパイル (警告をエラーに)
   cd src/rust
   RUSTDOCFLAGS="-D warnings" cargo doc -p piper-g2p --all-features --no-deps
   ```
   コンパイルエラーが出た箇所に doc comment を追加する。

3. **後方互換エイリアス削除**
   ```rust
   // piper-core/src/phonemize/mod.rs
   // 削除:
   // #[deprecated(since = "0.2.0", note = "use request_builder instead")]
   // pub use request_builder as phoneme_converter;
   ```

4. **バージョン更新**
   ```toml
   # piper-g2p/Cargo.toml
   # workspace.version を使わず、crate 個別にバージョン管理する場合:
   version = "1.0.0"
   ```
   注: workspace の `version` を使用している場合は、piper-g2p のみ個別 version に切り替える必要がある。workspace 全体を v1.0.0 にするのは適切でないため。

5. **CHANGELOG.md 作成**
   ```markdown
   # Changelog

   ## [1.0.0] - 2026-xx-xx

   ### Added
   - Stable API: `Phonemizer` trait, `PhonemizerRegistry`, `ProsodyInfo`, `ProsodyFeature`
   - 7 languages: JA, EN, ZH, KO, ES, FR, PT
   - `encode` module: `tokens_to_ids()`, `prosody_to_features()`, `default_post_process_ids()`
   - PUA token map (87 entries, cross-platform compatible)
   - Custom dictionary support (JSON v1.0/v2.0)
   - `MultilingualPhonemizer` with Unicode language detection
   - jpreprocess compatibility test fixtures
   - Full API documentation with `#![deny(missing_docs)]`

   ### Changed
   - Error type: `G2pError` (independent of `PiperError`)
   - `Phonemizer` trait: IPA-first (no BOS/EOS/PUA)

   ### Removed
   - `phoneme_converter` backward-compat alias (use `request_builder`)

   ### Known limitations
   - English OOV words produce no output (CMU dictionary miss)
   - jpreprocess vs pyopenjtalk minor label differences (documented)

   ## [0.1.0] - 2026-xx-xx

   Initial release. All functionality present but API not yet stable.
   ```

6. **crates.io publish**
   ```bash
   git tag rust-g2p-v1.0.0
   git push origin rust-g2p-v1.0.0
   # CI の publish ジョブが自動実行される
   ```

### API / インターフェース

v1.0.0 の安定 API 一覧:

| パス | 種類 | 説明 |
|------|------|------|
| `piper_g2p::Phonemizer` | trait | IPA-first G2P trait |
| `piper_g2p::ProsodyInfo` | struct | 韻律情報 (a1, a2, a3) |
| `piper_g2p::ProsodyFeature` | type alias | `[i32; 3]` |
| `piper_g2p::PhonemeIdMap` | type alias | `HashMap<String, Vec<i64>>` |
| `piper_g2p::PhonemizerRegistry` | struct | 言語レジストリ |
| `piper_g2p::G2pError` | enum | G2P エラー型 (6 バリアント) |
| `piper_g2p::encode::tokens_to_ids()` | fn | トークン -> ID 変換 |
| `piper_g2p::encode::prosody_to_features()` | fn | プロソディ -> 特徴量変換 |
| `piper_g2p::encode::default_post_process_ids()` | fn | BOS/EOS/パディング挿入 |
| `piper_g2p::token_map::token_to_pua()` | fn | PUA 変換 |
| `piper_g2p::token_map::FIXED_PUA_MAP` | static | 87 エントリ PUA テーブル |
| `piper_g2p::japanese::JapanesePhonemizer` | struct | 日本語 G2P |
| `piper_g2p::english::EnglishPhonemizer` | struct | 英語 G2P |
| `piper_g2p::chinese::ChinesePhonemizer` | struct | 中国語 G2P |
| `piper_g2p::korean::KoreanPhonemizer` | struct | 韓国語 G2P |
| `piper_g2p::spanish::SpanishPhonemizer` | struct | スペイン語 G2P |
| `piper_g2p::french::FrenchPhonemizer` | struct | フランス語 G2P |
| `piper_g2p::portuguese::PortuguesePhonemizer` | struct | ポルトガル語 G2P |
| `piper_g2p::multilingual::MultilingualPhonemizer` | struct | 多言語 G2P |
| `piper_g2p::custom_dict::CustomDictionary` | struct | カスタム辞書 |

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | doc comment 追加、API 安定化、CHANGELOG |
| テクニカルライター | 1 | クイックスタート例、README、crate ドキュメント |
| リリースマネージャー | 1 | バージョン更新、タグ作成、publish 確認 |

---

## 4. テスト計画

### 提供範囲
ドキュメントコンパイル、doc test、全テストスイートの最終確認。

### Unit テスト
全既存テスト + doc tests。

### E2E テスト
```bash
# doc test (クイックスタート例がコンパイル・実行されること)
cargo test -p piper-g2p --all-features --doc

# 全テスト
cargo test -p piper-g2p --all-features

# ドキュメントビルド (警告なし)
RUSTDOCFLAGS="-D warnings" cargo doc -p piper-g2p --all-features --no-deps

# workspace 全体
cargo build --workspace
cargo test --workspace

# publish dry-run
cargo publish -p piper-g2p --dry-run
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **v0.1.0 からのフィードバック期間**: v0.1.0 リリース後、どの程度の期間フィードバックを収集するか。最低 2 週間は v0.1.0 のまま運用し、破壊的変更の要望がないことを確認してから v1.0.0 をリリースする。
- **semver 遵守**: v1.0.0 以降は API の破壊的変更が semver 上許容されない。trait のメソッド追加も breaking change になるため、将来の拡張ポイント (例: `phonemize_with_options()`) を v1.0.0 に含めるか検討する。
- **workspace version との乖離**: workspace.package.version が `0.1.0` の場合、piper-g2p のみ `1.0.0` にするには Cargo.toml で `version.workspace = true` を外す必要がある。
- **既知制限 (KL-200, KL-201, KL-202)**: v1.0.0 ドキュメントに既知制限を明記し、ユーザーの期待値を適切に設定する。

### レビュー項目
- `#![deny(missing_docs)]` が有効でコンパイルが通ること
- 全クイックスタート例が `cargo test --doc` で通ること
- CHANGELOG が v0.1.0 と v1.0.0 の両方のエントリを含むこと
- 後方互換エイリアス (`phoneme_converter`) が削除されていること
- `cargo publish --dry-run` が成功すること

---

## 6. 一から作り直すとしたら

- v0.1.0 を skip して最初から v1.0.0 をリリースする案。ユーザーフィードバックを得る前に API を凍結するリスクがあるため、v0.1.0 -> v1.0.0 の 2 段階リリースが妥当。
- `Phonemizer` trait を sealed trait にして、外部からの impl を制限する案。拡張性を犠牲にするが、API 安定性は高まる。現時点ではサードパーティの独自言語実装を許容したいため、sealed にしない。

---

## 7. 後続タスクへの連絡事項

- **Phase 3 (JS/WASM)**: Rust v1.0.0 の API 設計を参考にする。特に `Phonemizer` trait のメソッドシグネチャと `encode` モジュールの関数は JS/WASM でも同等の API を提供する。
- **piper-core メンテナ**: v1.0.0 リリース後、piper-core の `piper-g2p` 依存バージョンを `">=1.0.0, <2.0.0"` に更新する。
- **README / HuggingFace**: `piper-g2p` crate の存在をプロジェクトの README と HuggingFace モデルカードに記載する。
- **エコシステム告知**: crates.io 公開後、Rust TTS コミュニティ (Reddit r/rust, Rust Users Forum) にアナウンスする。
