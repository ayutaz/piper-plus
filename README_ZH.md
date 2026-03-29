![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | 中文 | [Français](README_FR.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

快速、高质量的神经网络文本转语音 (TTS) 系统。基于 [VITS](https://github.com/jaywalnut310/vits/) 架构，支持6种语言（日语、英语、普通话、西班牙语、法语、葡萄牙语）的多说话人语音合成。本项目是 [Piper](https://github.com/rhasspy/piper) 的分支，大幅增强了日语支持、音质和训练功能。

**[Hugging Face 演示](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly 演示](https://ayutaz.github.io/piper-plus/)** (浏览器运行，无需服务器)

---

## 目录

- [主要功能](#主要功能)
- [快速入门](#快速入门)
- [安装](#安装)
- [使用方法](#使用方法)
- [训练](#训练)
- [预训练模型](#预训练模型)
- [日语 TTS](#日语-tts)
- [平台支持](#平台支持)
- [相关链接](#相关链接)

---

## 主要功能

### 语音合成

- **6语言支持** — 日语、英语、普通话、西班牙语、法语、葡萄牙语 (ja=0, en=1, zh=2, es=3, fr=4, pt=5)
- **日语 TTS** — OpenJTalk 集成、韵律特征 (A1/A2/A3)、疑问标记 (#204)、上下文相关「ん」变体 (#207)
- **英语 TTS** — 无 GPL 依赖的 G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0)，无需 espeak-ng
- **多说话人** — 571说话人的6语言基础模型，SpeakerBalancedBatchSampler，语言均衡采样自动启用
- **自定义词典** — 内置 200+ 技术术语发音词典
- **音素输入** — 使用 `[[ phonemes ]]` 标记直接指定音素 — [指南](docs/features/phoneme-input.md)

### 训练

- **WavLM Discriminator** — MOS 提升 +0.15-0.25（默认启用，仅训练时使用）
- **FP16 混合精度** — 训练速度提升 2-3 倍，内存减少约 50%（默认启用）
- **EMA** — 指数移动平均，提高训练稳定性（默认启用）
- **多 GPU** — DDP 支持，自动学习率缩放
- **韵律特征** — 向 Duration Predictor 注入韵律信息 (`--prosody-dim 16`)
- **Wandb 集成** — 实时指标监控

### 接口

- **[WebUI (Gradio)](docs/features/webui.md)** — 推理和训练，支持 Docker
- **C++ CLI** — 流式处理、CUDA 推理、音素时间输出、自定义词典
- **[WebAssembly](src/wasm/openjtalk-web/README.md)** — 完全在浏览器中运行，无需服务器
- **[Docker](docker/README.md)** — 提供推理、训练、WebUI、C++ 共 5 个镜像
- **PyPI** — `pip install piper-plus`
- **C# CLI** — .NET 8/9 跨平台，6语言多语言支持，ONNX 推理
- **Rust CLI** — piper-plus/piper-plus-cli，流式处理，CUDA/CoreML/DirectML 支持，词典自动下载

### 平台

| 平台 | 架构 | 备注 |
|---|---|---|
| Linux | x86_64 / ARM64 | 完整支持 |
| macOS | ARM64 (Apple Silicon) 仅限 | M1/M2/M3+ |
| Windows | x64 | 完整支持 |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9，Linux/macOS/Windows |
| Rust | x64 / ARM64 | Linux/macOS/Windows，CUDA/CoreML/DirectML |

---

## 快速入门

### 预构建二进制文件（无需构建）

从 [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) 下载预构建二进制文件，即可立即开始语音合成。

**1. 下载二进制文件**

根据您的操作系统下载并解压。

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

**2. 下载模型并生成语音**

```sh
# 下载 Tsukuyomi-chan 模型
./bin/piper --download-model tsukuyomi

# 生成语音（只需模型名 — 自动解析已下载的模型）
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **关于 Windows cmd 代码页：** `--text` 选项内部使用 `GetCommandLineW()` (UTF-16)，不依赖代码页，可直接使用。仅在使用管道输入（`echo ... | piper`）时，需要先运行 `chcp 65001` 切换到 UTF-8。
>
> **output.wav 输出位置：** 生成在当前目录（即 `cd piper` 后的位置）。

### Python 推理

```bash
# 安装
uv pip install ".[inference]"

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

主要选项：`--speaker-id`（说话人 ID）、`--device auto|cpu|gpu`、`--noise-scale`（音频变化）、`--length-scale`（语速）

> **WavLM 模型推荐设置：** 使用 WavLM Discriminator 训练的模型（如 Tsukuyomi-chan 等）建议设置 `--noise-scale 0.5` 以获得最佳音质（默认值为 0.667）。

#### Python CLI 模型管理

```bash
# 显示模型列表
python -m piper --list-models
python -m piper --list-models ja

# 下载模型
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# 下载后使用
python -m piper --model ja_JP-tsukuyomi-chan-medium --text "こんにちは" -f output.wav
```

### WebUI

```bash
uv pip install -r src/python_run/requirements_webui.txt
cd src/python_run
python -m piper.webui --data-dir /path/to/models
# → http://localhost:7860
```

### C++ 二进制

从 [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) 下载 (amd64 / arm64)。

```sh
echo 'Welcome to the world of speech synthesis!' | \
  ./bin/piper --model en_US-lessac-medium.onnx --output_file welcome.wav
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
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main
docker pull ghcr.io/ayutaz/piper-plus/python-train:main
docker pull ghcr.io/ayutaz/piper-plus/webui:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

详情请参阅 [docker/README.md](docker/README.md)。

---

## 安装

### Python

需要 Python 3.11+。推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

```bash
# CPU 推理
uv pip install ".[inference]"

# GPU 推理（需要 CUDA 环境）
uv pip install ".[inference-gpu]"

# 训练
uv pip install ".[train]"

# 开发（包含测试和 lint 工具）
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
piper-plus = "0.1.0"
```

### 从源码构建 (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

前提条件：C++17 编译器、CMake 3.13+

- **Linux**：构建前将 [piper-phonemize](https://github.com/rhasspy/piper-phonemize) 放置到 `lib/Linux-$(uname -m)/piper_phonemize`
- **Windows**：参阅 [Windows 设置指南](docs/getting-started/windows-setup.md)
- **macOS**：依赖项自动下载

### 从源码构建 (C#)

```bash
# C# CLI 构建
dotnet build src/csharp/PiperPlus.sln -c Release
# 测试
dotnet test src/csharp/PiperPlus.Core.Tests/
```

前提条件：.NET 8 SDK 以上

#### C# CLI 使用示例

```bash
# 使用模型名推理（支持自动下载，省略 --output-file 时输出为 output.wav）
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# 英语
piper-plus --model model.onnx --text "Hello world" --language en

# 多语言（自动语言检测）
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# 内联音素标记（在文本中直接指定音素）
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# 流式处理（逐句输出 PCM）
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# 自定义词典（JSON v1/v2 或 TSV）
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# 模型下载
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# 测试模式（无需 ONNX 推理，查看 phoneme IDs）
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Rust CLI 使用示例

```bash
# 使用模型名推理（支持自动下载）
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# 英语
piper-plus-cli --model model.onnx --text "Hello world" --language en

# 模型下载与管理
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# 流式处理（逐句合成）
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# 自定义词典
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# GPU 推理
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# 测试模式 / 静默模式
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# 原始 PCM 输出（无 WAV 头）
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **注意：** C# CLI 可通过 `dotnet tool install -g PiperPlus.Cli` 安装，Rust CLI 可通过 `cargo install piper-plus-cli` 安装。两者均支持6语言、自定义词典和流式处理。

### 从源码构建 (Rust)

```bash
# Rust CLI 构建
cargo build --release -p piper-plus-cli
# 测试
cargo test -p piper-plus
```

前提条件：Rust 1.70+、cargo

---

## 使用方法

### C++ CLI

#### 文本直接输入（推荐）

使用 `--text` 选项可以直接输入文本，无需管道：

```sh
# 从文本生成语音
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# 日语文本（避免 Windows 编码问题）
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# 指定说话人
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### 管道输入

```sh
# 基本用法
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# 流式处理（低延迟）
echo "长文本..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# GPU 推理
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# 音素时间输出（用于口型同步、字幕同步）
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# 自定义词典
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# 内联音素输入
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# 原始音素输入
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# 流式处理（原始音频输出）
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

主要选项：

| 选项 | 说明 | 默认值 |
|---|---|---|
| `--model PATH\|NAME` | 模型文件路径或模型名（自动解析已下载模型） | - |
| `--text TEXT` | 文本直接输入（无需管道） | - |
| `--streaming` | 分块流式处理模式 | off |
| `--use-cuda` | 启用 CUDA GPU 推理 | off |
| `--gpu-device-id NUM` | GPU 设备 ID | 0 |
| `--length-scale VAL` | 语速调节（越小越快） | 1.0 |
| `--noise-scale VAL` | 音频变化控制 | 0.667 |
| `--noise-w VAL` | 音素时长变化控制 | 0.8 |
| `--sentence-silence SEC` | 句间静音（秒） | 0.2 |
| `--speaker NUM` | 多说话人模型的说话人编号 | 0 |
| `--phoneme-silence PHONEME SEC` | 特定音素的静音时间 | - |
| `--raw-phonemes` | 将输入解释为音素 | off |
| `--output-timing FILE` | 音素时间信息输出 (JSON/TSV) | - |
| `--custom-dict FILE` | 自定义词典（逗号分隔可指定多个） | - |
| `--json-input` | JSON 输入模式 | off |
| `--list-models [LANG]` | 显示可用模型列表 | - |
| `--download-model NAME` | 下载模型 | - |
| `--model-dir DIR` | 模型下载目录 | - |
| `--version` | 显示版本 | - |

运行 `piper --help` 查看所有选项。

> **WavLM 模型推荐设置：** 使用 WavLM Discriminator 训练的模型建议设置 `--noise-scale 0.5`（默认值为 0.667）。
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON 输入

使用 `--json-input` 标志接收 JSON 输入：

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### 模型管理

#### 显示模型列表

```bash
# 显示可用模型列表
./bin/piper --list-models

# 按语言筛选
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### 下载模型

```bash
# 指定模型名下载（也可使用别名）
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# 指定下载目录
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# 下载后使用模型名推理（无需完整路径）
./bin/piper --model tsukuyomi --text "こんにちは"
```

### 环境变量 (C++ CLI)

| 变量名 | 说明 | 示例 |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | `--model` 未指定时的默认模型路径 | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | `--config` 未指定时的默认配置文件路径 | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | 下载模型的保存目录 | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA GPU 设备 ID | `0` |

---

## 训练

详细说明请参阅[训练指南](docs/guides/training/training-guide.md)。

### 基本训练

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

### 多说话人 / 多 GPU

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

多 GPU 自动配置 DDP（分布式数据并行）。需要设置 NCCL 环境变量。详情请参阅多 GPU 训练指南。

### ONNX 导出

默认启用FP16转换，模型大小减少约50%。使用 `--no-fp16` 可以禁用。为保证数值稳定性，LayerNormalization、Sigmoid、Softmax 保持 FP32。

```bash
# 标准模型（默认FP16，模型大小约50%）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# 禁用FP16（完整精度）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM 模型（必须使用 --stochastic）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### 检查点管理

- `--resume_from_checkpoint` — 从检查点恢复训练
- `--resume_from_single_speaker_checkpoint` — 将单说话人模型转换为多说话人模型
- `--resume-from-multispeaker-checkpoint` — 多说话人到单说话人的迁移学习（自动启用 `--freeze-dp`）

### 语音评估

`scripts/evaluation/` 中提供了 MCD、PESQ 和 UTMOS 评估工具。

---

## 预训练模型

推理用语音合成模型已在 Hugging Face 上发布。

**推理用模型（可直接使用）：**

| 模型 | 语言 | 说话人数 | 说明 | 下载 |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan 语音，6语言支持，FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 日语 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 日语语音，6语言支持，FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**训练用基础模型（用于微调）：**

| 模型 | 语言 | 说话人数 | 说明 | 下载 |
|---|---|---|---|---|
| 6语言基础模型 | JA/EN/ZH/ES/FR/PT | 571 | 多语言预训练 (508,187条语音, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### 模型下载

**Tsukuyomi-chan 模型：**

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

### 6语言基础模型特征（训练用）

**piper-plus-base 特征：**

- 架构：VITS + 韵律特征 (Prosody Features)
- 语言：6种 — 日语 (ja)、英语 (en)、普通话 (zh)、西班牙语 (es)、法语 (fr)、葡萄牙语 (pt)
- 训练数据：508,187 条语音（571 位说话人）
- 采样率：22,050 Hz
- 音素数：173
- 韵律特征：A1/A2/A3 韵律信息（日语）
- 扩展音素：疑问标记、上下文相关「ん」变体
- 语言均衡采样：自动启用

**语言ID映射：**

| 语言 | ID | 说话人数 | 语音数 | 来源 |
|---|---|---|---|---|
| 日语 (ja) | 0 | 20 | 60,148 | MOE-Speech |
| 英语 (en) | 1 | 310 | 74,912 | LibriTTS-R |
| 普通话 (zh) | 2 | 142 | 63,223 | AISHELL-3 |
| 西班牙语 (es) | 3 | 63 | 168,374 | CML-TTS |
| 法语 (fr) | 4 | 28 | 107,464 | CML-TTS |
| 葡萄牙语 (pt) | 5 | 8 | 34,066 | CML-TTS |

> **注意：** piper-plus 进行了独自的架构扩展（多语言嵌入、韵律 A1/A2/A3、173个符号），因此与 upstream Piper 的检查点/ONNX 模型不兼容。请使用 piper-plus 专用模型。

上游 Piper 检查点也可使用：[piper-checkpoints](https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main)

---

## 日语 TTS

基于 OpenJTalk 集成的高质量日语语音合成。词典和语音文件在首次运行时自动下载。

**环境变量（可选）：**

| 变量名 | 说明 |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk 词典路径（未设置时自动下载） |
| `PIPER_AUTO_DOWNLOAD_DICT` | 设为 `0` 禁用自动下载 |
| `PIPER_OFFLINE_MODE` | 设为 `1` 启用离线模式 |

详情请参阅日语使用指南和[音素映射参考](docs/api-reference/phoneme-mapping.md)。

---

## 平台支持

### macOS

**仅支持 Apple Silicon (M1/M2/M3+)。** Intel Mac 用户请使用 Docker 或从源码构建。

首次运行时的安全警告处理：

```bash
xattr -cr piper/
```

### Windows

需要 espeak-ng-data 目录。详情请参阅 [Windows 设置指南](docs/getting-started/windows-setup.md)。

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

日语 TTS 可直接在浏览器中运行。无需服务器，支持离线使用。

- **[在线演示](https://ayutaz.github.io/piper-plus/)**
- **[技术详情和集成指南](src/wasm/openjtalk-web/README.md)**

---

## 相关链接

### Unity — uPiper

Piper 的 Unity 插件：[github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+，Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- 日语和英语支持，异步 API，流式传输

### 语音模型 (Voices)

上游 Piper 语音模型（30+ 种语言）也可使用：[piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

每个语音需要一个 `.onnx` 模型和 `.onnx.json` 配置文件。[语音样本](https://rhasspy.github.io/piper-samples) | [视频教程](https://youtu.be/rjq5eZoWWSo)

### 相关文章（日语）

- [使用 LJSpeech 创建英语 Piper 预训练模型](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [使用 JVS 语音数据集创建 Piper 日语模型](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [使用 Tsukuyomi-chan 数据集从 Piper 模型进行微调](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## 文档

| 类别 | 链接 |
|---|---|
| 日语 TTS | 日语使用指南 |
| 训练 | [训练指南](docs/guides/training/training-guide.md) · 多 GPU |
| API | [音素映射](docs/api-reference/phoneme-mapping.md) · [环境变量](docs/getting-started/environment-variables.md) |
| 功能 | [WebUI](docs/features/webui.md) · CLI 增强 · 流式处理 |
| 设置 | 快速入门（日语） · [Windows](docs/getting-started/windows-setup.md) · [故障排除](docs/getting-started/troubleshooting.md) |
| Docker | [Docker 环境](docker/README.md) |
| WebAssembly | [技术详情](src/wasm/openjtalk-web/README.md) |

## 贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 更新日志

请参阅 [CHANGELOG.md](CHANGELOG.md)。
