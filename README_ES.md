![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | Español | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Paquetes:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 El único fork de Piper con licencia MIT** — El proyecto original [rhasspy/piper](https://github.com/rhasspy/piper) se archivó en octubre de 2025. [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) pasó a la licencia GPL-3.0. piper-plus es el único fork compatible con MIT sin dependencia de espeak-ng. Su implementación propia de G2P admite 8 idiomas (JA/EN/ZH/KO/ES/FR/PT/SV), lo que lo hace adecuado para uso comercial e integrado.

> **📢 v2.0.0 Cambios incompatibles:** Las imágenes Docker predeterminadas usan CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (se requiere el driver NVIDIA del host **R570+**). El entrenamiento usa torch **2.11.0** + CUDA 12.8, con TF32 + bf16-mixed por defecto. No se admite reanudar checkpoints creados con torch 2.2. El import de Python y la CLI pasan a ser `piper_plus` / `piper-plus`. Para actualizar desde 1.13.0 a la versión pública actual, ejecute `pip install --upgrade "piper-plus[cpu]==2.0.2"`. Detalles: [guía de migración](docs/migration/v1.12-to-v2.0.md).

Sistema de texto a voz (TTS) neuronal, rápido y de alta calidad. Basado en la arquitectura [VITS](https://github.com/jaywalnut310/vits/), admite G2P/fonemización en 8 idiomas y síntesis de voz multihablante con los modelos entrenados actuales en 6 idiomas. Es un fork de [Piper](https://github.com/rhasspy/piper) que amplía notablemente el soporte para japonés, la calidad de audio y las funciones de entrenamiento.

**[Demo en Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (funciona en el navegador, sin servidor)

---

## Tabla de contenidos

- [Benchmark](#benchmark)
- [Características principales](#características-principales)
- [Inicio rápido](#inicio-rápido)
- [Instalación](#instalación)
- [Uso](#uso)
- [Entrenamiento](#entrenamiento-1)
- [Modelos preentrenados](#modelos-preentrenados)
- [Plataformas](#plataformas)
- [Enlaces relacionados](#enlaces-relacionados)

---

## Benchmark

> **Entorno de medición**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 núcleos / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Texto de prueba**: "Hello, how are you doing today?" (inglés, 25 fonemas)
> **Parámetros de medición**: 5 iteraciones de calentamiento / 30 iteraciones medidas (intra-op threads = auto)
> **Modelos utilizados**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (decodificador unificado introducido en el PR #320)
> - Piper original: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (versión de k2-fsa)
>
> **Reproducción**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| Sistema | RTF ↓ | Latency P50 (ms) | Tamaño (MB) | RAM (MB) | Arranque en frío (ms) | Parámetros | Idiomas | Licencia |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (archivado) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/modelo | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/modelo | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/modelo | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Nota**: RTF (Real-Time Factor): cuanto más bajo, más rápido. `Latency P50` es la mediana de una inferencia individual y el indicador más directo de la capacidad de respuesta real. Gracias al decodificador unificado MB-iSTFT, piper-plus logra la Latency P50 más baja, 27 ms (-23 % frente a los 35 ms de Piper original y -49 % frente a los 53 ms de sherpa-onnx), y con 38 MB su modelo está entre los más pequeños. Frente al anterior piper-plus basado en HiFi-GAN (P50 43.3 ms), la mejora también es del -38 %.
>
> Las filas marcadas con **†** no se volvieron a medir en este PR (`piper1-gpl` comparte arquitectura y formato ONNX con Piper original, por lo que debería ser prácticamente equivalente a la fila de Piper original; `Kokoro-82M` usa otra arquitectura y `eSpeak-NG` es una CLI no neuronal, de modo que ninguno encaja en el contrato de tensores de `scripts/benchmark.py` y requieren un arnés aparte). Estos valores proceden de una medición anterior (Apple M2 Max).

### Benchmark de RTF multi-runtime (valores más recientes)

Publicamos los resultados más recientes de RTF y latencia medidos en 6 runtimes (Python / Rust / Go / C# / C++ / WASM) con `multilingual-test-medium.onnx`. Se actualizan automáticamente con cada merge en la rama dev.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Características principales

### Síntesis de voz

- **G2P/fonemización en 8 idiomas** — japonés, inglés, chino, español, francés, portugués, sueco y coreano (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Los modelos entrenados actuales cubren 6 idiomas (JA/EN/ZH/ES/FR/PT)
- **TTS en japonés** — integración con OpenJTalk, información prosódica (A1/A2/A3), marcadores de interrogativos (#204), variantes de «N» dependientes del contexto (#207)
- **TTS en inglés** — v2.0.2 incluye un G2P basado en [g2p-en](https://github.com/Kyubyong/g2p), con código de inferencia Apache-2.0 y el aviso de licencia MIT de Tacotron. No se necesitan `g2p-en` / `Distance` externos ni espeak-ng. La definición de dependencias del antiguo PyPI 2.0.1 no cambia. Consulte la [guía de migración](docs/migration/python-g2p-license.md)
- **Multihablante** — 571 hablantes (modelo base para entrenamiento), SpeakerBalancedBatchSampler, muestreo equilibrado por grupo de idioma
- **Diccionario personalizado** — diccionario de pronunciación integrado con más de 200 términos técnicos
- **Entrada de fonemas** — especificación directa con la notación `[[ phonemes ]]` — [Guía](docs/features/phoneme-input.md)

### Entrenamiento

- **WavLM Discriminator** — mejora del MOS de +0.15-0.25 (activado por defecto, solo se usa durante el entrenamiento)
- **MB-iSTFT-VITS2 Decoder** — decodificador unificado en MB-iSTFT + PQMF, inferencia en CPU 2.21 veces más rápida. El formato ONNX no cambia y es compatible con los runtimes existentes
- **BF16 Mixed Precision** — `--precision bf16-mixed` es el valor predeterminado (TF32 también está activado por defecto). Es numéricamente más estable que FP16 y no requiere loss scaling. En GPU sin soporte para BF16 (como la T4), especifique `--precision 16-mixed`
- **EMA** — mayor estabilidad del entrenamiento mediante Exponential Moving Average (activado por defecto)
- **Multi-GPU** — soporte DDP, escalado automático de la tasa de aprendizaje
- **Prosody Features** — inyección de información prosódica en el Duration Predictor (`--prosody-dim 16`)
- **Integración con Wandb** — monitorización de métricas en tiempo real

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — admite inferencia y Docker. La pestaña Training local todavía envía argumentos de CLI obsoletos; para entrenar, use la [guía de entrenamiento](docs/guides/training/training-guide.md).
- **C++ CLI** — streaming, inferencia CUDA, **salida de tiempos de fonemas (JSON/TSV/SRT)**, diccionario personalizado
- **[Biblioteca compartida de la API de C](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatible con FFI (Flutter/Godot/Swift, etc.), API de streaming
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), el motor de síntesis se distribuye como universal para dispositivo iOS arm64 + simulador
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — biblioteca independiente `PiperPlusG2P`, G2P en 8 idiomas en iOS sin depender de ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — funciona por completo en el navegador, **salida de tiempos de fonemas (JSON/TSV/SRT)**, sin servidor
- **[Docker](docker/README.md)** — 6 imágenes para inferencia, entrenamiento, WebUI, C++ (inferencia/desarrollo) y Wyoming (Home Assistant)
- **PyPI** — instalación sencilla con `pip install piper-plus`, G2P/fonemización en 8 idiomas (los modelos entrenados actuales cubren 6 idiomas), **salida de tiempos de fonemas (JSON/TSV/SRT)**, streaming, API HTTP
- **C# CLI** — multiplataforma con .NET 10, G2P/fonemización en 8 idiomas (los modelos entrenados actuales cubren 6 idiomas), inferencia ONNX, **salida de tiempos de fonemas (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, soporte para CUDA/CoreML/DirectML, **salida de tiempos de fonemas (JSON/TSV/SRT)**, descarga automática de diccionarios
- **[Go CLI](src/go/README.md)** — servidor de API HTTP, pool de sesiones, soporte para Docker, binario único, **salida de tiempos de fonemas (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — los 6 runtimes (Python/Rust/C#/Go/WASM/C++) admiten como entrada un `speaker_embedding` precalculado compatible con el modelo. La C++ CLI y la API de C solo aceptan embeddings precalculados; la extracción mediante `--reference-audio` no está implementada. La inferencia real con el `zs-v1` público solo se ha comprobado con Python `piper-plus==2.0.0`. La ejecución pública de CI `38189966578` confirmó la inferencia en 6 runtimes usando como entrada IDs de fonemas compartidos de Python; el G2P nativo y la calidad en escucha humana quedan fuera de su alcance, y no se ha otorgado la aprobación de calidad.
- **Soporte de SSML** — el contrato del parser SSML está implementado en Python/Rust/Go/C#/WASM/C++. La síntesis lo admite en Python/Rust/Go/WASM/C++; C# Core incluye el parser, pero no está conectado a `--text` de la CLI. En C++ se usa mediante la opción `--ssml` de la CLI (no se exporta en la API de C).
- **Mejora de calidad para textos cortos (Strategy A/B/C)** — las Strategy A/B están implementadas en todos los runtimes. La Strategy C (inserción automática de `<break>` de SSML) abarca la inferencia en Python/Rust/Go/C#; el Python de entrenamiento, WASM y C++ quedan fuera. Detalles en el [contrato de textos cortos](docs/spec/short-text-contract.toml).

### Funciones admitidas por runtime

Los 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++) permiten sintetizar los 6 idiomas de los modelos entrenados actuales y además ofrecen G2P/fonemización en 8 idiomas. Los tiempos de fonemas, el streaming (incluida la división por frases), el Voice Cloning con embeddings precalculados compatibles con el modelo y los diccionarios personalizados se admiten como funciones del runtime. C++ solo acepta embeddings precalculados y `--reference-audio` no está implementado. La inferencia real con el `zs-v1` público solo se ha comprobado con Python `piper-plus==2.0.0`. La ejecución pública de CI `38189966578` confirma la inferencia en 6 runtimes con IDs de fonemas compartidos de Python, pero el G2P nativo y la calidad en escucha humana quedan fuera de su alcance, y no se ha otorgado la aprobación de calidad. La síntesis SSML se admite en Python/Rust/Go/WASM/C++ (C++ mediante la opción `--ssml` de la CLI, no exportada en la API de C). El parser de C# Core no está conectado a `--text` de la CLI, y la API HTTP está disponible en 2 runtimes (Python/Go).

---

## Inicio rápido

### Binarios precompilados (sin compilación)

Descargue los binarios precompilados desde [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) y empiece a sintetizar voz de inmediato.

**1. Descargar el binario**

Descargue y descomprima el archivo correspondiente a su sistema operativo.

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

**Compatibilidad ARM64:** el paquete C++ para Linux ARM64 de v2.0.2 se verifica con glibc 2.31 como límite superior de ABI. El arranque y la síntesis en japonés se validan con QEMU en Debian Bullseye / Bookworm / Trixie (64 bits). No se han probado el hardware real de Raspberry Pi ni Raspberry Pi OS en sí. El paquete anterior de v2.0.1 requiere glibc 2.38 o superior, así que use v2.0.2.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, ARM de 32 bits):**

Para ARMv7 solo se distribuye la C++ CLI. La CI comprueba la compilación y la síntesis en japonés con QEMU en Debian Trixie (ARM de 32 bits). No se ha probado en hardware real de Raspberry Pi.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Descargar un modelo y generar voz**

```sh
# Descargar el modelo de Tsukuyomi-chan
./bin/piper-plus --download-model tsukuyomi

# Generar voz (basta con el nombre del modelo - los modelos descargados se resuelven automaticamente)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Sobre la página de códigos de Windows cmd:** la opción `--text` usa internamente `GetCommandLineW()` (UTF-16), por lo que funciona sin depender de la página de códigos. Solo si usa entrada por tubería (`echo ... | piper-plus`) debe cambiar antes a UTF-8 con `chcp 65001`.
>
> **Ubicación de output.wav:** se genera en el directorio actual (donde ejecutó `cd piper-plus`).

> **¿Qué binario elijo?** Además de `piper-plus-cpp-*` (C++), Releases incluye las CLI `piper-plus-cli-*` (C# .NET) y `piper-plus-rs-cli-*` (Rust). La **C++ CLI (`piper-plus-cpp-*`)** que se usa en el inicio rápido anterior es la que admite más plataformas y la recomendada. Más detalles en [Cómo elegir el binario de la CLI](docs/getting-started/binary-selection.md).

### Inferencia con Python

```bash
# Instalacion
# Ejecutar desde la raiz del repositorio de un checkout del codigo fuente
uv sync --extra inference

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

Opciones principales: `--speaker-id` (ID de hablante), `--device auto|cpu|gpu`, `--noise-scale` (variación de la voz), `--length-scale` (velocidad del habla), `--noise-scale-w` (variación de la duración de los fonemas, predeterminado: 0.5)

> **Configuración recomendada para modelos WavLM:** los modelos entrenados con el WavLM Discriminator (como Tsukuyomi-chan) alcanzan la mejor calidad de audio con `--noise-scale 0.5` (el valor predeterminado es 0.4).

#### Gestión de modelos con la CLI de Python

```bash
# Mostrar la lista de modelos
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# Descargar un modelo
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Usar tras la descarga
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

# Inferencia con Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device cpu

# Inferencia con GPU (anadir --gpus all)
docker run --rm --gpus all \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device gpu
```

Imágenes compiladas por CI/CD:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

Más detalles en [docker/README.md](docker/README.md).

---

## Instalación

### Python

Se recomienda Python 3.13+ (se admite 3.11+). Para la gestión de dependencias se recomienda [uv](https://docs.astral.sh/uv/).

```bash
# Inferencia en CPU
uv sync --extra inference

# Inferencia en GPU (requiere un entorno CUDA)
uv sync --no-group cpu --extra inference-gpu

# Entrenamiento
uv sync --extra train

# Desarrollo (incluye pruebas y linters)
uv sync --extra dev
```

También se puede instalar desde el paquete de PyPI:

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

**C# CLI (.NET Global Tool):**

```bash
dotnet tool install -g PiperPlus.Cli
```

**Rust CLI (crates.io):**

```bash
cargo install piper-plus-cli
```

**Biblioteca de C# (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Biblioteca de Rust (crates.io):**

```toml
[dependencies]
piper-plus = "0.5"
```

### Compilar desde el código fuente

Si no hay binarios precompilados para su plataforma o desea modificar piper-plus, puede compilarlo desde el código fuente. Consulte la **[guía de compilación desde el código fuente](docs/guides/development/building-from-source.md)** para ver las instrucciones de compilación de los runtimes C++ / C# / Rust.

---

## Uso

Para conocer en detalle las opciones de línea de comandos de la C++ CLI, el formato de entrada JSON, la gestión de modelos, las variables de entorno y el uso de los scripts auxiliares de Windows, consulte la **[guía de uso de la CLI](docs/guides/development/cli-usage.md)**.

Ejemplo sencillo:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Entrenamiento

Para entrenar y hacer fine-tuning de modelos piper-plus (configuración básica, multihablante / multi-GPU, conversión a ONNX, gestión de checkpoints, evaluación de voz), consulte la **[guía de entrenamiento](docs/guides/training/training-guide.md)**.

Las plantillas de comandos para uso real (preentrenamiento en 6 idiomas y fine-tuning de Tsukuyomi-chan) están en [CLAUDE.md](CLAUDE.md).

---

## Modelos preentrenados

Para ver la lista de modelos piper-plus publicados, cómo descargarlos, las características del modelo base de 6 idiomas y los detalles del TTS en japonés, consulte la **[guía de modelos](docs/guides/development/pretrained-models.md)**.

Modelos principales: `tsukuyomi` (japonés), `zs-v1` (base experimental Zero-Shot/FT en 6 idiomas), `bilingual-ja-en-v4` (japonés-inglés, 2 idiomas) — para más detalles, consulte el [paquete zs-v1 de versión fija](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) en HuggingFace y [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

> **Base Zero-Shot/FT (`zs-v1`, 2026-10-10):** el paquete público de versión fija es la base experimental existente de v7 epoch 32 (JA/EN/ZH/ES/FR/PT, 571 hablantes, 173 fonemas, CAM++ de 192 dimensiones). Para la inferencia Zero-Shot, use `base.onnx` con un embedding de referencia extraído con el `campplus.onnx` incluido; para el entrenamiento adicional, use `base.ckpt` con el `config.json` incluido. Los ejemplos públicos se comprobaron funcionalmente con PyPI `piper-plus==2.0.0`, pero eso no implica aprobación de calidad, superación de una prueba de escucha humana ni la calidad más reciente o más alta. Los alias `base` / `zero-shot-base-zs-v1` están incluidos en v2.0.2 (no en 2.0.0 / 2.0.1). El `model.ckpt` de la raíz se trata por separado como una generación anterior.

> **FT de Tsukuyomi-chan (`zs-v1`, 2026-10-15):** hemos publicado un [modelo público de versión fija](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1) entrenado adicionalmente a partir de la misma generación de base pública. Combinando `tsukuyomi.onnx` y `tsukuyomi.onnx.json` se puede generar voz sin audio de referencia ni CAM++. Se registró una revisión humana de 3 frases en japonés y se aprobó su publicación como versión experimental (quality_approval=false; no es una aprobación de calidad). El alias `tsukuyomi` existente sigue seleccionando el modelo antiguo de la raíz, así que descargue el nuevo modelo desde las URL fijas de la [guía de modelos](docs/guides/development/pretrained-models.md).

---

## Plataformas

- **macOS**: compatibilidad nativa con Apple Silicon (arm64). Más detalles en [configuración de macOS](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: los paquetes C++ son para x64 y la C# CLI para x64 / arm64. Para configurar OpenJTalk, consulte la [guía de configuración de Windows](docs/getting-started/windows-setup.md)
- **WebAssembly**: ejecución completamente offline en el navegador. [Demo](https://ayutaz.github.io/piper-plus/) | [paquete npm](https://www.npmjs.com/package/piper-plus)

---

## Enlaces relacionados

### Unity — uPiper

Plugin para usar Piper en Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Compatible con Windows / macOS (Apple Silicon) / Linux / Android
- Japonés e inglés, API asíncrona, streaming

### Modelos de voz (Voices)

Modelos propios de piper-plus: [base Zero-Shot/FT zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Nota:** piper-plus usa su propio G2P y sistema de fonemas, por lo que no es compatible con los modelos del Piper upstream (rhasspy/piper-voices).

### Artículos relacionados (en japonés)

- [Crear un modelo preentrenado de Piper en inglés con LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Crear un modelo japonés de Piper con el conjunto de datos de voz JVS](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Entrenamiento adicional de un modelo de Piper con el conjunto de datos de Tsukuyomi-chan](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (paquete G2P independiente)

G2P multilingüe (Grapheme-to-Phoneme) disponible como paquete independiente:

- **Python**: `pip install piper-plus-g2p` — [Código fuente](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Código fuente](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Código fuente](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Código fuente](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [Código fuente](android/piper-plus-g2p/) · [Guía de distribución del diccionario](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentación

| Categoría | Enlaces |
|---|---|
| TTS en japonés | Guía de síntesis de voz en japonés |
| Entrenamiento | [Guía de entrenamiento](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Mapeo de fonemas](docs/api-reference/phoneme-mapping.md) · [Variables de entorno](docs/getting-started/environment-variables.md) |
| Funciones | [WebUI](docs/features/webui.md) · Mejoras de la CLI · Streaming |
| Configuración | Inicio rápido (japonés) · [Windows](docs/getting-started/windows-setup.md) · [Solución de problemas](docs/getting-started/troubleshooting.md) |
| Docker | [Entornos Docker](docker/README.md) |
| WebAssembly | [Detalles técnicos](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Consulte [CONTRIBUTING.md](CONTRIBUTING.md). Envíe sus preguntas e informes de errores a [Issues](https://github.com/ayutaz/piper-plus/issues). El código de conducta está en [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Changelog

Consulte [CHANGELOG.md](CHANGELOG.md).

## Agradecimientos

Los experimentos con GPU de piper-plus cuentan con el apoyo del AI Builder Grant (créditos de GPU) de [CloudRift](https://www.cloudrift.ai/).
