![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | Deutsch

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

> **📢 v2.0.0 Breaking Changes (2026-05):** Standard-Docker-Images auf CUDA 12.8 + Ubuntu 24.04 + Python 3.13 vereinheitlicht (Host-NVIDIA-Treiber **R570+** erforderlich; ältere Treiber können die neuen Images nicht starten) / Training auf torch 2.11+cu128 aktualisiert (mit torch 2.2 erstellte Checkpoints können nicht fortgesetzt werden) / TF32 + bf16-mixed sind die neuen Trainings-Standards. Details: [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

**Pakete:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 Der einzige Piper-Fork unter MIT-Lizenz** — Das ursprüngliche [rhasspy/piper](https://github.com/rhasspy/piper) wurde im Oktober 2025 archiviert und [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) ist auf GPL-3.0 umgestiegen. piper-plus ist der einzige MIT-kompatible Fork ohne espeak-ng-Abhängigkeit. Das eigene G2P unterstützt 8 Sprachen (JA/EN/ZH/KO/ES/FR/PT/SV) und eignet sich für den kommerziellen und eingebetteten Einsatz.

> **📢 v1.12.0 Breaking Changes (2026-05):** HiFi-GAN-Decoder entfernt (auf MB-iSTFT vereinheitlicht, `--mb-istft`-Flag eingestellt) / Flask → FastAPI HTTP-Server / HTS-voice-Abhängigkeit entfernt (nur Python-Runtime) / Unity UPM in separates Repository ausgelagert (`ayutaz/uPiper`) / alle .NET-Projekte auf `net10.0` LTS aktualisiert. Details: [docs/migration/v1.11-to-v1.12.md](docs/migration/v1.11-to-v1.12.md)

Ein schnelles und hochwertiges neuronales Text-to-Speech-System (TTS). Basierend auf der [VITS](https://github.com/jaywalnut310/vits/)-Architektur mit Multi-Speaker-Sprachsynthese in 8 Sprachen: Japanisch, Englisch, Chinesisch, Koreanisch, Spanisch, Französisch, Portugiesisch und Schwedisch. Ein Fork von [Piper](https://github.com/rhasspy/piper) mit umfassend erweiterter japanischer Sprachunterstützung, verbesserter Audioqualität und erweiterten Trainingsfunktionen.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (läuft im Browser, kein Server erforderlich)

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

- **8 Sprachen** — Japanisch, Englisch, Chinesisch, Spanisch, Französisch, Portugiesisch, Schwedisch und Koreanisch (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *Das trainierte Modell umfasst 6 Sprachen (JA/EN/ZH/ES/FR/PT)*
- **Japanisches TTS** — OpenJTalk-Integration, Prosodieinformationen (A1/A2/A3), Fragemarkierungen (#204), kontextabhängige "N"-Varianten (#207)
- **Englisches TTS** — GPL-freies G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), kein espeak-ng erforderlich
- **Multi-Speaker** — Unterstützung für 571 Sprecher (Basis-Trainingsmodell), SpeakerBalancedBatchSampler, ausgewogene Sprachgruppen-Abtastung
- **Benutzerdefinierte Wörterbücher** — Integriertes Aussprachwörterbuch mit über 200 Fachbegriffen
- **Phoneingabe** — Direkte Eingabe über `[[ Phoneme ]]`-Notation — [Anleitung](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS-Verbesserung von +0,15-0,25 (standardmäßig aktiviert, nur beim Training verwendet)
- **MB-iSTFT-VITS2 Decoder** — Decoder vereinheitlicht zu MB-iSTFT + PQMF, ~2,21x schnellere CPU-Inferenz. ONNX-kompatibel mit bestehenden Runtimes
- **FP16 Mixed Precision** — 2-3x schnelleres Training, ca. 50% weniger Speicherbedarf (standardmäßig aktiviert)
- **EMA** — Exponential Moving Average für stabiles Training (standardmäßig aktiviert)
- **Multi-GPU** — DDP-Unterstützung, automatische Lernraten-Skalierung
- **Prosody Features** — Einspeisung von Prosodieinformationen in den Duration Predictor (`--prosody-dim 16`)
- **Wandb-Integration** — Echtzeit-Metriküberwachung

### Schnittstellen

- **[WebUI (Gradio)](docs/features/webui.md)** — Für Inferenz und Training, Docker-kompatibel
- **C++ CLI** — Streaming, CUDA-Inferenz, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, benutzerdefinierte Wörterbücher
- **[C API Shared Library](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI-fähig (Flutter/Godot/Swift etc.), Streaming API
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Läuft vollständig im Browser, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, kein Server erforderlich
- **[Docker](docker/README.md)** — 5 Images für Inferenz, Training, WebUI und C++
- **PyPI** — `pip install piper-plus`, 8 Sprachen multilingual, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, Streaming, **HTTP API auf FastAPI-Basis**
- **C# CLI** — .NET 10, plattformübergreifend, 8 Sprachen, ONNX-Inferenz, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, Streaming, CUDA/CoreML/DirectML-Unterstützung, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, automatischer Wörterbuch-Download
- **[Go CLI](src/go/README.md)** — HTTP-API-Server, Session-Pooling, Docker-kompatibel, einzelne Binärdatei, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — in allen 6 Runtimes (Python/Rust/C#/Go/WASM/C++) verfügbar
- **SSML-Unterstützung** — `<speak>`, `<break>`, `<prosody rate="...">` in 4 Runtimes (Python/Rust/C#/Go) verfügbar
- **Qualitätsverbesserung für Kurztexte (Strategy A/B/C)** — Silence Padding, dynamische Scales und automatisches SSML `<break>` in allen 6 Runtimes

### Funktionsunterstützung pro Runtime

Äquivalente 8-sprachige multilinguale Synthese über 6 Runtimes (Python/Rust/C#/Go/JS-WASM/C++). Phoneme Timing, Streaming (inkl. satzweiser Aufteilung), Voice Cloning und benutzerdefinierte Wörterbücher werden von allen Runtimes unterstützt. SSML wird von 4 Runtimes (Python/Rust/C#/Go), die HTTP API von 2 Runtimes (Python/Go) unterstützt.

### Plattformen

| Plattform | Architektur | Hinweise |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | Volle Unterstützung |
| macOS | ARM64 (Apple Silicon) nur | M1/M2/M3+ |
| Windows | x64 | Volle Unterstützung |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | Shared Library, Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 10, Linux/macOS/Windows |
| Rust | Linux x64, macOS ARM64, Windows x64 | CUDA/CoreML/DirectML |
| Go | Linux x64, macOS ARM64, Windows x64 | HTTP API, Docker |

---

## Schnellstart

### Vorkompilierte Binaries (kein Build erforderlich)

Laden Sie vorkompilierte Binaries von [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) herunter und starten Sie sofort mit der Sprachsynthese.

**1. Binary herunterladen**

Laden Sie die passende Version für Ihr Betriebssystem herunter und entpacken Sie diese.

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

**2. Modell herunterladen & Sprache generieren**

```sh
# Tsukuyomi-chan Modell herunterladen
./bin/piper --download-model tsukuyomi

# Sprache generieren (nur der Modellname reicht — heruntergeladene Modelle werden automatisch aufgeloest)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Hinweis zur Windows cmd-Codepage:** Die Option `--text` verwendet intern `GetCommandLineW()` (UTF-16) und funktioniert daher unabhängig von der Codepage. Nur bei Pipe-Eingabe (`echo ... | piper`) müssen Sie vorher mit `chcp 65001` auf UTF-8 umschalten.
>
> **Ausgabeort von output.wav:** Die Datei wird im aktuellen Verzeichnis erstellt (dort, wo Sie `cd piper` ausgeführt haben).

> **Welches Binary soll ich wählen?** Die Releases enthalten außerdem `piper-plus-cli-*` (C# .NET) und `piper-plus-rs-cli-*` (Rust) CLIs. Der obige Schnellstart verwendet **C++ CLI (`piper-*`)**, das die breiteste Plattformunterstützung bietet und für die meisten Nutzer empfohlen wird. Details siehe [Auswahl eines CLI-Binarys](docs/getting-started/binary-selection.md).

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

Wichtige Optionen: `--speaker-id` (Sprecher-ID), `--device auto|cpu|gpu`, `--noise-scale` (Sprachvariation), `--noise-scale-w` (Phonemlängenvariation, Standard: 0.8), `--length-scale` (Sprechgeschwindigkeit)

> **Empfohlene Einstellungen für WavLM-Modelle:** Modelle, die mit dem WavLM Discriminator trainiert wurden (z.B. Tsukuyomi-chan), erreichen mit `--noise-scale 0.5` optimale Audioqualität (Standard ist 0.667).

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
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Hinweis:** Das webui-Image wird nicht automatisch von CI gebaut. Manuell bauen mit: `docker build -t piper-webui -f docker/webui/Dockerfile .`

Weitere Details unter [docker/README.md](docker/README.md).

---

## Installation

### Python

Python 3.13+ empfohlen (3.11+ unterstutzt). [uv](https://docs.astral.sh/uv/) wird als Paketmanager empfohlen.

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

Alternativ über das PyPI-Paket installierbar:

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
piper-plus = "0.4"
```

### Aus Quellcode bauen (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Voraussetzungen: C++17-kompatibler Compiler, CMake 3.15+

- **Linux**: Abhängigkeiten (ONNX Runtime, OpenJTalk usw.) werden automatisch von CMake heruntergeladen
- **Windows**: Siehe [Windows-Setup-Anleitung](docs/getting-started/windows-setup.md)
- **macOS**: Abhängigkeiten werden automatisch heruntergeladen

### Aus Quellcode bauen (C#)

```bash
# C# CLI bauen
dotnet build src/csharp/PiperPlus.sln -c Release
# Tests
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Voraussetzungen: .NET 10 SDK oder höher

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

> **Hinweis:** Die C# CLI ist über `dotnet tool install -g PiperPlus.Cli` und die Rust CLI über `cargo install piper-plus-cli` installierbar. Beide unterstützen 8 Sprachen, benutzerdefinierte Wörterbücher und Streaming.

### Aus Quellcode bauen (Rust)

```bash
# Rust CLI bauen
cargo build --release -p piper-plus-cli
# Tests
cargo test -p piper-plus
```

Voraussetzungen: Rust 1.88+, cargo

---

## Verwendung

### C++ CLI

#### Direkte Texteingabe (empfohlen)

Mit der Option `--text` können Sie Text direkt ohne Pipe eingeben:

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
| `--model PATH\|NAME` | Pfad zur Modelldatei oder Modellname (heruntergeladene Modelle werden automatisch aufgelöst) | - |
| `--text TEXT` | Direkte Texteingabe (kein Pipe erforderlich) | - |
| `--streaming` | Chunk-basierter Streaming-Modus | aus |
| `--use-cuda` | CUDA-GPU-Inferenz aktivieren | aus |
| `--gpu-device-id NUM` | GPU-Geräte-ID | 0 |
| `--length-scale VAL` | Sprechgeschwindigkeit (kleiner = schneller) | 1.0 |
| `--noise-scale VAL` | Steuerung der Sprachvariation | 0.667 |
| `--noise-w VAL` | Steuerung der Phonemlängen-Variation | 0.8 |
| `--sentence-silence SEC` | Pause zwischen Sätzen (Sekunden) | 0.2 |
| `--speaker NUM` | Sprechernummer für Multi-Speaker-Modelle | 0 |
| `--phoneme-silence PHONEME SEC` | Pausendauer für bestimmte Phoneme | - |
| `--raw-phonemes` | Eingabe als Phoneme interpretieren | aus |
| `--output-timing FILE` | Phonem-Timing-Informationen in Datei ausgeben (JSON/TSV) | - |
| `--custom-dict FILE` | Benutzerdefiniertes Wörterbuch (mehrere durch Komma getrennt) | - |
| `--json-input` | JSON-Eingabemodus | aus |
| `--list-models [LANG]` | Verfügbare Modelle auflisten | - |
| `--download-model NAME` | Modell herunterladen | - |
| `--model-dir DIR` | Zielverzeichnis für heruntergeladene Modelle | - |
| `--config/-c PATH` | Pfad zur Konfigurationsdatei | - |
| `--output_file/-f PATH` | Pfad zur WAV-Ausgabedatei | - |
| `--output_dir/-d DIR` | Ausgabeverzeichnis | - |
| `--output-raw` | Raw-PCM-Audio auf stdout ausgeben | aus |
| `--language/-l CODE` | Sprachcode | - |
| `--timing-format FORMAT` | Timing-Ausgabeformat (json/tsv) | - |
| `--test-mode` | Testmodus, ONNX-Inferenz überspringen | aus |
| `--debug` | Debug-Logging aktivieren | aus |
| `--quiet/-q` | Logging deaktivieren | aus |
| `--version` | Version anzeigen | - |

Alle Optionen mit `piper --help` anzeigen.

> **Empfohlene Einstellungen für WavLM-Modelle:** Für Modelle, die mit dem WavLM Discriminator trainiert wurden, wird `--noise-scale 0.5` empfohlen (Standard ist 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON-Eingabe

Mit dem Flag `--json-input` wird JSON-Eingabe unterstützt:

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
| `PIPER_MODEL_DIR` | Speicherverzeichnis für heruntergeladene Modelle | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA-GPU-Geräte-ID | `0` |

### Hilfsskripte (Windows)

Im Verzeichnis `scripts/` stehen Hilfsskripte für Windows-Nutzer bereit.

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

Bei Multi-GPU wird DDP (Distributed Data Parallel) automatisch konfiguriert. Die NCCL-Umgebungsvariablen müssen gesetzt werden. Weitere Details im Multi-GPU-Trainingshandbuch.

### ONNX-Konvertierung

Standardmäßig wird eine FP16-Konvertierung angewendet, die die Modellgröße um ca. 50% reduziert. Deaktivierbar mit `--no-fp16`. Für numerische Stabilität bleiben LayerNormalization, Sigmoid und Softmax in FP32.

```bash
# Standardmodell (FP16-Ausgabe)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# FP32-Ausgabe
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM-Modell (--stochastic standardmaessig aktiviert)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Checkpoint-Verwaltung

- `--resume_from_checkpoint` — Training von einem Checkpoint fortsetzen
- `--resume_from_single_speaker_checkpoint` — Konvertierung von Single-Speaker zu Multi-Speaker-Modell

### Sprachevaluation

`scripts/evaluation/` enthält Evaluierungstexte.

---

## Vortrainierte Modelle

Vortrainierte Sprachsynthesemodelle stehen auf Hugging Face zur Verfügung.

**Inferenzmodelle (sofort einsatzbereit):**

| Modell | Sprachen | Sprecher | Beschreibung | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan Stimme, 6 Sprachen, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japanisch 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 Japanische Stimme, 6 Sprachen, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Trainings-Basismodelle (für Feinabstimmung):**

| Modell | Sprachen | Sprecher | Beschreibung | Download |
|---|---|---|---|---|
| 6-Sprachen-Basismodell | JA/EN/ZH/ES/FR/PT | 571 | Multilingual vortrainiert (508.187 Äußerungen, VITS + Prosodie) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

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

### Merkmale des 6-Sprachen-Basismodells (für Training)

- Architektur: VITS + Prosody Features
- Trainingsdaten: 508.187 Äußerungen (571 Sprecher, 6 Sprachen)
- Abtastrate: 22.050 Hz
- Symbolanzahl: 173
- Prosody Features: A1/A2/A3-Prosodieinformationen (Japanisch)
- Ausgewogene Sprachgruppen-Abtastung: automatisch aktiviert

**Unterstützte Sprachen:**

| Sprache | Code | language_id | Sprecher | Äußerungen | Quelle |
|---|---|---|---|---|---|
| Japanisch | ja | 0 | 20 | 60.148 | MOE-Speech |
| Englisch | en | 1 | 310 | 74.912 | LibriTTS-R |
| Chinesisch | zh | 2 | 142 | 63.223 | AISHELL-3 |
| Spanisch | es | 3 | 63 | 168.374 | CML-TTS |
| Französisch | fr | 4 | 28 | 107.464 | CML-TTS |
| Portugiesisch | pt | 5 | 8 | 34.066 | CML-TTS |

> **Hinweis:** piper-plus verwendet eigene Architekturerweiterungen (multilinguale Embeddings, Prosodie A1/A2/A3, 173 Symbole) und ist daher nicht kompatibel mit Checkpoints/ONNX-Modellen des upstream Piper. Bitte verwenden Sie ausschließlich piper-plus-spezifische Modelle.

---

## Japanisches TTS

Hochwertige japanische Sprachsynthese durch OpenJTalk-Integration. Wörterbuch und Sprachdateien werden beim ersten Start automatisch heruntergeladen.

**Umgebungsvariablen (optional):**

| Variable | Beschreibung |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk-Wörterbuchpfad (bei fehlender Angabe automatischer Download) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` zum Deaktivieren des automatischen Downloads |
| `PIPER_OFFLINE_MODE` | `1` für den Offline-Modus |

Weitere Details im Japanischen Sprachsynthesehandbuch und in der [Phonem-Mapping-Referenz](docs/api-reference/phoneme-mapping.md).

---

## Plattformen

### macOS

**Nur Apple Silicon (M1/M2/M3+) wird unterstützt.** Für Intel-Macs verwenden Sie bitte Docker oder den Quellcode-Build.

Sicherheitswarnung beim ersten Start:

```bash
xattr -cr piper/
```

### Windows

x64 / arm64 werden unterstützt. Das OpenJTalk-Wörterbuch wird beim ersten Start automatisch heruntergeladen. Weitere Details in der [Windows-Setup-Anleitung](docs/getting-started/windows-setup.md).

```cmd
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

Japanisches TTS direkt im Browser. Kein Server erforderlich, offline-fähig.

- **[Online-Demo](https://ayutaz.github.io/piper-plus/)**
- **[Technische Details & Integrationsanleitung](src/wasm/openjtalk-web/README.npm.md)**

---

## Weitere Links

### piper-plus-g2p (Eigenständiges G2P-Paket)

Mehrsprachiges G2P (Grapheme-to-Phoneme) als eigenständige Pakete verfügbar:

- **Python**: `pip install piper-plus-g2p` — [Quellcode](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Quellcode](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Quellcode](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Quellcode](src/wasm/g2p/)

### Unity — uPiper

Plugin zur Verwendung von Piper in Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japanisch und Englisch, asynchrone API, Streaming

### Stimmmodelle (Voices)

piper-plus-Modelle: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6-Sprachen-Basis) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Hinweis:** piper-plus verwendet ein eigenes G2P- und Phonem-System, daher sind upstream-Piper-Modelle (rhasspy/piper-voices) NICHT kompatibel.

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
| Funktionen | [WebUI](docs/features/webui.md) · CLI-Erweiterungen · Streaming · Phoneme Timing · SSML |
| Einrichtung | Schnellstart (Japanisch) · [Windows](docs/getting-started/windows-setup.md) · [Fehlerbehebung](docs/getting-started/troubleshooting.md) |
| Docker | [Docker-Umgebung](docker/README.md) |
| WebAssembly | [Technische Details](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).
