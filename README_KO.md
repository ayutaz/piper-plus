![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | 한국어 | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**패키지:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 유일한 MIT 라이선스 Piper 포크** — 원본 [rhasspy/piper](https://github.com/rhasspy/piper)는 2025년 10월에 아카이브되었으며, [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)은 GPL-3.0으로 전환되었습니다. piper-plus는 espeak-ng에 의존하지 않는 유일한 MIT 호환 포크입니다. 자체 구현 G2P로 8개 언어 (JA/EN/ZH/KO/ES/FR/PT/SV)를 지원하며, 상용 및 임베디드 용도에 적합합니다.

> **📢 v2.0.0 주요 변경사항 (2026-05, `dev`에서 준비 중 · 최신 릴리스 태그는 v1.13.0):** 기본 Docker 이미지가 CUDA 12.8 + Ubuntu 24.04 + Python 3.13으로 통합 (호스트 NVIDIA 드라이버 **R570+** 필요; 구버전 드라이버에서는 새 이미지를 시작할 수 없음) / 학습이 torch 2.11+cu128로 업데이트 (torch 2.2로 생성한 체크포인트는 더 이상 재개 불가) / TF32 + bf16-mixed가 새로운 학습 기본값. 자세히: [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

빠르고 고품질의 뉴럴 텍스트 음성 합성 (TTS) 시스템. [VITS](https://github.com/jaywalnut310/vits/) 아키텍처를 채택하여 일본어, 영어, 중국어, 한국어, 스페인어, 프랑스어, 포르투갈어, 스웨덴어 등 8개 언어 다중 화자 음성 합성을 지원합니다. [Piper](https://github.com/rhasspy/piper)의 포크로, 일본어 지원, 음질 향상, 학습 기능을 대폭 강화했습니다.

**[Hugging Face 데모](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly 데모](https://ayutaz.github.io/piper-plus/)** (브라우저에서 동작, 서버 불필요)

---

## 목차

- [벤치마크](#벤치마크)
- [주요 기능](#주요-기능)
- [빠른 시작](#빠른-시작)
- [설치](#설치)
- [사용법](#사용법)
- [학습](#학습)
- [사전 학습 모델](#사전-학습-모델)
- [플랫폼](#플랫폼)
- [관련 링크](#관련-링크)

---

## 벤치마크

> **측정 환경**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cores / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **테스트 문장**: "Hello, how are you doing today?" (영어, 25 음소)
> **측정 파라미터**: warmup 5회 / 측정 30회 (intra-op threads = auto)
> **사용 모델**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (PR #320에서 도입된 통합 디코더)
> - Piper 원본: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa 릴리스)
>
> **재현**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| 시스템 | RTF ↓ | Latency P50 (ms) | 크기 (MB) | RAM (MB) | 콜드 스타트 (ms) | 파라미터 | 언어 수 | 라이선스 |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper 원본 (archived) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/model | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/model | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/model | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **참고**: RTF (Real-Time Factor)는 낮을수록 빠릅니다. `Latency P50`은 단일 추론 시간의 중앙값으로, "실제 응답성"을 가장 직접적으로 나타내는 지표입니다. piper-plus는 MB-iSTFT 통합 디코더로 Latency P50 27ms를 달성해 가장 빠르며 (Piper 원본 35ms 대비 -23%, sherpa-onnx 53ms 대비 -49%), 모델 크기도 38MB로 최소 수준입니다. 기존 piper-plus HiFi-GAN 기반 (P50 43.3ms) 대비로도 -38% 개선되었습니다.
>
> **†** 표시가 있는 행은 이번 PR에서 재측정하지 않았습니다 (`piper1-gpl`은 Piper 원본과 동일한 아키텍처 및 ONNX 형식이므로 Piper 원본 행과 거의 동등할 것으로 예상됩니다. `Kokoro-82M`은 다른 아키텍처이고 `eSpeak-NG`는 비뉴럴 CLI이므로 `scripts/benchmark.py`의 텐서 계약에 맞지 않아 별도의 하니스가 필요합니다). 이 값들은 이전 측정 (Apple M2 Max) 당시의 것입니다.

### 멀티 런타임 RTF 벤치마크 (최신 값)

Python / Rust / Go / C# / C++ / WASM 6개 런타임을 `multilingual-test-medium.onnx`로 횡단 측정한 최신 RTF 및 레이턴시 결과를 공개하고 있습니다. dev 브랜치에 머지될 때마다 자동으로 업데이트됩니다.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## 주요 기능

### 음성 합성

- **8개 언어 지원** — 일본어, 영어, 중국어, 스페인어, 프랑스어, 포르투갈어 (BR/EU 방언 전환: `pt`/`pt-BR`/`pt-PT`), 스웨덴어, 한국어 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *학습된 모델은 6개 언어 (JA/EN/ZH/ES/FR/PT)*
- **일본어 TTS** — OpenJTalk 통합, 운율 정보 (A1/A2/A3), 의문사 마커 (#204), 문맥 의존 'ん' 변이형 (#207)
- **영어 TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), espeak-ng 불필요
- **다중 화자** — 571 화자 지원 (학습용 기본 모델), SpeakerBalancedBatchSampler, 언어 그룹 균등 샘플링
- **커스텀 사전** — JSON (v1/v2) / TSV를 통한 사용자 발음 사전 추가 지원
- **음소 입력** — `[[ phonemes ]]` 표기법으로 직접 지정 — [가이드](docs/features/phoneme-input.md)

### 학습

- **WavLM 판별기** — MOS +0.15-0.25 향상 (기본 활성화, 학습 시에만 사용)
- **MB-iSTFT-VITS2 디코더** — 디코더를 MB-iSTFT + PQMF로 통합, CPU 추론 2.21배 가속. ONNX 형식이 유지되어 기존 런타임과 호환
- **BF16 혼합 정밀도** — `--precision bf16-mixed` (기본값) + TF32로 학습 가속, 메모리 약 50% 절감
- **EMA** — Exponential Moving Average를 통한 학습 안정성 향상 (기본 활성화)
- **다중 GPU** — DDP 지원, 자동 학습률 스케일링
- **운율 특성** — Duration Predictor에 운율 정보 주입 (`--prosody-dim 16`)
- **Wandb 통합** — 실시간 메트릭 모니터링

### 인터페이스

- **[WebUI (Gradio)](docs/features/webui.md)** — 추론 및 학습 지원, Docker 지원
- **C++ CLI** — 스트리밍, CUDA 추론, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 커스텀 사전
- **[C API 공유 라이브러리](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI 호환 (Flutter/Godot/Swift 등), 스트리밍 API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), 합성 엔진 본체를 iOS arm64 device + simulator universal로 배포
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — `PiperPlusG2P` 독립 라이브러리, 8개 언어 G2P를 ONNX Runtime 없이 iOS에서 사용 가능 (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — 브라우저 내에서 완전 동작, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 서버 불필요
- **[Docker](docker/README.md)** — 추론, 학습, WebUI, C++, Wyoming (Home Assistant) 등 7개 계열 이미지 제공
- **PyPI** — `pip install piper-plus`로 간단 설치, 8개 언어 다중 언어, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 스트리밍, HTTP API
- **C# CLI** — .NET 10 크로스 플랫폼, 8개 언어 다중 언어, ONNX 추론, **Phoneme Timing 출력 (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, 스트리밍, CUDA/CoreML/DirectML 지원, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 사전 자동 다운로드
- **[Go CLI](src/go/README.md)** — HTTP API 서버, 세션 풀링, Docker 지원, 단일 바이너리, **Phoneme Timing 출력 (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — 6개 런타임 (Python/Rust/C#/Go/WASM/C++) 모두 지원. C++는 CLI 바이너리와 `libpiper_plus` C API 라이브러리 두 형태로 사용 가능. ECAPA-TDNN을 통한 참조 음성 기반 화자 embedding 추출 (`--reference-audio`)
- **SSML 지원** — `<speak>`, `<break>`, `<prosody rate="...">`를 Python/Rust/C#/Go/WASM/C++ 6개 런타임에서 구현 (C++는 CLI `--ssml` 경유)
- **단문 품질 개선 (Strategy A/B/C)** — Silence Padding, Dynamic Scales, SSML `<break>` 자동 삽입을 6개 런타임 모두에서 지원 (`docs/spec/short-text-contract.toml`)

### 런타임별 기능 지원

6개 런타임 (Python/Rust/C#/Go/JS-WASM/C++) 에서 동등한 8개 언어 다중 언어 합성을 제공합니다. Phoneme Timing, 스트리밍 (문장 단위 분할 포함), Voice Cloning, 커스텀 사전은 모든 런타임에서 지원합니다. SSML은 6개 런타임 모두 지원 (C++는 CLI `--ssml` 경유, C API 미노출), HTTP API는 2개 런타임 (Python/Go) 에서 지원합니다.

---

## 빠른 시작

### 프리빌드 바이너리 (빌드 불필요)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases)에서 프리빌드 바이너리를 다운로드하여 바로 음성 합성을 시작할 수 있습니다.

**1. 바이너리 다운로드**

사용 중인 OS에 맞게 다운로드 및 압축을 해제하세요.

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

**Linux (ARM64, 라즈베리 파이 4/5):**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. 모델 다운로드 및 음성 생성**

```sh
# つくよみちゃんモデルをダウンロード
./bin/piper-plus --download-model tsukuyomi

# 音声を生成 (モデル名だけで OK — ダウンロード済みモデルを自動解決)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd의 코드 페이지에 대해:** `--text` 옵션은 내부적으로 `GetCommandLineW()` (UTF-16)를 사용하므로 코드 페이지에 관계없이 그대로 동작합니다. 파이프 입력(`echo ... | piper-plus`)을 사용하는 경우에만 `chcp 65001`로 UTF-8로 전환해 주세요.
>
> **output.wav 출력 위치:** 현재 디렉터리(`cd piper-plus`한 위치)에 생성됩니다.

> **어떤 바이너리를 선택해야 하나요?** Releases에는 `piper-plus-cpp-*` (C++) 외에 `piper-plus-cli-*` (C# .NET)와 `piper-plus-rs-cli-*` (Rust) CLI도 있습니다. 위의 빠른 시작에서 사용하는 **C++ CLI (`piper-plus-cpp-*`)**가 가장 많은 플랫폼을 지원하므로 권장됩니다. 자세한 내용은 [CLI 바이너리 선택하기](docs/getting-started/binary-selection.md)를 참조하세요.

### Python 추론

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

주요 옵션: `--speaker-id`(화자 ID), `--device auto|cpu|gpu`, `--noise-scale`(음성 변동), `--length-scale`(말하기 속도), `--noise-scale-w`(음소 길이 변동, 기본값: 0.5)

> **WavLM 모델 권장 설정:** WavLM 판별기로 학습된 모델 (츠쿠요미짱 등)은 `--noise-scale 0.5`에서 최적의 음질을 얻을 수 있습니다 (기본값은 0.4).

#### Python CLI 모델 관리

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

CI/CD 빌드 이미지:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

자세한 내용은 [docker/README.md](docker/README.md)를 참조하세요.

---

## 설치

### Python

Python 3.13+ 권장 (3.11+ 지원). 의존성 관리에는 [uv](https://docs.astral.sh/uv/)를 권장합니다.

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

PyPI 패키지로도 설치 가능:

```bash
pip install piper-plus
```

### 패키지로 설치

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm (브라우저 WASM):**

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

**C# 라이브러리 (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Rust 라이브러리 (crates.io):**

```toml
[dependencies]
piper-plus = "0.5"
```

### 소스에서 빌드

프리빌드 바이너리가 제공되지 않는 플랫폼에서 사용하거나 piper-plus를 수정하려는 경우 소스에서 빌드할 수 있습니다. C++ / C# / Rust 각 런타임의 빌드 방법은 **[소스 빌드 가이드](docs/guides/development/building-from-source.md)**를 참조하세요.

---

## 사용법

C++ CLI의 자세한 명령줄 옵션, JSON 입력 형식, 모델 관리, 환경 변수, Windows 헬퍼 스크립트 사용법은 **[CLI 사용 가이드](docs/guides/development/cli-usage.md)**를 참조하세요.

간단한 사용 예:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## 학습

piper-plus 모델의 학습 및 파인튜닝 방법 (기본 설정, 다중 화자 / 다중 GPU, ONNX 변환, 체크포인트 관리, 음성 평가)은 **[학습 가이드](docs/guides/training/training-guide.md)**를 참조하세요.

실운영용 6개 언어 사전 학습 및 츠쿠요미짱 파인튜닝 명령 템플릿은 [CLAUDE.md](CLAUDE.md)에 있습니다.

---

## 사전 학습 모델

공개된 piper-plus 모델 목록, 다운로드 방법, 6개 언어 기본 모델의 특징, 일본어 TTS 상세 정보는 **[모델 가이드](docs/guides/development/pretrained-models.md)**를 참조하세요.

주요 모델: `tsukuyomi` (일본어)와 `css10-6lang` (`--download-model`로 다운로드 가능), 그리고 학습·파인튜닝용 6개 언어 기본 ckpt — 자세한 내용은 HuggingFace의 [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base)와 [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)을 참조하세요.

---

## 플랫폼

- **macOS**: Apple Silicon (arm64) 네이티브 지원. 자세한 내용은 [macOS 설정](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません) 참조
- **Windows**: x64 / arm64 지원. OpenJTalk 설정은 [Windows 설정 가이드](docs/getting-started/windows-setup.md) 참조
- **WebAssembly**: 브라우저에서 완전 오프라인 실행. [데모](https://ayutaz.github.io/piper-plus/) | [npm 패키지](https://www.npmjs.com/package/piper-plus)

---

## 관련 링크

### Unity — uPiper

Piper를 Unity에서 사용하기 위한 플러그인: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2) 지원
- 7개 언어 지원 (ja/en/zh/es/fr/pt/ko), 비동기 API, 스트리밍

### 음성 모델 (Voices)

piper-plus 전용 모델: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6개 언어 기본 모델) · [츠쿠요미짱](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note:** piper-plus는 자체 G2P 및 음소 시스템을 사용하므로 upstream Piper 모델 (rhasspy/piper-voices)은 호환되지 않습니다.

### 관련 글

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (독립 G2P 패키지)

다국어 G2P (Grapheme-to-Phoneme) 를 독립 패키지로 제공:

- **Python**: `pip install piper-plus-g2p` — [소스 코드](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [소스 코드](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [소스 코드](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [소스 코드](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` — [소스 코드](android/piper-plus-g2p/) · [사전 배포 가이드](docs/guides/platform/android-g2p-dictionary.md)
- **Swift (iOS/macOS)**: SPM product `PiperPlusG2P` — [통합 가이드](docs/guides/platform/swift-g2p-integration.md) · [소스 코드](Sources/PiperPlusG2P/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## 문서

| 카테고리 | 링크 |
|---|---|
| 학습 | [학습 가이드](docs/guides/training/training-guide.md) (다중 GPU 포함) |
| API | [음소 매핑](docs/api-reference/phoneme-mapping.md) · [환경 변수](docs/getting-started/environment-variables.md) |
| 기능 | [WebUI](docs/features/webui.md) · [음소 타이밍](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| 설정 | [Windows](docs/getting-started/windows-setup.md) · [문제 해결](docs/getting-started/troubleshooting.md) |
| Docker | [Docker 환경](docker/README.md) |
| WebAssembly | [기술 상세](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md)를 참조하세요. 질문이나 버그 리포트는 [Issues](https://github.com/ayutaz/piper-plus/issues)로 보내주세요. 행동 강령은 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)를 참조하세요.

## Changelog

[CHANGELOG.md](CHANGELOG.md)를 참조하세요.
