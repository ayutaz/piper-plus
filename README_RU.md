![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md) | Русский | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

Быстрая и качественная нейронная система синтеза речи (TTS). Построена на архитектуре [VITS](https://github.com/jaywalnut310/vits/) и поддерживает мультиспикерный синтез на 8 языках: японском, английском, китайском, корейском, испанском, французском, португальском и шведском. Форк [Piper](https://github.com/rhasspy/piper) со значительным расширением поддержки японского языка, улучшением качества звука и возможностей обучения.

**[Hugging Face демо](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly демо](https://ayutaz.github.io/piper-plus/)** (работает в браузере, сервер не требуется)

---

## Содержание

- [Основные возможности](#основные-возможности)
- [Быстрый старт](#быстрый-старт)
- [Предобученные модели](#предобученные-модели)
- [Установка](#установка)
- [Использование](#использование)
- [Обучение](#обучение)
- [Японский TTS](#японский-tts)
- [Платформы](#платформы)
- [Ссылки](#ссылки)

---

## Основные возможности

### Синтез речи

- **8 языков** — японский, английский, китайский, испанский, французский, португальский, шведский, корейский (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *Обученная модель покрывает 6 языков (JA/EN/ZH/ES/FR/PT)*
- **Японский TTS** — интеграция с OpenJTalk, просодическая информация (A1/A2/A3), маркеры вопросительных слов (#204), контекстно-зависимые варианты «ん» (#207)
- **Английский TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), espeak-ng не требуется
- **Мультиспикер** — поддержка до 571 диктора (базовая модель для обучения), SpeakerBalancedBatchSampler, сбалансированная выборка по языковым группам
- **Пользовательский словарь** — встроенный словарь произношений для 200+ технических терминов
- **Фонемный ввод** — прямой ввод фонем через нотацию `[[ phonemes ]]` — [руководство](docs/features/phoneme-input.md)

### Обучение

- **WavLM Discriminator** — улучшение MOS на +0.15–0.25 (включён по умолчанию, используется только при обучении)
- **MB-iSTFT-VITS2 Decoder** — Декодер унифицирован на MB-iSTFT + PQMF, CPU-инференс ~2.21x быстрее. Совместимо с ONNX и существующими runtime
- **FP16 Mixed Precision** — ускорение обучения в 2–3 раза, сокращение памяти ~50% (включено по умолчанию)
- **EMA** — Exponential Moving Average для стабилизации обучения (включено по умолчанию)
- **Мульти-GPU** — поддержка DDP, автоматическое масштабирование скорости обучения
- **Prosody Features** — внедрение просодической информации в Duration Predictor (`--prosody-dim 16`)
- **Интеграция с Wandb** — мониторинг метрик в реальном времени

### Интерфейсы

- **[WebUI (Gradio)](docs/features/webui.md)** — вывод и обучение, поддержка Docker
- **C++ CLI** — потоковый вывод, CUDA-инференс, **вывод Phoneme Timing (JSON/TSV/SRT)**, пользовательский словарь
- **[C API Разделяемая библиотека](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, поддержка FFI (Flutter/Godot/Swift и др.), потоковый API
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — полная работа в браузере, **вывод Phoneme Timing (JSON/TSV/SRT)**, сервер не требуется
- **[Docker](docker/README.md)** — 5 образов: вывод, обучение, WebUI, C++
- **PyPI** — `pip install piper-plus`, 8 языков мультиязычно, **вывод Phoneme Timing (JSON/TSV/SRT)**, потоковый вывод, **HTTP API на основе FastAPI**
- **C# CLI** — кроссплатформенный .NET 10, 8 языков, ONNX-инференс, **вывод Phoneme Timing (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, потоковый вывод, CUDA/CoreML/DirectML, **вывод Phoneme Timing (JSON/TSV/SRT)**, автозагрузка словарей
- **[Go CLI](src/go/README.md)** — HTTP API-сервер, пулинг сессий, Docker, единый бинарник, **вывод Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — поддерживается во всех 6 рантаймах (Python/Rust/C#/Go/WASM/C++)
- **Поддержка SSML** — `<speak>`, `<break>`, `<prosody rate="...">` доступны в 4 рантаймах (Python/Rust/C#/Go)
- **Улучшение качества коротких текстов (Strategy A/B/C)** — Silence Padding, Dynamic Scales и автоматический SSML `<break>` во всех 6 рантаймах

### Поддержка функций по рантаймам

Эквивалентный мультиязычный синтез на 8 языках в 6 рантаймах (Python/Rust/C#/Go/JS-WASM/C++). Phoneme Timing, потоковый вывод (включая разбиение по предложениям), Voice Cloning и пользовательские словари доступны во всех рантаймах. SSML поддерживается в 4 рантаймах (Python/Rust/C#/Go), HTTP API — в 2 рантаймах (Python/Go).

### Платформы

| Платформа | Архитектура | Примечание |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | Полная поддержка |
| macOS | ARM64 (Apple Silicon) | M1/M2/M3+ |
| Windows | x64 | Полная поддержка |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | Разделяемая библиотека, Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 10, Linux/macOS/Windows |
| Rust | x64 | Linux x64, macOS ARM64, Windows x64 |
| Go | x64 | Linux x64, macOS ARM64, Windows x64 |

---

## Быстрый старт

### Предсобранные бинарники (сборка не требуется)

Скачайте предсобранные бинарники из [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) и сразу начните синтезировать речь.

**1. Скачайте бинарник**

Скачайте и распакуйте архив для вашей ОС.

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

**Linux (ARM64, Raspberry Pi 4/5):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-linux-arm64.tar.gz
tar xzf piper.tar.gz
cd piper
```

**2. Скачайте модель и сгенерируйте речь**

```sh
# Скачать модель Цукуёми-тян
./bin/piper --download-model tsukuyomi

# Сгенерировать речь (достаточно указать имя модели — загруженная модель определяется автоматически)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **О кодовой странице Windows cmd:** Опция `--text` внутри использует `GetCommandLineW()` (UTF-16), поэтому работает независимо от кодовой страницы. При использовании ввода через конвейер (`echo ... | piper`) предварительно переключите кодовую страницу на UTF-8 командой `chcp 65001`.
>
> **Каталог вывода output.wav:** Файл создаётся в текущем каталоге (куда вы перешли командой `cd piper`).

> **Какой бинарник выбрать?** Релизы также включают CLI `piper-plus-cli-*` (C# .NET) и `piper-plus-rs-cli-*` (Rust). В быстром старте выше используется **C++ CLI (`piper-*`)**, который имеет самую широкую поддержку платформ и рекомендуется для большинства пользователей. Подробнее см. [Выбор CLI-бинарника](docs/getting-started/binary-selection.md).

### Вывод через Python

```bash
# Установка
uv pip install ".[inference]"

# Вывод на японском
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# Вывод на английском
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

Основные параметры: `--speaker-id` (ID диктора), `--device auto|cpu|gpu`, `--noise-scale` (вариативность голоса), `--noise-scale-w` (вариация длины фонем, по умолчанию: 0.8), `--length-scale` (скорость речи)

> **Рекомендации для моделей WavLM:** Для моделей, обученных с WavLM Discriminator (например, Цукуёми-тян), оптимальное качество достигается при `--noise-scale 0.5` (по умолчанию 0.667).

#### Управление моделями через Python CLI

```bash
# Список моделей
python -m piper --list-models
python -m piper --list-models ja

# Скачивание модели
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# Использование после скачивания
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

# Вывод через Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# Вывод на GPU (добавьте --gpus all)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

Готовые образы CI/CD:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Примечание:** Образ webui не собирается автоматически в CI. Соберите вручную: docker build -t piper-webui -f docker/webui/Dockerfile .

Подробности см. в [docker/README.md](docker/README.md).

---

## Установка

### Python

Требуется Python 3.11+. Для управления зависимостями рекомендуется [uv](https://docs.astral.sh/uv/).

```bash
# Вывод на CPU
uv pip install ".[inference]"

# Вывод на GPU (требуется окружение CUDA)
uv pip install ".[inference-gpu]"

# Обучение
uv pip install ".[train]"

# Разработка (тесты и линтеры)
uv pip install ".[dev]"
```

Также доступна установка через PyPI:

```bash
pip install piper-plus
```

### Установка из пакетных менеджеров

**Python (PyPI):**
```bash
pip install piper-plus
```

**npm (WASM для браузера):**
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

**C# библиотека (NuGet):**
```bash
dotnet add package PiperPlus.Core
```

**Rust библиотека (crates.io):**
```toml
[dependencies]
piper-plus = "0.4"
```

### Сборка из исходников (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Требования: компилятор с поддержкой C++17, CMake 3.15+

- **Linux**: зависимости (ONNX Runtime, OpenJTalk и др.) скачиваются автоматически через CMake
- **Windows**: см. [руководство по настройке для Windows](docs/getting-started/windows-setup.md)
- **macOS**: зависимости скачиваются автоматически

### Сборка из исходников (C#)

```bash
# Сборка C# CLI
dotnet build src/csharp/PiperPlus.sln -c Release
# Тесты
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Требования: .NET 10 SDK или новее

#### Примеры использования C# CLI

```bash
# Вывод по имени модели (с автозагрузкой, без --output-file выводит в output.wav)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# Английский
piper-plus --model model.onnx --text "Hello world" --language en

# Мультиязычный (автоопределение языка)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Встроенная фонемная нотация (указание фонем прямо в тексте)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Потоковый вывод (последовательный PCM-вывод по предложениям)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# Пользовательский словарь (JSON v1/v2 или TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# Скачивание модели
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Тестовый режим (проверка phoneme IDs без ONNX-инференса)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Примеры использования Rust CLI

```bash
# Вывод по имени модели (с автозагрузкой)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# Английский
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Скачивание и управление моделями
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Потоковый вывод (последовательный синтез по предложениям)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# Пользовательский словарь
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# Инференс на GPU
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Тестовый и тихий режимы
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Сырой PCM-вывод (без WAV-заголовка)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Примечание:** C# CLI устанавливается через `dotnet tool install -g PiperPlus.Cli`, Rust CLI — через `cargo install piper-plus-cli`. Оба поддерживают 8 языков, пользовательские словари и потоковый вывод.

### Сборка из исходников (Rust)

```bash
# Сборка Rust CLI
cargo build --release -p piper-plus-cli
# Тесты
cargo test -p piper-plus
```

Требования: Rust 1.88+, cargo

---

## Использование

### C++ CLI

#### Прямой ввод текста (рекомендуется)

С помощью опции `--text` можно вводить текст напрямую без использования конвейера:

```sh
# Генерация речи из текста
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# Японский текст (обход проблем с кодировкой на Windows)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# Выбор диктора
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Ввод через конвейер

```sh
# Базовый вариант
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# Потоковый вывод (низкая задержка)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# Инференс на GPU
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# Вывод тайминга фонем (для синхронизации губ и субтитров)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Пользовательский словарь
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Встроенный ввод фонем
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# Сырой ввод фонем
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# Потоковый вывод (сырой звук)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Основные параметры:

| Параметр | Описание | По умолчанию |
|---|---|---|
| `--model PATH\|NAME` | Путь к файлу модели или имя модели (загруженные модели определяются автоматически) | - |
| `--text TEXT` | Прямой ввод текста (без конвейера) | - |
| `--streaming` | Режим потокового вывода по чанкам | выкл. |
| `--use-cuda` | Включить CUDA GPU-инференс | выкл. |
| `--gpu-device-id NUM` | ID GPU-устройства | 0 |
| `--length-scale VAL` | Скорость речи (меньше = быстрее) | 1.0 |
| `--noise-scale VAL` | Управление вариативностью голоса | 0.667 |
| `--noise-w VAL` | Управление вариативностью длительности фонем | 0.8 |
| `--sentence-silence SEC` | Пауза между предложениями (сек.) | 0.2 |
| `--speaker NUM` | Номер диктора для мультиспикерной модели | 0 |
| `--phoneme-silence PHONEME SEC` | Длительность паузы для конкретной фонемы | - |
| `--raw-phonemes` | Интерпретировать ввод как фонемы | выкл. |
| `--output-timing FILE` | Вывод тайминга фонем в файл (JSON/TSV) | - |
| `--custom-dict FILE` | Пользовательский словарь (несколько файлов через запятую) | - |
| `--json-input` | Режим JSON-ввода | выкл. |
| `--list-models [LANG]` | Показать список доступных моделей | - |
| `--download-model NAME` | Скачать модель | - |
| `--model-dir DIR` | Каталог для скачивания моделей | - |
| `--config`/`-c` | Путь к файлу конфигурации | - |
| `--output_file`/`-f` | Путь к выходному WAV-файлу | - |
| `--output_dir`/`-d` | Выходной каталог | - |
| `--output-raw` | Вывод raw PCM-аудио в stdout | выкл. |
| `--language`/`-l` | Код языка | - |
| `--timing-format` | Формат вывода тайминга json/tsv | - |
| `--test-mode` | Тестовый режим, пропуск ONNX-инференса | выкл. |
| `--debug` | Включить отладочное логирование | выкл. |
| `--quiet`/`-q` | Отключить логирование | выкл. |
| `--version` | Показать версию | - |

Все параметры можно посмотреть командой `piper --help`.

> **Рекомендации для моделей WavLM:** Для моделей, обученных с WavLM Discriminator, рекомендуется `--noise-scale 0.5` (по умолчанию 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON-ввод

Флаг `--json-input` включает приём входных данных в формате JSON:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Управление моделями

#### Просмотр списка моделей

```bash
# Показать список доступных моделей
./bin/piper --list-models

# Фильтр по языку
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### Скачивание моделей

```bash
# Скачать по имени модели (поддерживаются псевдонимы)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# Указать каталог для скачивания
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# После скачивания модель доступна по имени (полный путь не нужен)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### Переменные окружения (C++ CLI)

| Переменная | Описание | Пример |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | Модель по умолчанию, если `--model` не указан | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | Файл конфигурации по умолчанию, если `--config` не указан | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | Каталог для хранения скачанных моделей | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | ID CUDA GPU-устройства | `0` |

### Вспомогательные скрипты (Windows)

Для пользователей Windows в каталоге `scripts/` доступны вспомогательные скрипты.

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Командная строка:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Обучение

Подробности см. в [руководстве по обучению](docs/guides/training/training-guide.md).

### Основы

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

### Мультиспикер и мульти-GPU

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

При использовании нескольких GPU DDP (Distributed Data Parallel) настраивается автоматически. Требуется установка переменных окружения NCCL. Подробности см. в руководстве по обучению на нескольких GPU.

### Конвертация в ONNX

По умолчанию применяется FP16-конвертация, уменьшающая размер модели примерно на 50%. Отключается флагом `--no-fp16`. Для численной стабильности LayerNormalization, Sigmoid и Softmax остаются в FP32.

```bash
# Стандартная модель (FP16)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Вывод FP32
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# Модель WavLM (--stochastic включено по умолчанию)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Управление чекпоинтами

- `--resume_from_checkpoint` — возобновление обучения с чекпоинта
- `--resume_from_single_speaker_checkpoint` — преобразование из односпикерной модели в мультиспикерную

### Оценка качества речи

`scripts/evaluation/` содержит тестовые тексты для оценки.

---

## Предобученные модели

Модели для синтеза речи доступны на Hugging Face.

**Модели для инференса (готовы к использованию):**

| Модель | Языки | Дикторов | Описание | Скачать |
|---|---|---|---|---|
| Цукуёми-тян 6lang | JA/EN/ZH/ES/FR/PT | 1 | Голос Цукуёми-тян, 6 языков, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Японский 6lang | JA/EN/ZH/ES/FR/PT | 1 | Японский голос CSS10, 6 языков, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Базовые модели для обучения (для дообучения):**

| Модель | Языки | Дикторов | Описание | Скачать |
|---|---|---|---|---|
| 6-языковая базовая модель | JA/EN/ZH/ES/FR/PT | 571 | Предобученная мультиязычная модель (508 187 высказываний, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### Скачивание моделей

**Модель Цукуёми-тян:**

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

### Характеристики 6-языковой базовой модели (для обучения)

- Архитектура: VITS + Prosody Features
- Данные для обучения: 508 187 высказываний (571 диктор, 6 языков)
- Частота дискретизации: 22 050 Гц
- Количество символов: 173
- Prosody Features: просодическая информация A1/A2/A3 (японский)
- Сбалансированная выборка по языковым группам: включается автоматически

**Поддерживаемые языки:**

| Язык | Код | language_id | Дикторов | Высказываний | Источник |
|---|---|---|---|---|---|
| Японский | ja | 0 | 20 | 60 148 | MOE-Speech |
| Английский | en | 1 | 310 | 74 912 | LibriTTS-R |
| Китайский | zh | 2 | 142 | 63 223 | AISHELL-3 |
| Испанский | es | 3 | 63 | 168 374 | CML-TTS |
| Французский | fr | 4 | 28 | 107 464 | CML-TTS |
| Португальский | pt | 5 | 8 | 34 066 | CML-TTS |

> **Примечание:** piper-plus использует собственные архитектурные расширения (мультиязычные эмбеддинги, Prosody A1/A2/A3, 173 символа), поэтому не совместим с чекпоинтами и ONNX-моделями оригинального Piper. Используйте модели, специально созданные для piper-plus.

---

## Японский TTS

Высококачественный синтез японской речи с интеграцией OpenJTalk. Словарь и голосовые файлы загружаются автоматически при первом запуске.

**Переменные окружения (необязательно):**

| Переменная | Описание |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | Путь к словарю OpenJTalk (при отсутствии загружается автоматически) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` — отключить автозагрузку |
| `PIPER_OFFLINE_MODE` | `1` — автономный режим |

Подробности см. в руководстве по синтезу японской речи и в [справочнике по фонемному маппингу](docs/api-reference/phoneme-mapping.md).

---

## Платформы

### macOS

**Поддерживается только Apple Silicon (M1/M2/M3+).** Для Intel Mac используйте Docker или сборку из исходников.

При первом запуске может появиться предупреждение безопасности:

```bash
xattr -cr piper/
```

### Windows

Поддерживаются x64 / arm64. Словарь OpenJTalk загружается автоматически при первом запуске. Подробности см. в [руководстве по настройке для Windows](docs/getting-started/windows-setup.md).

```cmd
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

Японский TTS, работающий прямо в браузере. Не требует сервера, поддерживает автономный режим.

- **[Онлайн-демо](https://ayutaz.github.io/piper-plus/)**
- **[Техническая документация и руководство по интеграции](src/wasm/openjtalk-web/README.npm.md)**

---

### piper-plus-g2p (Автономный пакет G2P)

Мультиязычный G2P (Grapheme-to-Phoneme) доступен как автономные пакеты:

- **Python**: `pip install piper-plus-g2p` — [Исходный код](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Исходный код](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Исходный код](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Исходный код](src/wasm/g2p/)

---

## Ссылки

### Unity — uPiper

Плагин для использования Piper в Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Японский и английский языки, асинхронный API, потоковый вывод

### Voices

Модели piper-plus: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6-языковая базовая) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Примечание:** piper-plus использует собственную систему G2P и фонем, поэтому модели оригинального Piper (rhasspy/piper-voices) НЕ совместимы.

### Статьи

- [Создание предобученной модели Piper для английского языка на основе LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Создание японской модели Piper на основе набора данных JVS](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Дообучение модели Piper на наборе данных Цукуёми-тян](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### Проекты, использующие Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Документация

| Категория | Ссылки |
|---|---|
| Японский TTS | Руководство по синтезу японской речи |
| Обучение | [Руководство по обучению](docs/guides/training/training-guide.md) · Мульти-GPU |
| API | [Фонемный маппинг](docs/api-reference/phoneme-mapping.md) · [Переменные окружения](docs/getting-started/environment-variables.md) |
| Функции | [WebUI](docs/features/webui.md) · Расширенный CLI · Потоковый вывод · Phoneme Timing · SSML |
| Настройка | Быстрый старт (японский) · [Windows](docs/getting-started/windows-setup.md) · [Устранение неполадок](docs/getting-started/troubleshooting.md) |
| Docker | [Окружение Docker](docker/README.md) |
| WebAssembly | [Техническая документация](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

См. [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

См. [CHANGELOG.md](CHANGELOG.md).
