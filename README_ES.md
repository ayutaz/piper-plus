![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | Español | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Paquetes:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 El único fork de Piper con licencia MIT** — El proyecto original [rhasspy/piper](https://github.com/rhasspy/piper) se archivó en octubre de 2025 y [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) pasó a la licencia GPL-3.0. piper-plus es el único fork compatible con MIT sin dependencia de espeak-ng. Su G2P propio admite 8 idiomas (JA/EN/ZH/KO/ES/FR/PT/SV), lo que lo hace adecuado para uso comercial e integrado.

> **📢 v2.0.0 Cambios incompatibles (2026-05, en preparación en `dev`; la última etiqueta de release es v1.13.0):** Imágenes Docker predeterminadas unificadas a CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (se requiere driver NVIDIA del host **R570+**; los drivers antiguos no pueden iniciar las nuevas imágenes) / entrenamiento actualizado a torch 2.11+cu128 (los checkpoints creados con torch 2.2 ya no se pueden reanudar) / TF32 + bf16-mixed son los nuevos valores predeterminados de entrenamiento. Detalles: [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

Sistema de texto a voz (TTS) neuronal, rápido y de alta calidad. Basado en la arquitectura [VITS](https://github.com/jaywalnut310/vits/), soporta síntesis de voz multilingüe y multihablante en 8 idiomas: japonés, inglés, chino, coreano, español, francés, portugués y sueco. Es un fork de [Piper](https://github.com/rhasspy/piper) con mejoras significativas en soporte para japonés, calidad de audio y funcionalidades de entrenamiento.

**[Demo en Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (funciona en el navegador, sin servidor)

---

## Tabla de contenidos

- [Benchmark](#benchmark)
- [Características principales](#características-principales)
- [Inicio rápido](#inicio-rápido)
- [Instalación](#instalación)
- [Uso](#uso)
- [Entrenamiento](#entrenamiento)
- [Modelos preentrenados](#modelos-preentrenados)
- [Plataformas](#plataformas)
- [Enlaces relacionados](#enlaces-relacionados)

---

## Benchmark

> **Entorno de medición**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cores / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Texto de prueba**: "Hello, how are you doing today?" (inglés, 25 fonemas)
> **Parámetros de medición**: 5 iteraciones de warmup + 30 mediciones (intra-op threads = auto)
> **Modelos utilizados**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (decodificador unificado introducido en el PR #320)
> - Piper original: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (release de k2-fsa)
>
> **Reproducción**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| Sistema | RTF ↓ | Latencia P50 (ms) | Tamaño (MB) | RAM (MB) | Arranque inicial (ms) | Parámetros | Idiomas | Licencia |
|---------|-------|-------------------|-------------|---------|-----------------------|-----------|---------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (archivado) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/modelo | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/modelo | Apache-2.0 |
| piper1-gpl (fork OHF) † | 0.06 | — | 75 | 150 | 400 | — | 1/modelo | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Nota**: RTF (Real-Time Factor): cuanto más bajo, más rápido. `Latencia P50` es la mediana de una inferencia individual y el indicador más directo de la capacidad de respuesta real. Gracias al decodificador unificado MB-iSTFT, piper-plus logra la latencia P50 más baja con 27 ms (-23% frente a los 35 ms del Piper original, -49% frente a los 53 ms de sherpa-onnx), con un tamaño de modelo de 38 MB, entre los más pequeños. También supone una mejora del -38% respecto al anterior piper-plus basado en HiFi-GAN (P50 de 43.3 ms).
>
> **†** Las filas marcadas no se volvieron a medir en este PR (`piper1-gpl` comparte arquitectura y formato ONNX con el Piper original, por lo que debería ser prácticamente equivalente a la fila del Piper original. `Kokoro-82M` usa otra arquitectura y `eSpeak-NG` es un CLI no neuronal, por lo que no encajan en el contrato de tensores de `scripts/benchmark.py` y requerirían un arnés aparte). Sus valores provienen de la medición anterior (Apple M2 Max).

### Benchmark RTF multi-runtime (valores más recientes)

Publicamos los resultados más recientes de RTF y latencia medidos de forma transversal en los 6 runtimes (Python / Rust / Go / C# / C++ / WASM) con `multilingual-test-medium.onnx`. Se actualizan automáticamente con cada merge a la rama dev.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Características principales

### Síntesis de voz

- **8 idiomas** — Japonés, inglés, chino, español, francés, portugués (con cambio de dialecto BR/EU: `pt`/`pt-BR`/`pt-PT`), sueco y coreano (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *El modelo entrenado cubre 6 idiomas (JA/EN/ZH/ES/FR/PT)*
- **TTS en japonés** — Integración con OpenJTalk, información prosódica (A1/A2/A3), marcadores de interrogación (#204), variantes contextuales de "n" (#207)
- **TTS en inglés** — G2P libre de GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), sin necesidad de espeak-ng
- **Multihablante** — Soporte para 571 hablantes (modelo base de entrenamiento), SpeakerBalancedBatchSampler, muestreo equilibrado por grupo de idioma
- **Diccionario personalizado** — Adición de diccionarios de pronunciación del usuario mediante JSON (v1/v2) / TSV
- **Entrada de fonemas** — Especificación directa mediante la notación `[[ fonemas ]]` — [Guía](docs/features/phoneme-input.md)

### Entrenamiento

- **Discriminador WavLM** — Mejora de MOS +0.15-0.25 (activo por defecto, solo durante el entrenamiento)
- **Decodificador MB-iSTFT-VITS2** — Decodificador unificado a MB-iSTFT + PQMF, inferencia CPU 2.21x más rápida. Formato ONNX sin cambios, compatible con los runtimes existentes
- **Precisión mixta BF16** — `--precision bf16-mixed` (predeterminado) + TF32 aceleran el entrenamiento, con ~50% menos memoria
- **EMA** — Estabilidad de entrenamiento mejorada con Exponential Moving Average (activo por defecto)
- **Multi-GPU** — Soporte DDP, escalado automático de tasa de aprendizaje
- **Características prosódicas** — Inyección de información prosódica al Duration Predictor (`--prosody-dim 16`)
- **Integración con Wandb** — Monitorización de métricas en tiempo real

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inferencia y entrenamiento, compatible con Docker
- **CLI C++** — Streaming, inferencia CUDA, **salida de Phoneme Timing (JSON/TSV/SRT)**, diccionario personalizado
- **[Biblioteca compartida C API](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatible con FFI (Flutter/Godot/Swift, etc.), API de streaming
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), el motor de síntesis se distribuye como xcframework universal para iOS arm64 device + simulator
- **[Swift G2P para iOS (SPM)](docs/guides/platform/swift-g2p-integration.md)** — Biblioteca independiente `PiperPlusG2P`: G2P de 8 idiomas en iOS sin depender de ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Funciona completamente en el navegador, **salida de Phoneme Timing (JSON/TSV/SRT)**, sin servidor
- **[Docker](docker/README.md)** — 7 familias de imágenes: inferencia, entrenamiento, WebUI, C++, Wyoming (Home Assistant) y más
- **PyPI** — Instalación sencilla con `pip install piper-plus`, 8 idiomas multilingüe, **salida de Phoneme Timing (JSON/TSV/SRT)**, streaming, HTTP API
- **CLI C#** — .NET 10 multiplataforma, 8 idiomas multilingüe, inferencia ONNX, **salida de Phoneme Timing (JSON/TSV/SRT)**
- **CLI Rust** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML, **salida de Phoneme Timing (JSON/TSV/SRT)**, descarga automática de diccionarios
- **[CLI Go](src/go/README.md)** — Servidor HTTP API, pooling de sesiones, compatible con Docker, binario único, **salida de Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — Disponible en los 6 runtimes (Python/Rust/C#/Go/WASM/C++). En C++ está disponible tanto en el binario CLI como en la biblioteca C API `libpiper_plus`. Extracción del speaker embedding a partir de un audio de referencia con ECAPA-TDNN (`--reference-audio`)
- **Soporte SSML** — `<speak>`, `<break>`, `<prosody rate="...">` implementados en los 6 runtimes Python/Rust/C#/Go/WASM/C++ (en C++ mediante el CLI `--ssml`)
- **Mejora de calidad para textos cortos (Estrategia A/B/C)** — Silence Padding, Dynamic Scales y SSML `<break>` automático en los 6 runtimes (`docs/spec/short-text-contract.toml`)

### Soporte de funcionalidades por runtime

Síntesis multilingüe equivalente en 8 idiomas a través de 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++). Phoneme Timing, streaming (incluida la división por oraciones), Voice Cloning y diccionarios personalizados están disponibles en todos los runtimes. SSML es compatible con los 6 runtimes (en C++ mediante el CLI `--ssml`; no exportado en la C API) y la API HTTP con 2 runtimes (Python/Go).

---

## Inicio rápido

### Binarios precompilados (sin necesidad de compilar)

Descarga los binarios precompilados desde [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) y comienza a sintetizar voz de inmediato.

**1. Descargar el binario**

Descarga y descomprime según tu sistema operativo.

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

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Descargar un modelo y generar audio**

```sh
# Descargar el modelo de Tsukuyomi-chan
./bin/piper-plus --download-model tsukuyomi

# Generar audio (solo el nombre del modelo es suficiente - los modelos descargados se resuelven automaticamente)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Sobre el code page en Windows cmd:** La opción `--text` utiliza internamente `GetCommandLineW()` (UTF-16), por lo que funciona independientemente del code page. Solo si usas entrada por pipe (`echo ... | piper-plus`) necesitas cambiar antes a UTF-8 con `chcp 65001`.
>
> **Ubicación de output.wav:** Se genera en el directorio actual (donde ejecutaste `cd piper-plus`).

> **¿Qué binario debo elegir?** Las releases también incluyen los CLIs `piper-plus-cli-*` (C# .NET) y `piper-plus-rs-cli-*` (Rust) además de `piper-plus-cpp-*` (C++). El Inicio rápido anterior utiliza el **CLI de C++ (`piper-plus-cpp-*`)**, que tiene el soporte de plataformas más amplio y es el recomendado. Consulta [Cómo elegir un binario CLI](docs/getting-started/binary-selection.md) para más detalles.

### Inferencia con Python

```bash
# Instalacion
uv pip install ".[inference]"

# Inferencia en japones
uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --config /path/to/config.json \
    --output-dir ./output \
    --text "こんにちは、今日は良い天気ですね。"

# Inferencia en ingles
uv run python -m piper_train.infer_onnx \
    --model /path/to/en_model.onnx \
    --config /path/to/en_model.onnx.json \
    --output-dir ./output \
    --text "Hello, how are you today?" \
    --language en
```

Opciones principales: `--speaker-id` (ID del hablante), `--device auto|cpu|gpu`, `--noise-scale` (variación de la voz), `--length-scale` (velocidad de habla), `--noise-scale-w` (variación de duración de fonemas, predeterminado: 0.5)

> **Configuración recomendada para modelos WavLM:** Los modelos entrenados con WavLM Discriminator (como Tsukuyomi-chan) obtienen la mejor calidad de audio con `--noise-scale 0.5` (el valor predeterminado es 0.4).

#### Gestión de modelos con el CLI de Python

```bash
# Listar modelos disponibles
python -m piper_plus --list-models
python -m piper_plus --list-models ja

# Descargar un modelo
python -m piper_plus --download-model tsukuyomi
python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Usar despues de descargar
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

# Inferencia con Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device cpu

# Inferencia con GPU (agregar --gpus all)
docker run --rm --gpus all \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device gpu
```

Imágenes precompiladas por CI/CD:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

Para más detalles, consulta [docker/README.md](docker/README.md).

---

## Instalación

### Python

Se recomienda Python 3.13+ (3.11+ soportado). Se recomienda [uv](https://docs.astral.sh/uv/) para la gestión de dependencias.

```bash
# Inferencia CPU
uv pip install ".[inference]"

# Inferencia GPU (requiere entorno CUDA)
uv pip install ".[inference-gpu]"

# Entrenamiento
uv pip install ".[train]"

# Desarrollo (incluye tests y linters)
uv pip install ".[dev]"
```

También disponible como paquete de PyPI:

```bash
pip install piper-plus
```

### Instalación desde paquetes

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm (WASM para navegador):**

```bash
npm install piper-plus onnxruntime-web
```

**CLI C# (.NET Global Tool):**

```bash
dotnet tool install -g PiperPlus.Cli
```

**CLI Rust (crates.io):**

```bash
cargo install piper-plus-cli
```

**Biblioteca C# (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Biblioteca Rust (crates.io):**

```toml
[dependencies]
piper-plus = "0.5"
```

### Compilar desde el código fuente

Si no hay binarios precompilados para tu plataforma o quieres modificar piper-plus, puedes compilarlo desde el código fuente. Consulta la **[guía de compilación desde el código fuente](docs/guides/development/building-from-source.md)** para las instrucciones de compilación de los runtimes C++ / C# / Rust.

---

## Uso

Para las opciones detalladas de línea de comandos del CLI de C++, el formato de entrada JSON, la gestión de modelos, las variables de entorno y los scripts auxiliares de Windows, consulta la **[guía de uso del CLI](docs/guides/development/cli-usage.md)**.

Ejemplo sencillo:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Entrenamiento

Para el entrenamiento y fine-tuning de modelos piper-plus (configuración básica, multihablante / multi-GPU, conversión a ONNX, gestión de checkpoints, evaluación de audio), consulta la **[guía de entrenamiento](docs/guides/training/training-guide.md)**.

Las plantillas de comandos orientadas a producción para el preentrenamiento en 6 idiomas y el fine-tuning de Tsukuyomi-chan están en [CLAUDE.md](CLAUDE.md).

---

## Modelos preentrenados

Para la lista de modelos piper-plus publicados, las instrucciones de descarga, las características del modelo base de 6 idiomas y los detalles del TTS en japonés, consulta la **[guía de modelos](docs/guides/development/pretrained-models.md)**.

Modelos principales: `tsukuyomi` (japonés) y `css10-6lang` (descargables con `--download-model`), además del ckpt base de 6 idiomas (para entrenamiento / fine-tuning) — consulta [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) y [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) en HuggingFace.

---

## Plataformas

- **macOS**: Soporte nativo para Apple Silicon (arm64). Detalles en la [configuración de macOS](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: Compatible con x64 / arm64. Para la configuración de OpenJTalk, consulta la [guía de configuración de Windows](docs/getting-started/windows-setup.md)
- **WebAssembly**: Ejecución completamente offline en el navegador. [Demo](https://ayutaz.github.io/piper-plus/) | [Paquete npm](https://www.npmjs.com/package/piper-plus)

---

## Enlaces relacionados

### Unity — uPiper

Plugin para usar Piper en Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+, Unity.InferenceEngine
- Compatible con Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2)
- 7 idiomas (ja/en/zh/es/fr/pt/ko), API asíncrona, streaming

### Modelos de voz (Voices)

Modelos específicos de piper-plus: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (base de 6 idiomas) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Nota:** piper-plus utiliza su propio sistema G2P y de fonemas, por lo que los modelos del Piper original (rhasspy/piper-voices) NO son compatibles.

### Artículos relacionados (en japonés)

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (Paquete G2P independiente)

G2P multilingüe (Grapheme-to-Phoneme) disponible como paquetes independientes:

- **Python**: `pip install piper-plus-g2p` — [Código fuente](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Código fuente](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Código fuente](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Código fuente](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` — [Código fuente](android/piper-plus-g2p/) · [Guía de distribución de diccionarios](docs/guides/platform/android-g2p-dictionary.md)
- **Swift (iOS/macOS)**: Producto SPM `PiperPlusG2P` — [Guía de integración](docs/guides/platform/swift-g2p-integration.md) · [Código fuente](Sources/PiperPlusG2P/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentación

| Categoría | Enlaces |
|---|---|
| Entrenamiento | [Guía de entrenamiento](docs/guides/training/training-guide.md) (incluye multi-GPU) |
| API | [Mapeo de fonemas](docs/api-reference/phoneme-mapping.md) · [Variables de entorno](docs/getting-started/environment-variables.md) |
| Funcionalidades | [WebUI](docs/features/webui.md) · [Phoneme Timing](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| Configuración | [Windows](docs/getting-started/windows-setup.md) · [Solución de problemas](docs/getting-started/troubleshooting.md) |
| Docker | [Entorno Docker](docker/README.md) |
| WebAssembly | [Detalles técnicos](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Consulta [CONTRIBUTING.md](CONTRIBUTING.md). Para preguntas o reportes de errores, utiliza [Issues](https://github.com/ayutaz/piper-plus/issues). El código de conducta está en [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Changelog

Consulta [CHANGELOG.md](CHANGELOG.md).
