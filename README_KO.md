![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | 한국어 | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md) | [Русский](README_RU.md) | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **📢 v1.12.0 주요 변경사항 (2026-05):** HiFi-GAN 디코더 제거 (MB-iSTFT로 통합, `--mb-istft` 플래그 폐지) / Flask → FastAPI HTTP 서버 / HTS-voice 의존성 제거 (Python 런타임만 해당) / Unity UPM 별도 저장소로 이동 (`ayutaz/uPiper`) / 모든 .NET 프로젝트 `net10.0` LTS로 업그레이드. 자세히: [docs/migration/v1.11-to-v1.12.md](docs/migration/v1.11-to-v1.12.md)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

빠르고 고품질의 뉴럴 텍스트 음성 합성 (TTS) 시스템. [VITS](https://github.com/jaywalnut310/vits/) 아키텍처를 채택하여 일본어, 영어, 중국어, 한국어, 스페인어, 프랑스어, 포르투갈어, 스웨덴어 등 8개 언어 다중 화자 음성 합성을 지원합니다. [Piper](https://github.com/rhasspy/piper)의 포크로, 일본어 지원, 음질 향상, 학습 기능을 대폭 강화했습니다.

**[Hugging Face 데모](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly 데모](https://ayutaz.github.io/piper-plus/)** (브라우저에서 동작, 서버 불필요)

---

## 목차

- [주요 기능](#주요-기능)
- [빠른 시작](#빠른-시작)
- [사전 학습 모델](#사전-학습-모델)
- [설치](#설치)
- [사용법](#사용법)
- [학습](#학습)
- [일본어 TTS](#일본어-tts)
- [플랫폼](#플랫폼)
- [관련 링크](#관련-링크)

---

## 주요 기능

### 음성 합성

- **8개 언어 지원** — 일본어, 영어, 중국어, 스페인어, 프랑스어, 포르투갈어, 스웨덴어, 한국어 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *학습된 모델은 6개 언어 (JA/EN/ZH/ES/FR/PT) 를 지원합니다*
- **일본어 TTS** — OpenJTalk 통합, 운율 정보 (A1/A2/A3), 의문사 마커 (#204), 문맥 의존 'ん' 변이형 (#207)
- **영어 TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), espeak-ng 불필요
- **다중 화자** — 571 화자 지원 (학습용 기본 모델), SpeakerBalancedBatchSampler, 언어 그룹 균등 샘플링
- **커스텀 사전** — 200개 이상의 기술 용어 발음 사전 내장
- **음소 입력** — `[[ phonemes ]]` 표기법으로 직접 지정 — [가이드](docs/features/phoneme-input.md)

### 학습

- **WavLM 판별기** — MOS +0.15-0.25 향상 (기본 활성화, 학습 시에만 사용)
- **MB-iSTFT-VITS2 디코더** — 디코더를 MB-iSTFT + PQMF로 통합, CPU 추론 약 2.21배 가속. 기존 런타임과 ONNX 호환
- **FP16 혼합 정밀도** — 학습 속도 2-3배, 메모리 약 50% 절감 (기본 활성화)
- **EMA** — Exponential Moving Average를 통한 학습 안정성 향상 (기본 활성화)
- **다중 GPU** — DDP 지원, 자동 학습률 스케일링
- **운율 특성** — Duration Predictor에 운율 정보 주입 (`--prosody-dim 16`)
- **Wandb 통합** — 실시간 메트릭 모니터링

### 인터페이스

- **[WebUI (Gradio)](docs/features/webui.md)** — 추론 및 학습 지원, Docker 지원
- **C++ CLI** — 스트리밍, CUDA 추론, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 커스텀 사전
- **[C API 공유 라이브러리](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI 호환 (Flutter/Godot/Swift 등), 스트리밍 API
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — 브라우저 내에서 완전 동작, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 서버 불필요
- **[Docker](docker/README.md)** — 추론, 학습, WebUI, C++ 등 5개 이미지 제공
- **PyPI** — `pip install piper-plus`, 8개 언어 다중 언어, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 스트리밍, **FastAPI 기반 HTTP API**
- **C# CLI** — .NET 10 크로스 플랫폼, 8개 언어 다중 언어, ONNX 추론, **Phoneme Timing 출력 (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, 스트리밍, CUDA/CoreML/DirectML 지원, **Phoneme Timing 출력 (JSON/TSV/SRT)**, 사전 자동 다운로드
- **[Go CLI](src/go/README.md)** — HTTP API 서버, 세션 풀링, Docker 지원, 단일 바이너리, **Phoneme Timing 출력 (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — 6개 런타임 (Python/Rust/C#/Go/WASM/C++) 모두 지원
- **SSML 지원** — `<speak>`, `<break>`, `<prosody rate="...">` 4개 런타임 (Python/Rust/C#/Go) 지원
- **단문 품질 개선 (Strategy A/B/C)** — Silence Padding, Dynamic Scales, SSML `<break>` 자동 삽입을 6개 런타임 모두에서 지원

### 런타임별 기능 지원

6개 런타임 (Python/Rust/C#/Go/JS-WASM/C++) 에서 동등한 8개 언어 다중 언어 합성 제공. Phoneme Timing, 스트리밍 (문장 단위 분할 포함), Voice Cloning, 커스텀 사전은 모든 런타임에서 지원합니다. SSML은 4개 런타임 (Python/Rust/C#/Go), HTTP API는 2개 런타임 (Python/Go) 에서 지원합니다.

### 플랫폼

| 플랫폼 | 아키텍처 | 비고 |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | 전체 지원 |
| macOS | ARM64 (Apple Silicon) 전용 | M1/M2/M3+ |
| Windows | x64 | 전체 지원 |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | 공유 라이브러리, Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 10, Linux/macOS/Windows |
| Rust | Linux x64, macOS ARM64, Windows x64 | CUDA/CoreML/DirectML |
| Go | Linux x64, macOS ARM64, Windows x64 | HTTP API, Docker |

---

## 빠른 시작

### 프리빌드 바이너리 (빌드 불필요)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases)에서 프리빌드 바이너리를 다운로드하여 바로 음성 합성을 시작할 수 있습니다.

**1. 바이너리 다운로드**

사용 중인 OS에 맞게 다운로드 및 압축을 해제하세요.

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

**Linux (ARM64, 라즈베리 파이 4/5):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-linux-arm64.tar.gz
tar xzf piper.tar.gz
cd piper
```

**2. 모델 다운로드 및 음성 생성**

```sh
# 츠쿠요미짱 모델 다운로드
./bin/piper --download-model tsukuyomi

# 음성 생성 (모델 이름만으로 OK — 다운로드된 모델을 자동 검색)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd의 코드 페이지에 대해:** `--text` 옵션은 내부적으로 `GetCommandLineW()` (UTF-16)를 사용하므로 코드 페이지에 관계없이 그대로 동작합니다. 파이프 입력(`echo ... | piper`)을 사용하는 경우에만 `chcp 65001`로 UTF-8로 전환해 주세요.
>
> **output.wav 출력 위치:** 현재 디렉터리(`cd piper`한 위치)에 생성됩니다.

> **어떤 바이너리를 선택해야 하나요?** 릴리스에는 `piper-plus-cli-*` (C# .NET) 및 `piper-plus-rs-cli-*` (Rust) CLI도 포함되어 있습니다. 위의 빠른 시작은 **C++ CLI (`piper-*`)**를 사용하며, 가장 폭넓은 플랫폼을 지원하므로 대부분의 사용자에게 권장됩니다. 자세한 내용은 [CLI 바이너리 선택하기](docs/getting-started/binary-selection.md)를 참조하세요.

### Python 추론

```bash
# 설치
uv pip install ".[inference]"

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

주요 옵션: `--speaker-id`(화자 ID), `--device auto|cpu|gpu`, `--noise-scale`(음성 변동), `--noise-scale-w`(음소 길이 변동, 기본값: 0.8), `--length-scale`(말하기 속도)

> **WavLM 모델 권장 설정:** WavLM 판별기로 학습된 모델 (츠쿠요미짱 등)은 `--noise-scale 0.5`에서 최적의 음질을 얻을 수 있습니다 (기본값은 0.667).

#### Python CLI 모델 관리

```bash
# 모델 목록 표시
python -m piper --list-models
python -m piper --list-models ja

# 모델 다운로드
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# 다운로드 후 사용
python -m piper --model ja_JP-tsukuyomi-chan-medium --text "こんにちは" -f output.wav
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
```

> **참고:** webui 이미지는 CI에서 자동 빌드되지 않습니다. 수동 빌드: `docker build -t piper-webui -f docker/webui/Dockerfile .`

자세한 내용은 [docker/README.md](docker/README.md)를 참조하세요.

---

## 설치

### Python

Python 3.11 이상 필요. 의존성 관리에는 [uv](https://docs.astral.sh/uv/)를 권장합니다.

```bash
# CPU 추론
uv pip install ".[inference]"

# GPU 추론 (CUDA 환경 필요)
uv pip install ".[inference-gpu]"

# 학습
uv pip install ".[train]"

# 개발 (테스트, 린터 포함)
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
piper-plus = "0.4"
```

### 소스에서 빌드 (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

필수 요건: C++17 호환 컴파일러, CMake 3.15+

- **Linux**: 의존성 (ONNX Runtime, OpenJTalk 등)은 CMake에 의해 자동 다운로드됩니다
- **Windows**: [Windows 설정 가이드](docs/getting-started/windows-setup.md) 참조
- **macOS**: 의존성은 자동 다운로드

### 소스에서 빌드 (C#)

```bash
# C# CLI 빌드
dotnet build src/csharp/PiperPlus.sln -c Release
# 테스트
dotnet test src/csharp/PiperPlus.Core.Tests/
```

필수 요건: .NET 10 SDK 이상

#### C# CLI 사용 예시

```bash
# 모델 이름으로 추론 (자동 다운로드 지원, --output-file 생략 시 output.wav로 출력)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# 영어
piper-plus --model model.onnx --text "Hello world" --language en

# 다중 언어 (자동 언어 감지)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# 인라인 음소 표기 (텍스트 안에 직접 음소 지정)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# 스트리밍 (문장별 순차 PCM 출력)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# 커스텀 사전 (JSON v1/v2 또는 TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# 모델 다운로드
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# 테스트 모드 (ONNX 추론 없이 음소 ID 확인)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Rust CLI 사용 예시

```bash
# 모델 이름으로 추론 (자동 다운로드 지원)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# 영어
piper-plus-cli --model model.onnx --text "Hello world" --language en

# 모델 다운로드 및 관리
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# 스트리밍 (문장별 순차 합성)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# 커스텀 사전
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# GPU 추론
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# 테스트 모드 및 무음 모드
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# raw PCM 출력 (WAV 헤더 없음)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Note:** C# CLI는 `dotnet tool install -g PiperPlus.Cli`로, Rust CLI는 `cargo install piper-plus-cli`로 설치할 수 있습니다. 두 CLI 모두 8개 언어, 커스텀 사전, 스트리밍을 지원합니다.

### 소스에서 빌드 (Rust)

```bash
# Rust CLI 빌드
cargo build --release -p piper-plus-cli
# 테스트
cargo test -p piper-plus
```

필수 요건: Rust 1.88+, cargo

---

## 사용법

### C++ CLI

#### 텍스트 직접 입력 (권장)

`--text` 옵션으로 파이프 없이 텍스트를 직접 입력할 수 있습니다:

```sh
# 텍스트에서 음성 생성
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# 일본어 텍스트 (Windows에서의 인코딩 문제 회피)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# 화자 지정
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### 파이프 입력

```sh
# 기본
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# 스트리밍 (저지연)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# GPU 추론
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# 음소 타이밍 출력 (립싱크, 자막 동기화용)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# 커스텀 사전
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# 인라인 음소 입력
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# 원시 음소 입력
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# 스트리밍 (raw audio 출력)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

주요 옵션:

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--model PATH\|NAME` | 모델 파일 경로 또는 모델 이름 (다운로드된 모델 자동 검색) | - |
| `--text TEXT` | 텍스트 직접 입력 (파이프 불필요) | - |
| `--streaming` | 청크 기반 스트리밍 모드 | off |
| `--use-cuda` | CUDA GPU 추론 활성화 | off |
| `--gpu-device-id NUM` | GPU 디바이스 ID | 0 |
| `--length-scale VAL` | 말하기 속도 조정 (작을수록 빠름) | 1.0 |
| `--noise-scale VAL` | 음성 변동 제어 | 0.667 |
| `--noise-w VAL` | 음소 길이 변동 제어 | 0.8 |
| `--sentence-silence SEC` | 문장 사이 무음 (초) | 0.2 |
| `--speaker NUM` | 다중 화자 모델의 화자 번호 | 0 |
| `--phoneme-silence PHONEME SEC` | 특정 음소의 무음 시간 설정 | - |
| `--raw-phonemes` | 입력을 음소로 해석 | off |
| `--output-timing FILE` | 음소 타이밍 정보를 파일로 출력 (JSON/TSV) | - |
| `--custom-dict FILE` | 커스텀 사전 (쉼표 구분으로 복수 지정 가능) | - |
| `--json-input` | JSON 입력 모드 | off |
| `--list-models [LANG]` | 사용 가능한 모델 목록 표시 | - |
| `--download-model NAME` | 모델 다운로드 | - |
| `--model-dir DIR` | 모델 다운로드 디렉터리 | - |
| `--version` | 버전 표시 | - |
| `--config PATH` / `-c` | 설정 파일 경로 | - |
| `--output_file PATH` / `-f` | 출력 WAV 파일 경로 | - |
| `--output_dir PATH` / `-d` | 출력 디렉토리 | - |
| `--output-raw` | raw PCM 오디오를 표준 출력으로 출력 | off |
| `--language LANG` / `-l` | 언어 코드 | - |
| `--timing-format FMT` | 타이밍 출력 형식 (json/tsv) | json |
| `--test-mode` | 테스트 모드 (ONNX 추론 스킵) | off |
| `--debug` | 디버그 로그 활성화 | off |
| `--quiet` / `-q` | 로그 비활성화 | off |

`piper --help`로 전체 옵션을 확인할 수 있습니다.

> **WavLM 모델 권장 설정:** WavLM 판별기로 학습된 모델은 `--noise-scale 0.5`를 권장합니다 (기본값은 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON 입력

`--json-input` 플래그로 JSON 입력을 받을 수 있습니다:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### 모델 관리

#### 모델 목록 보기

```bash
# 사용 가능한 모델 목록 표시
./bin/piper --list-models

# 언어별 필터링
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### 모델 다운로드

```bash
# 모델 이름을 지정하여 다운로드 (별칭도 사용 가능)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# 다운로드 디렉터리 지정
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# 다운로드 후 모델 이름으로 추론 (전체 경로 불필요)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### 환경 변수 (C++ CLI)

| 변수명 | 설명 | 예시 |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | `--model` 미지정 시 기본 모델 경로 | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | `--config` 미지정 시 기본 설정 파일 경로 | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | 다운로드 모델 저장 디렉터리 | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA GPU 디바이스 ID | `0` |

### 헬퍼 스크립트 (Windows)

Windows 사용자를 위해 `scripts/` 디렉터리에 헬퍼 스크립트를 제공하고 있습니다.

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**명령 프롬프트:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## 학습

자세한 내용은 [학습 가이드](docs/guides/training/training-guide.md)를 참조하세요.

### 기본

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

### 다중 화자 및 다중 GPU

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

다중 GPU에서는 DDP (Distributed Data Parallel)가 자동으로 설정됩니다. NCCL 환경 변수 설정이 필요합니다. 자세한 내용은 다중 GPU 학습 가이드를 참조하세요.

### ONNX 변환

기본적으로 FP16 변환이 적용되어 모델 크기가 약 50% 줄어듭니다. `--no-fp16`으로 비활성화 가능합니다. 수치 안정성을 위해 LayerNormalization, Sigmoid, Softmax는 FP32로 유지됩니다.

```bash
# 표준 모델 (FP16 출력)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# FP32 출력
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM 모델 (--stochastic 기본 활성화)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### 체크포인트 관리

- `--resume_from_checkpoint` — 체크포인트에서 학습 재개
- `--resume_from_single_speaker_checkpoint` — 단일 화자 모델에서 다중 화자로 변환

### 음성 평가

`scripts/evaluation/` 에 평가용 테스트 텍스트가 있습니다.

---

## 사전 학습 모델

추론용 음성 합성 모델을 Hugging Face에 공개하고 있습니다.

**추론용 모델 (바로 사용 가능):**

| 모델 | 언어 | 화자 수 | 설명 | 다운로드 |
|---|---|---|---|---|
| 츠쿠요미짱 6lang | JA/EN/ZH/ES/FR/PT | 1 | 츠쿠요미짱 음성, 6개 언어 지원, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 일본어 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 일본어 음성, 6개 언어 지원, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**학습용 기본 모델 (파인튜닝용):**

| 모델 | 언어 | 화자 수 | 설명 | 다운로드 |
|---|---|---|---|---|
| 6개 언어 기본 모델 | JA/EN/ZH/ES/FR/PT | 571 | 다중 언어 사전 학습 완료 (508,187 발화, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### 모델 다운로드

**츠쿠요미짱 모델:**

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

### 6개 언어 기본 모델 특징 (학습용)

- 아키텍처: VITS + Prosody Features
- 학습 데이터: 508,187 발화 (571 화자, 6개 언어)
- 샘플링 레이트: 22,050 Hz
- 심볼 수: 173
- 운율 특성: A1/A2/A3 운율 정보 (일본어)
- 언어 그룹 균등 샘플링: 자동 활성화

**지원 언어:**

| 언어 | 코드 | language_id | 화자 수 | 발화 수 | 소스 |
|---|---|---|---|---|---|
| 일본어 | ja | 0 | 20 | 60,148 | MOE-Speech |
| 영어 | en | 1 | 310 | 74,912 | LibriTTS-R |
| 중국어 | zh | 2 | 142 | 63,223 | AISHELL-3 |
| 스페인어 | es | 3 | 63 | 168,374 | CML-TTS |
| 프랑스어 | fr | 4 | 28 | 107,464 | CML-TTS |
| 포르투갈어 | pt | 5 | 8 | 34,066 | CML-TTS |

> **Note:** piper-plus는 독자적인 아키텍처 확장(다중 언어 임베딩, Prosody A1/A2/A3, 173 심볼)을 적용하고 있으므로 upstream Piper의 체크포인트/ONNX 모델과의 호환성이 없습니다. piper-plus 전용 모델을 이용해 주세요.

---

## 일본어 TTS

OpenJTalk 통합에 의한 고품질 일본어 음성 합성. 사전 및 음성 파일은 첫 실행 시 자동으로 다운로드됩니다.

**환경 변수 (선택사항):**

| 변수명 | 설명 |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk 사전 경로 (미설정 시 자동 다운로드) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0`으로 자동 다운로드 비활성화 |
| `PIPER_OFFLINE_MODE` | `1`로 오프라인 모드 |

자세한 내용은 일본어 음성 합성 가이드 및 [음소 매핑 레퍼런스](docs/api-reference/phoneme-mapping.md)를 참조하세요.

---

## 플랫폼

### macOS

**Apple Silicon (M1/M2/M3+)만 지원.** Intel Mac은 Docker 또는 소스 빌드를 이용해 주세요.

첫 실행 시 보안 경고:

```bash
xattr -cr piper/
```

### Windows

x64 / arm64이 지원됩니다. OpenJTalk 사전은 첫 실행 시 자동으로 다운로드됩니다. 자세한 내용은 [Windows 설정 가이드](docs/getting-started/windows-setup.md)를 참조하세요.

```cmd
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

브라우저에서 직접 동작하는 일본어 TTS. 서버 불필요, 오프라인 지원.

- **[온라인 데모](https://ayutaz.github.io/piper-plus/)**
- **[기술 상세 및 통합 가이드](src/wasm/openjtalk-web/README.npm.md)**

---

## 관련 링크

### Unity — uPiper

Piper를 Unity에서 사용하기 위한 플러그인: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android 지원
- 일본어, 영어 지원, 비동기 API, 스트리밍

### 음성 모델 (Voices)

piper-plus 모델: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6개 언어 기본 모델) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

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

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## 문서

| 카테고리 | 링크 |
|---|---|
| 일본어 TTS | 일본어 음성 합성 가이드 |
| 학습 | [학습 가이드](docs/guides/training/training-guide.md) · 다중 GPU |
| API | [음소 매핑](docs/api-reference/phoneme-mapping.md) · [환경 변수](docs/getting-started/environment-variables.md) |
| 기능 | [WebUI](docs/features/webui.md) · CLI 강화 · 스트리밍 · Phoneme Timing · SSML |
| 설정 | 빠른 시작 (일본어) · [Windows](docs/getting-started/windows-setup.md) · [문제 해결](docs/getting-started/troubleshooting.md) |
| Docker | [Docker 환경](docker/README.md) |
| WebAssembly | [기술 상세](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md)를 참조하세요.

## Changelog

[CHANGELOG.md](CHANGELOG.md)를 참조하세요.
