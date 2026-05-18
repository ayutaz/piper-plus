# Piper Documentation

piper-plus ドキュメント。利用ガイド・各ランタイム連携・仕様契約・マイグレーション資料の目次。

## はじめての方へ

### すぐに使いたい方 (ビルド不要)

1. [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリをダウンロード
2. [事前学習済みモデル](https://huggingface.co/ayousanz) をダウンロード
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

- [Training guide](guides/training/training-guide.md) — 学習全体ガイド
- [WavLM discriminator](guides/training/wavlm-guide.md) — WavLM 音質向上ガイド
- [Training overview (短縮版)](guides/training.md) — 早見表

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

## Proposals (ロードマップ / 議論起点)

- [CI/CD 拡張プラン (2026-05)](proposals/ci-expansion-2026-05.md) — Unlimited CI 前提の網羅調査 + 真に追加する価値があるトップ 10 + 3 ヶ月ロードマップ
- [CI/CD 拡張プラン — マイルストーン詳細](proposals/ci-expansion-milestones.md) — Top 10 を M1-M3 + M4 + M-Stretch に分解、 各 M に目的 / 成功基準 / タスク / 依存 / リスク / 工数を明記

## Tickets (実装単位の個別チケット)

- [Tickets INDEX](tickets/README.md) — CI/CD 拡張プラン マイルストーンを実装者が一人で着手できるレベルまで分解した 10 チケット + 5 phase overview (M1-M4 + M-Stretch) / マイルストーン↔チケット相互マップ / 依存グラフ
- Phase overview: [M1 Defensive Foundations](tickets/M1-overview.md) / [M2 Audio Quality Moat](tickets/M2-overview.md) / [M3 ABI & Ecosystem Hardening](tickets/M3-overview.md) / [M4 Informational Tier](tickets/M4-overview.md) / [M-Stretch Strategic Bets](tickets/M-Stretch-overview.md)

## Migration

- [v1.11 → v1.12](migration/v1.11-to-v1.12.md) — HiFi-GAN/Flask/HTS-voice 削除など

## Benchmarks

- [MOS benchmark](benchmark-mos.md) — PESQ / STOI / 主観評価フォーム
- [Multi-runtime RTF (公開)](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)

## Development

- [Contributing](../CONTRIBUTING.md) — Contribution guidelines
- [Contributing models](../CONTRIBUTING_MODELS.md) — モデル投稿ガイド
- [Changelog](../CHANGELOG.md) (v1.5.1 以降) / [archive](../CHANGELOG-archive.md) (v1.5.0 以前)
- [Security](../SECURITY.md) — サポート対象とセキュリティ報告
- [License](../LICENSE.md) — MIT

## Implementations

- **C++ (libpiper)**: メインの推論ライブラリ — [src/cpp/](../src/cpp/)
- **C# CLI (PiperPlus)**: .NET 10 クロスプラットフォーム CLI — [src/csharp/](../src/csharp/)
- **Rust 推論エンジン**: piper-plus / piper-plus-cli — [src/rust/](../src/rust/)
- **Go バインディング**: サーバーサイド推論・HTTP API・セッションプーリング — [src/go/](../src/go/) ([README](../src/go/README.md))
- **WebAssembly**: Browser-based TTS — [src/wasm/openjtalk-web/](../src/wasm/openjtalk-web/)
- **iOS xcframework + SPM**: [`Package.swift`](../Package.swift) (PiperPlus + PiperPlusG2P)
- **Kotlin/Android G2P**: Maven Central [`io.github.ayutaz:piper-plus-g2p-android`](../android/piper-plus-g2p/)
