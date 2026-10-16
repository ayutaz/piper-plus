# Piper Documentation

piper-plus ドキュメント。利用ガイド・各ランタイム連携・仕様契約・マイグレーション資料の目次。

## 公開版と開発ブランチ

Python/native のリリースは **v2.0.2** です。Rust・npm・NuGet・Kotlin の版は独立しており、[バージョン契約](spec/release-versions.toml) で管理します。`dev` の機能が既存の配布バイナリやパッケージに収録済みとは限りません。

Linux ARM64 の glibc 2.31 互換修正は **v2.0.2** に収録されています。CI は Debian Bullseye／Bookworm／Trixie の QEMU 起動・日本語合成を検証します。Raspberry Pi 実機は未検証です。取得方法と制約は [バイナリの選び方](getting-started/binary-selection.md) を参照してください。

公開 Zero-Shot base とつくよみちゃん FT のモデルは、[モデル一覧](guides/development/pretrained-models.md) の pinned `releases/zs-v1` を使用します。base は参照由来の話者埋め込みが必要で、参照なしの固定音声とは入力が異なります。

## はじめての方へ

### すぐに使いたい方 (ビルド不要)

1. [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリをダウンロード
2. [事前学習済みモデル](guides/development/pretrained-models.md) から用途に合う ONNX と対応設定を取得
3. 音声を生成 → 詳しくは [README のクイックスタート](../README.md#クイックスタート)

### 開発者・カスタマイズしたい方

- [Windows セットアップ](getting-started/windows-setup.md) — ソースからビルド
- [Building from source](guides/development/building-from-source.md) — C++/C#/Rust CLI ビルド
- [学習ガイド](guides/training/training-guide.md) — 独自モデルの学習

### トラブルシューティング

- [よくある問題と解決策](getting-started/troubleshooting.md)
- [環境変数リファレンス](getting-started/environment-variables.md)

## Getting Started

- [Binary selection](getting-started/binary-selection.md) — どのバイナリを選ぶか
- [Windows setup](getting-started/windows-setup.md) — Windows プラットフォーム
- [Environment variables](getting-started/environment-variables.md) — 設定オプション
- [Troubleshooting](getting-started/troubleshooting.md) — 既知の問題

## Features

- [Phoneme input](features/phoneme-input.md) — IPA / PUA / 直接音素指定
- [Phoneme timing](features/phoneme-timing.md) — JSON/TSV/SRT 出力 (リップシンク・字幕)
- [WebUI](features/webui.md) — Gradio ベース UI

## Guides

### 学習

- [Training guide](guides/training/training-guide.md) — 学習全体ガイド (canonical、 早見表 + 詳細を統合)
- [WavLM discriminator](guides/training/wavlm-guide.md) — WavLM 音質向上ガイド

### 推論・ビルド

- [CLI usage](guides/development/cli-usage.md) — C++ CLI オプション
- [Building from source](guides/development/building-from-source.md) — C++/C#/Rust CLI ビルド
- [Pretrained models](guides/development/pretrained-models.md) — HF モデル一覧

### ランタイム統合

- [iOS integration](guides/platform/ios-integration.md) — xcframework / Swift / Dart / Godot
- [Swift G2P (G2P-only)](guides/platform/swift-g2p-integration.md) — ORT 非依存 G2P SPM
- [Android G2P dictionary](guides/platform/android-g2p-dictionary.md) — 辞書配布 3 パターン
- [Android G2P integration](guides/platform/android-g2p-integration.md) — AAR API 利用
- [Home Assistant](guides/integration/home-assistant.md) — Wyoming Protocol 統合
- [Open WebUI](guides/integration/open-webui-integration.md) — OpenAI 互換 TTS 接続
- [LLM ecosystem](guides/integration/llm-ecosystem.md) — LangChain / Ollama 等
- [WASM bundler](guides/integration/wasm-bundler-guide.md) — Vite / webpack 設定

### G2P カスタマイズ

- [Adding PUA codepoint](guides/development/adding-pua-codepoint.md) — 新音素の PUA 登録

### Testing

- [Multilingual testing](guides/testing/multilingual-testing.md) — CI/CD テストカバレッジ

## API Reference

- [Phoneme mapping](api-reference/phoneme-mapping.md) — 全言語の音素 ID 参照

## Specification & Reference

- [Spec INDEX](spec/README.md) — `.toml` 契約 (PUA / phoneme-timing / SSML / 推論入力など、CI gate 対応)
- [Reference INDEX](reference/README.md) — `.md` 設計書 (Kotlin/Swift G2P / iOS shared-lib / ZH-EN ランタイム展開 / Model 解決 等)
- [ORT Version Matrix](reference/ort-versions.md) — ランタイムごとの ONNX Runtime 依存

## Migration

- [Python 英語G2Pのライセンス対応](migration/python-g2p-license.md) — Distance依存を除去したソース版への移行、学習側のローカルG2P導入境界、既存配布物との差
- [Python 2.0.2 / G2P 0.3.1 リリース準備](guides/development/python-release-2.0.2.md) — 版番号、公開前の必須CI、公開操作との境界
- [Python 2.0.2 provider / WebUI 環境](migration/provider-environments.md) — CPU/GPU extra の選択、UI と学習環境の分離
- [v1.11 → v1.12](migration/v1.11-to-v1.12.md) — HiFi-GAN/Flask/HTS-voice 削除など
- [v1.12 → v2.0](migration/v1.12-to-v2.0.md) — Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一、 TF32 / bf16-mixed Template default、 旧 ckpt resume 非サポート

## Benchmarks

- [MOS benchmark](benchmark-mos.md) — 音量・無音区間などの検査、任意の UTMOS、主観 MOS フォーム (PESQ/STOI は未実装)
- [Multi-runtime RTF (公開)](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)

## Research

- [Research INDEX](research/README.md) — 先行研究・最新論文を用いた改善調査スナップショット
- [改善調査 統合レポート 2026-06-15](research/improvement-survey-2026-06-15.md) — VITS2/MB-iSTFT を超える/取り込める先行研究の統合スナップショット (5 軸 31 アクション、 deep-dive companion 付き)

## Design Documents

- [Python 英語G2Pのライセンス監査](design/python-g2p-license-2026-10-16.md) — 依存経路、同梱物の出典、scanner判定、CI
- [第三次監査の対応記録](design/consumer-audit-remediation-2026-10-15.md) — A01～A16 の修正とローカル検証、CI
- [文書・consumer 経路の第三次監査](design/documentation-consumer-audit-2026-10-15.md) — 2026-10-15 時点の導入・実行・配布・CI の対応漏れ、根拠と修正順序
- [Zero-Shot base zs-v1 公開記録](design/zero-shot-base-zs-v1-release-2026-10-10.md) — 公開 revision、成果物、検証範囲
- [つくよみちゃん zs-v1 公開記録](design/tsukuyomi-publication-ready-2026-10-12.md) — 公開済み FT bundle と consumer 検証
- [Zero-Shot Public Model Release Plan](design/zero-shot-public-model-release-plan-2026-10-10.md) — 完了済み公開工程と将来の品質改善計画を分離した記録
- [Zero-Shot Quality Improvement Plan](design/zero-shot-quality-improvement-plan.md) — 実装済み項目と未着手の研究提案
- [Multi-6lang Zero-Shot v7 Training Results](design/multi-6lang-zero-shot-v7-training-results.md) - Canonical v7 training results + 5 fix commit history
- [2026-06-20 研究環境引き継ぎ](handoff/zero-shot-tts-handoff-2026-06-20.md) — 過去の private 研究環境の記録。現在の一般公開モデル利用手順はモデル一覧を参照

## Development

- [Contributing](../CONTRIBUTING.md) — Contribution guidelines
- [Contributing models](../CONTRIBUTING_MODELS.md) — モデル投稿ガイド
- [Changelog](../CHANGELOG.md) (v1.5.1 以降) / [archive](../CHANGELOG-archive.md) (v1.5.0 以前)
- [Security](../SECURITY.md) — サポート対象とセキュリティ報告
- [License](../LICENSE.md) — MIT

## Implementations

- **C++ (libpiper)**: メインの推論ライブラリ — [src/cpp/](../src/cpp/)
- **C# CLI (PiperPlus)**: .NET 10 クロスプラットフォーム CLI — [src/csharp/](../src/csharp/)
- **Rust 推論エンジン**: piper-plus / piper-plus-cli — [CLI README](../src/rust/piper-cli/README.md)
- **Go バインディング**: サーバーサイド推論・HTTP API・セッションプーリング — [src/go/](../src/go/) ([README](../src/go/README.md))
- **WebAssembly**: Browser-based TTS — [src/wasm/openjtalk-web/](../src/wasm/openjtalk-web/)
- **iOS xcframework + SPM**: [`Package.swift`](../Package.swift) (PiperPlus + PiperPlusG2P)
- **Kotlin/Android G2P**: Maven Central [`io.github.ayutaz:piper-plus-g2p-android`](../android/piper-plus-g2p/)
