![Piper logo](etc/logo.png)

[English](README_EN.md) | 日本語 | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md) | [Русский](README_RU.md) | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

> **🔑 唯一の MIT ライセンス Piper フォーク** — オリジナルの [rhasspy/piper](https://github.com/rhasspy/piper) は 2025年10月にアーカイブ済み。[OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) は GPL-3.0 に移行。piper-plus は espeak-ng に依存しない唯一の MIT 互換フォークです。独自実装の G2P で8言語 (JA/EN/ZH/KO/ES/FR/PT/SV) に対応し、商用利用・組込み利用に適しています。

高速・高品質なニューラルテキスト音声合成 (TTS) システム。[VITS](https://github.com/jaywalnut310/vits/) アーキテクチャを採用し、日本語・英語・中国語・韓国語・スペイン語・フランス語・ポルトガル語・スウェーデン語の8言語マルチスピーカー音声合成に対応。[Piper](https://github.com/rhasspy/piper) のフォークで、日本語対応・音質向上・学習機能を大幅に強化しています。

**[Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly デモ](https://ayutaz.github.io/piper-plus/)** (ブラウザで動作、サーバー不要)

---

## 目次

- [30秒で試す](#30秒で試す)
- [ベンチマーク](#ベンチマーク)
- [主要機能](#主要機能)
- [クイックスタート](#クイックスタート)
- [インストール](#インストール)
- [使い方](#使い方)
- [学習](#学習)
- [事前学習済みモデル](#事前学習済みモデル)
- [日本語 TTS](#日本語-tts)
- [プラットフォーム](#プラットフォーム)
- [関連リンク](#関連リンク)

---

## 30秒で試す

### 方法1: プリビルドバイナリ (推奨)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からダウンロードしてすぐに使えます。

```bash
# macOS / Linux
./piper --download-model tsukuyomi
./piper --model tsukuyomi --text "こんにちは" -f hello.wav
```

```powershell
# Windows (PowerShell)
.\piper.exe --download-model tsukuyomi
.\piper.exe --model tsukuyomi --text "こんにちは" -f hello.wav
```

### 方法2: Python

```bash
pip install piper-plus
uv run python -c "from piper_plus import PiperPlus; PiperPlus('tsukuyomi').tts_to_file('こんにちは', 'hello.wav')"
```

<details>
<summary>CLI でも利用できます</summary>

```bash
pip install piper-tts-plus
python -m piper --download-model tsukuyomi
python -m piper --model tsukuyomi --text "こんにちは" -f hello.wav
```

</details>

### 方法3: ブラウザ (インストール不要)

**[WebAssembly デモを開く →](https://ayutaz.github.io/piper-plus/)**

npm で自分のアプリに組み込むこともできます:

```js
import { PiperPlus } from "piper-plus";
const piper = await PiperPlus.initialize("tsukuyomi");
const audio = await piper.synthesize("Hello, world!");
audio.play();
```

> **Note:** npm パッケージはブラウザ専用です。Node.js 環境では Python または Rust CLI をお使いください。

<details>
<summary>🔊 サンプル音声を聴く</summary>

| 言語 | テキスト | 音声 |
|------|---------|------|
| 日本語 | こんにちは、つくよみちゃんです。 | [再生](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/samples/ja.wav) |
| English | Hello, how are you today? | [再生](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/samples/en.wav) |
| 中文 | 你好，今天天气很好。 | [再生](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/samples/zh.wav) |
| Español | ¿Hola, cómo estás hoy? | [再生](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/samples/es.wav) |
| Français | Bonjour, comment allez-vous? | [再生](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/samples/fr.wav) |
| Português | Olá, como você está hoje? | [再生](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/samples/pt.wav) |

> サンプル音声は [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) モデルで生成されています。

</details>

## ベンチマーク

> **計測環境**: Apple M2 Max / 32GB RAM / macOS 15 / Python 3.12 / ONNX Runtime 1.17
> **テスト文**: "Hello, how are you doing today?" (英語, 約25音素)
> **再現**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --format markdown`

| システム | RTF ↓ | サイズ (MB) | RAM (MB) | 初回起動 (ms) | 言語数 | ライセンス |
|---------|-------|-----------|---------|-------------|--------|----------|
| **piper-plus** | **0.05** | **38** | **120** | **350** | **8** | **MIT** |
| Piper 本家 (archived) | 0.06 | 75 | 150 | 400 | 1/model | MIT |
| piper1-gpl (OHF fork) | 0.06 | 75 | 150 | 400 | 1/model | GPL-3.0 |
| Kokoro-82M | 0.12 | 320 | 450 | 800 | 1 | Apache-2.0 |
| sherpa-onnx | 0.07 | 75 | 130 | 380 | 1/model | Apache-2.0 |
| eSpeak-NG | 0.001 | 2 | 15 | 10 | 100+ | GPL-3.0 |

> **注**: RTF (Real-Time Factor) は低いほど高速。eSpeak-NG は非ニューラルTTSのため参考値。piper-plus は1モデルで8言語をカバー (学習済み6言語 + G2P対応2言語)。計測環境・条件の詳細は `scripts/benchmark.py` で再現可能です。数値はリファレンス実装での計測値です。

---

## 主要機能

### 音声合成

- **8言語対応** — 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語・スウェーデン語・韓国語 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) ※学習済みモデルは6言語 (JA/EN/ZH/ES/FR/PT)
- **日本語 TTS** — OpenJTalk統合、韻律情報 (A1/A2/A3)、疑問詞マーカー (#204)、文脈依存「ん」バリアント (#207)
- **英語 TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0)、espeak-ng 不要
- **マルチスピーカー** — 571話者対応 (学習用ベースモデル)、SpeakerBalancedBatchSampler、言語グループ均等サンプリング
- **カスタム辞書** — 200+技術用語の発音辞書内蔵
- **音素入力** — `[[ phonemes ]]` 記法による直接指定 — [ガイド](docs/features/phoneme-input.md)

### 学習

- **WavLM Discriminator** — MOS +0.15-0.25 向上 (デフォルト有効、学習時のみ使用)
- **FP16 Mixed Precision** — 学習速度2-3倍、メモリ約50%削減 (デフォルト有効)
- **EMA** — Exponential Moving Average による学習安定性向上 (デフォルト有効)
- **マルチGPU** — DDP対応、自動学習率スケーリング
- **Prosody Features** — Duration Predictorへの韻律情報注入 (`--prosody-dim 16`)
- **Wandb統合** — リアルタイムメトリクス監視

### インターフェース

- **[WebUI (Gradio)](docs/features/webui.md)** — 推論・学習対応、Docker対応
- **C++ CLI** — ストリーミング、CUDA推論、音素タイミング出力、カスタム辞書
- **[C API 共有ライブラリ](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`、FFI対応 (Flutter/Godot/Swift等)、ストリーミング API
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — ブラウザ内で完全動作、サーバー不要
- **[Docker](docker/README.md)** — 推論・学習・WebUI・C++の5イメージ提供
- **PyPI** — `pip install piper-plus` で簡単インストール
- **C# CLI** — .NET 8/9 クロスプラットフォーム、8言語マルチリンガル、ONNX推論
- **Rust CLI** — piper-plus/piper-plus-cli、ストリーミング、CUDA/CoreML/DirectML対応、辞書自動ダウンロード
- **[Go CLI](src/go/README.md)** — HTTP APIサーバー、セッションプーリング、Docker対応、シングルバイナリ

### プラットフォーム

| プラットフォーム | アーキテクチャ | 備考 |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | フルサポート |
| macOS | ARM64 (Apple Silicon) のみ | M1/M2/M3+ |
| Windows | x64 | フルサポート |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | 共有ライブラリ、Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9、Linux/macOS/Windows |
| Rust | Linux x64, macOS ARM64, Windows x64 | Linux/macOS/Windows、CUDA/CoreML/DirectML |
| Go | Linux x64, macOS ARM64, Windows x64 | Linux/macOS/Windows、HTTP API、Docker |

---

## クイックスタート

> 💡 初めての方は [30秒で試す](#30秒で試す) セクションから始めることをお勧めします。

### プリビルドバイナリ (ビルド不要)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリをダウンロードして、すぐに音声合成を開始できます。

**1. バイナリをダウンロード**

お使いのOSに合わせてダウンロード・展開してください。

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://github.com/ayutaz/piper-plus/releases/latest/download/piper-windows-x64.zip" -OutFile piper.zip
Expand-Archive piper.zip -DestinationPath .
cd piper
```

**macOS (Apple Silicon):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-macos-arm64.tar.gz
tar xzf piper.tar.gz
cd piper
xattr -cr .
```

**Linux (x86_64):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-linux-x64.tar.gz
tar xzf piper.tar.gz
cd piper
```

**2. モデルをダウンロード & 音声を生成**

```sh
# つくよみちゃんモデルをダウンロード
./bin/piper --download-model tsukuyomi

# 音声を生成 (モデル名だけで OK — ダウンロード済みモデルを自動解決)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd のコードページについて:** `--text` オプションは内部で `GetCommandLineW()` (UTF-16) を使用するため、コードページに依存せずそのまま動作します。パイプ入力（`echo ... | piper`）を使う場合のみ、事前に `chcp 65001` で UTF-8 に切り替えてください。
>
> **output.wav の出力先:** カレントディレクトリ（`cd piper` した場所）に生成されます。

### Python推論

```bash
# インストール
uv pip install ".[inference]"

# 日本語推論
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# 英語推論
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

主なオプション: `--speaker-id`(話者ID)、`--device auto|cpu|gpu`、`--noise-scale`(音声バリエーション)、`--length-scale`(話速)、`--noise-scale-w`(音素長バリエーション、デフォルト: 0.8)

> **WavLMモデルの推奨設定:** WavLM Discriminatorで学習されたモデル (つくよみちゃん等) は `--noise-scale 0.5` で最適な音質になります (デフォルトは 0.667)。

#### Python CLI モデル管理

```bash
# モデル一覧表示
python -m piper --list-models
python -m piper --list-models ja

# モデルダウンロード
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# ダウンロード後に使用
python -m piper --model ja_JP-tsukuyomi-chan-medium -f output.wav "こんにちは"
```

### WebUI

```bash
uv pip install -r src/python_run/requirements_webui.txt
cd src/python_run
python -m piper.webui --data-dir /path/to/models
# → http://localhost:7860
```

### Docker

```bash
# WebUI
docker build -t piper-webui -f docker/webui/Dockerfile .
docker run -p 7860:7860 -v ./models:/models:ro piper-webui

# Python推論 (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# GPU推論 (--gpus all を追加)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

CI/CD ビルド済みイメージ:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Note:** webui イメージは CI で自動ビルドされません。`docker build -t piper-webui -f docker/webui/Dockerfile .` で手動ビルドしてください。

詳細は [docker/README.md](docker/README.md) を参照。

---

## インストール

### Python

Python 3.11+ が必要。依存管理は [uv](https://docs.astral.sh/uv/) を推奨。

```bash
# CPU推論
uv pip install ".[inference]"

# GPU推論 (CUDA環境が必要)
uv pip install ".[inference-gpu]"

# 学習
uv pip install ".[train]"

# 開発 (テスト・リンター含む)
uv pip install ".[dev]"
```

PyPI パッケージからもインストール可能:

```bash
pip install piper-plus
```

### パッケージからインストール

**Python (PyPI):**
```bash
pip install piper-plus
```

**npm (ブラウザ WASM):**
```bash
npm install piper-plus onnxruntime-web
```

**C# CLI (.NET Global Tool):**
```bash
dotnet tool install -g PiperPlus.Cli
```

**Rust CLI (crates.io):**
```bash
cargo install piper-plus-cli
```

**C# ライブラリ (NuGet):**
```bash
dotnet add package PiperPlus.Core
```

**Rust ライブラリ (crates.io):**
```toml
[dependencies]
piper-plus = "0.2.0"
```

### ソースからビルド (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

前提条件: C++17対応コンパイラ、CMake 3.15+

- **Linux**: 依存関係 (ONNX Runtime, OpenJTalk 等) は CMake が自動ダウンロード
- **Windows**: [Windows セットアップガイド](docs/getting-started/windows-setup.md) を参照
- **macOS**: 依存関係は自動ダウンロード

### ソースからビルド (C#)

```bash
# C# CLI ビルド
dotnet build src/csharp/PiperPlus.sln -c Release
# テスト
dotnet test src/csharp/PiperPlus.Core.Tests/
```

前提条件: .NET 8 SDK 以上

#### C# CLI 使用例

```bash
# モデル名で推論 (自動ダウンロード対応、--output-file 省略で output.wav に出力)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# 英語
piper-plus --model model.onnx --text "Hello world" --language en

# マルチリンガル (自動言語検出)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# インライン音素記法 (テキスト中に直接音素を指定)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# ストリーミング (文ごとに逐次PCM出力)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# カスタム辞書 (JSON v1/v2 または TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# モデルダウンロード
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# テストモード (ONNX推論なしで phoneme IDs を確認)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Rust CLI 使用例

```bash
# モデル名で推論 (自動ダウンロード対応)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# 英語
piper-plus-cli --model model.onnx --text "Hello world" --language en

# モデルダウンロード・管理
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# ストリーミング (文ごとに逐次合成)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# カスタム辞書
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# GPU推論
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# テストモード・静音モード
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# raw PCM出力 (WAVヘッダなし)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Note:** C# CLI は `dotnet tool install -g PiperPlus.Cli` で、Rust CLI は `cargo install piper-plus-cli` でインストールできます。両方とも8言語対応・カスタム辞書・ストリーミングをサポートしています。

### ソースからビルド (Rust)

```bash
# Rust CLI ビルド
cargo build --release -p piper-plus-cli
# テスト
cargo test -p piper-plus
```

前提条件: Rust 1.88+、cargo

---

## 使い方

### C++ CLI

#### テキスト直接入力 (推奨)

`--text` オプションでパイプなしにテキストを直接入力できます:

```sh
# テキストから音声生成
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# 日本語テキスト (Windowsでのエンコーディング問題を回避)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# 話者指定
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### パイプ入力

```sh
# 基本
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# ストリーミング (低レイテンシ)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# GPU推論
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# 音素タイミング出力 (リップシンク・字幕同期用)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# カスタム辞書
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# インライン音素入力
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# 生の音素入力
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# ストリーミング (raw audio 出力)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

主なオプション:

| オプション | 説明 | デフォルト |
|---|---|---|
| `--model PATH\|NAME` | モデルファイルのパス、またはモデル名 (ダウンロード済みモデルを自動解決) | - |
| `--text TEXT` | テキスト直接入力 (パイプ不要) | - |
| `--streaming` | チャンクベースのストリーミングモード | off |
| `--use-cuda` | CUDA GPU推論を有効化 | off |
| `--gpu-device-id NUM` | GPU デバイスID | 0 |
| `--length-scale VAL` | 話速調整 (小さい=速い) | 1.0 |
| `--noise-scale VAL` | 音声バリエーション制御 | 0.667 |
| `--noise-w VAL` | 音素長バリエーション制御 | 0.8 |
| `--sentence-silence SEC` | 文間の無音 (秒) | 0.2 |
| `--speaker NUM` | マルチスピーカーモデルの話者番号 | 0 |
| `--phoneme-silence PHONEME SEC` | 特定音素の無音時間設定 | - |
| `--raw-phonemes` | 入力を音素として解釈 | off |
| `--output-timing FILE` | 音素タイミング情報をファイル出力 (JSON/TSV) | - |
| `--custom-dict FILE` | カスタム辞書 (カンマ区切りで複数指定可) | - |
| `--json-input` | JSON入力モード | off |
| `--list-models [LANG]` | 利用可能なモデル一覧を表示 | - |
| `--download-model NAME` | モデルをダウンロード | - |
| `--model-dir DIR` | モデルのダウンロード先ディレクトリ | - |
| `--version` | バージョン表示 | - |
| `--config PATH` / `-c` | 設定ファイルパス | - |
| `--output_file PATH` / `-f` | 出力WAVファイルパス | - |
| `--output_dir PATH` / `-d` | 出力ディレクトリ | - |
| `--output-raw` | raw PCM音声を標準出力に出力 | off |
| `--language LANG` / `-l` | 言語コード | - |
| `--timing-format FMT` | タイミング出力形式 (json/tsv) | json |
| `--test-mode` | テストモード (ONNX推論スキップ) | off |
| `--debug` | デバッグログ有効化 | off |
| `--quiet` / `-q` | ログ無効化 | off |

`piper --help` で全オプションを確認できます。

> **WavLMモデルの推奨設定:** WavLM Discriminatorで学習されたモデルは `--noise-scale 0.5` を推奨します (デフォルトは 0.667)。
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON入力

`--json-input` フラグでJSON入力を受け付けます:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### モデル管理

#### モデル一覧の表示

```bash
# 利用可能なモデル一覧を表示
./bin/piper --list-models

# 言語でフィルタリング
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### モデルのダウンロード

```bash
# モデル名を指定してダウンロード (エイリアスも使用可能)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# ダウンロード先ディレクトリを指定
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# ダウンロード後、モデル名で推論 (フルパス不要)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### 環境変数 (C++ CLI)

| 変数名 | 説明 | 例 |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | `--model` 未指定時のデフォルトモデルパス | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | `--config` 未指定時のデフォルト設定ファイルパス | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | ダウンロードモデルの保存先ディレクトリ | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA GPUデバイスID | `0` |

### ヘルパースクリプト (Windows)

Windows ユーザー向けに `scripts/` ディレクトリにヘルパースクリプトを提供しています。

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**コマンドプロンプト:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## 学習

詳細は [学習ガイド](docs/guides/training/training-guide.md) を参照。

### 基本

```bash
uv pip install ".[train]"

uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --accelerator gpu --devices 1 --precision 16-mixed \
  --max_epochs 200 --batch-size 16 \
  --quality medium \
  --prosody-dim 16 \
  --ema-decay 0.9995
```

### マルチスピーカー・マルチGPU

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995
```

マルチGPUでは DDP (Distributed Data Parallel) が自動設定されます。NCCL環境変数の設定が必要です。詳細はマルチGPU学習ガイドを参照。

### ONNX変換

デフォルトでFP16変換が適用され、モデルサイズが約50%削減されます。`--no-fp16` で無効化可能。数値安定性のため LayerNormalization, Sigmoid, Softmax は FP32 のまま保持されます。

```bash
# 標準モデル (FP16出力)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# FP32出力
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# deterministic エクスポート (デバッグ用)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### チェックポイント管理

- `--resume_from_checkpoint` — チェックポイントからの学習再開
- `--resume_from_single_speaker_checkpoint` — シングルスピーカーモデルからマルチスピーカーへの変換
- `--resume-from-multispeaker-checkpoint` — マルチスピーカーからシングルスピーカーへの転移学習 (自動で `--freeze-dp` 有効化)

### 音声評価

`scripts/evaluation/` に評価用テストテキストがあります。

---

## 事前学習済みモデル

推論用の音声合成モデルを Hugging Face で公開しています。

**推論用モデル (すぐに使えます):**

| モデル | 言語 | 話者数 | 説明 | ダウンロード |
|---|---|---|---|---|
| つくよみちゃん 6lang | JA/EN/ZH/ES/FR/PT | 1 | つくよみちゃん音声、6言語対応、FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 日本語 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10日本語音声、6言語対応、FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**学習用ベースモデル (ファインチューニング用):**

| モデル | 言語 | 話者数 | 説明 | ダウンロード |
|---|---|---|---|---|
| 6言語ベースモデル | JA/EN/ZH/ES/FR/PT | 571 | マルチリンガル事前学習済み (508,187発話, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### モデルのダウンロード

**つくよみちゃんモデル:**

**Windows (PowerShell):**

```powershell
mkdir models
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx" -OutFile models/tsukuyomi.onnx
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json" -OutFile models/config.json
```

**macOS / Linux:**

```bash
mkdir -p models
curl -L -o models/tsukuyomi.onnx https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx
curl -L -o models/config.json https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json
```

### 6言語ベースモデルの特徴 (学習用)

- アーキテクチャ: VITS + Prosody Features
- 学習データ: 508,187発話 (571話者, 6言語)
- サンプリングレート: 22,050 Hz
- シンボル数: 173
- Prosody Features: A1/A2/A3 韻律情報 (日本語)
- 言語グループ均等サンプリング: 自動有効化

**対応言語:**

| 言語 | コード | language_id | 話者数 | 発話数 | ソース |
|---|---|---|---|---|---|
| 日本語 | ja | 0 | 20 | 60,148 | MOE-Speech |
| 英語 | en | 1 | 310 | 74,912 | LibriTTS-R |
| 中国語 | zh | 2 | 142 | 63,223 | AISHELL-3 |
| スペイン語 | es | 3 | 63 | 168,374 | CML-TTS |
| フランス語 | fr | 4 | 28 | 107,464 | CML-TTS |
| ポルトガル語 | pt | 5 | 8 | 34,066 | CML-TTS |

> **Note:** piper-plus は独自のアーキテクチャ拡張 (多言語埋め込み、Prosody A1/A2/A3、173シンボル) を行っているため、upstream Piper のチェックポイント/ONNXモデルとの互換性はありません。piper-plus 専用のモデルをご利用ください。

---

## 日本語 TTS

OpenJTalk 統合による高品質な日本語音声合成。辞書・ボイスファイルは初回実行時に自動ダウンロードされます。

**環境変数 (オプション):**

| 変数名 | 説明 |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk辞書パス (未設定時は自動ダウンロード) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` で自動ダウンロード無効化 |
| `PIPER_OFFLINE_MODE` | `1` でオフラインモード |

詳細は日本語音声合成ガイドおよび [音素マッピングリファレンス](docs/api-reference/phoneme-mapping.md) を参照。

---

## プラットフォーム

### macOS

**Apple Silicon (M1/M2/M3+) のみサポート。** Intel Mac は Docker またはソースビルドをご利用ください。

初回実行時のセキュリティ警告:

```bash
xattr -cr piper/
```

### Windows

詳細は [Windows セットアップガイド](docs/getting-started/windows-setup.md) を参照。

```cmd
piper.exe --model model.onnx -f output.wav
```

### WebAssembly

ブラウザで直接動作する日本語 TTS。サーバー不要、オフライン対応。

- **[オンラインデモ](https://ayutaz.github.io/piper-plus/)**
- **[技術詳細・統合ガイド](src/wasm/openjtalk-web/README.npm.md)**

---

## 関連リンク

### Unity — uPiper

Piper を Unity で使用するプラグイン: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+、Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android 対応
- 日本語・英語対応、非同期API、ストリーミング

### 音声モデル (Voices)

piper-plus 専用モデル: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6言語ベース) · [つくよみちゃん](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note:** piper-plus は独自の G2P・音素体系を使用しているため、upstream Piper (rhasspy/piper-voices) のモデルとは互換性がありません。

### 関連記事

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (独立G2Pパッケージ)

多言語G2P (Grapheme-to-Phoneme) を独立パッケージとして提供:

- **Python**: `pip install piper-plus-g2p` — [ソースコード](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [ソースコード](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [ソースコード](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [ソースコード](src/wasm/g2p/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## ドキュメント

| カテゴリ | リンク |
|---|---|
| 日本語TTS | 日本語音声合成ガイド |
| 学習 | [学習ガイド](docs/guides/training/training-guide.md) · マルチGPU |
| API | [音素マッピング](docs/api-reference/phoneme-mapping.md) · [環境変数](docs/getting-started/environment-variables.md) |
| 機能 | [WebUI](docs/features/webui.md) · CLI強化 · ストリーミング |
| セットアップ | クイックスタート (日本語) · [Windows](docs/getting-started/windows-setup.md) · [トラブルシューティング](docs/getting-started/troubleshooting.md) |
| Docker | [Docker環境](docker/README.md) |
| WebAssembly | [技術詳細](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## Changelog

[CHANGELOG.md](CHANGELOG.md) を参照。
