![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | 한국어 | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**패키지:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 유일한 MIT 라이선스 Piper 포크** — 원본 [rhasspy/piper](https://github.com/rhasspy/piper)는 2025년 10월에 아카이브되었으며, [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)은 GPL-3.0으로 전환되었습니다. piper-plus는 espeak-ng에 의존하지 않는 유일한 MIT 호환 포크입니다. 자체 구현 G2P로 8개 언어 (JA/EN/ZH/KO/ES/FR/PT/SV)를 지원하며, 상용 및 임베디드 용도에 적합합니다.

> **📢 v2.0.0 주요 변경사항:** Docker 기본 이미지는 CUDA 12.8 + Ubuntu 24.04 + Python 3.13을 사용합니다 (호스트 NVIDIA 드라이버 **R570+** 필요). 학습은 torch **2.11.0** + CUDA 12.8이며 TF32 + bf16-mixed가 기본값입니다. torch 2.2로 만든 체크포인트의 학습 재개는 지원하지 않습니다. Python import / CLI는 `piper_plus` / `piper-plus`로 변경되었습니다. 1.13.0에서 현재 공개 버전으로 업데이트하려면 `pip install --upgrade "piper-plus[cpu]==2.0.2"`를 실행하세요. 자세한 내용: [마이그레이션 가이드](docs/migration/v1.12-to-v2.0.md).

빠르고 고품질의 뉴럴 텍스트 음성 합성 (TTS) 시스템입니다. [VITS](https://github.com/jaywalnut310/vits/) 아키텍처를 채택하여 8개 언어 G2P/음소화와, 현재 6개 언어로 학습된 모델을 통한 다중 화자 음성 합성을 지원합니다. [Piper](https://github.com/rhasspy/piper)의 포크로, 일본어 지원, 음질 향상, 학습 기능을 대폭 강화했습니다.

**[Hugging Face 데모](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly 데모](https://ayutaz.github.io/piper-plus/)** (브라우저에서 동작, 서버 불필요)

---

## 목차

- [벤치마크](#벤치마크)
- [주요 기능](#주요-기능)
- [빠른 시작](#빠른-시작)
- [설치](#설치)
- [사용법](#사용법)
- [학습](#학습-1)
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
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (PR #320에서 도입된 통합 Decoder)
> - Piper 원본: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa 릴리스)
>
> **재현**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| 시스템 | RTF ↓ | Latency P50 (ms) | 크기 (MB) | RAM (MB) | 첫 실행 (ms) | 파라미터 | 언어 수 | 라이선스 |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper 원본 (archived) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/model | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/model | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/model | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **참고**: RTF (Real-Time Factor)는 낮을수록 빠릅니다. `Latency P50`은 단일 추론의 중앙값으로 "실제 응답성"을 직접 나타내는 지표입니다. piper-plus는 MB-iSTFT 통합 Decoder 덕분에 Latency P50 27ms로 가장 빠르며 (Piper 원본 35ms 대비 -23%, sherpa-onnx 53ms 대비 -49%), 모델 크기도 38MB로 가장 작은 수준입니다. 이전 piper-plus HiFi-GAN 기반 (P50 43.3ms)과 비교해도 -38% 개선되었습니다.
>
> **†** 표시된 행은 이번 PR에서 다시 측정하지 않았습니다 (`piper1-gpl`은 Piper 원본과 동일한 아키텍처·ONNX 형식이므로 Piper 원본 행과 거의 같을 것으로 예상됩니다. `Kokoro-82M`은 다른 아키텍처이고 `eSpeak-NG`는 비뉴럴 CLI이므로 `scripts/benchmark.py`의 텐서 계약에 맞지 않아 별도의 측정 도구가 필요합니다). 이 값들은 이전 측정 (Apple M2 Max) 결과입니다.

### 멀티 런타임 RTF 벤치마크 (최신 값)

Python / Rust / Go / C# / C++ / WASM 6개 런타임을 `multilingual-test-medium.onnx`로 횡단 측정한 최신 RTF·지연 시간 결과를 공개하고 있습니다. dev 브랜치에 병합될 때마다 자동으로 갱신됩니다.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## 주요 기능

### 음성 합성

- **8개 언어 G2P/음소화** — 일본어, 영어, 중국어, 스페인어, 프랑스어, 포르투갈어, 스웨덴어, 한국어 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). 현재 학습된 모델은 6개 언어 (JA/EN/ZH/ES/FR/PT)
- **일본어 TTS** — OpenJTalk 통합, 운율 정보 (A1/A2/A3), 의문사 마커 (#204), 문맥 의존 'ん' 변이형 (#207)
- **영어 TTS** — v2.0.2에는 [g2p-en](https://github.com/Kyubyong/g2p) 기반 G2P가 Apache-2.0 추론 코드 및 Tacotron의 MIT 라이선스 고지와 함께 포함되어 있습니다. 외부 `g2p-en` / `Distance`나 espeak-ng는 필요하지 않습니다. 이전 PyPI 2.0.1의 의존성 정의는 변경되지 않습니다. [마이그레이션 가이드](docs/migration/python-g2p-license.md)를 참조하세요
- **다중 화자** — 571 화자 지원 (학습용 기본 모델), SpeakerBalancedBatchSampler, 언어 그룹 균등 샘플링
- **커스텀 사전** — 200개 이상의 기술 용어 발음 사전 내장
- **음소 입력** — `[[ phonemes ]]` 표기법으로 직접 지정 — [가이드](docs/features/phoneme-input.md)

### 학습

- **WavLM Discriminator** — MOS +0.15-0.25 향상 (기본 활성화, 학습 시에만 사용)
- **MB-iSTFT-VITS2 Decoder** — Decoder를 MB-iSTFT + PQMF로 통합, CPU 추론 2.21배 가속. ONNX 형식은 변경되지 않아 기존 런타임과 호환
- **BF16 혼합 정밀도** — `--precision bf16-mixed`가 기본값 (TF32도 기본 활성화). FP16보다 수치적으로 안정적이며 loss scaling이 필요 없습니다. BF16을 지원하지 않는 GPU (T4 등)에서는 `--precision 16-mixed`를 지정하세요
- **EMA** — Exponential Moving Average를 통한 학습 안정성 향상 (기본 활성화)
- **다중 GPU** — DDP 지원, 자동 학습률 스케일링
- **Prosody Features** — Duration Predictor에 운율 정보 주입 (`--prosody-dim 16`)
- **Wandb 통합** — 실시간 메트릭 모니터링

### 인터페이스

- **[WebUI (Gradio)](docs/features/webui.md)** — 추론 및 Docker 지원. 로컬 Training Tab은 이전 CLI 인자를 보내므로 학습에는 [학습 가이드](docs/guides/training/training-guide.md)를 사용하세요.
- **C++ CLI** — 스트리밍, CUDA 추론, **음소 타이밍 출력 (JSON/TSV/SRT)**, 커스텀 사전
- **[C API 공유 라이브러리](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI 지원 (Flutter/Godot/Swift 등), 스트리밍 API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), 합성 엔진 본체를 iOS arm64 device + simulator universal로 배포
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — `PiperPlusG2P` 단독 라이브러리, 8개 언어 G2P를 ONNX Runtime 없이 iOS에서 사용 가능 (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — 브라우저 내에서 완전 동작, **음소 타이밍 출력 (JSON/TSV/SRT)**, 서버 불필요
- **[Docker](docker/README.md)** — 추론·학습·WebUI·C++ (추론/개발)·Wyoming (Home Assistant)의 6개 이미지 제공
- **PyPI** — `pip install piper-plus`로 간편 설치, 8개 언어 G2P/음소화 (현재 학습된 모델은 6개 언어), **음소 타이밍 출력 (JSON/TSV/SRT)**, 스트리밍, HTTP API
- **C# CLI** — .NET 10 크로스 플랫폼, 8개 언어 G2P/음소화 (현재 학습된 모델은 6개 언어), ONNX 추론, **음소 타이밍 출력 (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, 스트리밍, CUDA/CoreML/DirectML 지원, **음소 타이밍 출력 (JSON/TSV/SRT)**, 사전 자동 다운로드
- **[Go CLI](src/go/README.md)** — HTTP API 서버, 세션 풀링, Docker 지원, 단일 바이너리, **음소 타이밍 출력 (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — 6개 런타임 (Python/Rust/C#/Go/WASM/C++) 모두에서 모델 호환 사전 계산 `speaker_embedding` 입력을 지원합니다. C++ CLI/C API는 사전 계산 embedding만 받으며, `--reference-audio`를 통한 추출은 구현되지 않았습니다. 공개 `zs-v1`의 실제 추론 확인은 Python `piper-plus==2.0.0`에서만 이루어졌습니다. 공개 CI run `38189966578`에서는 Python이 생성한 공유 phoneme IDs를 입력으로 6개 런타임 추론을 확인했으며, native G2P와 사람의 청취 품질은 범위 밖이고 품질 승인은 이루어지지 않았습니다.
- **SSML 지원** — SSML 파서 계약은 Python/Rust/Go/C#/WASM/C++에 구현되어 있습니다. 합성 측은 Python/Rust/Go/WASM/C++가 지원하며, C# Core에는 파서가 있지만 CLI의 `--text`에는 아직 연결되지 않았습니다. C++는 CLI `--ssml`을 통해 제공됩니다 (C API에는 노출되지 않음).
- **단문 품질 개선 (Strategy A/B/C)** — Strategy A/B는 각 런타임에 구현되어 있습니다. Strategy C (SSML `<break>` 자동 삽입)는 추론용 Python/Rust/Go/C# 범위이며, 학습용 Python·WASM·C++는 대상이 아닙니다. 자세한 내용은 [단문 계약](docs/spec/short-text-contract.toml)을 참조하세요.

### 런타임별 기능 지원

6개 런타임 (Python/Rust/C#/Go/JS-WASM/C++)에서 현재 학습된 모델의 6개 언어 합성을 제공하며, 8개 언어 G2P/음소화도 제공합니다. 음소 타이밍, 스트리밍 (문장 단위 분할 포함), 모델 호환 사전 계산 embedding을 사용하는 Voice Cloning, 커스텀 사전은 런타임 기능으로 지원합니다. C++는 사전 계산 embedding만 받으며 `--reference-audio`는 구현되지 않았습니다. 공개 `zs-v1`의 실제 추론 확인은 Python `piper-plus==2.0.0`에서만 이루어졌습니다. 공개 CI run `38189966578`은 Python 공유 phoneme IDs를 사용한 6개 런타임 추론을 확인하지만, native G2P와 사람의 청취 품질은 범위 밖이며 품질 승인은 이루어지지 않았습니다. SSML 합성 측 지원은 Python/Rust/Go/WASM/C++입니다 (C++는 CLI `--ssml` 경유, C API에는 노출되지 않음). C# Core의 파서는 CLI `--text`에 연결되지 않았으며, HTTP API는 Python/Go 2개 런타임에서 지원합니다.

---

## 빠른 시작

### 프리빌드 바이너리 (빌드 불필요)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases)에서 프리빌드 바이너리를 다운로드하여 바로 음성 합성을 시작할 수 있습니다.

**1. 바이너리 다운로드**

사용 중인 OS에 맞게 다운로드 및 압축 해제하세요.

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

**ARM64 호환성:** v2.0.2 Linux ARM64 C++ 배포물은 glibc 2.31을 ABI 상한으로 검사합니다. QEMU에서 Debian Bullseye / Bookworm / Trixie (64비트)의 실행과 일본어 합성을 검증합니다. Raspberry Pi 실기기와 Raspberry Pi OS 자체는 검증하지 않았습니다. 이전 v2.0.1 배포물은 glibc 2.38 이상이 필요하므로 v2.0.2를 사용하세요.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, 32비트 ARM):**

ARMv7 배포물은 C++ CLI만 제공됩니다. CI에서는 QEMU의 Debian Trixie (32비트 ARM)에서 빌드와 일본어 합성을 확인하고 있습니다. Raspberry Pi 실기기는 검증하지 않았습니다.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. 모델 다운로드 및 음성 생성**

```sh
# 츠쿠요미짱 모델 다운로드
./bin/piper-plus --download-model tsukuyomi

# 음성 생성 (모델 이름만으로 OK — 다운로드된 모델을 자동으로 찾음)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd의 코드 페이지에 대해:** `--text` 옵션은 내부적으로 `GetCommandLineW()` (UTF-16)를 사용하므로 코드 페이지와 관계없이 그대로 동작합니다. 파이프 입력 (`echo ... | piper-plus`)을 사용하는 경우에만 미리 `chcp 65001`로 UTF-8로 전환하세요.
>
> **output.wav 출력 위치:** 현재 디렉터리 (`cd piper-plus`한 위치)에 생성됩니다.

> **어떤 바이너리를 선택해야 하나요?** Releases에는 `piper-plus-cpp-*` (C++) 외에도 `piper-plus-cli-*` (C# .NET)와 `piper-plus-rs-cli-*` (Rust) CLI가 있습니다. 위 빠른 시작에서 사용하는 **C++ CLI**(`piper-plus-cpp-*`)가 가장 많은 플랫폼을 지원하므로 권장합니다. 자세한 내용은 [CLI 바이너리 선택 방법](docs/getting-started/binary-selection.md)을 참조하세요.

### Python 추론

```bash
# 설치
# 저장소 루트의 source checkout에서 실행
uv sync --extra inference

# 일본어 추론
uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --config /path/to/config.json \
    --output-dir ./output \
    --text "こんにちは、今日は良い天気ですね。"

# 영어 추론
uv run python -m piper_train.infer_onnx \
    --model /path/to/en_model.onnx \
    --config /path/to/en_model.onnx.json \
    --output-dir ./output \
    --text "Hello, how are you today?" \
    --language en
```

주요 옵션: `--speaker-id`(화자 ID), `--device auto|cpu|gpu`, `--noise-scale`(음성 변동), `--length-scale`(말하기 속도), `--noise-scale-w`(음소 길이 변동, 기본값: 0.5)

> **WavLM 모델 권장 설정:** WavLM Discriminator로 학습된 모델 (츠쿠요미짱 등)은 `--noise-scale 0.5`에서 최적의 음질을 얻을 수 있습니다 (기본값은 0.4).

#### Python CLI 모델 관리

```bash
# 모델 목록 표시
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# 모델 다운로드
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# 다운로드 후 사용
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

# Python 추론 (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device cpu

# GPU 추론 (--gpus all 추가)
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

Python 3.13+ 권장 (3.11+ 지원). 의존성 관리는 [uv](https://docs.astral.sh/uv/)를 권장합니다.

```bash
# CPU 추론
uv sync --extra inference

# GPU 추론 (CUDA 환경 필요)
uv sync --no-group cpu --extra inference-gpu

# 학습
uv sync --extra train

# 개발 (테스트·린터 포함)
uv sync --extra dev
```

PyPI 패키지로도 설치할 수 있습니다:

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

프리빌드 바이너리가 제공되지 않는 플랫폼에서 사용하거나 piper-plus를 수정하려는 경우 소스에서 빌드할 수 있습니다. C++ / C# / Rust 각 런타임의 빌드 절차는 **[소스 빌드 가이드](docs/guides/development/building-from-source.md)** 문서를 참조하세요.

---

## 사용법

C++ CLI의 자세한 명령줄 옵션, JSON 입력 형식, 모델 관리, 환경 변수, Windows 헬퍼 스크립트 사용법은 **[CLI 사용 가이드](docs/guides/development/cli-usage.md)** 문서를 참조하세요.

간단한 사용 예:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## 학습

piper-plus 모델의 학습·파인튜닝 방법 (기본 설정, 다중 화자 / 다중 GPU, ONNX 변환, 체크포인트 관리, 음성 평가)은 **[학습 가이드](docs/guides/training/training-guide.md)** 문서를 참조하세요.

실제 운용용 6개 언어 사전 학습 및 츠쿠요미짱 파인튜닝 명령 템플릿은 [CLAUDE.md](CLAUDE.md)에 있습니다.

---

## 사전 학습 모델

공개된 piper-plus 모델 목록, 다운로드 방법, 6개 언어 기본 모델의 특징, 일본어 TTS의 자세한 내용은 **[모델 가이드](docs/guides/development/pretrained-models.md)** 문서를 참조하세요.

주요 모델: `tsukuyomi` (일본어), `zs-v1` (6개 언어 Zero-Shot/FT 실험용 기본 모델), `bilingual-ja-en-v4` (일본어·영어 2개 언어) — 자세한 내용은 Hugging Face의 [고정 공개 zs-v1 번들](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)과 [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)을 참조하세요.

> **Zero-Shot/FT 기본 모델 (`zs-v1`, 2026-10-10):** 고정 공개 번들은 기존 v7 epoch 32 실험 기준 버전입니다 (JA/EN/ZH/ES/FR/PT, 571 화자, 173 음소, CAM++ 192차원). Zero-Shot 추론에는 `base.onnx`와 함께 제공되는 `campplus.onnx`로 추출한 참조 embedding을, 추가 학습에는 `base.ckpt`와 함께 제공되는 `config.json`을 사용하세요. PyPI `piper-plus==2.0.0`의 공개 예제로 기능을 확인했지만, 품질 승인·사람의 청취 합격·최신/최고 품질을 의미하지는 않습니다. `base` / `zero-shot-base-zs-v1` alias는 v2.0.2에 포함되어 있습니다 (2.0.0 / 2.0.1에는 미포함). 루트의 `model.ckpt`는 이전 세대로 별도 취급합니다.

> **츠쿠요미짱 FT (`zs-v1`, 2026-10-15):** 동일한 공개 base 세대를 추가 학습한 [고정 공개 모델](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1)을 공개했습니다. `tsukuyomi.onnx`와 `tsukuyomi.onnx.json`을 조합하면 참조 음성이나 CAM++ 없이 생성할 수 있습니다. 일본어 3문장에 대한 사람의 확인을 기록했고 실험 버전으로서의 공개를 승인했습니다 (quality_approval=false, 품질 승인은 아닙니다). 기존 `tsukuyomi` alias는 계속 이전 루트 모델을 선택하므로, 새 모델은 [모델 가이드](docs/guides/development/pretrained-models.md)의 고정 URL에서 받으세요.

---

## 플랫폼

- **macOS**: Apple Silicon (arm64) 네이티브 지원. 자세한 내용은 [macOS 설정](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)을 참조
- **Windows**: C++ 배포물은 x64, C# CLI는 x64 / arm64. OpenJTalk 설정은 [Windows 설정 가이드](docs/getting-started/windows-setup.md)를 참조
- **WebAssembly**: 브라우저에서 완전 오프라인 실행. [데모](https://ayutaz.github.io/piper-plus/) | [npm 패키지](https://www.npmjs.com/package/piper-plus)

---

## 관련 링크

### Unity — uPiper

Piper를 Unity에서 사용하기 위한 플러그인: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android 지원
- 일본어·영어 지원, 비동기 API, 스트리밍

### 음성 모델 (Voices)

piper-plus 전용 모델: [zs-v1 Zero-Shot/FT 기본 모델](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [츠쿠요미짱](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note:** piper-plus는 자체 G2P·음소 체계를 사용하므로 upstream Piper (rhasspy/piper-voices) 모델과 호환되지 않습니다.

### 관련 글

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341) (LJSpeech로 영어 Piper 사전 학습 모델 만들기, 일본어)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217) (JVS 음성 데이터셋으로 Piper 일본어 모델 만들기, 일본어)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232) (츠쿠요미짱 데이터셋으로 Piper 모델 추가 학습하기, 일본어)

### piper-plus-g2p (독립 G2P 패키지)

다국어 G2P (Grapheme-to-Phoneme)를 독립 패키지로 제공합니다:

- **Python**: `pip install piper-plus-g2p` — [소스 코드](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [소스 코드](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [소스 코드](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [소스 코드](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [소스 코드](android/piper-plus-g2p/) · [사전 배포 가이드](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## 문서

| 카테고리 | 링크 |
|---|---|
| 일본어 TTS | 일본어 음성 합성 가이드 |
| 학습 | [학습 가이드](docs/guides/training/training-guide.md) · 다중 GPU |
| API | [음소 매핑](docs/api-reference/phoneme-mapping.md) · [환경 변수](docs/getting-started/environment-variables.md) |
| 기능 | [WebUI](docs/features/webui.md) · CLI 강화 · 스트리밍 |
| 설정 | 빠른 시작 (일본어) · [Windows](docs/getting-started/windows-setup.md) · [문제 해결](docs/getting-started/troubleshooting.md) |
| Docker | [Docker 환경](docker/README.md) |
| WebAssembly | [기술 상세](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md)를 참조하세요. 질문이나 버그 보고는 [Issues](https://github.com/ayutaz/piper-plus/issues)에 남겨 주세요. 행동 강령은 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)를 참조하세요.

## Changelog

[CHANGELOG.md](CHANGELOG.md)를 참조하세요.

## 감사의 말

piper-plus의 GPU를 사용하는 실험은 [CloudRift](https://www.cloudrift.ai/)의 AI Builder Grant (GPU 크레딧) 지원을 받고 있습니다.
