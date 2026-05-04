# Piper Documentation

Piper Plus documentation. Guides and references for using and developing with Piper Plus.

## はじめての方へ

### すぐに使いたい方 (ビルド不要)
1. [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリをダウンロード
2. [事前学習済みモデル](https://huggingface.co/ayousanz) をダウンロード
3. 音声を生成 → 詳しくは [README のクイックスタート](/README.md#クイックスタート)

### 開発者・カスタマイズしたい方
- [Windows セットアップ](getting-started/windows-setup.md) — ソースからビルド
- [学習ガイド](guides/training/training-guide.md) — 独自モデルの学習

### トラブルシューティング
- [よくある問題と解決策](getting-started/troubleshooting.md)
- [環境変数リファレンス](getting-started/environment-variables.md)

## Getting Started
- [Windows Setup](getting-started/windows-setup.md) - Windows platform setup guide
- [Environment Variables](getting-started/environment-variables.md) - Configuration options
- [Troubleshooting](getting-started/troubleshooting.md) - Common issues and solutions

## Features
- [Phoneme Input](features/phoneme-input.md) - Direct phoneme specification guide
- [Phoneme Timing](features/phoneme-timing.md) - 音素ごとのタイミング情報出力 (リップシンク・字幕)
- [WebUI](features/webui.md) - Browser-based interface

## Guides

### Training
- [Training Guide](guides/training/training-guide.md) - General training instructions
- [WavLM Discriminator Guide](guides/training/wavlm-guide.md) - WavLM による音質向上ガイド

### Testing
- [Multilingual Testing](guides/testing/multilingual-testing.md) - Testing infrastructure

## API Reference
- [Phoneme Mapping](api-reference/phoneme-mapping.md) - Phoneme reference for all languages

## Development
- [Contributing](/CONTRIBUTING.md) - Contribution guidelines
- [Changelog](/CHANGELOG.md) - Version history
- [License](/LICENSE.md) - Project license (MIT)

## Implementations
- **C++ (libpiper)**: メインの推論ライブラリ — [src/cpp/](../src/cpp/)
- **C# CLI (PiperPlus)**: .NET 10 クロスプラットフォーム CLI — [src/csharp/](../src/csharp/)
- **Rust 推論エンジン**: piper-plus / piper-plus-cli — [src/rust/](../src/rust/)
- **Go バインディング**: サーバーサイド推論・HTTP API・セッションプーリング — [src/go/](../src/go/) ([README](../src/go/README.md))
- **WebAssembly**: Browser-based TTS — [src/wasm/openjtalk-web/](../src/wasm/openjtalk-web/)
