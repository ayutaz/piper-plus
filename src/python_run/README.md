# Piper Plus

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

高速・高品質なニューラルテキスト音声合成 (TTS) システム。[VITS](https://github.com/jaywalnut310/vits/) アーキテクチャを採用し、6言語マルチスピーカー音声合成に対応。[Piper](https://github.com/rhasspy/piper) のフォークで、日本語対応・音質向上・学習機能を大幅に強化しています。

**[Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly デモ](https://ayutaz.github.io/piper-plus/)** | **[GitHub](https://github.com/ayutaz/piper-plus)**

## 主要機能

- **6言語対応** — 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語
- **日本語 TTS** — OpenJTalk統合、韻律情報 (A1/A2/A3)、文脈依存音素バリアント
- **英語 TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0)、espeak-ng 不要
- **マルチスピーカー** — ベースモデル571話者、言語グループ均等サンプリング
- **カスタム辞書** — 200+技術用語の発音辞書内蔵
- **音素入力** — `[[ phonemes ]]` 記法による直接指定
- **クロスプラットフォーム** — Linux (x86_64/ARM64)、macOS (Apple Silicon)、Windows (x64)

## インストール

```bash
pip install piper-tts-plus

# GPU サポート
pip install "piper-tts-plus[gpu]"
```

Python 3.11+ が必要です。

## クイックスタート

### コマンドライン

```bash
# モデル一覧を表示
piper --list-models
piper --list-models ja

# モデルをダウンロード
piper --download-model tsukuyomi

# 音声を生成
piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

### Python API

```python
import wave
from piper import PiperVoice

voice = PiperVoice.load("path/to/model.onnx", config_path="path/to/config.json")
with wave.open("output.wav", "wb") as wav_file:
    voice.synthesize("こんにちは、今日は良い天気ですね。", wav_file)
```

## 事前学習済みモデル

| モデル | 言語 | 話者数 | ダウンロード |
|--------|------|--------|-------------|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | 6言語 (ja/en/zh/es/fr/pt) | 571 | `piper --download-model base` |
| [tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | 6言語 (ja/en/zh/es/fr/pt) | 1 | `piper --download-model tsukuyomi` |

## 対応言語

| 言語 | コード | Phonemizer | 依存 |
|------|--------|------------|------|
| 日本語 | ja | OpenJTalk | pyopenjtalk-plus |
| 英語 | en | g2p-en | g2p-en (Apache-2.0) |
| 中国語 | zh | pypinyin | pypinyin |
| スペイン語 | es | 規則ベース | なし |
| フランス語 | fr | 規則ベース | なし |
| ポルトガル語 | pt | 規則ベース | なし |

## その他のインターフェース

- **[C++ CLI](https://github.com/ayutaz/piper-plus/releases)** — ストリーミング、CUDA推論、カスタム辞書
- **[Rust CLI](https://github.com/ayutaz/piper-plus/tree/dev/src/rust)** — ストリーミング、CUDA/CoreML/DirectML対応
- **[C# CLI (.NET)](https://github.com/ayutaz/piper-plus/tree/dev/src/csharp)** — クロスプラットフォーム .NET 8/9
- **[WebAssembly](https://ayutaz.github.io/piper-plus/)** — ブラウザ内で完全動作
- **[Docker](https://github.com/ayutaz/piper-plus/tree/dev/docker)** — 推論・学習・WebUI イメージ

## リンク

- [GitHub リポジトリ](https://github.com/ayutaz/piper-plus)
- [Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
- [Hugging Face モデル](https://huggingface.co/ayousanz/piper-plus-base)
- [ドキュメント](https://github.com/ayutaz/piper-plus/tree/dev/docs)

## ライセンス

MIT License — 詳細は [LICENSE](https://github.com/ayutaz/piper-plus/blob/dev/LICENSE.md) を参照。
