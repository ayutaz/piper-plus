![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md) | [Русский](README_RU.md) | Svenska | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

Ett snabbt och högkvalitativt neuralt text-till-tal-system (TTS). Bygger på [VITS](https://github.com/jaywalnut310/vits/)-arkitekturen och stöder talsyntes med flera talare på 8 språk: japanska, engelska, kinesiska, koreanska, spanska, franska, portugisiska och svenska. Projektet är en fork av [Piper](https://github.com/rhasspy/piper) med utökad japansk support, förbättrad ljudkvalitet och avsevärt förbättrad träning.

**[Hugging Face-demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly-demo](https://ayutaz.github.io/piper-plus/)** (körs i webbläsaren, ingen server krävs)

---

## Innehåll

- [Huvudfunktioner](#huvudfunktioner)
- [Snabbstart](#snabbstart)
- [Förtränade modeller](#förtränade-modeller)
- [Installation](#installation)
- [Användning](#användning)
- [Träning](#träning)
- [Japansk TTS](#japansk-tts)
- [Plattformar](#plattformar)
- [Relaterade länkar](#relaterade-länkar)

---

## Huvudfunktioner

### Talsyntes

- **Stöd för 8 språk** — Japanska, engelska, kinesiska, koreanska, spanska, franska, portugisiska och svenska (ja=0, en=1, zh=2, ko=3, es=4, fr=5, pt=6, sv=7)
- **Japansk TTS** — OpenJTalk-integration, prosodiinformation (A1/A2/A3), frågeordsmarkörer (#204), kontextberoende "ん"-varianter (#207)
- **Engelsk TTS** — GPL-fri G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), ingen espeak-ng krävs
- **Flera talare** — Stöd för 571 talare (basmodell för träning), SpeakerBalancedBatchSampler, balanserad språkgrupps-sampling
- **Anpassad ordlista** — Inbyggd uttalsordlista med 200+ tekniska termer
- **Foneminmatning** — Direkt specifikation med `[[ fonemer ]]`-notation — [Guide](docs/features/phoneme-input.md)

### Träning

- **WavLM Discriminator** — MOS-förbättring +0,15–0,25 (aktiverad som standard, används enbart vid träning)
- **FP16 Mixed Precision** — 2–3x snabbare träning, ca 50 % minnesreduktion (aktiverad som standard)
- **EMA** — Exponential Moving Average för stabilare träning (aktiverad som standard)
- **Multi-GPU** — DDP-stöd, automatisk skalning av inlärningsfrekvens
- **Prosody Features** — Injicering av prosodiinformation i Duration Predictor (`--prosody-dim 16`)
- **Wandb-integration** — Övervakning av mätvärden i realtid

### Gränssnitt

- **[WebUI (Gradio)](docs/features/webui.md)** — Stöd för inferens och träning, Docker-kompatibelt
- **C++ CLI** — Streaming, CUDA-inferens, fonemtidning, anpassad ordlista
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Körs helt i webbläsaren, ingen server krävs
- **[Docker](docker/README.md)** — 5 images: inferens, träning, WebUI, C++
- **PyPI** — Enkel installation med `pip install piper-plus`
- **C# CLI** — .NET 8/9 plattformsoberoende, 8 språk, ONNX-inferens
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML-stöd, automatisk ordlistenedladdning
- **[Go CLI](src/go/README.md)** — HTTP API-server, sessionspoolning, Docker-kompatibelt, enskild binärfil

### Plattformar

| Plattform | Arkitektur | Anmärkning |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | Fullt stöd |
| macOS | ARM64 (Apple Silicon) enbart | M1/M2/M3+ |
| Windows | x64 | Fullt stöd |
| Webb | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9, Linux/macOS/Windows |
| Rust | Linux x64, macOS ARM64, Windows x64 | CUDA/CoreML/DirectML |
| Go | Linux x64, macOS ARM64, Windows x64 | HTTP API, Docker |

---

## Snabbstart

### Förbyggda binärfiler (ingen kompilering krävs)

Ladda ner förbyggda binärfiler från [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) och börja generera tal direkt.

**1. Ladda ner binärfilerna**

Ladda ner och packa upp för ditt operativsystem.

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

**2. Ladda ner en modell och generera tal**

```sh
# Ladda ner Tsukuyomi-chan-modellen
./bin/piper --download-model tsukuyomi

# Generera tal (modellnamnet räcker — nedladdade modeller hittas automatiskt)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Om kodsidor i Windows cmd:** Flaggan `--text` använder internt `GetCommandLineW()` (UTF-16) och fungerar därför oberoende av kodsida. Endast vid pipe-inmatning (`echo ... | piper`) behöver du först köra `chcp 65001` för att byta till UTF-8.
>
> **Utdatafil för output.wav:** Filen skapas i den aktuella katalogen (där du körde `cd piper`).

### Python-inferens

```bash
# Installera
uv pip install ".[inference]"

# Japansk inferens
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# Engelsk inferens
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

Vanliga flaggor: `--speaker-id` (talar-ID), `--device auto|cpu|gpu`, `--noise-scale` (röstvariation), `--noise-scale-w` (fonemets längdvariation, standard: 0.8), `--length-scale` (talhastighet)

> **Rekommenderad inställning för WavLM-modeller:** Modeller tränade med WavLM Discriminator (t.ex. Tsukuyomi-chan) ger bäst ljudkvalitet med `--noise-scale 0.5` (standard är 0.667).

#### Modellhantering i Python CLI

```bash
# Visa modelllista
python -m piper --list-models
python -m piper --list-models ja

# Ladda ner modell
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# Använd efter nedladdning
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

# Python-inferens (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# GPU-inferens (lägg till --gpus all)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

Förbyggda CI/CD-images:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Obs:** webui-imagen byggs inte automatiskt av CI. Bygg manuellt med: `docker build -t piper-webui -f docker/webui/Dockerfile .`

Se [docker/README.md](docker/README.md) för mer information.

---

## Installation

### Python

Kräver Python 3.11+. [uv](https://docs.astral.sh/uv/) rekommenderas för beroendehantering.

```bash
# CPU-inferens
uv pip install ".[inference]"

# GPU-inferens (kräver CUDA-miljö)
uv pip install ".[inference-gpu]"

# Träning
uv pip install ".[train]"

# Utveckling (inklusive tester och linters)
uv pip install ".[dev]"
```

Kan även installeras från PyPI:

```bash
pip install piper-plus
```

### Paketinstallation

**Python (PyPI):**
```bash
pip install piper-plus
```

**npm (webbläsar-WASM):**
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

**C#-bibliotek (NuGet):**
```bash
dotnet add package PiperPlus.Core
```

**Rust-bibliotek (crates.io):**
```toml
[dependencies]
piper-plus = "0.1.0"
```

### Bygga från källkod (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Förutsättningar: C++17-kompatibel kompilator, CMake 3.15+

- **Linux**: Placera [piper-phonemize](https://github.com/rhasspy/piper-phonemize) i `lib/Linux-$(uname -m)/piper_phonemize` innan kompilering
- **Windows**: Se [installationsguide för Windows](docs/getting-started/windows-setup.md)
- **macOS**: Beroenden laddas ner automatiskt

### Bygga från källkod (C#)

```bash
# Bygg C# CLI
dotnet build src/csharp/PiperPlus.sln -c Release
# Kör tester
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Förutsättningar: .NET 8 SDK eller senare

#### Användningsexempel för C# CLI

```bash
# Inferens med modellnamn (automatisk nedladdning, utelämna --output-file för output.wav)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# Engelska
piper-plus --model model.onnx --text "Hello world" --language en

# Flerspråkig (automatisk språkdetektering)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Inline-fonemnotation (ange fonemer direkt i texten)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Streaming (sekventiell PCM-utmatning per mening)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# Anpassad ordlista (JSON v1/v2 eller TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# Modellnedladdning
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Testläge (kontrollera fonem-ID utan ONNX-inferens)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Användningsexempel för Rust CLI

```bash
# Inferens med modellnamn (automatisk nedladdning)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# Engelska
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Modellnedladdning och hantering
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Streaming (sekventiell syntes per mening)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# Anpassad ordlista
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# GPU-inferens
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Testläge och tyst läge
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Rå PCM-utmatning (utan WAV-header)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Obs:** C# CLI installeras med `dotnet tool install -g PiperPlus.Cli` och Rust CLI med `cargo install piper-plus-cli`. Båda stöder 8 språk, anpassad ordlista och streaming.

### Bygga från källkod (Rust)

```bash
# Bygg Rust CLI
cargo build --release -p piper-plus-cli
# Kör tester
cargo test -p piper-plus
```

Förutsättningar: Rust 1.88+, cargo

---

## Användning

### C++ CLI

#### Direkt textinmatning (rekommenderas)

Med flaggan `--text` kan du ange text direkt utan att använda pipe:

```sh
# Generera tal från text
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# Japansk text (undviker kodningsproblem i Windows)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# Välj talare
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Pipe-inmatning

```sh
# Grundläggande
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# Streaming (låg latens)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# GPU-inferens
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# Fonemtidning (för läppsynk och undertextsynkronisering)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Anpassad ordlista
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Inline-foneminmatning
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# Rå foneminmatning
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# Streaming (rå ljudutmatning)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Vanliga flaggor:

| Flagga | Beskrivning | Standard |
|---|---|---|
| `--model PATH\|NAME` | Sökväg till modellfil eller modellnamn (nedladdade modeller hittas automatiskt) | - |
| `--text TEXT` | Direkt textinmatning (ingen pipe krävs) | - |
| `--streaming` | Chunkbaserat streamingläge | av |
| `--use-cuda` | Aktivera CUDA GPU-inferens | av |
| `--gpu-device-id NUM` | GPU-enhets-ID | 0 |
| `--length-scale VAL` | Justering av talhastighet (lägre = snabbare) | 1.0 |
| `--noise-scale VAL` | Kontroll av röstvariation | 0.667 |
| `--noise-w VAL` | Kontroll av fonemlängdsvariation | 0.8 |
| `--sentence-silence SEC` | Tystnad mellan meningar (sekunder) | 0.2 |
| `--speaker NUM` | Talarnummer för modeller med flera talare | 0 |
| `--phoneme-silence PHONEME SEC` | Ange tystnadstid för specifikt fonem | - |
| `--raw-phonemes` | Tolka inmatning som fonemer | av |
| `--output-timing FILE` | Spara fonemtidning till fil (JSON/TSV) | - |
| `--custom-dict FILE` | Anpassad ordlista (kommaseparerat för flera filer) | - |
| `--json-input` | JSON-inmatningsläge | av |
| `--list-models [LANG]` | Visa tillgängliga modeller | - |
| `--download-model NAME` | Ladda ner modell | - |
| `--model-dir DIR` | Katalog för nedladdade modeller | - |
| `--version` | Visa version | - |
| `--config`/`-c` | Sökväg till konfigurationsfil | - |
| `--output_file`/`-f` | Sökväg till WAV-utdatafil | - |
| `--output_dir`/`-d` | Utdatakatalog | - |
| `--output-raw` | Raw PCM-ljud till stdout | av |
| `--language`/`-l` | Språkkod | - |
| `--timing-format` | Timingutdataformat (json/tsv) | - |
| `--test-mode` | Testläge, hoppa över ONNX-inferens | av |
| `--debug` | Aktivera felsökningsloggning | av |
| `--quiet`/`-q` | Inaktivera loggning | av |

Kör `piper --help` för alla tillgängliga flaggor.

> **Rekommenderad inställning för WavLM-modeller:** Modeller tränade med WavLM Discriminator bör använda `--noise-scale 0.5` (standard är 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON-inmatning

Med flaggan `--json-input` kan du skicka JSON-inmatning:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Modellhantering

#### Visa modelllista

```bash
# Visa tillgängliga modeller
./bin/piper --list-models

# Filtrera efter språk
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### Ladda ner modeller

```bash
# Ladda ner med modellnamn (alias fungerar också)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# Ange nedladdningskatalog
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# Kör inferens med modellnamn efter nedladdning (ingen fullständig sökväg krävs)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### Miljövariabler (C++ CLI)

| Variabelnamn | Beskrivning | Exempel |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | Standardmodell om `--model` inte anges | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | Standardkonfigurationsfil om `--config` inte anges | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | Katalog för nedladdade modeller | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA GPU-enhets-ID | `0` |

### Hjälpskript (Windows)

I `scripts/`-katalogen finns hjälpskript för Windows-användare.

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Kommandotolken:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Träning

Se [träningsguiden](docs/guides/training/training-guide.md) för mer information.

### Grundläggande

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

### Flera talare och Multi-GPU

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

Vid multi-GPU konfigureras DDP (Distributed Data Parallel) automatiskt. NCCL-miljövariabler måste anges. Se multi-GPU-träningsguiden för mer information.

### ONNX-konvertering

FP16-konvertering tillämpas som standard, vilket minskar modellstorleken med ca 50 %. Kan avaktiveras med `--no-fp16`. För numerisk stabilitet behålls LayerNormalization, Sigmoid och Softmax i FP32.

```bash
# Standardmodell (FP16-utdata)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# FP32-utdata
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM-modell (--stochastic aktiverat som standard)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Checkpoint-hantering

- `--resume_from_checkpoint` — Återuppta träning från checkpoint
- `--resume_from_single_speaker_checkpoint` — Konvertera entalare-modell till flertalare-modell

### Talkvalitetsbedömning

`scripts/evaluation/` innehåller testtexter för utvärdering.

---

## Förtränade modeller

Färdiga talsyntesmodeller för inferens finns tillgängliga på Hugging Face.

**Inferensmodeller (redo att använda):**

| Modell | Språk | Antal talare | Beskrivning | Nedladdning |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chans röst, 6 språk, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japanska 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 japansk röst, 6 språk, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Basmodeller för träning (för finjustering):**

| Modell | Språk | Antal talare | Beskrivning | Nedladdning |
|---|---|---|---|---|
| 6-språks basmodell | JA/EN/ZH/ES/FR/PT | 571 | Flerspråkig förtränad (508 187 yttranden, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### Nedladdning av modeller

**Tsukuyomi-chan-modellen:**

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

### Egenskaper för 6-språks basmodellen (för träning)

- Arkitektur: VITS + Prosody Features
- Träningsdata: 508 187 yttranden (571 talare, 6 språk)
- Samplingsfrekvens: 22 050 Hz
- Antal symboler: 173
- Prosody Features: A1/A2/A3 prosodiinformation (japanska)
- Balanserad språkgrupps-sampling: aktiveras automatiskt

**Språk som stöds:**

| Språk | Kod | language_id | Antal talare | Yttranden | Källa |
|---|---|---|---|---|---|
| Japanska | ja | 0 | 20 | 60 148 | MOE-Speech |
| Engelska | en | 1 | 310 | 74 912 | LibriTTS-R |
| Kinesiska | zh | 2 | 142 | 63 223 | AISHELL-3 |
| Spanska | es | 3 | 63 | 168 374 | CML-TTS |
| Franska | fr | 4 | 28 | 107 464 | CML-TTS |
| Portugisiska | pt | 5 | 8 | 34 066 | CML-TTS |

> **Obs:** piper-plus använder egna arkitekturutökningar (flerspråkiga inbäddningar, Prosody A1/A2/A3, 173 symboler) och är därför inte kompatibelt med checkpoints/ONNX-modeller från upstream Piper. Använd enbart modeller specifikt framtagna för piper-plus.

---

## Japansk TTS

Högkvalitativ japansk talsyntes med integrerat OpenJTalk. Ordlista och röstfiler laddas ner automatiskt vid första körningen.

**Miljövariabler (valfria):**

| Variabelnamn | Beskrivning |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | Sökväg till OpenJTalk-ordlista (laddas ner automatiskt om den inte anges) |
| `PIPER_AUTO_DOWNLOAD_DICT` | Ange `0` för att avaktivera automatisk nedladdning |
| `PIPER_OFFLINE_MODE` | Ange `1` för offline-läge |

Se guiden för japansk talsyntes och [referens för fonemmappning](docs/api-reference/phoneme-mapping.md) för mer information.

---

## Plattformar

### macOS

**Enbart Apple Silicon (M1/M2/M3+).** Intel Mac-användare hänvisas till Docker eller kompilering från källkod.

Säkerhetsvarning vid första körningen:

```bash
xattr -cr piper/
```

### Windows

espeak-ng-data-katalogen behövs. Se [installationsguide för Windows](docs/getting-started/windows-setup.md) för mer information.

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

Japansk TTS som körs direkt i webbläsaren. Ingen server krävs, offline-stöd.

- **[Online-demo](https://ayutaz.github.io/piper-plus/)**
- **[Teknisk dokumentation och integrationsguide](src/wasm/openjtalk-web/README.npm.md)**

---

### piper-g2p (Fristående G2P-paket)

Flerspråkig G2P (Grapheme-to-Phoneme) tillgänglig som fristående paket:

- **Python**: `pip install piper-plus-g2p` — [Källkod](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Källkod](src/rust/piper-plus-g2p/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Källkod](src/wasm/g2p/)

---

## Relaterade länkar

### Unity — uPiper

Plugin för att använda Piper i Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japanska och engelska, asynkront API, streaming

### Röstmodeller (Voices)

Röstmodeller från upstream Piper (30+ språk) kan också användas: [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

Varje röst kräver en `.onnx`-modell och en `.onnx.json`-konfigurationsfil. [Röstexempel](https://rhasspy.github.io/piper-samples) | [Videohandledning](https://youtu.be/rjq5eZoWWSo)

### Relaterade artiklar

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Dokumentation

| Kategori | Länk |
|---|---|
| Japansk TTS | Guide för japansk talsyntes |
| Träning | [Träningsguide](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Fonemmappning](docs/api-reference/phoneme-mapping.md) · [Miljövariabler](docs/getting-started/environment-variables.md) |
| Funktioner | [WebUI](docs/features/webui.md) · CLI-förbättringar · Streaming |
| Installation | Snabbstart (japanska) · [Windows](docs/getting-started/windows-setup.md) · [Felsökning](docs/getting-started/troubleshooting.md) |
| Docker | [Docker-miljö](docker/README.md) |
| WebAssembly | [Teknisk dokumentation](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Se [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

Se [CHANGELOG.md](CHANGELOG.md).
