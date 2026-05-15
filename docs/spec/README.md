# Specification Index

piper-plus の横断的な実装契約 / 仕様 / 設計書の目次。

実装側との byte-for-byte 整合を担保したい契約は `.toml` (機械可読 + CI gate で参照)、設計書・運用 SOP は `.md`。

## Core Contracts

ランタイム横断で byte-for-byte 整合させる契約。CI gate (`scripts/check_*.py`) が参照する canonical。

| 仕様 | パス | 適用範囲 |
|------|------|--------|
| PUA マッピング | [`pua-contract.toml`](pua-contract.toml) | Python/Rust/Go/C++/C#/WASM/Swift/Kotlin |
| Phoneme Set バージョン | [`phoneme-set-version.toml`](phoneme-set-version.toml) | 173 シンボル / PUA v2 |
| 音素タイミング | [`phoneme-timing-contract.toml`](phoneme-timing-contract.toml) | 全ランタイム JSON/TSV/SRT 出力 |
| Audio Format | [`audio-format-contract.toml`](audio-format-contract.toml) | WAV 出力 |
| Streaming API | [`streaming-api-contract.toml`](streaming-api-contract.toml) | 文単位 yield |
| Text Splitter | [`text-splitter-contract.toml`](text-splitter-contract.toml) | 句読点ベース文分割 |
| Short-text 戦略 | [`short-text-contract.toml`](short-text-contract.toml) | Strategy A/B/C |
| SSML | [`ssml-contract.toml`](ssml-contract.toml) | `<speak>` / `<break>` / `<prosody rate>` |
| 推論入力 | [`inference-input-contract.toml`](inference-input-contract.toml) | scales / language_id 正規化 |
| ONNX エクスポート | [`onnx-export-contract.toml`](onnx-export-contract.toml) | EMA / FP16 / emb_lang 統一 |
| CLI フラグ | [`cli-flag-contract.toml`](cli-flag-contract.toml) | 全ランタイム CLI parity |
| 言語 ID マップ | [`language-id-map-contract.toml`](language-id-map-contract.toml) | ja=0 ~ sv=7 |
| PT 方言 | [`pt-dialect-contract.toml`](pt-dialect-contract.toml) | BR / EU 切替 |
| ORT セッション | [`ort-session-contract.toml`](ort-session-contract.toml) | warmup / cache / threads |
| ORT プロバイダ | [`ort-provider-contract.toml`](ort-provider-contract.toml) | EP 選択優先度 |

## Versions & Manifests

| 仕様 | パス | 用途 |
|------|------|------|
| ORT バージョン表 | [`ort-versions.md`](ort-versions.md) | 各ランタイムの ORT pin |
| Release バージョン | [`release-versions.toml`](release-versions.toml) | package version の単一ソース |
| Dictionary バージョン | [`dictionary-versions.toml`](dictionary-versions.toml) | 外部辞書 SHA-256 pin |
| Dictionary mirrors | [`dictionary-mirrors.toml`](dictionary-mirrors.toml) | WASM 配布 mirror |
| Loanword mirrors | [`loanword-mirrors.toml`](loanword-mirrors.toml) | ZH-EN JSON の 10 ランタイム mirror |
| Model SHA-256 | [`model-sha256-manifest.toml`](model-sha256-manifest.toml) | 公式モデル hash |

## Design Documents

各ランタイム / 機能の設計書・運用 SOP。

| 文書 | パス | 状態 |
|------|------|------|
| Kotlin G2P 要件 | [`kotlin-g2p-requirements.md`](kotlin-g2p-requirements.md) | 実装済 (PR #400) |
| Kotlin G2P 設計 | [`kotlin-g2p-design.md`](kotlin-g2p-design.md) | 実装済 (PR #400) |
| Swift G2P 仕様 | [`swift-g2p.md`](swift-g2p.md) | 実装済 (Issue #387) |
| Swift G2P FFI 契約 | [`swift-g2p-contract.toml`](swift-g2p-contract.toml) | 実装済 |
| ZH-EN ランタイム展開 | [`zh-en-loanword-runtime-rollout.md`](zh-en-loanword-runtime-rollout.md) | 実装済 (PR #399) |
| iOS shared-lib | [`ios-shared-lib.md`](ios-shared-lib.md) | 実装済 (v1.13.0) |
| Model 解決 | [`model-resolution.md`](model-resolution.md) | 6 ランタイム統一中 (一部 TODO) |
| Speaker Encoder | [`speaker-encoder-contract.md`](speaker-encoder-contract.md) | 実装済 |

## Quality & Testing

| 文書 | パス | 用途 |
|------|------|------|
| PUA テストマトリクス | [`pua-test-matrix.md`](pua-test-matrix.md) | 7 ランタイム × 173 シンボル |
| Mutation Testing | [`mutation-testing.md`](mutation-testing.md) | Python/Rust/C# (baseline 計測中) |

## ファイル命名規則

- `*-contract.toml` — ランタイム横断で強制する byte-for-byte 整合契約
- `*-versions.toml` / `*-mirrors.toml` — バージョン pin / mirror リスト
- `*-manifest.toml` — 公式アセットの hash
- `*.md` — 設計書 / 運用 SOP / テストマトリクス

## CI Gate

`scripts/check_*.py` がここの spec を参照する。drift があると CI が fail:

- `check_loanword_consistency.py` ← `loanword-mirrors.toml`
- `check_phoneme_set_version.py` ← `phoneme-set-version.toml`
- `check_ruff_version_sync.py` ← `release-versions.toml`
- `check_cli_flag_parity.py` ← `cli-flag-contract.toml`
