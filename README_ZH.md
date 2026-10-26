![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | 中文 | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**软件包：**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 唯一采用 MIT 许可证的 Piper 分支** — 原版 [rhasspy/piper](https://github.com/rhasspy/piper) 已于 2025 年 10 月归档，[OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) 已转为 GPL-3.0。piper-plus 是唯一不依赖 espeak-ng 的 MIT 兼容分支。自研 G2P 支持 8 种语言 (JA/EN/ZH/KO/ES/FR/PT/SV)，适合商用和嵌入式场景。

> **📢 v2.0.0 重大变更：** Docker 默认镜像使用 CUDA 12.8 + Ubuntu 24.04 + Python 3.13（宿主机 NVIDIA 驱动需 **R570+**）。训练使用 torch **2.11.0** + CUDA 12.8，默认启用 TF32 + bf16-mixed。不支持恢复 torch 2.2 生成的检查点。Python 的 import / CLI 已改为 `piper_plus` / `piper-plus`。从 1.13.0 更新到当前公开版本时，请运行 `pip install --upgrade "piper-plus[cpu]==2.0.2"`。详情：[迁移指南](docs/migration/v1.12-to-v2.0.md)。

快速、高质量的神经网络文本转语音 (TTS) 系统。基于 [VITS](https://github.com/jaywalnut310/vits/) 架构，支持 8 种语言的 G2P/音素化，并可使用当前覆盖 6 种语言的训练模型进行多说话人语音合成。本项目是 [Piper](https://github.com/rhasspy/piper) 的分支，大幅增强了日语支持、音质和训练功能。

**[Hugging Face 演示](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly 演示](https://ayutaz.github.io/piper-plus/)**（在浏览器中运行，无需服务器）

---

## 目录

- [基准测试](#基准测试)
- [主要功能](#主要功能)
- [快速入门](#快速入门)
- [安装](#安装)
- [使用方法](#使用方法)
- [训练](#训练-1)
- [预训练模型](#预训练模型)
- [平台支持](#平台支持)
- [相关链接](#相关链接)

---

## 基准测试

> **测试环境**：Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cores / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **测试文本**："Hello, how are you doing today?"（英语，25 个音素）
> **测试参数**：预热 5 次 / 测量 30 次 (intra-op threads = auto)
> **使用的模型**：
>
> - piper-plus：6lang MB-iSTFT 75epoch ONNX（PR #320 引入的统一解码器）
> - Piper 原版：`en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx：`vits-piper-en_US-amy-low`（k2-fsa 发布版）
>
> **复现**：`uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| 系统 | RTF ↓ | Latency P50 (ms) | 大小 (MB) | RAM (MB) | 首次启动 (ms) | 参数量 | 语言数 | 许可证 |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper 原版 (archived) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/model | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/model | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/model | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **注**：RTF (Real-Time Factor) 越低越快。`Latency P50` 是单次推理的中位数，直接反映“实际响应速度”。piper-plus 借助 MB-iSTFT 统一解码器实现了最快的 Latency P50 27ms（比 Piper 原版的 35ms 快 23%，比 sherpa-onnx 的 53ms 快 49%），模型大小也仅 38MB，属于最小一档。与旧版基于 HiFi-GAN 的 piper-plus（P50 43.3ms）相比也改善了 38%。
>
> 带 **†** 的行未在本 PR 中重新测量（`piper1-gpl` 与 Piper 原版架构和 ONNX 格式相同，预计与 Piper 原版行基本相当；`Kokoro-82M` 是不同架构，`eSpeak-NG` 是非神经网络 CLI，二者均不符合 `scripts/benchmark.py` 的张量契约，需要单独的测试框架）。这些数值来自上一次测量 (Apple M2 Max)。

### 多运行时 RTF 基准测试（最新数据）

我们公开了使用 `multilingual-test-medium.onnx` 横向测量 Python / Rust / Go / C# / C++ / WASM 共 6 个运行时的最新 RTF 和延迟结果。每次合并到 dev 分支时都会自动更新。

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## 主要功能

### 语音合成

- **8 种语言的 G2P/音素化** — 日语、英语、普通话、西班牙语、法语、葡萄牙语、瑞典语、韩语 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7)。当前训练模型覆盖 6 种语言 (JA/EN/ZH/ES/FR/PT)
- **日语 TTS** — OpenJTalk 集成、韵律信息 (A1/A2/A3)、疑问词标记 (#204)、上下文相关的「ん」变体 (#207)
- **英语 TTS** — v2.0.2 内置源自 [g2p-en](https://github.com/Kyubyong/g2p) 的 G2P，附带 Apache-2.0 推理代码及 Tacotron 的 MIT 许可声明。无需外部 `g2p-en` / `Distance` 或 espeak-ng。旧版 PyPI 2.0.1 的依赖定义保持不变。请参阅[迁移指南](docs/migration/python-g2p-license.md)
- **多说话人** — 支持 571 位说话人（训练用基础模型）、SpeakerBalancedBatchSampler、按语言组均衡采样
- **自定义词典** — 内置 200+ 技术术语的发音词典
- **音素输入** — 使用 `[[ phonemes ]]` 标记直接指定音素 — [指南](docs/features/phoneme-input.md)

### 训练

- **WavLM Discriminator** — MOS 提升 +0.15-0.25（默认启用，仅在训练时使用）
- **MB-iSTFT-VITS2 解码器** — 解码器统一为 MB-iSTFT + PQMF，CPU 推理速度提升 2.21 倍。ONNX 格式不变，兼容现有运行时
- **BF16 混合精度** — 默认使用 `--precision bf16-mixed`（TF32 也默认启用）。数值比 FP16 更稳定，无需 loss scaling。在不支持 BF16 的 GPU（如 T4）上请指定 `--precision 16-mixed`
- **EMA** — 通过 Exponential Moving Average 提高训练稳定性（默认启用）
- **多 GPU** — 支持 DDP，自动缩放学习率
- **Prosody Features** — 向 Duration Predictor 注入韵律信息 (`--prosody-dim 16`)
- **Wandb 集成** — 实时监控指标

### 接口

- **[WebUI (Gradio)](docs/features/webui.md)** — 支持推理和 Docker。本地的 Training Tab 仍会发送旧版 CLI 参数，训练请使用[训练指南](docs/guides/training/training-guide.md)。
- **C++ CLI** — 流式处理、CUDA 推理、**音素时间戳输出 (JSON/TSV/SRT)**、自定义词典
- **[C API 共享库](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`，支持 FFI (Flutter/Godot/Swift 等)，流式 API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package)，以 iOS arm64 设备 + 模拟器通用 xcframework 形式分发合成引擎本体
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — 独立库 `PiperPlusG2P`，无需依赖 ONNX Runtime 即可在 iOS 上使用 8 种语言的 G2P (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — 完全在浏览器内运行，**音素时间戳输出 (JSON/TSV/SRT)**，无需服务器
- **[Docker](docker/README.md)** — 提供推理、训练、WebUI、C++（推理/开发）、Wyoming (Home Assistant) 共 6 个镜像
- **PyPI** — 通过 `pip install piper-plus` 轻松安装，8 种语言的 G2P/音素化（当前训练模型覆盖 6 种语言），**音素时间戳输出 (JSON/TSV/SRT)**，流式处理，HTTP API
- **C# CLI** — .NET 10 跨平台，8 种语言的 G2P/音素化（当前训练模型覆盖 6 种语言），ONNX 推理，**音素时间戳输出 (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli，流式处理，支持 CUDA/CoreML/DirectML，**音素时间戳输出 (JSON/TSV/SRT)**，词典自动下载
- **[Go CLI](src/go/README.md)** — HTTP API 服务器、会话池、支持 Docker、单一二进制文件、**音素时间戳输出 (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — 全部 6 个运行时 (Python/Rust/C#/Go/WASM/C++) 均支持与模型兼容的预计算 `speaker_embedding` 输入。C++ CLI/C API 仅接受预计算 embedding，尚未实现通过 `--reference-audio` 提取。公开 `zs-v1` 的实际推理仅在 Python `piper-plus==2.0.0` 中确认。公开 CI run `38189966578` 已确认以 Python 共享 phoneme IDs 为输入的 6 运行时推理，但 native G2P 与人工试听质量不在范围内，尚未进行质量批准。
- **SSML 支持** — SSML 解析器契约已在 Python/Rust/Go/C#/WASM/C++ 中实现。合成侧由 Python/Rust/Go/WASM/C++ 支持；C# Core 虽有解析器，但尚未接入 CLI 的 `--text`。C++ 通过 CLI `--ssml` 使用（C API 未导出）。
- **短文本质量改进 (Strategy A/B/C)** — Strategy A/B 已在各运行时中实现。Strategy C（自动注入 SSML `<break>`）的范围为推理 Python/Rust/Go/C#，训练用 Python、WASM 和 C++ 不在范围内。详见[短文本契约](docs/spec/short-text-contract.toml)。

### 各运行时功能支持

6 个运行时 (Python/Rust/C#/Go/JS-WASM/C++) 均可使用当前训练模型进行 6 种语言的合成，并提供 8 种语言的 G2P/音素化。音素时间戳、流式处理（含按句分割）、使用模型兼容预计算 embedding 的 Voice Cloning 以及自定义词典均作为运行时功能提供支持。C++ 仅支持预计算 embedding，尚未实现 `--reference-audio`。公开 `zs-v1` 的实际推理仅在 Python `piper-plus==2.0.0` 中确认。公开 CI run `38189966578` 确认了使用 Python 共享 phoneme IDs 的 6 运行时推理，但 native G2P 与人工试听质量不在范围内，尚未进行质量批准。SSML 合成侧由 Python/Rust/Go/WASM/C++ 支持（C++ 通过 CLI `--ssml`，C API 未导出）。C# Core 的解析器尚未接入 CLI 的 `--text`，HTTP API 由 Python/Go 两个运行时支持。

---

## 快速入门

### 预构建二进制文件（无需构建）

从 [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) 下载预构建二进制文件，即可立即开始语音合成。

**1. 下载二进制文件**

请根据您的操作系统下载并解压。

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

**ARM64 兼容性：** v2.0.2 的 Linux ARM64 C++ 发布包以 glibc 2.31 作为 ABI 上限进行检查。会在 QEMU 下的 Debian Bullseye / Bookworm / Trixie（64 位）中验证启动和日语合成。Raspberry Pi 实机及 Raspberry Pi OS 本身尚未验证。旧版 v2.0.1 发布包需要 glibc 2.38 及以上，请使用 v2.0.2。

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7，32 位 ARM):**

ARMv7 仅提供 C++ CLI 发布包。CI 在 QEMU 下的 Debian Trixie（32 位 ARM）中验证构建和日语合成。Raspberry Pi 实机尚未验证。

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. 下载模型并生成语音**

```sh
# 下载 Tsukuyomi-chan 模型
./bin/piper-plus --download-model tsukuyomi

# 生成语音（只需模型名即可 — 自动解析已下载的模型）
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **关于 Windows cmd 的代码页：** `--text` 选项内部使用 `GetCommandLineW()` (UTF-16)，因此不依赖代码页即可直接使用。仅在使用管道输入（`echo ... | piper-plus`）时，需要事先运行 `chcp 65001` 切换到 UTF-8。
>
> **output.wav 的输出位置：** 生成在当前目录（即执行 `cd piper-plus` 后所在的位置）。

> **应该选择哪个二进制文件？** Releases 中除 `piper-plus-cpp-*` (C++) 外，还提供 `piper-plus-cli-*` (C# .NET) 和 `piper-plus-rs-cli-*` (Rust) CLI。上述快速入门使用的 **C++ CLI (`piper-plus-cpp-*`)** 支持的平台最多，推荐使用。详情请参阅[选择 CLI 二进制文件](docs/getting-started/binary-selection.md)。

### Python 推理

```bash
# 安装
# 在 source checkout 的仓库根目录执行
uv sync --extra inference

# 日语推理
uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --config /path/to/config.json \
    --output-dir ./output \
    --text "こんにちは、今日は良い天気ですね。"

# 英语推理
uv run python -m piper_train.infer_onnx \
    --model /path/to/en_model.onnx \
    --config /path/to/en_model.onnx.json \
    --output-dir ./output \
    --text "Hello, how are you today?" \
    --language en
```

主要选项：`--speaker-id`（说话人 ID）、`--device auto|cpu|gpu`、`--noise-scale`（语音变化）、`--length-scale`（语速）、`--noise-scale-w`（音素时长变化，默认：0.5）

> **WavLM 模型的推荐设置：** 使用 WavLM Discriminator 训练的模型（如 Tsukuyomi-chan 等）在 `--noise-scale 0.5` 时音质最佳（默认值为 0.4）。

#### Python CLI 模型管理

```bash
# 显示模型列表
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# 下载模型
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# 下载后使用
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

# Python 推理 (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device cpu

# GPU 推理（添加 --gpus all）
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

推荐 Python 3.13+（支持 3.11+）。推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

```bash
# CPU 推理
uv sync --extra inference

# GPU 推理（需要 CUDA 环境）
uv sync --no-group cpu --extra inference-gpu

# 训练
uv sync --extra train

# 开发（包含测试和 linter）
uv sync --extra dev
```

也可以通过 PyPI 包安装：

```bash
pip install piper-plus
```

### 从包管理器安装

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm（浏览器 WASM）:**

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

如果您使用的平台没有提供预构建二进制文件，或者想要修改 piper-plus，可以从源码构建。C++ / C# / Rust 各运行时的构建步骤请参阅 **[从源码构建指南](docs/guides/development/building-from-source.md)**。

---

## 使用方法

C++ CLI 的详细命令行选项、JSON 输入格式、模型管理、环境变量以及 Windows 辅助脚本的用法，请参阅 **[CLI 使用指南](docs/guides/development/cli-usage.md)**。

简单示例：

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## 训练

piper-plus 模型的训练和微调方法（基本设置、多说话人 / 多 GPU、ONNX 转换、检查点管理、语音评估）请参阅 **[训练指南](docs/guides/training/training-guide.md)**。

面向实际使用的 6 语言预训练和 Tsukuyomi-chan 微调的命令模板位于 [CLAUDE.md](CLAUDE.md)。

---

## 预训练模型

已公开的 piper-plus 模型列表、下载方法、6 语言基础模型的特点以及日语 TTS 的详细信息，请参阅 **[模型指南](docs/guides/development/pretrained-models.md)**。

主要模型：`tsukuyomi`（日语）、`zs-v1`（6 语言 Zero-Shot/FT 实验基础模型）、`bilingual-ja-en-v4`（日英双语）— 详情请参阅 HuggingFace 上的[固定公开 zs-v1 bundle](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) 和 [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)。

> **Zero-Shot/FT 基础模型 (`zs-v1`, 2026-10-10)：** 固定公开 bundle 是现有的 v7 epoch 32 实验基准版（JA/EN/ZH/ES/FR/PT，571 位说话人，173 个音素，CAM++ 192 维）。Zero-Shot 推理请使用 `base.onnx` 以及由随附 `campplus.onnx` 提取的参考 embedding；追加训练请使用 `base.ckpt` 和随附的 `config.json`。已通过 PyPI `piper-plus==2.0.0` 的公开示例完成功能确认，但这并不代表质量批准、人工试听合格或最新/最高质量。`base` / `zero-shot-base-zs-v1` 别名已收录于 v2.0.2（2.0.0 / 2.0.1 中未收录）。根目录的 `model.ckpt` 作为旧一代模型另行处理。

> **Tsukuyomi-chan 微调 (`zs-v1`, 2026-10-15)：** 我们发布了基于同一公开基础模型世代追加训练的[固定公开模型](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1)。将 `tsukuyomi.onnx` 与 `tsukuyomi.onnx.json` 搭配使用，无需参考音频或 CAM++ 即可生成语音。已记录 3 句日语的人工确认，并批准作为实验版发布（quality_approval=false，并非质量批准）。现有的 `tsukuyomi` 别名仍会选择旧的根目录模型，因此请通过[模型指南](docs/guides/development/pretrained-models.md)中的固定 URL 获取新模型。

---

## 平台支持

- **macOS**：原生支持 Apple Silicon (arm64)。详情请参阅 [macOS 设置](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**：C++ 发布包为 x64，C# CLI 为 x64 / arm64。OpenJTalk 的设置请参阅 [Windows 设置指南](docs/getting-started/windows-setup.md)
- **WebAssembly**：在浏览器中完全离线运行。[演示](https://ayutaz.github.io/piper-plus/) | [npm 包](https://www.npmjs.com/package/piper-plus)

---

## 相关链接

### Unity — uPiper

在 Unity 中使用 Piper 的插件：[github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+，Unity.InferenceEngine
- 支持 Windows / macOS (Apple Silicon) / Linux / Android
- 支持日语和英语，异步 API，流式处理

### 语音模型 (Voices)

piper-plus 专用模型：[zs-v1 Zero-Shot/FT 基础模型](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note:** piper-plus 使用自有的 G2P 和音素体系，因此与上游 Piper (rhasspy/piper-voices) 的模型不兼容。

### 相关文章（日语）

- [使用 LJSpeech 创建英语 Piper 预训练模型](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [使用 JVS 语音数据集创建 Piper 日语模型](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [使用 Tsukuyomi-chan 数据集对 Piper 模型进行追加训练](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p（独立 G2P 包）

以独立包形式提供多语言 G2P (Grapheme-to-Phoneme)：

- **Python**：`pip install piper-plus-g2p` — [源代码](src/python/g2p/)
- **Rust**：`cargo add piper-plus-g2p` — [源代码](src/rust/piper-plus-g2p/)
- **Go**：`go get github.com/ayutaz/piper-plus/src/go/phonemize` — [源代码](src/go/phonemize/)
- **JavaScript/WASM**：`npm install @piper-plus/g2p` — [源代码](src/wasm/g2p/)
- **Kotlin/Android**：`implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [源代码](android/piper-plus-g2p/) · [词典分发指南](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## 文档

| 类别 | 链接 |
|---|---|
| 日语 TTS | 日语语音合成指南 |
| 训练 | [训练指南](docs/guides/training/training-guide.md) · 多 GPU |
| API | [音素映射](docs/api-reference/phoneme-mapping.md) · [环境变量](docs/getting-started/environment-variables.md) |
| 功能 | [WebUI](docs/features/webui.md) · CLI 增强 · 流式处理 |
| 设置 | 快速入门（日语） · [Windows](docs/getting-started/windows-setup.md) · [故障排除](docs/getting-started/troubleshooting.md) |
| Docker | [Docker 环境](docker/README.md) |
| WebAssembly | [技术详情](src/wasm/openjtalk-web/README.npm.md) |

## 贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。如有问题或 bug 报告，请提交至 [Issues](https://github.com/ayutaz/piper-plus/issues)。行为准则请参阅 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 更新日志

请参阅 [CHANGELOG.md](CHANGELOG.md)。

## 致谢

piper-plus 使用 GPU 的实验得到了 [CloudRift](https://www.cloudrift.ai/) AI Builder Grant（GPU 额度）的支持。
