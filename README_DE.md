![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | Deutsch

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Pakete:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 Der einzige Piper-Fork unter MIT-Lizenz** — Das ursprüngliche [rhasspy/piper](https://github.com/rhasspy/piper) wurde im Oktober 2025 archiviert. [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) ist auf GPL-3.0 umgestiegen. piper-plus ist der einzige MIT-kompatible Fork ohne espeak-ng-Abhängigkeit. Die eigene G2P-Implementierung unterstützt 8 Sprachen (JA/EN/ZH/KO/ES/FR/PT/SV) und eignet sich für den kommerziellen und eingebetteten Einsatz.

> **📢 v2.0.0 Breaking Changes:** Die Standard-Docker-Images verwenden CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (NVIDIA-Hosttreiber **R570+** erforderlich). Das Training verwendet torch **2.11.0** + CUDA 12.8, standardmäßig mit TF32 + bf16-mixed. Das Fortsetzen von torch-2.2-Checkpoints wird nicht unterstützt. Python-Import und CLI heißen nun `piper_plus` bzw. `piper-plus`. Für das Update von 1.13.0 auf die aktuelle öffentliche Version führen Sie `pip install --upgrade "piper-plus[cpu]==2.0.2"` aus. Details: [Migrationsleitfaden](docs/migration/v1.12-to-v2.0.md).

Ein schnelles, hochwertiges neuronales Text-to-Speech-System (TTS). Es basiert auf der [VITS](https://github.com/jaywalnut310/vits/)-Architektur und unterstützt G2P/Phonemisierung in 8 Sprachen sowie Multi-Speaker-Sprachsynthese mit den aktuell trainierten Modellen in 6 Sprachen. Ein Fork von [Piper](https://github.com/rhasspy/piper) mit stark erweiterter Japanisch-Unterstützung, verbesserter Klangqualität und ausgebauten Trainingsfunktionen.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (läuft im Browser, kein Server erforderlich)

---

## Inhaltsverzeichnis

- [Benchmark](#benchmark)
- [Hauptfunktionen](#hauptfunktionen)
- [Schnellstart](#schnellstart)
- [Installation](#installation)
- [Verwendung](#verwendung)
- [Training](#training-1)
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
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (in PR #320 eingeführter einheitlicher Decoder)
> - Original-Piper: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa-Release)
>
> **Reproduktion**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| System | RTF ↓ | Latency P50 (ms) | Größe (MB) | RAM (MB) | Kaltstart (ms) | Parameter | Sprachen | Lizenz |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Original-Piper (archiviert) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/Modell | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/Modell | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/Modell | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Hinweis**: RTF (Real-Time Factor) — je niedriger, desto schneller. `Latency P50` ist der Median einer einzelnen Inferenz und das direkteste Maß für die tatsächliche Reaktionsfähigkeit. Dank des einheitlichen MB-iSTFT-Decoders erreicht piper-plus mit 27 ms die niedrigste Latency P50 (-23 % gegenüber Original-Piper mit 35 ms, -49 % gegenüber sherpa-onnx mit 53 ms) und gehört mit 38 MB zu den kleinsten Modellen. Auch gegenüber dem früheren piper-plus mit HiFi-GAN (P50 43.3 ms) ist das eine Verbesserung um -38 %.
>
> Mit **†** markierte Zeilen wurden in diesem PR nicht neu gemessen (`piper1-gpl` hat dieselbe Architektur und dasselbe ONNX-Format wie Original-Piper und dürfte daher etwa der Zeile von Original-Piper entsprechen; `Kokoro-82M` hat eine andere Architektur und `eSpeak-NG` ist ein nicht-neuronales CLI, sodass beide nicht in den Tensorvertrag von `scripts/benchmark.py` passen und ein eigenes Harness benötigen). Diese Werte stammen aus einer früheren Messung (Apple M2 Max).

### Multi-Runtime-RTF-Benchmark (aktuelle Werte)

Wir veröffentlichen die aktuellen RTF- und Latenzergebnisse, die mit `multilingual-test-medium.onnx` über 6 Runtimes (Python / Rust / Go / C# / C++ / WASM) hinweg gemessen wurden. Die Ergebnisse werden bei jedem Merge in den dev-Branch automatisch aktualisiert.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Hauptfunktionen

### Sprachsynthese

- **G2P/Phonemisierung für 8 Sprachen** — Japanisch, Englisch, Chinesisch, Spanisch, Französisch, Portugiesisch, Schwedisch, Koreanisch (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Die aktuell trainierten Modelle decken 6 Sprachen ab (JA/EN/ZH/ES/FR/PT)
- **Japanisches TTS** — OpenJTalk-Integration, Prosodie-Informationen (A1/A2/A3), Fragewort-Marker (#204), kontextabhängige „N“-Varianten (#207)
- **Englisches TTS** — v2.0.2 bündelt ein auf [g2p-en](https://github.com/Kyubyong/g2p) basierendes G2P mit Apache-2.0-Inferenzcode und dem MIT-Lizenzhinweis von Tacotron. Externe Pakete wie `g2p-en` / `Distance` oder espeak-ng werden nicht benötigt. Die Abhängigkeitsdefinition des älteren PyPI-Releases 2.0.1 bleibt unverändert. Siehe den [Migrationsleitfaden](docs/migration/python-g2p-license.md)
- **Multi-Speaker** — 571 Sprecher (Basismodell für das Training), SpeakerBalancedBatchSampler, gleichmäßiges Sampling nach Sprachgruppen
- **Benutzerwörterbuch** — Integriertes Aussprachewörterbuch mit über 200 Fachbegriffen
- **Phoneingabe** — Direkte Angabe über die Notation `[[ phonemes ]]` — [Leitfaden](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS +0.15-0.25 (standardmäßig aktiviert, nur beim Training verwendet)
- **MB-iSTFT-VITS2 Decoder** — Decoder auf MB-iSTFT + PQMF vereinheitlicht, 2.21-mal schnellere CPU-Inferenz. ONNX-Format unverändert und mit bestehenden Runtimes kompatibel
- **BF16 Mixed Precision** — `--precision bf16-mixed` ist der Standard (TF32 ist ebenfalls standardmäßig aktiviert). Numerisch stabiler als FP16, kein Loss Scaling erforderlich. Auf GPUs ohne BF16-Unterstützung (z. B. T4) geben Sie `--precision 16-mixed` an
- **EMA** — Stabileres Training durch Exponential Moving Average (standardmäßig aktiviert)
- **Multi-GPU** — DDP-Unterstützung, automatische Skalierung der Lernrate
- **Prosody Features** — Einspeisung von Prosodie-Informationen in den Duration Predictor (`--prosody-dim 16`)
- **Wandb-Integration** — Echtzeit-Überwachung von Metriken

### Schnittstellen

- **[WebUI (Gradio)](docs/features/webui.md)** — Inferenz und Docker werden unterstützt. Der lokale Training-Tab sendet noch veraltete CLI-Argumente; verwenden Sie für das Training den [Trainingsleitfaden](docs/guides/training/training-guide.md).
- **C++ CLI** — Streaming, CUDA-Inferenz, **Phonem-Timing-Ausgabe (JSON/TSV/SRT)**, Benutzerwörterbuch
- **[C-API-Shared-Library](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI-fähig (Flutter/Godot/Swift usw.), Streaming-API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), die Synthese-Engine wird als Universal-Build für iOS-arm64-Geräte und -Simulator ausgeliefert
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — Eigenständige Bibliothek `PiperPlusG2P`, G2P für 8 Sprachen unter iOS ohne ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Läuft vollständig im Browser, **Phonem-Timing-Ausgabe (JSON/TSV/SRT)**, kein Server erforderlich
- **[Docker](docker/README.md)** — 6 Images für Inferenz, Training, WebUI, C++ (Inferenz/Entwicklung) und Wyoming (Home Assistant)
- **PyPI** — Einfache Installation mit `pip install piper-plus`, G2P/Phonemisierung für 8 Sprachen (die aktuell trainierten Modelle decken 6 Sprachen ab), **Phonem-Timing-Ausgabe (JSON/TSV/SRT)**, Streaming, HTTP-API
- **C# CLI** — Plattformübergreifend mit .NET 10, G2P/Phonemisierung für 8 Sprachen (die aktuell trainierten Modelle decken 6 Sprachen ab), ONNX-Inferenz, **Phonem-Timing-Ausgabe (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, Streaming, Unterstützung für CUDA/CoreML/DirectML, **Phonem-Timing-Ausgabe (JSON/TSV/SRT)**, automatischer Wörterbuch-Download
- **[Go CLI](src/go/README.md)** — HTTP-API-Server, Session-Pooling, Docker-Unterstützung, einzelnes Binary, **Phonem-Timing-Ausgabe (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — Alle 6 Runtimes (Python/Rust/C#/Go/WASM/C++) unterstützen die Eingabe eines modellkompatiblen, vorab berechneten `speaker_embedding`. C++ CLI und C-API akzeptieren nur vorab berechnete Embeddings; die Extraktion über `--reference-audio` ist nicht implementiert. Die tatsächliche Inferenz mit dem öffentlichen `zs-v1` wurde nur mit Python `piper-plus==2.0.0` bestätigt. Der öffentliche CI-Lauf `38189966578` bestätigt die Inferenz in 6 Runtimes mit gemeinsamen Python-Phonem-IDs als Eingabe; natives G2P und die Qualität beim menschlichen Hörtest liegen außerhalb seines Umfangs, eine Qualitätsfreigabe ist nicht erfolgt.
- **SSML-Unterstützung** — Der SSML-Parser-Vertrag ist in Python/Rust/Go/C#/WASM/C++ implementiert. Die Synthese unterstützen Python/Rust/Go/WASM/C++; C# Core enthält den Parser, er ist jedoch nicht mit `--text` des CLI verbunden. C++ ist über das CLI-Flag `--ssml` verfügbar (nicht von der C-API exportiert).
- **Verbesserte Qualität kurzer Texte (Strategy A/B/C)** — Strategy A/B ist in allen Runtimes implementiert. Strategy C (automatisches Einfügen von SSML-`<break>`) umfasst Python-Inferenz/Rust/Go/C#; Python für das Training, WASM und C++ sind nicht abgedeckt. Details im [Kurztext-Vertrag](docs/spec/short-text-contract.toml).

### Funktionsunterstützung pro Runtime

Die 6 Runtimes (Python/Rust/C#/Go/JS-WASM/C++) ermöglichen die Synthese der 6 Sprachen der aktuell trainierten Modelle und bieten zusätzlich G2P/Phonemisierung für 8 Sprachen. Phonem-Timing, Streaming (einschließlich satzweiser Aufteilung), Voice Cloning mit modellkompatiblen, vorab berechneten Embeddings und Benutzerwörterbücher werden als Runtime-Funktionen unterstützt. C++ akzeptiert nur vorab berechnete Embeddings, `--reference-audio` ist nicht implementiert. Die tatsächliche Inferenz mit dem öffentlichen `zs-v1` wurde nur mit Python `piper-plus==2.0.0` bestätigt. Der öffentliche CI-Lauf `38189966578` bestätigt die Inferenz in 6 Runtimes mit gemeinsamen Python-Phonem-IDs, natives G2P und die Qualität beim menschlichen Hörtest liegen jedoch außerhalb seines Umfangs, und eine Qualitätsfreigabe ist nicht erfolgt. Die SSML-Synthese unterstützen Python/Rust/Go/WASM/C++ (C++ über das CLI-Flag `--ssml`, nicht von der C-API exportiert). Der Parser von C# Core ist nicht mit `--text` des CLI verbunden; die HTTP-API wird von 2 Runtimes (Python/Go) unterstützt.

---

## Schnellstart

### Vorkompilierte Binaries (kein Build erforderlich)

Laden Sie vorkompilierte Binaries von [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) herunter und starten Sie sofort mit der Sprachsynthese.

**1. Binary herunterladen**

Laden Sie das Archiv für Ihr Betriebssystem herunter und entpacken Sie es.

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

**ARM64-Kompatibilität:** Das Linux-ARM64-C++-Archiv von v2.0.2 wird gegen glibc 2.31 als ABI-Obergrenze geprüft. Start und japanische Synthese werden unter QEMU auf Debian Bullseye / Bookworm / Trixie (64 Bit) verifiziert. Echte Raspberry-Pi-Hardware und Raspberry Pi OS selbst sind nicht getestet. Das ältere Archiv von v2.0.1 benötigt glibc 2.38 oder neuer; verwenden Sie daher v2.0.2.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, 32-Bit-ARM):**

Für ARMv7 wird nur das C++ CLI ausgeliefert. Die CI prüft Build und japanische Synthese unter QEMU auf Debian Trixie (32-Bit-ARM). Echte Raspberry-Pi-Hardware ist nicht getestet.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Modell herunterladen & Sprache generieren**

```sh
# Tsukuyomi-chan-Modell herunterladen
./bin/piper-plus --download-model tsukuyomi

# Sprache generieren (der Modellname reicht - heruntergeladene Modelle werden automatisch aufgeloest)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Zur Codepage von Windows cmd:** Die Option `--text` verwendet intern `GetCommandLineW()` (UTF-16) und funktioniert daher unabhängig von der Codepage. Nur bei Pipe-Eingabe (`echo ... | piper-plus`) müssen Sie vorher mit `chcp 65001` auf UTF-8 umschalten.
>
> **Speicherort von output.wav:** Die Datei wird im aktuellen Verzeichnis erzeugt (dort, wo Sie `cd piper-plus` ausgeführt haben).

> **Welches Binary soll ich wählen?** Neben `piper-plus-cpp-*` (C++) enthalten die Releases auch die CLIs `piper-plus-cli-*` (C# .NET) und `piper-plus-rs-cli-*` (Rust). Das im obigen Schnellstart verwendete **C++ CLI (`piper-plus-cpp-*`)** unterstützt die meisten Plattformen und wird empfohlen. Details unter [Auswahl des CLI-Binarys](docs/getting-started/binary-selection.md).

### Python-Inferenz

```bash
# Installation
# Aus dem Repository-Root eines Source-Checkouts ausfuehren
uv sync --extra inference

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

Wichtige Optionen: `--speaker-id` (Sprecher-ID), `--device auto|cpu|gpu`, `--noise-scale` (Stimmvariation), `--length-scale` (Sprechgeschwindigkeit), `--noise-scale-w` (Variation der Phonemdauer, Standard: 0.5)

> **Empfohlene Einstellung für WavLM-Modelle:** Mit dem WavLM Discriminator trainierte Modelle (z. B. Tsukuyomi-chan) erreichen mit `--noise-scale 0.5` die beste Klangqualität (Standard ist 0.4).

#### Python-CLI-Modellverwaltung

```bash
# Modellliste anzeigen
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# Modell herunterladen
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Nach dem Download verwenden
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

Per CI/CD gebaute Images:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

Details unter [docker/README.md](docker/README.md).

---

## Installation

### Python

Python 3.13+ empfohlen (3.11+ unterstützt). Für die Abhängigkeitsverwaltung wird [uv](https://docs.astral.sh/uv/) empfohlen.

```bash
# CPU-Inferenz
uv sync --extra inference

# GPU-Inferenz (CUDA-Umgebung erforderlich)
uv sync --no-group cpu --extra inference-gpu

# Training
uv sync --extra train

# Entwicklung (inkl. Tests und Linter)
uv sync --extra dev
```

Auch über das PyPI-Paket installierbar:

```bash
pip install piper-plus
```

### Installation aus Paketen

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm (Browser-WASM):**

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

**C#-Bibliothek (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Rust-Bibliothek (crates.io):**

```toml
[dependencies]
piper-plus = "0.5"
```

### Aus dem Quellcode bauen

Wenn für Ihre Plattform keine vorkompilierten Binaries bereitgestellt werden oder Sie piper-plus anpassen möchten, können Sie es aus dem Quellcode bauen. Die Build-Anleitungen für die Runtimes C++ / C# / Rust finden Sie im **[Leitfaden zum Bauen aus dem Quellcode](docs/guides/development/building-from-source.md)**.

---

## Verwendung

Detaillierte Kommandozeilenoptionen des C++ CLI, das JSON-Eingabeformat, die Modellverwaltung, Umgebungsvariablen und die Verwendung der Windows-Hilfsskripte finden Sie im **[CLI-Nutzungsleitfaden](docs/guides/development/cli-usage.md)**.

Einfaches Beispiel:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Training

Wie Sie piper-plus-Modelle trainieren und feinabstimmen (Grundeinstellungen, Multi-Speaker / Multi-GPU, ONNX-Konvertierung, Checkpoint-Verwaltung, Sprachevaluation), erfahren Sie im **[Trainingsleitfaden](docs/guides/training/training-guide.md)**.

Befehlsvorlagen für den praktischen Einsatz (6-Sprachen-Vortraining und Feinabstimmung von Tsukuyomi-chan) finden Sie in [CLAUDE.md](CLAUDE.md).

---

## Vortrainierte Modelle

Die Liste der veröffentlichten piper-plus-Modelle, Download-Anleitungen, die Merkmale des 6-Sprachen-Basismodells und Details zum japanischen TTS finden Sie im **[Modellleitfaden](docs/guides/development/pretrained-models.md)**.

Wichtige Modelle: `tsukuyomi` (Japanisch), `zs-v1` (experimentelle Zero-Shot/FT-Basis für 6 Sprachen), `bilingual-ja-en-v4` (Japanisch-Englisch, 2 Sprachen) — Details im fest versionierten [zs-v1-Bundle](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) auf HuggingFace und unter [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

> **Zero-Shot/FT-Basis (`zs-v1`, 2026-10-10):** Das fest versionierte öffentliche Bundle ist die bestehende experimentelle Basis aus v7 Epoche 32 (JA/EN/ZH/ES/FR/PT, 571 Sprecher, 173 Phoneme, CAM++ mit 192 Dimensionen). Verwenden Sie für Zero-Shot-Inferenz `base.onnx` mit einem Referenz-Embedding, das mit dem mitgelieferten `campplus.onnx` extrahiert wurde, und für zusätzliches Training `base.ckpt` mit der mitgelieferten `config.json`. Die öffentlichen Beispiele wurden mit PyPI `piper-plus==2.0.0` funktional geprüft; das bedeutet jedoch weder eine Qualitätsfreigabe noch einen bestandenen menschlichen Hörtest noch die neueste/beste Qualität. Die Aliase `base` / `zero-shot-base-zs-v1` sind in v2.0.2 enthalten (nicht in 2.0.0 / 2.0.1). Das `model.ckpt` im Root wird separat als ältere Generation behandelt.

> **Tsukuyomi-chan-FT (`zs-v1`, 2026-10-15):** Wir haben ein [fest versioniertes öffentliches Modell](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1) veröffentlicht, das aus derselben öffentlichen Basisgeneration weitertrainiert wurde. Mit `tsukuyomi.onnx` und `tsukuyomi.onnx.json` lässt sich Sprache ohne Referenzaudio und ohne CAM++ erzeugen. Eine menschliche Prüfung von 3 japanischen Sätzen wurde dokumentiert und die Veröffentlichung als experimentelle Version genehmigt (quality_approval=false, keine Qualitätsfreigabe). Der bestehende Alias `tsukuyomi` wählt weiterhin das ältere Root-Modell; laden Sie das neue Modell daher über die festen URLs im [Modellleitfaden](docs/guides/development/pretrained-models.md) herunter.

---

## Plattformen

- **macOS**: Native Unterstützung für Apple Silicon (arm64). Details unter [macOS-Einrichtung](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: Die C++-Release-Assets sind für x64, das C# CLI für x64 / arm64. Zur Einrichtung von OpenJTalk siehe den [Windows-Einrichtungsleitfaden](docs/getting-started/windows-setup.md)
- **WebAssembly**: Vollständig offline im Browser lauffähig. [Demo](https://ayutaz.github.io/piper-plus/) | [npm-Paket](https://www.npmjs.com/package/piper-plus)

---

## Weitere Links

### Unity — uPiper

Plugin zur Verwendung von Piper in Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Unterstützt Windows / macOS (Apple Silicon) / Linux / Android
- Japanisch und Englisch, asynchrone API, Streaming

### Stimmmodelle (Voices)

piper-plus-eigene Modelle: [zs-v1 Zero-Shot/FT-Basis](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Hinweis:** piper-plus verwendet ein eigenes G2P- und Phonemsystem und ist daher nicht mit den Modellen des Upstream-Piper (rhasspy/piper-voices) kompatibel.

### Verwandte Artikel (Japanisch)

- [Ein englisches vortrainiertes Piper-Modell mit LJSpeech erstellen](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Ein japanisches Piper-Modell mit dem JVS-Sprachdatensatz erstellen](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Ein Piper-Modell mit dem Tsukuyomi-chan-Datensatz weitertrainieren](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (eigenständiges G2P-Paket)

Mehrsprachiges G2P (Grapheme-to-Phoneme) als eigenständiges Paket:

- **Python**: `pip install piper-plus-g2p` — [Quellcode](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Quellcode](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Quellcode](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Quellcode](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [Quellcode](android/piper-plus-g2p/) · [Leitfaden zur Wörterbuchverteilung](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Dokumentation

| Kategorie | Links |
|---|---|
| Japanisches TTS | Leitfaden zur japanischen Sprachsynthese |
| Training | [Trainingsleitfaden](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Phonem-Mapping](docs/api-reference/phoneme-mapping.md) · [Umgebungsvariablen](docs/getting-started/environment-variables.md) |
| Funktionen | [WebUI](docs/features/webui.md) · CLI-Erweiterungen · Streaming |
| Einrichtung | Schnellstart (Japanisch) · [Windows](docs/getting-started/windows-setup.md) · [Fehlerbehebung](docs/getting-started/troubleshooting.md) |
| Docker | [Docker-Umgebungen](docker/README.md) |
| WebAssembly | [Technische Details](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Fragen und Fehlerberichte bitte über [Issues](https://github.com/ayutaz/piper-plus/issues). Den Verhaltenskodex finden Sie in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

## Danksagung

Die GPU-Experimente von piper-plus werden durch den AI Builder Grant (GPU-Guthaben) von [CloudRift](https://www.cloudrift.ai/) unterstützt.
