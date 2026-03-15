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
- [日本語 TTS ガイド](guides/japanese/japanese-usage.md) — 日本語音声合成の詳細

### トラブルシューティング
- [よくある問題と解決策](getting-started/troubleshooting.md)
- [環境変数リファレンス](getting-started/environment-variables.md)

## Getting Started
- [Windows Setup](getting-started/windows-setup.md) - Windows platform setup guide
- [Environment Variables](getting-started/environment-variables.md) - Configuration options
- [Troubleshooting](getting-started/troubleshooting.md) - Common issues and solutions

## Features
- [CLI Enhancements](features/cli-enhancements.md) - Enhanced command-line features
- [Custom Dictionary](features/custom_dictionary.md) - Custom dictionary for technical terms and proper nouns
- [Phoneme Input](features/phoneme-input.md) - Direct phoneme specification guide
- [Streaming Mode](features/streaming-mode.md) - Real-time streaming support
- [GPU Configuration](features/gpu-configuration.md) - Multi-GPU support
- [WebUI](features/webui.md) - Browser-based interface

## Guides

### Training
- [Training Guide](guides/training/training-guide.md) - General training instructions
- [WavLM Discriminator Guide](guides/training/wavlm-guide.md) - WavLM による音質向上ガイド
- [Multi-GPU Training](guides/training/multi-gpu-training.md) - Training with multiple GPUs
- [Model Size Impact Analysis](guides/training/model-size-impact-analysis-ja.md) - Model size vs quality

### Japanese Language Support
- [Japanese Usage Guide](guides/japanese/japanese-usage.md) - Comprehensive Japanese TTS guide

### Optimization
- [ARM64 Optimization](guides/optimization/arm64-optimization.md) - NEON optimizations

### Testing
- [Multilingual Testing](guides/testing/multilingual-testing.md) - Testing infrastructure

## API Reference
- [Phoneme Mapping](api-reference/phoneme-mapping.md) - Phoneme reference for all languages

## Development
- [Contributing](/CONTRIBUTING.md) - Contribution guidelines
- [Changelog](/CHANGELOG.md) - Version history
- [License](/LICENSE.md) - Project license (MIT)
- [License Compliance](development/license-compliance.md) - License compliance info

## WebAssembly
Browser-based TTS implementation is in [src/wasm/openjtalk-web/](../src/wasm/openjtalk-web/).
