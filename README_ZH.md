![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | 中文 | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**软件包：**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 唯一采用 MIT 许可证的 Piper 分支** — 原版 [rhasspy/piper](https://github.com/rhasspy/piper) 已于 2025 年 10 月归档，[OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) 已转为 GPL-3.0。piper-plus 是唯一不依赖 espeak-ng 的 MIT 兼容分支。自研 G2P 支持 8 种语言 (JA/EN/ZH/KO/ES/FR/PT/SV)，适合商用和嵌入式场景。

> **📢 v2.0.0 重大变更（2026-05，正在 `dev` 分支准备中，最新发布标签为 v1.13.0）：** 默认 Docker 镜像统一为 CUDA 12.8 + Ubuntu 24.04 + Python 3.13（需要宿主机 NVIDIA 驱动 **R570+**；旧版驱动无法启动新镜像）/ 训练更新至 torch 2.11+cu128（torch 2.2 生成的检查点无法续训）/ TF32 + bf16-mixed 成为新的训练默认值。详情：[docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

快速、高质量的神经网络文本转语音 (TTS) 系统。基于 [VITS](https://github.com/jaywalnut310/vits/) 架构，支持8种语言（日语、英语、普通话、韩语、西班牙语、法语、葡萄牙语、瑞典语）的多说话人语音合成。本项目是 [Piper](https://github.com/rhasspy/piper) 的分支，大幅增强了日语支持、音质和训练功能。

**[Hugging Face 演示](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly 演示](https://ayutaz.github.io/piper-plus/)** (浏览器运行，无需服务器)

---

## 目录

- [基准测试](#基准测试)
- [主要功能](#主要功能)
- [快速入门](#快速入门)
- [安装](#安装)
- [使用方法](#使用方法)
- [训练](#训练)
- [预训练模型](#预训练模型)
- [平台支持](#平台支持)
- [相关链接](#相关链接)

---

## 基准测试

> **测量环境**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cores / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **测试文本**: "Hello, how are you doing today?"（英语，25 个音素）
> **测量参数**: warmup 5 次 / 测量 30 次 (intra-op threads = auto)
> **使用模型**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX（PR #320 引入的统一解码器）
> - Piper 原版: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa 发布版)
>
> **复现**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| 系统 | RTF ↓ | Latency P50 (ms) | 大小 (MB) | RAM (MB) | 冷启动 (ms) | 参数量 | 语言数 | 许可证 |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper 原版 (已归档) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/model | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/model | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/model | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **注**: RTF (Real-Time Factor) 越低越快。`Latency P50` 是单次推理耗时的中位数，最直接地反映“实际响应速度”。piper-plus 凭借 MB-iSTFT 统一解码器实现了最快的 Latency P50 27ms（比 Piper 原版 35ms 快 23%，比 sherpa-onnx 53ms 快 49%），模型大小 38MB 也属最小之列。与旧版 piper-plus HiFi-GAN 基线 (P50 43.3ms) 相比同样改善了 38%。
>
> **†** 标注的行未在本 PR 中重新测量（`piper1-gpl` 与 Piper 原版采用相同架构和 ONNX 格式，预计与 Piper 原版行大致相当；`Kokoro-82M` 是不同架构，`eSpeak-NG` 是非神经网络 CLI，二者均不符合 `scripts/benchmark.py` 的张量契约，需要单独的测量工具）。这些数值来自此前在 Apple M2 Max 上的测量。

### 多运行时 RTF 基准测试（最新值）

我们公开了使用 `multilingual-test-medium.onnx` 对 Python / Rust / Go / C# / C++ / WASM 共 6 个运行时进行横向测量的最新 RTF 与延迟结果。每次合并到 dev 分支时自动更新。

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## 主要功能

### 语音合成

- **8语言支持** — 日语、英语、普通话、西班牙语、法语、葡萄牙语（支持 BR/EU 方言切换：`pt`/`pt-BR`/`pt-PT`）、瑞典语、韩语 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *训练模型覆盖6种语言 (JA/EN/ZH/ES/FR/PT)*
- **日语 TTS** — OpenJTalk 集成、韵律特征 (A1/A2/A3)、疑问标记 (#204)、上下文相关「ん」变体 (#207)
- **英语 TTS** — 无 GPL 依赖的 G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0)，无需 espeak-ng
- **多说话人** — 571 位说话人（训练用基础模型），SpeakerBalancedBatchSampler，语言组均衡采样
- **自定义词典** — 支持通过 JSON (v1/v2) / TSV 添加用户发音词典
- **音素输入** — 使用 `[[ phonemes ]]` 标记直接指定音素 — [指南](docs/features/phoneme-input.md)

### 训练

- **WavLM Discriminator** — MOS 提升 +0.15-0.25（默认启用，仅训练时使用）
- **MB-iSTFT-VITS2 解码器** — 解码器统一为 MB-iSTFT + PQMF，CPU 推理速度提升约 2.21 倍。ONNX 格式不变，兼容现有运行时
- **BF16 混合精度** — `--precision bf16-mixed`（默认）+ TF32 加速训练，内存减少约 50%
- **EMA** — 指数移动平均，提高训练稳定性（默认启用）
- **多 GPU** — DDP 支持，自动学习率缩放
- **韵律特征** — 向 Duration Predictor 注入韵律信息 (`--prosody-dim 16`)
- **Wandb 集成** — 实时指标监控

### 接口

- **[WebUI (Gradio)](docs/features/webui.md)** — 推理和训练，支持 Docker
- **C++ CLI** — 流式处理、CUDA 推理、**Phoneme Timing 输出 (JSON/TSV/SRT)**、自定义词典
- **[C API 共享库](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`，FFI 兼容 (Flutter/Godot/Swift 等)，流式 API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package)，合成引擎本体以 iOS arm64 device + simulator universal 形式分发
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — `PiperPlusG2P` 独立库，无需 ONNX Runtime 即可在 iOS 上使用 8 种语言的 G2P (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — 完全在浏览器中运行，**Phoneme Timing 输出 (JSON/TSV/SRT)**，无需服务器
- **[Docker](docker/README.md)** — 提供推理、训练、WebUI、C++、Wyoming (Home Assistant) 等 7 个系列镜像
- **PyPI** — `pip install piper-plus` 即可安装，8语言多语言支持，**Phoneme Timing 输出 (JSON/TSV/SRT)**，流式处理，HTTP API
- **C# CLI** — .NET 10 跨平台，8语言多语言支持，ONNX 推理，**Phoneme Timing 输出 (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli，流式处理，CUDA/CoreML/DirectML 支持，**Phoneme Timing 输出 (JSON/TSV/SRT)**，词典自动下载
- **[Go CLI](src/go/README.md)** — HTTP API 服务器、会话池、Docker、单一二进制文件、**Phoneme Timing 输出 (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — 全部 6 个运行时 (Python/Rust/C#/Go/WASM/C++) 支持。C++ 同时提供 CLI 二进制和 `libpiper_plus` C API 库两种形式。通过 ECAPA-TDNN 从参考音频提取说话人 embedding (`--reference-audio`)
- **SSML 支持** — `<speak>`、`<break>`、`<prosody rate="...">` 在 Python/Rust/C#/Go/WASM/C++ 共 6 个运行时中实现（C++ 通过 CLI `--ssml`）
- **短文本质量改进 (Strategy A/B/C)** — Silence Padding、Dynamic Scales、SSML `<break>` 自动注入，全部 6 个运行时支持 (`docs/spec/short-text-contract.toml`)

### 各运行时功能支持

6 个运行时 (Python/Rust/C#/Go/JS-WASM/C++) 提供等效的 8 语言多语言合成。Phoneme Timing、流式处理（含按句分割）、Voice Cloning、自定义词典在所有运行时均可用。SSML 在全部 6 个运行时中支持（C++ 通过 CLI `--ssml`，C API 未导出），HTTP API 在 Python/Go 2 个运行时中支持。

---

## 快速入门

### 预构建二进制文件（无需构建）

从 [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) 下载预构建二进制文件，即可立即开始语音合成。

**1. 下载二进制文件**

根据您的操作系统下载并解压。

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

**Linux (ARM64，树莓派 4/5):**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. 下载模型并生成语音**

```sh
# つくよみちゃんモデルをダウンロード
./bin/piper-plus --download-model tsukuyomi

# 音声を生成 (モデル名だけで OK — ダウンロード済みモデルを自動解決)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **关于 Windows cmd 代码页：** `--text` 选项内部使用 `GetCommandLineW()` (UTF-16)，不依赖代码页，可直接使用。仅在使用管道输入（`echo ... | piper-plus`）时，需要先运行 `chcp 65001` 切换到 UTF-8。
>
> **output.wav 输出位置：** 生成在当前目录（即 `cd piper-plus` 后的位置）。

> **应该选择哪个二进制文件？** Releases 中还提供 `piper-plus-cli-*`（C# .NET）和 `piper-plus-rs-cli-*`（Rust）CLI。上述快速入门使用的是 **C++ CLI（`piper-plus-cpp-*`）**，它支持的平台最广，推荐大多数用户使用。详情请参阅[选择 CLI 二进制文件](docs/getting-started/binary-selection.md)。

### Python 推理

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

主要选项：`--speaker-id`（说话人 ID）、`--device auto|cpu|gpu`、`--noise-scale`（音频变化）、`--length-scale`（语速）、`--noise-scale-w`（音素长度变化，默认：0.5）

> **WavLM 模型推荐设置：** 使用 WavLM Discriminator 训练的模型（如 Tsukuyomi-chan 等）建议设置 `--noise-scale 0.5` 以获得最佳音质（默认值为 0.4）。

#### Python CLI 模型管理

```bash
# モデル一覧表示
python -m piper_plus --list-models
python -m piper_plus --list-models ja

# モデルダウンロード
python -m piper_plus --download-model tsukuyomi
python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# ダウンロード後に使用
python -m piper_plus --model ja_JP-tsukuyomi-chan-medium -f output.wav "こんにちは"
```

### WebUI

```bash
uv pip install -r src/python_run/requirements_webui.txt
cd src/python_run
python -m piper_plus.webui --data-dir /path/to/models
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

CI/CD 预构建镜像：

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

详情请参阅 [docker/README.md](docker/README.md)。

---

## 安装

### Python

推荐 Python 3.13+ (支持 3.11+)。推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

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

也可从 PyPI 安装：

```bash
pip install piper-plus
```

### 从包管理器安装

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm (浏览器 WASM):**

```bash
npm install piper-plus onnxruntime-web
```

**C# CLI (.NET 全局工具):**

```bash
dotnet tool install -g PiperPlus.Cli
```

**Rust CLI (crates.io):**

```bash
cargo install piper-plus-cli
```

**C# 库 (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Rust 库 (crates.io):**

```toml
[dependencies]
piper-plus = "0.5"
```

### 从源码构建

如果您的平台没有预构建二进制文件，或者想要修改 piper-plus，可以从源码构建。C++ / C# / Rust 各运行时的构建步骤请参阅 **[源码构建指南](docs/guides/development/building-from-source.md)**。

---

## 使用方法

C++ CLI 的详细命令行选项、JSON 输入格式、模型管理、环境变量以及 Windows 辅助脚本的使用方法，请参阅 **[CLI 使用指南](docs/guides/development/cli-usage.md)**。

简单使用示例：

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## 训练

piper-plus 模型的训练与微调方法（基础配置、多说话人 / 多 GPU、ONNX 导出、检查点管理、语音评估），请参阅 **[训练指南](docs/guides/training/training-guide.md)**。

面向实际生产的 6 语言预训练和 Tsukuyomi-chan 微调命令模板见 [CLAUDE.md](CLAUDE.md)。

---

## 预训练模型

已发布的 piper-plus 模型列表、下载方法、6 语言基础模型的特点以及日语 TTS 的详细信息，请参阅 **[模型指南](docs/guides/development/pretrained-models.md)**。

主要模型：`tsukuyomi`（日语）和 `css10-6lang`（可通过 `--download-model` 获取），以及用于训练/微调的 6 语言基础 ckpt — 详情参阅 HuggingFace 的 [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) 和 [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)。

---

## 平台支持

- **macOS**: 原生支持 Apple Silicon (arm64)。详情参阅 [macOS 设置](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: 支持 x64 / arm64。OpenJTalk 设置请参阅 [Windows 设置指南](docs/getting-started/windows-setup.md)
- **WebAssembly**: 在浏览器中完全离线运行。[演示](https://ayutaz.github.io/piper-plus/) | [npm 包](https://www.npmjs.com/package/piper-plus)

---

## 相关链接

### Unity — uPiper

Piper 的 Unity 插件：[github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+，Unity.InferenceEngine
- 支持 Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2)
- 支持 7 种语言 (ja/en/zh/es/fr/pt/ko)，异步 API，流式处理

### 语音模型 (Voices)

piper-plus 专用模型：[piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base)（6语言基础模型）· [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **注意：** piper-plus 使用自研的 G2P 和音素体系，因此与 upstream Piper (rhasspy/piper-voices) 的模型不兼容。

### 相关文章（日语）

- [使用 LJSpeech 创建英语 Piper 预训练模型](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [使用 JVS 语音数据集创建 Piper 日语模型](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [使用 Tsukuyomi-chan 数据集从 Piper 模型进行微调](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p（独立 G2P 包）

提供多语言 G2P（字素到音素转换）独立包：

- **Python**：`pip install piper-plus-g2p` — [源代码](src/python/g2p/)
- **Rust**：`cargo add piper-plus-g2p` — [源代码](src/rust/piper-plus-g2p/)
- **Go**：`go get github.com/ayutaz/piper-plus/src/go/phonemize` — [源代码](src/go/phonemize/)
- **JavaScript/WASM**：`npm install @piper-plus/g2p` — [源代码](src/wasm/g2p/)
- **Kotlin/Android**：`implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` — [源代码](android/piper-plus-g2p/) · [词典分发指南](docs/guides/platform/android-g2p-dictionary.md)
- **Swift (iOS/macOS)**：SPM product `PiperPlusG2P` — [集成指南](docs/guides/platform/swift-g2p-integration.md) · [源代码](Sources/PiperPlusG2P/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## 文档

| 类别 | 链接 |
|---|---|
| 训练 | [训练指南](docs/guides/training/training-guide.md)（含多 GPU） |
| API | [音素映射](docs/api-reference/phoneme-mapping.md) · [环境变量](docs/getting-started/environment-variables.md) |
| 功能 | [WebUI](docs/features/webui.md) · [Phoneme Timing](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| 设置 | [Windows](docs/getting-started/windows-setup.md) · [故障排除](docs/getting-started/troubleshooting.md) |
| Docker | [Docker 环境](docker/README.md) |
| WebAssembly | [技术详情](src/wasm/openjtalk-web/README.npm.md) |

## 贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。如有问题或错误报告，欢迎提交 [Issues](https://github.com/ayutaz/piper-plus/issues)。行为准则请参阅 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 更新日志

请参阅 [CHANGELOG.md](CHANGELOG.md)。
