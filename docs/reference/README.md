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
| Model 解決 | [`model-resolution.md`](model-resolution.md) | ランタイム別の実装範囲・alias・入力検証を記録 |
| Speaker Encoder | [`speaker-encoder-contract.md`](speaker-encoder-contract.md) | 公開 CAM++/192 bundle と legacy ECAPA/256 gate を区別 |

## Operations & Versioning

| 文書 | パス | 用途 |
|------|------|------|
| ORT バージョン表 | [`ort-versions.md`](ort-versions.md) | 各ランタイムの ORT pin マトリクス |

## Quality & Testing

| 文書 | パス | 用途 |
|------|------|------|
| PUA テストマトリクス | [`pua-test-matrix.md`](pua-test-matrix.md) | 7 ソースの固定 PUA 99 エントリと回帰テスト。学習済みモデルの 173 シンボルとは別の件数 |
| Mutation Testing | [`mutation-testing.md`](mutation-testing.md) | Python/Rust/C# (2026-10-25 実測、`break` score は [`mutation-testing.toml`](../spec/mutation-testing.toml)) |

## CLI Help Snapshots

実際のヘルプ出力を保存した参照です。最新の利用方法は各ランタイムの README と実行ファイルの `--help` を参照してください。抽出・正規化は [CLI Help Extract](../../.github/workflows/cli-help-extract.yml) と [sanitizer](../../scripts/sanitize_cli_help.py) で管理します。C++ を含む 6 ランタイムとも同 workflow の Linux 取得 (artifact `cli-help-<runtime>-<run_id>`) を正本とし、ローカル (Windows / 日本語ロケール) で取得した出力では更新しません。

- [Python](cli-help/python.txt)
- [C++](cli-help/cpp.txt)
- [C#](cli-help/csharp.txt)
- [Rust](cli-help/rust.txt)
- [Go](cli-help/go.txt)
- [Node/WASM parity CLI](cli-help/wasm.txt)
