# Contract / Specification Index

piper-plus の **ランタイム横断の仕様・整合契約** の目次。`.toml` 形式で、対応する CI gate が読み取ります。

設計書 / 運用 SOP / テストマトリクスなどの `.md` 文書は [`../reference/`](../reference/README.md) を参照。
例外として zero-shot 評価契約 [`zs-eval-contract.md`](zs-eval-contract.md) (cross-utt SECS / dual-encoder / Goodhart 検知 / 音響ブロック / CER §7) は本ディレクトリ直下の `.md` 契約。

## Core Contracts

ランタイム横断の形式・数値規則・対応範囲を定める契約。byte-for-byte 一致、数値の許容差、未対応項目は各契約と検査スクリプトで定義します。G2P 専用の Kotlin/Android などには音声合成の契約を適用しません。

| 仕様 | パス | 適用範囲 |
|------|------|--------|
| PUA マッピング | [`pua-contract.toml`](pua-contract.toml) | Python/Rust/Go/C++/C#/WASM/Swift/Kotlin |
| Phoneme Set バージョン | [`phoneme-set-version.toml`](phoneme-set-version.toml) | live 185 シンボル (`1.1`) + 出荷済み snapshot 173 (`1.0`) / PUA v2 |
| 音素タイミング | [`phoneme-timing-contract.toml`](phoneme-timing-contract.toml) | 対応する推論ランタイムの JSON/TSV/SRT 出力 |
| Audio Format | [`audio-format-contract.toml`](audio-format-contract.toml) | WAV 出力 |
| Audio Parity | [`audio-parity-contract.toml`](audio-parity-contract.toml) | 推論ランタイム間の WAV 階層化等価性 (peak RMS / chromaprint / mel-spec) |
| Streaming API | [`streaming-api-contract.toml`](streaming-api-contract.toml) | 文単位 yield |
| Text Splitter | [`text-splitter-contract.toml`](text-splitter-contract.toml) | 句読点ベース文分割 |
| Short-text 戦略 | [`short-text-contract.toml`](short-text-contract.toml) | Strategy A/B/C |
| SSML | [`ssml-contract.toml`](ssml-contract.toml) | `<speak>` / `<break>` / `<prosody rate>` |
| 推論入力 | [`inference-input-contract.toml`](inference-input-contract.toml) | scales / language_id 正規化 |
| ONNX エクスポート | [`onnx-export-contract.toml`](onnx-export-contract.toml) | EMA / FP16 / emb_lang 統一 |
| CLI フラグ | [`cli-flag-contract.toml`](cli-flag-contract.toml) | CLI parity とランタイム別の未対応項目 |
| 言語 ID マップ | [`language-id-map-contract.toml`](language-id-map-contract.toml) | ja=0 ~ sv=7 |
| PT 方言 | [`pt-dialect-contract.toml`](pt-dialect-contract.toml) | BR / EU 切替 |
| ORT セッション | [`ort-session-contract.toml`](ort-session-contract.toml) | warmup / cache / threads |
| ORT プロバイダ | [`ort-provider-contract.toml`](ort-provider-contract.toml) | EP 選択優先度 |
| Swift G2P FFI | [`swift-g2p-contract.toml`](swift-g2p-contract.toml) | iOS / macOS FFI ABI |

## Versions & Manifests

| 仕様 | パス | 用途 |
|------|------|------|
| Release バージョン | [`release-versions.toml`](release-versions.toml) | package version の単一ソース |
| Dictionary バージョン | [`dictionary-versions.toml`](dictionary-versions.toml) | 外部辞書 SHA-256 pin |
| Dictionary mirrors | [`dictionary-mirrors.toml`](dictionary-mirrors.toml) | WASM 配布 mirror |
| Loanword mirrors | [`loanword-mirrors.toml`](loanword-mirrors.toml) | ZH-EN JSON のランタイムデータ・テスト fixture mirror |
| Model SHA-256 | [`model-sha256-manifest.toml`](model-sha256-manifest.toml) | 公式モデル hash |

## ファイル命名規則

- `*-contract.toml` — ランタイム横断の形式・数値規則・対応範囲の契約
- `*-versions.toml` / `*-mirrors.toml` — バージョン pin / mirror リスト
- `*-manifest.toml` — 公式アセットの hash

## CI Gate

対応する `scripts/check_*.py` が spec を参照し、各 workflow で設定された範囲を検査します。すべてのモデル・実機・品質を検証する意味ではありません。

- `check_loanword_consistency.py` ← `loanword-mirrors.toml`
- `check_phoneme_set_version.py` ← `phoneme-set-version.toml`
- `check_version_manifest_sync.py` ← `release-versions.toml`
- `check_cli_flag_parity.py` ← `cli-flag-contract.toml`

Ruff の pin 同期は `check_ruff_version_sync.py` が `pyproject.toml`、pre-commit、Python lint workflow を直接照合します。
