# Reference Documents Index

piper-plus の **設計書 / 運用 SOP / テストマトリクス** の目次。

機械可読契約 (`.toml`、CI gate 対応) は [`../spec/`](../spec/README.md) を参照。

## Design Documents

各ランタイム / 機能の設計書。

| 文書 | パス | 状態 |
|------|------|------|
| Kotlin G2P 要件 | [`kotlin-g2p-requirements.md`](kotlin-g2p-requirements.md) | 実装済 (PR #400) |
| Kotlin G2P 設計 | [`kotlin-g2p-design.md`](kotlin-g2p-design.md) | 実装済 (PR #400) |
| Swift G2P 仕様 | [`swift-g2p.md`](swift-g2p.md) | 実装済 (Issue #387) |
| ZH-EN ランタイム展開 | [`zh-en-loanword/README.md`](zh-en-loanword/README.md) | 実装済 (PR #399) |
| Swedish per-word LID | [`swedish-lid/README.md`](swedish-lid/README.md) | 実装済 (Issue #539) |
| iOS shared-lib | [`ios-shared-lib.md`](ios-shared-lib.md) | 実装済 (v1.13.0) |
| Model 解決 | [`model-resolution.md`](model-resolution.md) | 6 ランタイム統一中 (一部 TODO) |
| Speaker Encoder | [`speaker-encoder-contract.md`](speaker-encoder-contract.md) | 実装済 |

## Operations & Versioning

| 文書 | パス | 用途 |
|------|------|------|
| ORT バージョン表 | [`ort-versions.md`](ort-versions.md) | 各ランタイムの ORT pin マトリクス |

## Quality & Testing

| 文書 | パス | 用途 |
|------|------|------|
| PUA テストマトリクス | [`pua-test-matrix.md`](pua-test-matrix.md) | 7 ランタイム × 173 シンボル |
| Mutation Testing | [`mutation-testing.md`](mutation-testing.md) | Python/Rust/C# (baseline 計測中) |
