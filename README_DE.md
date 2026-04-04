![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | Deutsch | [Русский](README_RU.md) | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

Ein schnelles und hochwertiges neuronales Text-to-Speech-System (TTS). Basierend auf der [VITS](https://github.com/jaywalnut310/vits/)-Architektur mit Multi-Speaker-Sprachsynthese in 8 Sprachen: Japanisch, Englisch, Chinesisch, Koreanisch, Spanisch, Franzoesisch, Portugiesisch und Schwedisch. Ein Fork von [Piper](https://github.com/rhasspy/piper) mit umfassend erweiterter japanischer Sprachunterstuetzung, verbesserter Audioqualitaet und erweiterten Trainingsfunktionen.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (laeuft im Browser, kein Server erforderlich)

---

## Inhaltsverzeichnis

- [Hauptfunktionen](#hauptfunktionen)
- [Schnellstart](#schnellstart)
- [Vortrainierte Modelle](#vortrainierte-modelle)
- [Installation](#installation)
- [Verwendung](#verwendung)
- [Training](#training)
- [Japanisches TTS](#japanisches-tts)
- [Plattformen](#plattformen)
- [Weitere Links](#weitere-links)

---

## Hauptfunktionen

### Sprachsynthese

- **8 Sprachen** — Japanisch, Englisch, Chinesisch, Koreanisch, Spanisch, Franzoesisch, Portugiesisch und Schwedisch (ja=0, en=1, zh=2, ko=3, es=4, fr=5, pt=6, sv=7)
- **Japanisches TTS** — OpenJTalk-Integration, Prosodieinformationen (A1/A2/A3), Fragemarkierungen (#204), kontextabhaengige "N"-Varianten (#207)
- **Englisches TTS** — GPL-freies G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), kein espeak-ng erforderlich
- **Multi-Speaker** — Unterstuetzung fuer 571 Sprecher (Basis-Trainingsmodell), SpeakerBalancedBatchSampler, ausgewogene Sprachgruppen-Abtastung
- **Benutzerdefinierte Woerterbuecher** — Integriertes Aussprachwoerterbuch mit ueber 200 Fachbegriffen
- **Phoneingabe** — Direkte Eingabe ueber `[[ Phoneme ]]`-Notation — [Anleitung](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS-Verbesserung von +0,15-0,25 (standardmaessig aktiviert, nur beim Training verwendet)
- **FP16 Mixed Precision** — 2-3x schnelleres Training, ca. 50% weniger Speicherbedarf (standardmaessig aktiviert)
- **EMA** — Exponential Moving Average fuer stabiles Training (standardmaessig aktiviert)
- **Multi-GPU** — DDP-Unterstuetzung, automatische Lernraten-Skalierung
- **Prosody Features** — Einspeisung von Prosodieinformationen in den Duration Predictor (`--prosody-dim 16`)
- **Wandb-Integration** — Echtzeit-Metrikueberwachung

### Schnittstellen

- **[WebUI (Gradio)](docs/features/webui.md)** — Fuer Inferenz und Training, Docker-kompatibel
- **C++ CLI** — Streaming, CUDA-Inferenz, Phonem-Timing-Ausgabe, benutzerdefinierte Woerterbuecher
- **[WebAssembly](src/wasm/openjtalk-web/README.md)** — Laeuft vollstaendig im Browser, kein Server erforderlich
- **[Docker](docker/README.md)** — 5 Images fuer Inferenz, Training, WebUI und C++
- **PyPI** — Einfache Installation mit `pip install piper-plus`
- **C# CLI** — .NET 8/9, plattformuebergreifend, 8 Sprachen, ONNX-Inferenz
- **Rust CLI** — piper-plus/piper-plus-cli, Streaming, CUDA/CoreML/DirectML-Unterstuetzung, automatischer Woerterbuch-Download
- **[Go CLI](src/go/README.md)** — HTTP-API-Server, Session-Pooling, Docker-kompatibel, einzelne Binaerdatei

### Plattformen

| Plattform | Architektur | Hinweise |
|---|---|---|
| Linux | x86_64 / ARM64 | Volle Unterstuetzung |
| macOS | ARM64 (Apple Silicon) nur | M1/M2/M3+ |
| Windows | x64 | Volle Unterstuetzung |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9, Linux/macOS/Windows |
| Rust | x64 / ARM64 | Linux/macOS/Windows, CUDA/CoreML/DirectML |
| Go | x64 / ARM64 | Linux/macOS/Windows, HTTP API, Docker |

---

## Schnellstart

### Vorkompilierte Binaries (kein Build erforderlich)

Laden Sie vorkompilierte Binaries von [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) herunter und starten Sie sofort mit der Sprachsynthese.

**1. Binary herunterladen**

Laden Sie die passende Version fuer Ihr Betriebssystem herunter und entpacken Sie diese.

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

**2. Modell herunterladen & Sprache generieren**

```sh
# Tsukuyomi-chan Modell herunterladen
./bin/piper --download-model tsukuyomi

# Sprache generieren (nur der Modellname reicht — heruntergeladene Modelle werden automatisch aufgeloest)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Hinweis zur Windows cmd-Codepage:** Die Option `--text` verwendet intern `GetCommandLineW()` (UTF-16) und funktioniert daher unabhaengig von der Codepage. Nur bei Pipe-Eingabe (`echo ... | piper`) muessen Sie vorher mit `chcp 65001` auf UTF-8 umschalten.
>
> **Ausgabeort von output.wav:** Die Datei wird im aktuellen Verzeichnis erstellt (dort, wo Sie `cd piper` ausgefuehrt haben).

### Python-Inferenz

```bash
# Installation
uv pip install ".[inference]"

# Japanische Inferenz
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# Englische Inferenz
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

Wichtige Optionen: `--speaker-id` (Sprecher-ID), `--device auto|cpu|gpu`, `--noise-scale` (Sprachvariation), `--length-scale` (Sprechgeschwindigkeit)

> **Empfohlene Einstellungen fuer WavLM-Modelle:** Modelle, die mit dem WavLM Discriminator trainiert wurden (z.B. Tsukuyomi-chan), erreichen mit `--noise-scale 0.5` optimale Audioqualitaet (Standard ist 0.667).

#### Python CLI Modellverwaltung

```bash
# Modellliste anzeigen
python -m piper --list-models
python -m piper --list-models ja

# Modell herunterladen
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# Nach dem Download verwenden
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

# Python-Inferenz (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# GPU-Inferenz (--gpus all hinzufuegen)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

Vorkompilierte CI/CD-Images:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main
docker pull ghcr.io/ayutaz/piper-plus/python-train:main
docker pull ghcr.io/ayutaz/piper-plus/webui:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

Weitere Details unter [docker/README.md](docker/README.md).

---

## Installation

### Python

Erfordert Python 3.11+. [uv](https://docs.astral.sh/uv/) wird als Paketmanager empfohlen.

```bash
# CPU-Inferenz
uv pip install ".[inference]"

# GPU-Inferenz (CUDA-Umgebung erforderlich)
uv pip install ".[inference-gpu]"

# Training
uv pip install ".[train]"

# Entwicklung (inkl. Tests & Linter)
uv pip install ".[dev]"
```

Alternativ ueber das PyPI-Paket installierbar:

```bash
pip install piper-plus
```

### Paketinstallation

**Python (PyPI):**
```bash
pip install piper-plus
```

**npm (Browser WASM):**
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

**C# Bibliothek (NuGet):**
```bash
dotnet add package PiperPlus.Core
```

**Rust Bibliothek (crates.io):**
```toml
[dependencies]
piper-plus = "0.1.0"
```

### Aus Quellcode bauen (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Voraussetzungen: C++17-kompatibler Compiler, CMake 3.13+

- **Linux**: Vor dem Build [piper-phonemize](https://github.com/rhasspy/piper-phonemize) unter `lib/Linux-$(uname -m)/piper_phonemize` ablegen
- **Windows**: Siehe [Windows-Setup-Anleitung](docs/getting-started/windows-setup.md)
- **macOS**: Abhaengigkeiten werden automatisch heruntergeladen

### Aus Quellcode bauen (C#)

```bash
# C# CLI bauen
dotnet build src/csharp/PiperPlus.sln -c Release
# Tests
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Voraussetzungen: .NET 8 SDK oder hoeher

#### C# CLI Verwendungsbeispiele

```bash
# Inferenz per Modellname (automatischer Download, --output-file entfaellt -> output.wav)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# Englisch
piper-plus --model model.onnx --text "Hello world" --language en

# Multilingual (automatische Spracherkennung)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Inline-Phonem-Notation (Phoneme direkt im Text angeben)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Streaming (satzweise PCM-Ausgabe)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# Benutzerdefiniertes Woerterbuch (JSON v1/v2 oder TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# Modell herunterladen
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Testmodus (Phonem-IDs ohne ONNX-Inferenz pruefen)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Rust CLI Verwendungsbeispiele

```bash
# Inferenz per Modellname (automatischer Download)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# Englisch
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Modell-Download und -Verwaltung
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Streaming (satzweise Synthese)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# Benutzerdefiniertes Woerterbuch
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# GPU-Inferenz
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Test- und Stummschaltungsmodus
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Raw-PCM-Ausgabe (ohne WAV-Header)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Hinweis:** Die C# CLI ist ueber `dotnet tool install -g PiperPlus.Cli` und die Rust CLI ueber `cargo install piper-plus-cli` installierbar. Beide unterstuetzen 8 Sprachen, benutzerdefinierte Woerterbuecher und Streaming.

### Aus Quellcode bauen (Rust)

```bash
# Rust CLI bauen
cargo build --release -p piper-plus-cli
# Tests
cargo test -p piper-plus
```

Voraussetzungen: Rust 1.70+, cargo

---

## Verwendung

### C++ CLI

#### Direkte Texteingabe (empfohlen)

Mit der Option `--text` koennen Sie Text direkt ohne Pipe eingeben:

```sh
# Sprache aus Text generieren
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# Japanischer Text (umgeht Encoding-Probleme unter Windows)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# Sprecher angeben
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Pipe-Eingabe

```sh
# Grundlegend
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# Streaming (geringe Latenz)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# GPU-Inferenz
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# Phonem-Timing-Ausgabe (fuer Lippensynchronisation und Untertitel)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Benutzerdefiniertes Woerterbuch
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Inline-Phoneingabe
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# Direkte Phoneingabe
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# Streaming (Raw-Audio-Ausgabe)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Wichtige Optionen:

| Option | Beschreibung | Standard |
|---|---|---|
| `--model PATH\|NAME` | Pfad zur Modelldatei oder Modellname (heruntergeladene Modelle werden automatisch aufgeloest) | - |
| `--text TEXT` | Direkte Texteingabe (kein Pipe erforderlich) | - |
| `--streaming` | Chunk-basierter Streaming-Modus | aus |
| `--use-cuda` | CUDA-GPU-Inferenz aktivieren | aus |
| `--gpu-device-id NUM` | GPU-Geraete-ID | 0 |
| `--length-scale VAL` | Sprechgeschwindigkeit (kleiner = schneller) | 1.0 |
| `--noise-scale VAL` | Steuerung der Sprachvariation | 0.667 |
| `--noise-w VAL` | Steuerung der Phonemlaengen-Variation | 0.8 |
| `--sentence-silence SEC` | Pause zwischen Saetzen (Sekunden) | 0.2 |
| `--speaker NUM` | Sprechernummer fuer Multi-Speaker-Modelle | 0 |
| `--phoneme-silence PHONEME SEC` | Pausendauer fuer bestimmte Phoneme | - |
| `--raw-phonemes` | Eingabe als Phoneme interpretieren | aus |
| `--output-timing FILE` | Phonem-Timing-Informationen in Datei ausgeben (JSON/TSV) | - |
| `--custom-dict FILE` | Benutzerdefiniertes Woerterbuch (mehrere durch Komma getrennt) | - |
| `--json-input` | JSON-Eingabemodus | aus |
| `--list-models [LANG]` | Verfuegbare Modelle auflisten | - |
| `--download-model NAME` | Modell herunterladen | - |
| `--model-dir DIR` | Zielverzeichnis fuer heruntergeladene Modelle | - |
| `--version` | Version anzeigen | - |

Alle Optionen mit `piper --help` anzeigen.

> **Empfohlene Einstellungen fuer WavLM-Modelle:** Fuer Modelle, die mit dem WavLM Discriminator trainiert wurden, wird `--noise-scale 0.5` empfohlen (Standard ist 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON-Eingabe

Mit dem Flag `--json-input` wird JSON-Eingabe unterstuetzt:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Modellverwaltung

#### Modellliste anzeigen

```bash
# Verfuegbare Modelle auflisten
./bin/piper --list-models

# Nach Sprache filtern
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### Modelle herunterladen

```bash
# Modell per Name herunterladen (Aliase werden unterstuetzt)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# Zielverzeichnis angeben
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# Nach dem Download per Modellname inferieren (kein vollstaendiger Pfad noetig)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### Umgebungsvariablen (C++ CLI)

| Variable | Beschreibung | Beispiel |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | Standard-Modellpfad, wenn `--model` nicht angegeben | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | Standard-Konfigurationsdateipfad, wenn `--config` nicht angegeben | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | Speicherverzeichnis fuer heruntergeladene Modelle | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA-GPU-Geraete-ID | `0` |

### Hilfsskripte (Windows)

Im Verzeichnis `scripts/` stehen Hilfsskripte fuer Windows-Nutzer bereit.

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Eingabeaufforderung:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Training

Weitere Details im [Trainingshandbuch](docs/guides/training/training-guide.md).

### Grundlagen

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

### Multi-Speaker und Multi-GPU

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

Bei Multi-GPU wird DDP (Distributed Data Parallel) automatisch konfiguriert. Die NCCL-Umgebungsvariablen muessen gesetzt werden. Weitere Details im Multi-GPU-Trainingshandbuch.

### ONNX-Konvertierung

Standardmaessig wird eine FP16-Konvertierung angewendet, die die Modellgroesse um ca. 50% reduziert. Deaktivierbar mit `--no-fp16`. Fuer numerische Stabilitaet bleiben LayerNormalization, Sigmoid und Softmax in FP32.

```bash
# Standardmodell (FP16-Ausgabe)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# FP32-Ausgabe
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM-Modell (--stochastic erforderlich)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Checkpoint-Verwaltung

- `--resume_from_checkpoint` — Training von einem Checkpoint fortsetzen
- `--resume_from_single_speaker_checkpoint` — Konvertierung von Single-Speaker zu Multi-Speaker-Modell

### Sprachevaluation

Unter `scripts/evaluation/` finden Sie Evaluierungstools fuer MCD, PESQ und UTMOS.

---

## Vortrainierte Modelle

Vortrainierte Sprachsynthesemodelle stehen auf Hugging Face zur Verfuegung.

**Inferenzmodelle (sofort einsatzbereit):**

| Modell | Sprachen | Sprecher | Beschreibung | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan Stimme, 6 Sprachen, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japanisch 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 Japanische Stimme, 6 Sprachen, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Trainings-Basismodelle (fuer Feinabstimmung):**

| Modell | Sprachen | Sprecher | Beschreibung | Download |
|---|---|---|---|---|
| 6-Sprachen-Basismodell | JA/EN/ZH/ES/FR/PT | 571 | Multilingual vortrainiert (508.187 Aeusserungen, VITS + Prosodie) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### Modelle herunterladen

**Tsukuyomi-chan Modell:**

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

### Merkmale des 6-Sprachen-Basismodells (fuer Training)

- Architektur: VITS + Prosody Features
- Trainingsdaten: 508.187 Aeusserungen (571 Sprecher, 6 Sprachen)
- Abtastrate: 22.050 Hz
- Symbolanzahl: 173
- Prosody Features: A1/A2/A3-Prosodieinformationen (Japanisch)
- Ausgewogene Sprachgruppen-Abtastung: automatisch aktiviert

**Unterstuetzte Sprachen:**

| Sprache | Code | language_id | Sprecher | Aeusserungen | Quelle |
|---|---|---|---|---|---|
| Japanisch | ja | 0 | 20 | 60.148 | MOE-Speech |
| Englisch | en | 1 | 310 | 74.912 | LibriTTS-R |
| Chinesisch | zh | 2 | 142 | 63.223 | AISHELL-3 |
| Spanisch | es | 3 | 63 | 168.374 | CML-TTS |
| Franzoesisch | fr | 4 | 28 | 107.464 | CML-TTS |
| Portugiesisch | pt | 5 | 8 | 34.066 | CML-TTS |

> **Hinweis:** piper-plus verwendet eigene Architekturerweiterungen (multilinguale Embeddings, Prosodie A1/A2/A3, 173 Symbole) und ist daher nicht kompatibel mit Checkpoints/ONNX-Modellen des upstream Piper. Bitte verwenden Sie ausschliesslich piper-plus-spezifische Modelle.

---

## Japanisches TTS

Hochwertige japanische Sprachsynthese durch OpenJTalk-Integration. Woerterbuch und Sprachdateien werden beim ersten Start automatisch heruntergeladen.

**Umgebungsvariablen (optional):**

| Variable | Beschreibung |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk-Woerterbuchpfad (bei fehlender Angabe automatischer Download) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` zum Deaktivieren des automatischen Downloads |
| `PIPER_OFFLINE_MODE` | `1` fuer den Offline-Modus |

Weitere Details im Japanischen Sprachsynthesehandbuch und in der [Phonem-Mapping-Referenz](docs/api-reference/phoneme-mapping.md).

---

## Plattformen

### macOS

**Nur Apple Silicon (M1/M2/M3+) wird unterstuetzt.** Fuer Intel-Macs verwenden Sie bitte Docker oder den Quellcode-Build.

Sicherheitswarnung beim ersten Start:

```bash
xattr -cr piper/
```

### Windows

Das espeak-ng-data-Verzeichnis wird benoetigt. Weitere Details in der [Windows-Setup-Anleitung](docs/getting-started/windows-setup.md).

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

Japanisches TTS direkt im Browser. Kein Server erforderlich, offline-faehig.

- **[Online-Demo](https://ayutaz.github.io/piper-plus/)**
- **[Technische Details & Integrationsanleitung](src/wasm/openjtalk-web/README.md)**

---

## Weitere Links

### Unity — uPiper

Plugin zur Verwendung von Piper in Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japanisch und Englisch, asynchrone API, Streaming

### Stimmmodelle (Voices)

Die Stimmmodelle des upstream Piper (30+ Sprachen) sind ebenfalls verfuegbar: [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

Jede Stimme benoetigt ein `.onnx`-Modell und eine `.onnx.json`-Konfigurationsdatei. [Stimmbeispiele](https://rhasspy.github.io/piper-samples) | [Video-Tutorial](https://youtu.be/rjq5eZoWWSo)

### Verwandte Artikel

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Dokumentation

| Kategorie | Links |
|---|---|
| Japanisches TTS | Japanisches Sprachsynthesehandbuch |
| Training | [Trainingshandbuch](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Phonem-Mapping](docs/api-reference/phoneme-mapping.md) · [Umgebungsvariablen](docs/getting-started/environment-variables.md) |
| Funktionen | [WebUI](docs/features/webui.md) · CLI-Erweiterungen · Streaming |
| Einrichtung | Schnellstart (Japanisch) · [Windows](docs/getting-started/windows-setup.md) · [Fehlerbehebung](docs/getting-started/troubleshooting.md) |
| Docker | [Docker-Umgebung](docker/README.md) |
| WebAssembly | [Technische Details](src/wasm/openjtalk-web/README.md) |

## Contributing

Siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).
