![Piper logo](etc/logo.png)

[English](README_EN.md) | 日本語 | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**パッケージ:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 唯一の MIT ライセンス Piper フォーク** — オリジナルの [rhasspy/piper](https://github.com/rhasspy/piper) は 2025年10月にアーカイブ済み。[OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) は GPL-3.0 に移行。piper-plus は espeak-ng に依存しない唯一の MIT 互換フォークです。独自実装の G2P で8言語 (JA/EN/ZH/KO/ES/FR/PT/SV) に対応し、商用利用・組込み利用に適しています。

> **📢 v2.0.0 Breaking changes:** Docker 既定イメージは CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (host NVIDIA driver **R570+** 必須)。学習は torch **2.11.0** + CUDA 12.8、TF32 + bf16-mixed が既定です。torch 2.2 製 checkpoint の resume は非対応です。Python の import / CLI は `piper_plus` / `piper-plus` に変更されました。1.13.0 から現在の公開版へ更新する場合は `pip install --upgrade "piper-plus[cpu]==2.0.2"` を実行してください。詳細: [移行ガイド](docs/migration/v1.12-to-v2.0.md)。

高速・高品質なニューラルテキスト音声合成 (TTS) システム。[VITS](https://github.com/jaywalnut310/vits/) アーキテクチャを採用し、8言語のG2P/音素化と、現在6言語の学習済みモデルによるマルチスピーカー音声合成に対応。[Piper](https://github.com/rhasspy/piper) のフォークで、日本語対応・音質向上・学習機能を大幅に強化しています。

**[Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly デモ](https://ayutaz.github.io/piper-plus/)** (ブラウザで動作、サーバー不要)

---

## 目次

- [ベンチマーク](#ベンチマーク)
- [主要機能](#主要機能)
- [クイックスタート](#クイックスタート)
- [インストール](#インストール)
- [使い方](#使い方)
- [学習](#学習-1)
- [事前学習済みモデル](#事前学習済みモデル)
- [プラットフォーム](#プラットフォーム)
- [関連リンク](#関連リンク)

---

## ベンチマーク

> **計測環境**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cores / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **テスト文**: "Hello, how are you doing today?" (英語, 25 音素)
> **計測パラメータ**: warmup 5 回 / 計測 30 回 (intra-op threads = auto)
> **使用モデル**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (PR #320 で導入された統一 Decoder)
> - Piper 本家: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa リリース)
>
> **再現**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| システム | RTF ↓ | Latency P50 (ms) | サイズ (MB) | RAM (MB) | 初回起動 (ms) | パラメータ | 言語数 | ライセンス |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper 本家 (archived) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/model | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/model | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/model | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **注**: RTF (Real-Time Factor) は低いほど高速。`Latency P50` は単発推論の中央値で「実際の応答性」を直接表す指標。piper-plus は MB-iSTFT 統一 Decoder により Latency P50 27ms と最速 (Piper 本家 35ms 比 -23%、sherpa-onnx 53ms 比 -49%) 、かつモデルサイズも 38MB と最小クラス。旧 piper-plus HiFi-GAN ベース (P50 43.3ms) と比べても -38% の改善。
>
> **†** がついた行は本 PR では再計測していません (`piper1-gpl` は piper 本家と同一アーキテクチャ・ONNX 形式のため Piper 本家行とほぼ同等になる見込み。`Kokoro-82M` は別アーキテクチャ、`eSpeak-NG` は非ニューラル CLI のため `scripts/benchmark.py` のテンソル契約に乗らず、別ハーネスが必要)。これらの値は前回計測時 (Apple M2 Max) のもの。

### マルチランタイム RTF ベンチマーク (最新値)

Python / Rust / Go / C# / C++ / WASM の 6 ランタイムを `multilingual-test-medium.onnx` で横断測定した最新の RTF・レイテンシ結果を公開しています。dev ブランチへのマージのたびに自動更新されます。

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## 主要機能

### 音声合成

- **8言語G2P/音素化対応** — 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語・スウェーデン語・韓国語 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7)。現行の学習済みモデルは6言語 (JA/EN/ZH/ES/FR/PT)
- **日本語 TTS** — OpenJTalk統合、韻律情報 (A1/A2/A3)、疑問詞マーカー (#204)、文脈依存「ん」バリアント (#207)
- **英語 TTS** — v2.0.2 では [g2p-en](https://github.com/Kyubyong/g2p) 由来の G2P を Apache-2.0 の推論コードと Tacotron の MIT 許諾表示付きで同梱しています。外部の `g2p-en` / `Distance` や espeak-ng は不要です。旧 PyPI 2.0.1 の依存定義は変更されません。[移行ガイド](docs/migration/python-g2p-license.md)を参照してください
- **マルチスピーカー** — 571話者対応 (学習用ベースモデル)、SpeakerBalancedBatchSampler、言語グループ均等サンプリング
- **カスタム辞書** — JSON (v1/v2) / TSV によるユーザー発音辞書の追加に対応
- **音素入力** — `[[ phonemes ]]` 記法による直接指定 — [ガイド](docs/features/phoneme-input.md)

### 学習

- **WavLM Discriminator** — MOS +0.15-0.25 向上 (デフォルト有効、学習時のみ使用)
- **MB-iSTFT-VITS2 Decoder** — Decoder を MB-iSTFT + PQMF に統一、CPU 推論 2.21x 高速化。ONNX 形式不変で既存ランタイム互換
- **BF16 Mixed Precision** — `--precision bf16-mixed` が既定 (TF32 も既定で有効)。FP16 より数値が安定し loss scaling 不要。BF16 非対応の GPU (T4 等) では `--precision 16-mixed` を指定
- **EMA** — Exponential Moving Average による学習安定性向上 (デフォルト有効)
- **マルチGPU** — DDP対応、自動学習率スケーリング
- **Prosody Features** — Duration Predictorへの韻律情報注入 (`--prosody-dim 16`)
- **Wandb統合** — リアルタイムメトリクス監視

### インターフェース

- **[WebUI (Gradio)](docs/features/webui.md)** — 推論対応、Docker対応。local の Training Tab は旧CLI引数を送るため、学習には [学習ガイド](docs/guides/training/training-guide.md) を使用してください。
- **C++ CLI** — ストリーミング、CUDA推論、**音素タイミング出力 (JSON/TSV/SRT)**、カスタム辞書
- **[C API 共有ライブラリ](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`、FFI対応 (Flutter/Godot/Swift等)、ストリーミング API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package)、合成エンジン本体を iOS arm64 device + simulator universal で配信
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — `PiperPlusG2P` 単独ライブラリ、8言語の G2P を ONNX Runtime 非依存で iOS 上で利用可能 (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — ブラウザ内で完全動作、**音素タイミング出力 (JSON/TSV/SRT)**、サーバー不要
- **[Docker](docker/README.md)** — 推論・学習・WebUI・C++ (推論/開発)・Wyoming (Home Assistant) の6イメージ提供
- **PyPI** — `pip install piper-plus` で簡単インストール、8言語G2P/音素化 (現行の学習済みモデルは6言語)、**音素タイミング出力 (JSON/TSV/SRT)**、ストリーミング、HTTP API
- **C# CLI** — .NET 10 クロスプラットフォーム、8言語G2P/音素化 (現行の学習済みモデルは6言語)、ONNX推論、**音素タイミング出力 (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli、ストリーミング、CUDA/CoreML/DirectML対応、**音素タイミング出力 (JSON/TSV/SRT)**、辞書自動ダウンロード
- **[Go CLI](src/go/README.md)** — HTTP APIサーバー、セッションプーリング、Docker対応、シングルバイナリ、**音素タイミング出力 (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — 全 6 ランタイム (Python/Rust/C#/Go/WASM/C++) でモデル互換の事前計算 `speaker_embedding` 入力に対応。C++ CLI/C API は事前計算 embedding のみ受け付け、`--reference-audio` による抽出は未実装。公開 `zs-v1` の実推論確認は Python `piper-plus==2.0.0` のみ。公開 CI run `38189966578` では Python 共有 phoneme IDs を入力に6ランタイム推論を確認済みで、native G2P と人手試聴品質は範囲外、品質承認は未実施です。
- **SSML サポート** — SSML パーサー契約は Python/Rust/Go/C#/WASM/C++ に実装。合成側は Python/Rust/Go/WASM/C++ が対応し、C# Core にはパーサーがありますが CLI の `--text` には未接続です。C++ は CLI `--ssml` 経由（C API 非エクスポート）。
- **短文品質改善 (Strategy A/B/C)** — Strategy A/B は各ランタイムで実装。Strategy C（SSML `<break>` 自動注入）は Python 推論/Rust/Go/C# の範囲で、訓練用 Python・WASM・C++ は対象外です。詳細は [短文契約](docs/spec/short-text-contract.toml)。

### ランタイム別機能サポート

6 ランタイム (Python/Rust/C#/Go/JS-WASM/C++) で現行学習済みモデルの6言語合成を実現し、8言語のG2P/音素化も提供します。音素タイミング・ストリーミング (文単位分割含む)・モデル互換の事前計算 embedding を使う Voice Cloning・カスタム辞書はランタイム機能として対応。C++ は事前計算 embedding のみで `--reference-audio` は未実装。公開 `zs-v1` の実推論確認は Python `piper-plus==2.0.0` のみです。公開 CI run `38189966578` は Python 共有 phoneme IDs による6ランタイム推論を確認しますが、native G2P と人手試聴品質は範囲外で、品質承認は未実施です。SSML の合成側対応は Python/Rust/Go/WASM/C++（C++ は CLI `--ssml` 経由、C API 非エクスポート）。C# Core のパーサーは CLI `--text` に未接続、HTTP API は Python/Go の 2 ランタイム対応。

---

## クイックスタート

### プリビルドバイナリ (ビルド不要)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリをダウンロードして、すぐに音声合成を開始できます。

**1. バイナリをダウンロード**

お使いのOSに合わせてダウンロード・展開してください。

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-windows-x64.zip" -OutFile piper-plus-cpp.zip
Expand-Archive piper-plus-cpp.zip -DestinationPath .
cd piper-plus
```

**macOS (Apple Silicon):**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-macos-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
xattr -cr .
```

**Linux (x86_64):**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-x64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARM64, Raspberry Pi 4/5):**

**ARM64 の互換性:** v2.0.2 の Linux ARM64 C++ 配布物は glibc 2.31 を ABI 上限として検査します。Debian Bullseye / Bookworm / Trixie（64bit）での起動と日本語合成を QEMU で検証します。Raspberry Pi 実機と Raspberry Pi OS 自体は未検証です。旧 v2.0.1 配布物は glibc 2.38 以上を必要とするため、v2.0.2 を使用してください。

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, 32bit ARM):**

ARMv7 の配布物は C++ CLI のみです。CI では QEMU 上の Debian Trixie (32bit ARM) でビルドと日本語合成を確認しています。Raspberry Pi 実機は未検証です。

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. モデルをダウンロード & 音声を生成**

```sh
# つくよみちゃんモデルをダウンロード
./bin/piper-plus --download-model tsukuyomi

# 音声を生成 (モデル名だけで OK — ダウンロード済みモデルを自動解決)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd のコードページについて:** `--text` オプションは内部で `GetCommandLineW()` (UTF-16) を使用するため、コードページに依存せずそのまま動作します。パイプ入力（`echo ... | piper-plus`）を使う場合のみ、事前に `chcp 65001` で UTF-8 に切り替えてください。
>
> **output.wav の出力先:** カレントディレクトリ（`cd piper-plus` した場所）に生成されます。

> **どのバイナリを選べばよい？** Releases には `piper-plus-cpp-*` (C++) のほか、`piper-plus-cli-*` (C# .NET) と `piper-plus-rs-cli-*` (Rust) のCLIもあります。上記のクイックスタートで使っている **C++ CLI (`piper-plus-cpp-*`)** が最も多くのプラットフォームに対応していて推奨です。詳しくは [CLIバイナリの選び方](docs/getting-started/binary-selection.md) を参照。

### Python推論

```bash
# インストール
# リポジトリルートの source checkout から実行
uv sync --extra inference

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

主なオプション: `--speaker-id`(話者ID)、`--device auto|cpu|gpu`、`--noise-scale`(音声バリエーション)、`--length-scale`(話速)、`--noise-scale-w`(音素長バリエーション、デフォルト: 0.5)

> **WavLMモデルの推奨設定:** WavLM Discriminatorで学習されたモデル (つくよみちゃん等) は `--noise-scale 0.5` で最適な音質になります (デフォルトは 0.4)。

#### Python CLI モデル管理

```bash
# モデル一覧表示
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# モデルダウンロード
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# ダウンロード後に使用
uv run --no-sync python -m piper_plus --model ja_JP-tsukuyomi-chan-medium -f output.wav "こんにちは"
```

### WebUI

```bash
uv sync --project environments/webui --locked
uv run --project environments/webui --no-sync python -m piper_plus.webui --data-dir /path/to/models
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
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

詳細は [docker/README.md](docker/README.md) を参照。

---

## インストール

### Python

Python 3.13+ 推奨 (3.11+ サポート)。依存管理は [uv](https://docs.astral.sh/uv/) を推奨。

```bash
# CPU推論
uv sync --extra inference

# GPU推論 (CUDA環境が必要)
uv sync --no-group cpu --extra inference-gpu

# 学習
uv sync --extra train

# 開発 (テスト・リンター含む)
uv sync --extra dev
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
piper-plus = "0.5"
```

### ソースからビルド

プリビルドバイナリが提供されていないプラットフォームで使う場合や piper-plus を改変したい場合は、ソースからビルドできます。C++ / C# / Rust の各ランタイムのビルド手順は **[ソースからのビルドガイド](docs/guides/development/building-from-source.md)** を参照してください。

---

## 使い方

C++ CLI の詳細なコマンドラインオプション、JSON 入力フォーマット、モデル管理、環境変数、Windows ヘルパースクリプトの使い方は **[CLI 使用ガイド](docs/guides/development/cli-usage.md)** を参照してください。

簡単な使用例:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## 学習

ピパープラスモデルの学習・ファインチューニング方法 (基本設定、マルチスピーカー / マルチ GPU、ONNX 変換、チェックポイント管理、音声評価) は **[学習ガイド](docs/guides/training/training-guide.md)** を参照してください。

実運用向けの 6 言語事前学習・つくよみちゃんファインチューニングのコマンドテンプレートは [CLAUDE.md](CLAUDE.md) にあります。

---

## 事前学習済みモデル

公開されている piper-plus モデルの一覧、ダウンロード方法、6 言語ベースモデルの特徴、日本語 TTS の詳細は **[モデルガイド](docs/guides/development/pretrained-models.md)** を参照してください。

主要モデル: `tsukuyomi` (日本語), `zs-v1` (6 言語 Zero-Shot/FT 実験ベース), `bilingual-ja-en-v4` (日英 2 言語) — 詳細は HuggingFace の [固定公開 zs-v1 バンドル](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) や [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) を参照してください。

> **Zero-Shot/FT ベース (`zs-v1`, 2026-10-10):** 固定公開バンドルは既存の v7 epoch 32 実験基準版（JA/EN/ZH/ES/FR/PT、571 話者、173 音素、CAM++ 192 次元）です。Zero-Shot 推論は `base.onnx` と同梱 `campplus.onnx` から抽出した参照 embedding、追加学習は `base.ckpt` と同梱 `config.json` を使ってください。PyPI `piper-plus==2.0.0` の公開例で機能確認済みですが、品質承認・人手試聴合格・最新/最高品質を意味しません。`base` / `zero-shot-base-zs-v1` alias は v2.0.2 に収録されています（2.0.0 / 2.0.1 には未収録）。ルートの `model.ckpt` は旧世代として別扱いです。

> **つくよみちゃんFT (`zs-v1`, 2026-10-15):** 同じ公開base世代を追加学習した[固定公開モデル](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1)を公開しました。`tsukuyomi.onnx`と`tsukuyomi.onnx.json`を組み合わせれば、参照音声やCAM++なしで生成できます。日本語3文の人手確認を記録し、実験版としての公開を承認済みです（quality_approval=false、品質承認ではありません）。既存の`tsukuyomi` aliasは引き続き旧rootモデルを選ぶため、新モデルは[モデルガイド](docs/guides/development/pretrained-models.md)の固定URLから取得してください。

---

## プラットフォーム

- **macOS**: Apple Silicon (arm64) ネイティブ対応。詳細は [macOS セットアップ](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません) 参照
- **Windows**: C++ 配布物は x64、C# CLI は x64 / arm64。OpenJTalk セットアップは [Windows セットアップガイド](docs/getting-started/windows-setup.md)
- **WebAssembly**: ブラウザで完全オフライン実行。[デモ](https://ayutaz.github.io/piper-plus/) | [npm パッケージ](https://www.npmjs.com/package/piper-plus)

---

## 関連リンク

### Unity — uPiper

Piper を Unity で使用するプラグイン: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+、Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2) 対応
- 7言語対応 (ja/en/zh/es/fr/pt/ko)、非同期API、ストリーミング

### 音声モデル (Voices)

piper-plus 専用モデル: [zs-v1 Zero-Shot/FT ベース](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [つくよみちゃん](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

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
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [ソースコード](android/piper-plus-g2p/) · [辞書配布ガイド](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## ドキュメント

| カテゴリ | リンク |
|---|---|
| 学習 | [学習ガイド](docs/guides/training/training-guide.md) (マルチGPU 含む) |
| API | [音素マッピング](docs/api-reference/phoneme-mapping.md) · [環境変数](docs/getting-started/environment-variables.md) |
| 機能 | [WebUI](docs/features/webui.md) · [音素タイミング](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| セットアップ | [Windows](docs/getting-started/windows-setup.md) · [トラブルシューティング](docs/getting-started/troubleshooting.md) |
| Docker | [Docker環境](docker/README.md) |
| WebAssembly | [技術詳細](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) を参照。質問やバグ報告は [Issues](https://github.com/ayutaz/piper-plus/issues) へどうぞ。行動規範は [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) を参照してください。

## Changelog

[CHANGELOG.md](CHANGELOG.md) を参照。

## 謝辞

piper-plus の GPU を使う実験は、[CloudRift](https://www.cloudrift.ai/) の AI Builder Grant（GPU クレジット）の支援を受けています。
