![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | Español | [Português](README_PT.md) | [Deutsch](README_DE.md) | [Русский](README_RU.md) | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

Sistema de texto a voz (TTS) neuronal, rapido y de alta calidad. Basado en la arquitectura [VITS](https://github.com/jaywalnut310/vits/), soporta sintesis de voz multilingue y multihablante en 8 idiomas: japones, ingles, chino, coreano, espanol, frances, portugues y sueco. Es un fork de [Piper](https://github.com/rhasspy/piper) con mejoras significativas en soporte para japones, calidad de audio y funcionalidades de entrenamiento.

**[Demo en Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (funciona en el navegador, sin servidor)

---

## Tabla de contenidos

- [Caracteristicas principales](#caracteristicas-principales)
- [Inicio rapido](#inicio-rapido)
- [Modelos preentrenados](#modelos-preentrenados)
- [Instalacion](#instalacion)
- [Uso](#uso)
- [Entrenamiento](#entrenamiento)
- [TTS en japones](#tts-en-japones)
- [Plataformas](#plataformas)
- [Enlaces relacionados](#enlaces-relacionados)

---

## Caracteristicas principales

### Sintesis de voz

- **8 idiomas** — Japones, ingles, chino, espanol, frances, portugues, sueco y coreano (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *El modelo entrenado cubre 6 idiomas (JA/EN/ZH/ES/FR/PT)*
- **TTS en japones** — Integracion con OpenJTalk, informacion prosodica (A1/A2/A3), marcadores de interrogacion (#204), variantes contextuales de "n" (#207)
- **TTS en ingles** — G2P libre de GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), sin necesidad de espeak-ng
- **Multihablante** — Soporte para 571 hablantes (modelo base de entrenamiento), SpeakerBalancedBatchSampler, muestreo equilibrado por grupo de idioma
- **Diccionario personalizado** — Diccionario de pronunciacion integrado con mas de 200 terminos tecnicos
- **Entrada de fonemas** — Especificacion directa mediante la notacion `[[ fonemas ]]` — [Guia](docs/features/phoneme-input.md)

### Entrenamiento

- **Discriminador WavLM** — Mejora de MOS +0.15-0.25 (activo por defecto, solo durante el entrenamiento)
- **Decodificador MB-iSTFT-VITS2** — Decodificador unificado a MB-iSTFT + PQMF, inferencia CPU ~2,21x más rápida. Compatible con ONNX y los runtimes existentes
- **Precision mixta FP16** — Velocidad de entrenamiento 2-3x mayor, ~50% menos memoria (activo por defecto)
- **EMA** — Estabilidad de entrenamiento mejorada con Exponential Moving Average (activo por defecto)
- **Multi-GPU** — Soporte DDP, escalado automatico de tasa de aprendizaje
- **Caracteristicas prosodicas** — Inyeccion de informacion prosodica al Duration Predictor (`--prosody-dim 16`)
- **Integracion con Wandb** — Monitorizacion de metricas en tiempo real

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inferencia y entrenamiento, compatible con Docker
- **CLI C++** — Streaming, inferencia CUDA, **salida de Phoneme Timing (JSON/TSV/SRT)**, diccionario personalizado
- **[C API Biblioteca compartida](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatible con FFI (Flutter/Godot/Swift etc.), API de streaming
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Funciona completamente en el navegador, **salida de Phoneme Timing (JSON/TSV/SRT)**, sin servidor
- **[Docker](docker/README.md)** — 5 imagenes disponibles para inferencia, entrenamiento, WebUI y C++
- **PyPI** — `pip install piper-plus`, 8 idiomas multilingue, **salida de Phoneme Timing (JSON/TSV/SRT)**, streaming, **HTTP API basada en FastAPI**
- **CLI C#** — .NET 10 multiplataforma, 8 idiomas multilingue, inferencia ONNX, **salida de Phoneme Timing (JSON/TSV/SRT)**
- **CLI Rust** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML, **salida de Phoneme Timing (JSON/TSV/SRT)**, descarga automatica de diccionarios
- **[CLI Go](src/go/README.md)** — Servidor HTTP API, pooling de sesiones, compatible con Docker, binario unico, **salida de Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — disponible en los 6 runtimes (Python/Rust/C#/Go/WASM/C++)
- **Soporte SSML** — `<speak>`, `<break>`, `<prosody rate="...">` disponibles en 4 runtimes (Python/Rust/C#/Go)
- **Mejora de calidad para textos cortos (Estrategia A/B/C)** — Silence Padding, Dynamic Scales y SSML `<break>` automatico en los 6 runtimes

### Soporte de funcionalidades por runtime

Sintesis multilingue equivalente en 8 idiomas a traves de 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++). Phoneme Timing, streaming (incluyendo division por oraciones), Voice Cloning y diccionarios personalizados estan disponibles en todos los runtimes. SSML es compatible con 4 runtimes (Python/Rust/C#/Go) y la API HTTP con 2 runtimes (Python/Go).

### Plataformas

| Plataforma | Arquitectura | Notas |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | Soporte completo |
| macOS | ARM64 (Apple Silicon) unicamente | M1/M2/M3+ |
| Windows | x64 | Soporte completo |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | Biblioteca compartida, Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 10, Linux/macOS/Windows |
| Rust | Linux x64, macOS ARM64, Windows x64 | CUDA/CoreML/DirectML |
| Go | Linux x64, macOS ARM64, Windows x64 | HTTP API, Docker |

---

## Inicio rapido

### Binarios precompilados (sin necesidad de compilar)

Descarga los binarios precompilados desde [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) y comienza a sintetizar voz de inmediato.

**1. Descargar el binario**

Descarga y descomprime segun tu sistema operativo.

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

**2. Descargar un modelo y generar audio**

```sh
# Descargar el modelo de Tsukuyomi-chan
./bin/piper --download-model tsukuyomi

# Generar audio (solo el nombre del modelo es suficiente — resolucion automatica de modelos descargados)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Sobre el code page en Windows cmd:** La opcion `--text` utiliza internamente `GetCommandLineW()` (UTF-16), por lo que funciona independientemente del code page. Solo si usa entrada por pipe (`echo ... | piper`) necesita cambiar a UTF-8 previamente con `chcp 65001`.
>
> **Ubicacion de output.wav:** Se genera en el directorio actual (donde ejecuto `cd piper`).

> **¿Que binario debo elegir?** Las releases tambien incluyen los CLIs `piper-plus-cli-*` (C# .NET) y `piper-plus-rs-cli-*` (Rust). El Inicio rapido anterior utiliza el **CLI de C++ (`piper-*`)**, que tiene el soporte de plataformas mas amplio y es el recomendado para la mayoria de los usuarios. Consulta [Como elegir un binario CLI](docs/getting-started/binary-selection.md) para mas detalles.

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

Opciones principales: `--speaker-id` (ID del hablante), `--device auto|cpu|gpu`, `--noise-scale` (variacion de voz), `--noise-scale-w` (variación de longitud de fonema, predeterminado: 0.8), `--length-scale` (velocidad de habla)

> **Configuracion recomendada para modelos WavLM:** Los modelos entrenados con WavLM Discriminator (como Tsukuyomi-chan) obtienen la mejor calidad de audio con `--noise-scale 0.5` (el valor predeterminado es 0.667).

#### Gestion de modelos con Python CLI

```bash
# Listar modelos
python -m piper --list-models
python -m piper --list-models ja

# Descargar modelos
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# Usar despues de descargar
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

Imagenes precompiladas de CI/CD:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Nota:** La imagen webui no se construye automáticamente por CI. Construya manualmente con: docker build -t piper-webui -f docker/webui/Dockerfile .

Para mas detalles, consulta [docker/README.md](docker/README.md).

---

## Instalacion

### Python

Se requiere Python 3.11+. Se recomienda [uv](https://docs.astral.sh/uv/) para la gestion de dependencias.

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

Tambien disponible en PyPI:

```bash
pip install piper-plus
```

### Instalacion desde paquetes

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
piper-plus = "0.4"
```

### Compilar desde fuente (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Requisitos previos: Compilador compatible con C++17, CMake 3.15+

- **Linux**: Las dependencias (ONNX Runtime, OpenJTalk, etc.) se descargan automaticamente por CMake
- **Windows**: Consulta la [guia de configuracion de Windows](docs/getting-started/windows-setup.md)
- **macOS**: Las dependencias se descargan automaticamente

### Compilar desde fuente (C#)

```bash
# Compilar CLI C#
dotnet build src/csharp/PiperPlus.sln -c Release
# Tests
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Requisitos previos: .NET 10 SDK o superior

#### Ejemplos de uso del CLI C#

```bash
# Inferencia por nombre de modelo (descarga automatica, sin --output-file genera output.wav)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# Ingles
piper-plus --model model.onnx --text "Hello world" --language en

# Multilingue (deteccion automatica de idioma)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Notacion de fonemas en linea (especificar fonemas directamente en el texto)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Streaming (salida PCM secuencial por oracion)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# Diccionario personalizado (JSON v1/v2 o TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# Descargar modelos
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Modo de prueba (verificar phoneme IDs sin inferencia ONNX)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Ejemplos de uso del CLI Rust

```bash
# Inferencia por nombre de modelo (descarga automatica)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# Ingles
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Descarga y gestion de modelos
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Streaming (sintesis secuencial por oracion)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# Diccionario personalizado
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# Inferencia GPU
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Modo de prueba y modo silencioso
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Salida PCM raw (sin cabecera WAV)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Nota:** El CLI C# se instala con `dotnet tool install -g PiperPlus.Cli` y el CLI Rust con `cargo install piper-plus-cli`. Ambos soportan 8 idiomas, diccionarios personalizados y streaming.

### Compilar desde fuente (Rust)

```bash
# Compilar CLI Rust
cargo build --release -p piper-plus-cli
# Tests
cargo test -p piper-plus
```

Requisitos previos: Rust 1.88+, cargo

---

## Uso

### CLI C++

#### Entrada de texto directa (recomendado)

Con la opcion `--text` puedes introducir texto directamente sin usar pipes:

```sh
# Generar audio desde texto
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# Texto en japones (evita problemas de codificacion en Windows)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# Especificar hablante
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Entrada por pipe

```sh
# Basico
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# Streaming (baja latencia)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# Inferencia GPU
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# Salida de timing de fonemas (para lip sync y sincronizacion de subtitulos)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Diccionario personalizado
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Entrada de fonemas en linea
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# Entrada de fonemas raw
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# Streaming (salida de audio raw)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Opciones principales:

| Opcion | Descripcion | Predeterminado |
|---|---|---|
| `--model PATH\|NAME` | Ruta al modelo o nombre del modelo (resolucion automatica de modelos descargados) | - |
| `--text TEXT` | Entrada de texto directa (sin pipe) | - |
| `--streaming` | Modo streaming basado en chunks | desactivado |
| `--use-cuda` | Activar inferencia GPU con CUDA | desactivado |
| `--gpu-device-id NUM` | ID del dispositivo GPU | 0 |
| `--length-scale VAL` | Ajuste de velocidad de habla (menor=mas rapido) | 1.0 |
| `--noise-scale VAL` | Control de variacion de voz | 0.667 |
| `--noise-w VAL` | Control de variacion de duracion de fonemas | 0.8 |
| `--sentence-silence SEC` | Silencio entre oraciones (segundos) | 0.2 |
| `--speaker NUM` | Numero de hablante en modelos multihablante | 0 |
| `--phoneme-silence PHONEME SEC` | Configuracion de silencio para fonemas especificos | - |
| `--raw-phonemes` | Interpretar la entrada como fonemas | desactivado |
| `--output-timing FILE` | Exportar timing de fonemas a archivo (JSON/TSV) | - |
| `--custom-dict FILE` | Diccionario personalizado (multiples archivos separados por coma) | - |
| `--json-input` | Modo de entrada JSON | desactivado |
| `--list-models [LANG]` | Mostrar lista de modelos disponibles | - |
| `--download-model NAME` | Descargar un modelo | - |
| `--model-dir DIR` | Directorio de destino para modelos descargados | - |
| `--version` | Mostrar version | - |
| `--config/-c PATH` | Ruta del archivo de configuración | - |
| `--output_file/-f PATH` | Ruta del archivo WAV de salida | - |
| `--output_dir/-d DIR` | Directorio de salida | - |
| `--output-raw` | Salida de audio PCM raw a stdout | desactivado |
| `--language/-l CODE` | Código de idioma | - |
| `--timing-format FMT` | Formato de salida de temporización (json/tsv) | - |
| `--test-mode` | Modo de prueba, omitir inferencia ONNX | desactivado |
| `--debug` | Activar registro de depuración | desactivado |
| `--quiet/-q` | Desactivar registro | desactivado |

Ejecuta `piper --help` para ver todas las opciones.

> **Configuracion recomendada para modelos WavLM:** Se recomienda `--noise-scale 0.5` para modelos entrenados con WavLM Discriminator (el predeterminado es 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### Entrada JSON

Con el flag `--json-input` se acepta entrada en formato JSON:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Gestion de modelos

#### Listar modelos

```bash
# Mostrar lista de modelos disponibles
./bin/piper --list-models

# Filtrar por idioma
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### Descargar modelos

```bash
# Descargar especificando el nombre del modelo (tambien se pueden usar alias)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# Especificar directorio de destino
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# Despues de descargar, inferencia por nombre de modelo (sin ruta completa)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### Variables de entorno (CLI C++)

| Variable | Descripcion | Ejemplo |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | Ruta de modelo predeterminada cuando no se especifica `--model` | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | Ruta de configuracion predeterminada cuando no se especifica `--config` | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | Directorio de almacenamiento de modelos descargados | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | ID del dispositivo CUDA GPU | `0` |

### Scripts auxiliares (Windows)

Se proporcionan scripts auxiliares en el directorio `scripts/` para usuarios de Windows.

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Simbolo del sistema:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Entrenamiento

Para mas detalles, consulta la [guia de entrenamiento](docs/guides/training/training-guide.md).

### Basico

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

### Multihablante y multi-GPU

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

Con multi-GPU se configura automaticamente DDP (Distributed Data Parallel). Es necesario configurar las variables de entorno NCCL. Consulta la guia de entrenamiento multi-GPU para mas detalles.

### Conversion a ONNX

Por defecto se aplica conversion FP16, reduciendo el tamano del modelo en aproximadamente un 50%. Se puede desactivar con `--no-fp16`. Por estabilidad numerica, LayerNormalization, Sigmoid y Softmax se mantienen en FP32.

```bash
# Modelo estandar (salida FP16)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Salida FP32
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# Modelo WavLM (--stochastic activado por defecto)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Gestion de checkpoints

- `--resume_from_checkpoint` — Reanudar entrenamiento desde un checkpoint
- `--resume_from_single_speaker_checkpoint` — Conversion de modelo de un solo hablante a multihablante

### Evaluacion de audio

`scripts/evaluation/` contiene textos de prueba para evaluación.

---

## Modelos preentrenados

Publicamos modelos de sintesis de voz para inferencia en Hugging Face.

**Modelos de inferencia (listos para usar):**

| Modelo | Idiomas | Hablantes | Descripcion | Descarga |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Voz de Tsukuyomi-chan, 6 idiomas, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 japones 6lang | JA/EN/ZH/ES/FR/PT | 1 | Voz CSS10 en japones, 6 idiomas, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Modelos base para entrenamiento (para fine-tuning):**

| Modelo | Idiomas | Hablantes | Descripcion | Descarga |
|---|---|---|---|---|
| Modelo base 6 idiomas | JA/EN/ZH/ES/FR/PT | 571 | Preentrenado multilingue (508,187 enunciados, VITS + Prosodia) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### Descarga de modelos

**Modelo Tsukuyomi-chan:**

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

### Caracteristicas del modelo base de 6 idiomas (para entrenamiento)

- Arquitectura: VITS + Caracteristicas prosodicas
- Datos de entrenamiento: 508,187 enunciados (571 hablantes, 6 idiomas)
- Frecuencia de muestreo: 22,050 Hz
- Numero de simbolos: 173
- Caracteristicas prosodicas: Informacion prosodica A1/A2/A3 (japones)
- Muestreo equilibrado por grupo de idioma: activado automaticamente

**Idiomas soportados:**

| Idioma | Codigo | language_id | Hablantes | Enunciados | Fuente |
|---|---|---|---|---|---|
| Japones | ja | 0 | 20 | 60,148 | MOE-Speech |
| Ingles | en | 1 | 310 | 74,912 | LibriTTS-R |
| Chino | zh | 2 | 142 | 63,223 | AISHELL-3 |
| Espanol | es | 3 | 63 | 168,374 | CML-TTS |
| Frances | fr | 4 | 28 | 107,464 | CML-TTS |
| Portugues | pt | 5 | 8 | 34,066 | CML-TTS |

> **Nota:** piper-plus tiene extensiones de arquitectura propias (embeddings multilingues, Prosodia A1/A2/A3, 173 simbolos), por lo que no es compatible con checkpoints ni modelos ONNX del Piper original. Utiliza modelos especificos de piper-plus.

---

## TTS en japones

Sintesis de voz en japones de alta calidad mediante integracion con OpenJTalk. El diccionario y los archivos de voz se descargan automaticamente en la primera ejecucion.

**Variables de entorno (opcionales):**

| Variable | Descripcion |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | Ruta del diccionario OpenJTalk (descarga automatica si no se especifica) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` para desactivar la descarga automatica |
| `PIPER_OFFLINE_MODE` | `1` para modo offline |

Para mas detalles, consulta la guia de sintesis de voz en japones y la [referencia de mapeo de fonemas](docs/api-reference/phoneme-mapping.md).

---

## Plataformas

### macOS

**Solo compatible con Apple Silicon (M1/M2/M3+).** Para Intel Mac, utiliza Docker o compilacion desde fuente.

Advertencia de seguridad en la primera ejecucion:

```bash
xattr -cr piper/
```

### Windows

Se admiten x64 y arm64. El diccionario de OpenJTalk se descarga automáticamente en el primer arranque. Consulta la [guia de configuracion de Windows](docs/getting-started/windows-setup.md) para mas detalles.

```cmd
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

TTS en japones que funciona directamente en el navegador. Sin servidor, compatible con modo offline.

- **[Demo en linea](https://ayutaz.github.io/piper-plus/)**
- **[Detalles tecnicos y guia de integracion](src/wasm/openjtalk-web/README.npm.md)**

---

## Enlaces relacionados

### piper-plus-g2p (Paquete G2P independiente)

G2P multilingüe (Grapheme-to-Phoneme) disponible como paquetes independientes:

- **Python**: `pip install piper-plus-g2p` — [Código fuente](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Código fuente](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Código fuente](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Código fuente](src/wasm/g2p/)

### Unity — uPiper

Plugin para usar Piper en Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Compatible con Windows / macOS (Apple Silicon) / Linux / Android
- Japones e ingles, API asincrona, streaming

### Modelos de voz (Voices)

Modelos de piper-plus: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (base 6 idiomas) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Nota:** piper-plus utiliza su propio sistema G2P y de fonemas, por lo que los modelos del Piper original (rhasspy/piper-voices) NO son compatibles.

### Articulos relacionados

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentacion

| Categoria | Enlace |
|---|---|
| TTS en japones | Guia de sintesis de voz en japones |
| Entrenamiento | [Guia de entrenamiento](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Mapeo de fonemas](docs/api-reference/phoneme-mapping.md) · [Variables de entorno](docs/getting-started/environment-variables.md) |
| Funcionalidades | [WebUI](docs/features/webui.md) · Mejoras de CLI · Streaming · Phoneme Timing · SSML |
| Configuracion | Inicio rapido (japones) · [Windows](docs/getting-started/windows-setup.md) · [Solucion de problemas](docs/getting-started/troubleshooting.md) |
| Docker | [Entorno Docker](docker/README.md) |
| WebAssembly | [Detalles tecnicos](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

Consulta [CHANGELOG.md](CHANGELOG.md).
