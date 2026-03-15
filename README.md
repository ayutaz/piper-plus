![Piper logo](etc/logo.png)

[English](README_EN.md) | 日本語 | [中文](README_ZH.md) | [Français](README_FR.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

高速・高品質なニューラルテキスト音声合成 (TTS) システム。[VITS](https://github.com/jaywalnut310/vits/) アーキテクチャを採用し、日本語・英語のマルチスピーカー音声合成に対応。[Piper](https://github.com/rhasspy/piper) のフォークで、日本語対応・音質向上・学習機能を大幅に強化しています。

**[Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly デモ](https://ayutaz.github.io/piper-plus/)** (ブラウザで動作、サーバー不要)

---

## 目次

- [主要機能](#主要機能)
- [クイックスタート](#クイックスタート)
- [事前学習済みモデル](#事前学習済みモデル)
- [インストール](#インストール)
- [使い方](#使い方)
- [学習](#学習)
- [日本語 TTS](#日本語-tts)
- [プラットフォーム](#プラットフォーム)
- [関連リンク](#関連リンク)

---

## 主要機能

### 音声合成

- **日本語 TTS** — OpenJTalk統合、韻律情報 (A1/A2/A3)、疑問詞マーカー (#204)、文脈依存「ん」バリアント (#207)
- **英語 TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0)、espeak-ng 不要
- **マルチスピーカー** — 最大20+話者対応、SpeakerBalancedBatchSampler
- **カスタム辞書** — 200+技術用語の発音辞書内蔵 — [ガイド](docs/features/custom_dictionary.md)
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
- **[WebAssembly](src/wasm/openjtalk-web/README.md)** — ブラウザ内で完全動作、サーバー不要
- **[Docker](docker/README.md)** — 推論・学習・WebUI・C++の5イメージ提供
- **PyPI** — `pip install piper-tts-plus` で簡単インストール

### プラットフォーム

| プラットフォーム | アーキテクチャ | 備考 |
|---|---|---|
| Linux | x86_64 / ARM64 | フルサポート |
| macOS | ARM64 (Apple Silicon) のみ | M1/M2/M3+ |
| Windows | x64 | フルサポート |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |

---

## クイックスタート

### プリビルドバイナリ (ビルド不要)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリをダウンロードして、すぐに音声合成を開始できます。

**1. バイナリをダウンロード**

お使いのOSに合わせてダウンロード・展開してください。

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://github.com/ayutaz/piper-plus/releases/latest/download/piper-windows-x64.zip" -OutFile piper.zip
Expand-Archive piper.zip -DestinationPath piper
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

**2. モデルをダウンロード**

つくよみちゃんモデルの例:

**Windows (PowerShell):**

```powershell
mkdir models
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-wavlm-300epoch.onnx" -OutFile models/tsukuyomi.onnx
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json" -OutFile models/config.json
```

**macOS / Linux:**

```bash
mkdir -p models
curl -L -o models/tsukuyomi.onnx https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-wavlm-300epoch.onnx
curl -L -o models/config.json https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json
```

**3. 音声を生成**

**Windows (cmd):**

```cmd
echo こんにちは、今日は良い天気ですね。| piper.exe --model models\tsukuyomi.onnx --config models\config.json --output_file output.wav
```

**macOS / Linux:**

```bash
echo 'こんにちは、今日は良い天気ですね。' | \
  ./piper --model models/tsukuyomi.onnx --config models/config.json --output_file output.wav
```

> **config.json の命名規則:** piper は `<モデル名>.onnx.json` (例: `tsukuyomi.onnx.json`) を自動検出します。設定ファイルが別名の場合 (例: `config.json`) は `--config` で明示的に指定してください。
>
> ```sh
> # 自動検出される場合 (--config 不要)
> ./piper --model models/tsukuyomi.onnx --output_file output.wav
> # → models/tsukuyomi.onnx.json を自動読み込み
>
> # 別名の場合 (--config 必須)
> ./piper --model models/tsukuyomi.onnx --config models/config.json --output_file output.wav
> ```

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

主なオプション: `--speaker-id`(話者ID)、`--device auto|cpu|gpu`、`--noise-scale`(音声バリエーション)、`--length-scale`(話速)

> **WavLMモデルの推奨設定:** WavLM Discriminatorで学習されたモデル (つくよみちゃん等) は `--noise-scale 0.5` で最適な音質になります (デフォルトは 0.667)。

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
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main
docker pull ghcr.io/ayutaz/piper-plus/python-train:main
docker pull ghcr.io/ayutaz/piper-plus/webui:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

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
pip install piper-tts-plus
```

### ソースからビルド (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

前提条件: C++17対応コンパイラ、CMake 3.13+

- **Linux**: ビルド前に [piper-phonemize](https://github.com/rhasspy/piper-phonemize) を `lib/Linux-$(uname -m)/piper_phonemize` に配置
- **Windows**: [Windows セットアップガイド](docs/getting-started/windows-setup.md) を参照
- **macOS**: 依存関係は自動ダウンロード

---

## 使い方

### C++ CLI

```sh
# 基本
echo "こんにちは" | ./piper --model ja_model.onnx --output_file output.wav

# ストリーミング (低レイテンシ)
echo "長いテキスト..." | ./piper --model ja_model.onnx --output_file output.wav --streaming

# GPU推論
echo "Hello" | ./piper --model en_model.onnx --use-cuda --output_file output.wav

# 音素タイミング出力 (リップシンク・字幕同期用)
echo "Hello world" | ./piper --model en_model.onnx -f speech.wav --output-timing timing.json

# カスタム辞書
echo "DockerとGitHubを使います" | ./piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# インライン音素入力
echo 'Hello [[ h ə l oʊ ]] world' | ./piper --model en_model.onnx -f output.wav

# 生の音素入力
echo 'h ə l oʊ _ w ɜː l d' | ./piper --model en_model.onnx --raw-phonemes -f output.wav

# ストリーミング (raw audio 出力)
echo 'Long text...' | ./piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

主なオプション:

| オプション | 説明 | デフォルト |
|---|---|---|
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

`piper --help` で全オプションを確認できます。

> **WavLMモデルの推奨設定:** WavLM Discriminatorで学習されたモデルは `--noise-scale 0.5` を推奨します (デフォルトは 0.667)。
>
> ```sh
> echo "こんにちは" | ./piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON入力

`--json-input` フラグでJSON入力を受け付けます:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
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

マルチGPUでは DDP (Distributed Data Parallel) が自動設定されます。NCCL環境変数の設定が必要です。詳細は [マルチGPU学習ガイド](docs/guides/training/multi-gpu-training.md) を参照。

### ONNX変換

```bash
# 標準モデル
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLMモデル (--stochastic 必須)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### チェックポイント管理

- `--resume_from_checkpoint` — チェックポイントからの学習再開
- `--resume_from_single_speaker_checkpoint` — シングルスピーカーモデルからマルチスピーカーへの変換

### 音声評価

`scripts/evaluation/` に MCD, PESQ, UTMOS の評価ツールがあります。

---

## 事前学習済みモデル

日本語TTSのファインチューニング用ベースモデルを Hugging Face で公開しています。

| モデル | 言語 | 話者数 | 説明 | ダウンロード |
|---|---|---|---|---|
| つくよみちゃん | 日本語 | 1 | ファインチューニング済み、すぐに利用可能 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| 20話者ベースモデル | 日本語 | 20 | ファインチューニング用ベースモデル (VITS + WavLM + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### モデルのダウンロード

**つくよみちゃんモデル:**

**Windows (PowerShell):**

```powershell
mkdir models
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-wavlm-300epoch.onnx" -OutFile models/tsukuyomi.onnx
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json" -OutFile models/config.json
```

**macOS / Linux:**

```bash
mkdir -p models
curl -L -o models/tsukuyomi.onnx https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-wavlm-300epoch.onnx
curl -L -o models/config.json https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json
```

### piper-plus-base の特徴

- アーキテクチャ: VITS + WavLM Discriminator
- 学習データ: 60,164発話 (20話者)
- サンプリングレート: 22,050 Hz
- Prosody Features: A1/A2/A3 韻律情報
- 拡張音素: 疑問詞マーカー、文脈依存「ん」バリアント (65音素)
- ライセンス: CC-BY-SA-4.0

upstream Piper のチェックポイントも利用可能: [piper-checkpoints](https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main)

---

## 日本語 TTS

OpenJTalk 統合による高品質な日本語音声合成。辞書・ボイスファイルは初回実行時に自動ダウンロードされます。

**環境変数 (オプション):**

| 変数名 | 説明 |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk辞書パス (未設定時は自動ダウンロード) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` で自動ダウンロード無効化 |
| `PIPER_OFFLINE_MODE` | `1` でオフラインモード |

詳細は [日本語音声合成ガイド](docs/guides/japanese/japanese-usage.md) および [音素マッピングリファレンス](docs/api-reference/phoneme-mapping.md) を参照。

---

## プラットフォーム

### macOS

**Apple Silicon (M1/M2/M3+) のみサポート。** Intel Mac は Docker またはソースビルドをご利用ください。

初回実行時のセキュリティ警告:

```bash
xattr -cr piper/
```

### Windows

espeak-ng-data ディレクトリが必要です。詳細は [Windows セットアップガイド](docs/getting-started/windows-setup.md) を参照。

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

ブラウザで直接動作する日本語 TTS。サーバー不要、オフライン対応。

- **[オンラインデモ](https://ayutaz.github.io/piper-plus/)**
- **[技術詳細・統合ガイド](src/wasm/openjtalk-web/README.md)**

---

## 関連リンク

### Unity — uPiper

Piper を Unity で使用するプラグイン: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+、Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android 対応
- 日本語・英語対応、非同期API、ストリーミング

### 音声モデル (Voices)

upstream Piper の音声モデル (30+言語) も利用可能: [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

各音声には `.onnx` モデルと `.onnx.json` 設定ファイルが必要です。[音声サンプル](https://rhasspy.github.io/piper-samples) | [ビデオチュートリアル](https://youtu.be/rjq5eZoWWSo)

### 関連記事

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://www.nvaccess.org/post/in-process-8th-may-2023/#voices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## ドキュメント

| カテゴリ | リンク |
|---|---|
| 日本語TTS | [日本語音声合成ガイド](docs/guides/japanese/japanese-usage.md) |
| 学習 | [学習ガイド](docs/guides/training/training-guide.md) · [マルチGPU](docs/guides/training/multi-gpu-training.md) |
| API | [音素マッピング](docs/api-reference/phoneme-mapping.md) · [環境変数](docs/getting-started/environment-variables.md) |
| 機能 | [WebUI](docs/features/webui.md) · [CLI強化](docs/features/cli-enhancements.md) · [ストリーミング](docs/features/streaming-mode.md) |
| セットアップ | [クイックスタート (日本語)](docs/guides/japanese/japanese-usage.md) · [Windows](docs/getting-started/windows-setup.md) · [トラブルシューティング](docs/getting-started/troubleshooting.md) |
| Docker | [Docker環境](docker/README.md) |
| WebAssembly | [技術詳細](src/wasm/openjtalk-web/README.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## Changelog

[CHANGELOG.md](CHANGELOG.md) を参照。

[![A library from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-library.png)](https://www.openhomefoundation.org/)
