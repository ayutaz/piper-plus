![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | Deutsch

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Pakete:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 Der einzige Piper-Fork unter MIT-Lizenz** — Das ursprüngliche [rhasspy/piper](https://github.com/rhasspy/piper) wurde im Oktober 2025 archiviert und [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) ist auf GPL-3.0 umgestiegen. piper-plus ist der einzige MIT-kompatible Fork ohne espeak-ng-Abhängigkeit. Das eigene G2P unterstützt 8 Sprachen (JA/EN/ZH/KO/ES/FR/PT/SV) und eignet sich für den kommerziellen und eingebetteten Einsatz.

> **📢 v2.0.0 Breaking Changes (2026-05, in Vorbereitung auf `dev` — der aktuellste Release-Tag ist v1.13.0):** Standard-Docker-Images auf CUDA 12.8 + Ubuntu 24.04 + Python 3.13 vereinheitlicht (Host-NVIDIA-Treiber **R570+** erforderlich; ältere Treiber können die neuen Images nicht starten) / Training auf torch 2.11+cu128 aktualisiert (mit torch 2.2 erstellte Checkpoints können nicht fortgesetzt werden) / TF32 + bf16-mixed sind die neuen Trainings-Standards. Details: [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

Ein schnelles und hochwertiges neuronales Text-to-Speech-System (TTS). Basierend auf der [VITS](https://github.com/jaywalnut310/vits/)-Architektur mit Multi-Speaker-Sprachsynthese in 8 Sprachen: Japanisch, Englisch, Chinesisch, Koreanisch, Spanisch, Französisch, Portugiesisch und Schwedisch. Ein Fork von [Piper](https://github.com/rhasspy/piper) mit umfassend erweiterter japanischer Sprachunterstützung, verbesserter Audioqualität und erweiterten Trainingsfunktionen.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (läuft im Browser, kein Server erforderlich)

---

## Inhaltsverzeichnis

- [Benchmark](#benchmark)
- [Hauptfunktionen](#hauptfunktionen)
- [Schnellstart](#schnellstart)
- [Installation](#installation)
- [Verwendung](#verwendung)
- [Training](#training)
- [Vortrainierte Modelle](#vortrainierte-modelle)
- [Plattformen](#plattformen)
- [Weitere Links](#weitere-links)

---

## Benchmark

> **Messumgebung**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 Kerne / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Testsatz**: "Hello, how are you doing today?" (Englisch, 25 Phoneme)
> **Messparameter**: 5 Warmup-Durchläufe / 30 Messdurchläufe (intra-op threads = auto)
> **Verwendete Modelle**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (vereinheitlichter Decoder aus PR #320)
> - Piper Original: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa-Release)
>
> **Reproduktion**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| System | RTF ↓ | Latency P50 (ms) | Größe (MB) | RAM (MB) | Kaltstart (ms) | Parameter | Sprachen | Lizenz |
|--------|-------|------------------|-----------|---------|----------------|-----------|----------|--------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper Original (archiviert) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/Modell | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/Modell | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/Modell | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Hinweis**: RTF (Real-Time Factor) — niedriger ist schneller. `Latency P50` ist der Median der Einzelinferenz-Latenz und damit das direkteste Maß für die tatsächliche Reaktionsschnelligkeit. piper-plus erreicht dank des vereinheitlichten MB-iSTFT-Decoders mit 27 ms die niedrigste Latency P50 (-23% gegenüber Piper Original mit 35 ms, -49% gegenüber sherpa-onnx mit 53 ms) bei zugleich einer der kleinsten Modellgrößen (38 MB). Gegenüber der früheren HiFi-GAN-Basis von piper-plus (P50 43.3 ms) bedeutet das eine Verbesserung um -38%.
>
> **†** Mit † markierte Zeilen wurden in diesem PR nicht neu vermessen (`piper1-gpl` teilt Architektur und ONNX-Format mit dem ursprünglichen Piper und dürfte daher in etwa der Zeile "Piper Original" entsprechen; `Kokoro-82M` verwendet eine andere Architektur und `eSpeak-NG` ist eine nicht-neuronale CLI — beide passen nicht auf den Tensor-Vertrag von `scripts/benchmark.py` und bräuchten eigene Mess-Harnesse). Diese Werte stammen aus einer früheren Messung (Apple M2 Max).

### Multi-Runtime-RTF-Benchmark (aktuelle Werte)

Die aktuellen RTF- und Latenzwerte der 6 Runtimes Python / Rust / Go / C# / C++ / WASM, gemessen mit `multilingual-test-medium.onnx`, werden fortlaufend veröffentlicht und bei jedem Merge in den dev-Branch automatisch aktualisiert.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Hauptfunktionen

### Sprachsynthese

- **8 Sprachen** — Japanisch, Englisch, Chinesisch, Spanisch, Französisch, Portugiesisch (BR/EU-Dialektumschaltung: `pt`/`pt-BR`/`pt-PT`), Schwedisch und Koreanisch (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *Das trainierte Modell umfasst 6 Sprachen (JA/EN/ZH/ES/FR/PT)*
- **Japanisches TTS** — OpenJTalk-Integration, Prosodieinformationen (A1/A2/A3), Fragewort-Marker (#204), kontextabhängige "N"-Varianten (#207)
- **Englisches TTS** — GPL-freies G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), kein espeak-ng erforderlich
- **Multi-Speaker** — Unterstützung für 571 Sprecher (Basismodell für das Training), SpeakerBalancedBatchSampler, sprachgruppen-ausgewogenes Sampling
- **Benutzerdefinierte Wörterbücher** — Hinzufügen eigener Aussprachewörterbücher im JSON- (v1/v2) oder TSV-Format
- **Phonemeingabe** — Direkte Angabe über die `[[ phonemes ]]`-Notation — [Anleitung](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS-Verbesserung von +0.15-0.25 (standardmäßig aktiviert, nur beim Training verwendet)
- **MB-iSTFT-VITS2 Decoder** — Decoder vereinheitlicht auf MB-iSTFT + PQMF, 2.21x schnellere CPU-Inferenz. ONNX-Format unverändert, daher kompatibel mit bestehenden Runtimes
- **BF16 Mixed Precision** — `--precision bf16-mixed` (Standard) + TF32 für schnelleres Training, ca. 50% weniger Speicherbedarf
- **EMA** — Exponential Moving Average für stabiles Training (standardmäßig aktiviert)
- **Multi-GPU** — DDP-Unterstützung, automatische Lernraten-Skalierung
- **Prosody Features** — Einspeisung von Prosodieinformationen in den Duration Predictor (`--prosody-dim 16`)
- **Wandb-Integration** — Echtzeit-Metriküberwachung

### Schnittstellen

- **[WebUI (Gradio)](docs/features/webui.md)** — Für Inferenz und Training, Docker-kompatibel
- **C++ CLI** — Streaming, CUDA-Inferenz, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, benutzerdefinierte Wörterbücher
- **[C API Shared Library](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI-fähig (Flutter/Godot/Swift etc.), Streaming API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package); die Synthese-Engine selbst wird als universelles xcframework für iOS arm64 (Device + Simulator) ausgeliefert
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — eigenständige Bibliothek `PiperPlusG2P`: 8-sprachiges G2P auf iOS ohne ONNX-Runtime-Abhängigkeit (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Läuft vollständig im Browser, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, kein Server erforderlich
- **[Docker](docker/README.md)** — 7 Image-Familien: Inferenz, Training, WebUI, C++, Wyoming (Home Assistant) und mehr
- **PyPI** — Einfache Installation per `pip install piper-plus`, 8 Sprachen multilingual, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, Streaming, HTTP API
- **C# CLI** — .NET 10, plattformübergreifend, 8 Sprachen multilingual, ONNX-Inferenz, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, Streaming, CUDA/CoreML/DirectML-Unterstützung, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**, automatischer Wörterbuch-Download
- **[Go CLI](src/go/README.md)** — HTTP-API-Server, Session-Pooling, Docker-kompatibel, einzelne Binärdatei, **Phoneme-Timing-Ausgabe (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — in allen 6 Runtimes (Python/Rust/C#/Go/WASM/C++) verfügbar. C++ sowohl als CLI-Binary als auch über die `libpiper_plus`-C-API-Bibliothek. Extraktion des Sprecher-Embeddings aus einem Referenz-Audio per ECAPA-TDNN (`--reference-audio`)
- **SSML-Unterstützung** — `<speak>`, `<break>`, `<prosody rate="...">` in den 6 Runtimes Python/Rust/C#/Go/WASM/C++ implementiert (C++ über das CLI-Flag `--ssml`)
- **Qualitätsverbesserung für Kurztexte (Strategy A/B/C)** — Silence Padding, dynamische Scales und automatische SSML-`<break>`-Injektion in allen 6 Runtimes (`docs/spec/short-text-contract.toml`)

### Funktionsunterstützung pro Runtime

Die 6 Runtimes (Python/Rust/C#/Go/JS-WASM/C++) bieten gleichwertige 8-sprachige multilinguale Synthese. Phoneme Timing, Streaming (inkl. satzweiser Aufteilung), Voice Cloning und benutzerdefinierte Wörterbücher werden von allen Runtimes unterstützt. SSML wird von allen 6 Runtimes unterstützt (C++ über das CLI-Flag `--ssml`, nicht über die C API exportiert), die HTTP API von den 2 Runtimes Python und Go.

---

## Schnellstart

### Vorkompilierte Binaries (kein Build erforderlich)

Laden Sie vorkompilierte Binaries von [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) herunter und starten Sie sofort mit der Sprachsynthese.

**1. Binary herunterladen**

Laden Sie die passende Version für Ihr Betriebssystem herunter und entpacken Sie diese.

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

**2. Modell herunterladen & Sprache generieren**

```sh
# Tsukuyomi-chan-Modell herunterladen
./bin/piper-plus --download-model tsukuyomi

# Sprache generieren (der Modellname genuegt — heruntergeladene Modelle werden automatisch aufgeloest)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Hinweis zur Windows-cmd-Codepage:** Die Option `--text` verwendet intern `GetCommandLineW()` (UTF-16) und funktioniert daher unabhängig von der Codepage. Nur bei Pipe-Eingabe (`echo ... | piper-plus`) müssen Sie vorher mit `chcp 65001` auf UTF-8 umschalten.
>
> **Ausgabeort von output.wav:** Die Datei wird im aktuellen Verzeichnis erstellt (dort, wo Sie `cd piper-plus` ausgeführt haben).

> **Welches Binary soll ich wählen?** Die Releases enthalten außerdem `piper-plus-cli-*` (C# .NET) und `piper-plus-rs-cli-*` (Rust) CLIs. Der obige Schnellstart verwendet **C++ CLI (`piper-plus-cpp-*`)**, das die breiteste Plattformunterstützung bietet und für die meisten Nutzer empfohlen wird. Details siehe [Auswahl eines CLI-Binarys](docs/getting-started/binary-selection.md).

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

Wichtige Optionen: `--speaker-id` (Sprecher-ID), `--device auto|cpu|gpu`, `--noise-scale` (Sprachvariation), `--length-scale` (Sprechgeschwindigkeit), `--noise-scale-w` (Phonemlängenvariation, Standard: 0.5)

> **Empfohlene Einstellungen für WavLM-Modelle:** Modelle, die mit dem WavLM Discriminator trainiert wurden (z. B. Tsukuyomi-chan), erreichen mit `--noise-scale 0.5` optimale Audioqualität (Standard ist 0.4).

#### Python CLI Modellverwaltung

```bash
# Modellliste anzeigen
python -m piper_plus --list-models
python -m piper_plus --list-models ja

# Modell herunterladen
python -m piper_plus --download-model tsukuyomi
python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Nach dem Download verwenden
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

Von CI/CD gebaute Images:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

Weitere Details unter [docker/README.md](docker/README.md).

---

## Installation

### Python

Python 3.13+ empfohlen (3.11+ unterstützt). [uv](https://docs.astral.sh/uv/) wird als Paketmanager empfohlen.

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
piper-plus = "0.5"
```

### Aus Quellcode bauen

Wenn für Ihre Plattform keine vorkompilierten Binaries angeboten werden oder Sie piper-plus verändern möchten, können Sie aus dem Quellcode bauen. Die Build-Anleitungen für die C++-, C#- und Rust-Runtimes finden Sie im **[Build-Handbuch](docs/guides/development/building-from-source.md)**.

---

## Verwendung

Die detaillierten Kommandozeilenoptionen der C++ CLI, das JSON-Eingabeformat, die Modellverwaltung, Umgebungsvariablen und die Windows-Hilfsskripte sind im **[CLI-Handbuch](docs/guides/development/cli-usage.md)** beschrieben.

Einfaches Beispiel:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Training

Wie piper-plus-Modelle trainiert und feinabgestimmt werden (Grundkonfiguration, Multi-Speaker / Multi-GPU, ONNX-Export, Checkpoint-Verwaltung, Sprachevaluation), steht im **[Trainingshandbuch](docs/guides/training/training-guide.md)**.

Praxiserprobte Kommando-Vorlagen für das 6-Sprachen-Pretraining und das Tsukuyomi-chan-Finetuning finden sich in [CLAUDE.md](CLAUDE.md).

---

## Vortrainierte Modelle

Eine Übersicht der veröffentlichten piper-plus-Modelle, Download-Anleitungen, die Merkmale des 6-Sprachen-Basismodells und Details zum japanischen TTS stehen im **[Modellhandbuch](docs/guides/development/pretrained-models.md)**.

Wichtigste Modelle: `tsukuyomi` (Japanisch) und `css10-6lang` (per `--download-model` beziehbar) sowie der 6-Sprachen-Basis-Checkpoint (für Training / Finetuning) — Details auf Hugging Face unter [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) und [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

---

## Plattformen

- **macOS**: Apple Silicon (arm64) nativ unterstützt. Details siehe [macOS-Setup](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: x64 / arm64 unterstützt. OpenJTalk-Setup: [Windows-Setup-Anleitung](docs/getting-started/windows-setup.md)
- **WebAssembly**: Läuft vollständig offline im Browser. [Demo](https://ayutaz.github.io/piper-plus/) | [npm-Paket](https://www.npmjs.com/package/piper-plus)

---

## Weitere Links

### Unity — uPiper

Plugin zur Verwendung von Piper in Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2)
- 7 Sprachen (ja/en/zh/es/fr/pt/ko), asynchrone API, Streaming

### Stimmmodelle (Voices)

piper-plus-Modelle: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6-Sprachen-Basis) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Hinweis:** piper-plus verwendet ein eigenes G2P- und Phonem-System, daher sind upstream-Piper-Modelle (rhasspy/piper-voices) NICHT kompatibel.

### Verwandte Artikel (Japanisch)

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (Eigenständiges G2P-Paket)

Mehrsprachiges G2P (Grapheme-to-Phoneme) als eigenständige Pakete verfügbar:

- **Python**: `pip install piper-plus-g2p` — [Quellcode](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Quellcode](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Quellcode](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Quellcode](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` — [Quellcode](android/piper-plus-g2p/) · [Wörterbuch-Distributionsanleitung](docs/guides/platform/android-g2p-dictionary.md)
- **Swift (iOS/macOS)**: SPM-Produkt `PiperPlusG2P` — [Integrationsanleitung](docs/guides/platform/swift-g2p-integration.md) · [Quellcode](Sources/PiperPlusG2P/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Dokumentation

| Kategorie | Links |
|---|---|
| Training | [Trainingshandbuch](docs/guides/training/training-guide.md) (inkl. Multi-GPU) |
| API | [Phonem-Mapping](docs/api-reference/phoneme-mapping.md) · [Umgebungsvariablen](docs/getting-started/environment-variables.md) |
| Funktionen | [WebUI](docs/features/webui.md) · [Phoneme Timing](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| Einrichtung | [Windows](docs/getting-started/windows-setup.md) · [Fehlerbehebung](docs/getting-started/troubleshooting.md) |
| Docker | [Docker-Umgebung](docker/README.md) |
| WebAssembly | [Technische Details](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Fragen und Fehlerberichte gerne über die [Issues](https://github.com/ayutaz/piper-plus/issues). Der Verhaltenskodex steht in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).
