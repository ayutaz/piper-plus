![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | Français | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

> **📢 v2.0.0 Changements incompatibles :** Les images Docker utilisent CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (pilote NVIDIA hôte **R570+** requis). Entraînement : torch **2.11.0** + CUDA 12.8, TF32 + bf16-mixed par défaut ; reprise des checkpoints torch 2.2 non prise en charge. Les noms Python / CLI deviennent `piper_plus` / `piper-plus`. Pour passer de 1.13.0 à la version publique actuelle : `pip install --upgrade "piper-plus==2.0.1"`. Voir le [guide de migration](docs/migration/v1.12-to-v2.0.md).

**Paquets :**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 Le seul fork de Piper sous licence MIT** — Le projet original [rhasspy/piper](https://github.com/rhasspy/piper) a été archivé en octobre 2025 et [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) est passé sous licence GPL-3.0. piper-plus est le seul fork compatible MIT sans dépendance à espeak-ng. Son G2P maison prend en charge 8 langues (JA/EN/ZH/KO/ES/FR/PT/SV), ce qui le rend adapté à un usage commercial et embarqué.

> **📢 v1.12.0 Changements incompatibles (2026-05):** Décodeur HiFi-GAN supprimé (unifié sur MB-iSTFT, drapeau `--mb-istft` retiré) / Flask → serveur HTTP FastAPI / Dépendance HTS-voice supprimée (runtime Python uniquement) / Unity UPM déplacé vers un dépôt séparé (`ayutaz/uPiper`) / tous les projets .NET migrés vers `net10.0` LTS. Détails : [docs/migration/v1.11-to-v1.12.md](docs/migration/v1.11-to-v1.12.md)

Système de synthèse vocale neuronale (TTS) rapide et de haute qualité. Basé sur l'architecture [VITS](https://github.com/jaywalnut310/vits/), il fournit un G2P/une phonémisation en 8 langues et une synthèse multi-locuteurs avec les modèles entraînés actuels en 6 langues (japonais, anglais, chinois mandarin, espagnol, français, portugais). Fork de [Piper](https://github.com/rhasspy/piper) avec un support japonais, une qualité audio et des fonctionnalités d'entraînement considérablement améliorés.

**[Démo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Démo WebAssembly](https://ayutaz.github.io/piper-plus/)** (fonctionne dans le navigateur, sans serveur)

---

## Table des matières

- [Fonctionnalités principales](#fonctionnalités-principales)
- [Démarrage rapide](#démarrage-rapide)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Entraînement](#entraînement)
- [Modèles pré-entraînés](#modèles-pré-entraînés)
- [TTS japonais](#tts-japonais)
- [Plateformes](#plateformes)
- [Liens associés](#liens-associés)

---

## Fonctionnalités principales

### Synthèse vocale

- **TTS japonais** — Intégration OpenJTalk, caractéristiques prosodiques (A1/A2/A3), marqueurs interrogatifs (#204), variantes contextuelles du "N" (#207)
- **TTS anglais** — G2P sans GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), pas de dépendance à espeak-ng
- **G2P/phonémisation en 8 langues** — Japonais, anglais, chinois mandarin, espagnol, français, portugais, suédois, coréen (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Les modèles entraînés actuels couvrent 6 langues (JA/EN/ZH/ES/FR/PT)
- **Multi-locuteurs** — 571 locuteurs dans le bundle expérimental Zero-Shot/FT `zs-v1`, SpeakerBalancedBatchSampler
- **Dictionnaire personnalisé** — 200+ termes techniques intégrés
- **Saisie phonémique** — Spécification directe avec la notation `[[ phonemes ]]` — [Guide](docs/features/phoneme-input.md)

### Entraînement

- **WavLM Discriminator** — Amélioration MOS +0.15-0.25 (activé par défaut, uniquement à l'entraînement)
- **Décodeur MB-iSTFT-VITS2** — Décodeur unifié à MB-iSTFT + PQMF, inférence CPU ~2,21x plus rapide. Compatible ONNX avec les runtimes existants
- **FP16 Mixed Precision** — Entraînement 2-3x plus rapide, ~50% de mémoire en moins (activé par défaut)
- **EMA** — Moyenne mobile exponentielle pour la stabilité (activé par défaut)
- **Multi-GPU** — Support DDP, mise à l'échelle automatique du taux d'apprentissage
- **Caractéristiques prosodiques** — Injection de prosodie dans le Duration Predictor (`--prosody-dim 16`)
- **Intégration Wandb** — Surveillance des métriques en temps réel

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inférence et prise en charge de Docker. L’onglet d’entraînement local envoie encore des arguments CLI obsolètes ; utilisez le [guide d’entraînement](docs/guides/training/training-guide.md) pour entraîner.
- **CLI C++** — Streaming, inférence CUDA, **sortie Phoneme Timing (JSON/TSV/SRT)**, dictionnaire personnalisé
- **[C API Bibliothèque partagée](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatible FFI (Flutter/Godot/Swift etc.), API streaming
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Fonctionne entièrement dans le navigateur, **sortie Phoneme Timing (JSON/TSV/SRT)**, sans serveur
- **[Docker](docker/README.md)** — 5 images pour l'inférence, l'entraînement, WebUI et C++
- **PyPI** — `pip install piper-plus`, G2P/phonémisation en 8 langues (modèles entraînés actuels : 6 langues), **sortie Phoneme Timing (JSON/TSV/SRT)**, streaming, **HTTP API base FastAPI**
- **CLI C#** — .NET 10 multiplateforme, G2P/phonémisation en 8 langues (modèles entraînés actuels : 6 langues), inférence ONNX, **sortie Phoneme Timing (JSON/TSV/SRT)**
- **CLI Rust** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML, **sortie Phoneme Timing (JSON/TSV/SRT)**, téléchargement automatique des dictionnaires
- **[CLI Go](src/go/README.md)** — Serveur API HTTP, pooling de sessions, Docker, binaire unique, **sortie Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — pris en charge au niveau des capacités runtime par les 6 runtimes (Python/Rust/C#/Go/WASM/C++) pour des entrées `speaker_embedding` pré-calculées et compatibles avec le modèle. Le CLI et l'API C++ acceptent uniquement les embeddings pré-calculés ; l'extraction via `--reference-audio` n'est pas implémentée en C++. L'inférence publique de `zs-v1` n'a été vérifiée fonctionnellement qu'avec Python `piper-plus==2.0.0`. Le CI public `38189966578` rapporte une inférence dans six runtimes avec des IDs phonémiques Python partagés ; le G2P natif et la qualité d'écoute étaient hors périmètre, sans validation qualité.
- **Support SSML** — Le contrat du parseur est implémenté en Python/Rust/Go/C#/WASM/C++ ; les points d’entrée de synthèse sont Python/Rust/Go/WASM/C++. C# Core contient le parseur, mais le chemin `--text` de la CLI C# n’y est pas encore relié. C++ est exposé via la CLI `--ssml` (pas par l’API C).
- **Amélioration des textes courts (stratégies A/B/C)** — Les stratégies A/B sont implémentées dans les lignes de runtime. La stratégie C (injection automatique de SSML `<break>`) est limitée à Python d’inférence/Rust/Go/C# ; Python d’entraînement, WASM et C++ sont hors périmètre. Voir le [contrat des textes courts](docs/spec/short-text-contract.toml).

### Support des fonctionnalités par runtime

Synthèse avec les modèles entraînés actuels en 6 langues sur 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++), avec G2P/phonémisation en 8 langues. Phoneme Timing, streaming (avec division par phrases), Voice Cloning via des entrées `speaker_embedding` pré-calculées et compatibles avec le modèle, et dictionnaires personnalisés sont pris en charge au niveau runtime. C++ accepte uniquement les embeddings pré-calculés et `--reference-audio` n'est pas implémenté. L'inférence publique de `zs-v1` a été vérifiée avec Python `piper-plus==2.0.0` ; le CI `38189966578` rapporte séparément une inférence dans six runtimes avec des IDs phonémiques Python partagés. Le G2P natif et la qualité d'écoute étaient hors périmètre, sans validation qualité. La synthèse SSML est prise en charge par Python/Rust/Go/WASM/C++ ; le parseur de C# Core n’est pas relié au chemin `--text` de la CLI. L’API HTTP est prise en charge par 2 runtimes (Python/Go).

### Plateformes

| Plateforme | Architecture | Notes |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | Artefacts C++ v2.0.1 disponibles ; ARM64 nécessite glibc 2.38. Le correctif compatible glibc 2.31 est dans dev/source |
| macOS | ARM64 (Apple Silicon) uniquement | M1/M2/M3+ |
| Windows | x64 | Artefacts C++ x64 ; CLI C# également x64 / arm64 |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | Bibliothèque partagée, Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 10, Linux/macOS/Windows |
| Rust | Linux x64, macOS ARM64, Windows x64 | CUDA/CoreML/DirectML |
| Go | Linux x64, macOS ARM64, Windows x64 | API HTTP, Docker |

---

## Démarrage rapide

### Inférence Python

```bash
# Installation
# Exécuter depuis la racine d’un source checkout
uv sync --extra inference

# Inference japonaise
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# Inference anglaise
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

Options principales : `--speaker-id` (ID locuteur), `--device auto|cpu|gpu`, `--noise-scale` (variation audio), `--noise-scale-w` (variation de durée des phonèmes), `--length-scale` (vitesse)

> **Réglage recommandé pour les modèles WavLM :** Les modèles entraînés avec WavLM Discriminator (comme Tsukuyomi-chan) offrent une qualité optimale avec `--noise-scale 0.5` (défaut : 0.4).

#### Gestion des modèles (Python CLI)

```bash
# Lister les modeles disponibles
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# Telecharger un modele
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Utiliser apres telechargement
uv run --no-sync python -m piper_plus --model ja_JP-tsukuyomi-chan-medium "こんにちは" -f output.wav
```

### WebUI

```bash
uv sync --project environments/webui --locked
uv run --project environments/webui --no-sync python -m piper_plus.webui --data-dir /path/to/models
# → http://localhost:7860
```

### Binaires pré-compilés (aucune compilation requise)

Téléchargez les binaires pré-compilés depuis [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) et commencez la synthèse vocale immédiatement.

**1. Télécharger le binaire**

Téléchargez et extrayez selon votre système d'exploitation.

**Windows (PowerShell) :**

```powershell
Invoke-WebRequest -Uri "https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-windows-x64.zip" -OutFile piper-plus-cpp.zip
Expand-Archive piper-plus-cpp.zip -DestinationPath .
cd piper-plus
```

**macOS (Apple Silicon) :**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-macos-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
xattr -cr .
```

**Linux (x86_64) :**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-x64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARM64, Raspberry Pi 4/5) :**

**Compatibilité ARM64 :** l’artefact C++ Linux ARM64 de v2.0.1 nécessite glibc 2.38 ou ultérieure. Le correctif compatible glibc 2.31 est dans dev/source ; le démarrage et la synthèse japonaise ont été vérifiés sous QEMU avec Debian Bullseye / Bookworm / Trixie (64 bits). Le matériel Raspberry Pi et Raspberry Pi OS lui-même restent non testés. Construisez dev/source pour une compatibilité glibc plus large.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Télécharger un modèle et générer de l'audio**

```sh
# Telecharger le modele Tsukuyomi-chan
./bin/piper-plus --download-model tsukuyomi

# Generer de l'audio (le nom du modele suffit — resolution automatique des modeles telecharges)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Page de code Windows cmd :** L'option `--text` utilise `GetCommandLineW()` (UTF-16) en interne et fonctionne indépendamment de la page de code. Pour l'entrée par pipe (`echo ... | piper-plus`), basculez d'abord en UTF-8 avec `chcp 65001`.
>
> **Emplacement de output.wav :** Le fichier est généré dans le répertoire courant (l'endroit où vous avez exécuté `cd piper-plus`).

> **Quel binaire choisir ?** Les releases incluent également les CLI `piper-plus-cli-*` (C# .NET) et `piper-plus-rs-cli-*` (Rust). Le Démarrage rapide ci-dessus utilise le **CLI C++ (`piper-plus-cpp-*`)**, qui dispose de la prise en charge de plateformes la plus large et est recommandé pour la plupart des utilisateurs. Voir [Choisir un binaire CLI](docs/getting-started/binary-selection.md) pour plus de détails.

### Docker

```bash
# WebUI
docker build -t piper-webui -f docker/webui/Dockerfile .
docker run -p 7860:7860 -v ./models:/models:ro piper-webui

# Inference Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# Inference GPU (ajouter --gpus all)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

Images pré-construites CI/CD :

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Note :** L'image webui n'est pas automatiquement construite par le CI. Construisez manuellement avec : docker build -t piper-webui -f docker/webui/Dockerfile .

Voir [docker/README.md](docker/README.md) pour plus de détails.

---

## Installation

### Python

Python 3.13+ recommandé (3.11+ supporté). [uv](https://docs.astral.sh/uv/) est recommandé pour la gestion des dépendances.

```bash
# Inference CPU
uv sync --extra inference

# Inference GPU (necessite CUDA)
uv sync --no-group cpu --extra inference-gpu

# Entrainement
uv sync --extra train

# Developpement (inclut tests et linting)
uv sync --extra dev
```

Également disponible sur PyPI :

```bash
pip install piper-plus
```

### Installation depuis les gestionnaires de paquets

**Python (PyPI) :**

```bash
pip install piper-plus
```

**npm (Navigateur WASM) :**

```bash
npm install piper-plus onnxruntime-web
```

**C# CLI (Outil global .NET) :**

```bash
dotnet tool install -g PiperPlus.Cli
```

**Rust CLI (crates.io) :**

```bash
cargo install piper-plus-cli
```

**Bibliothèque C# (NuGet) :**

```bash
dotnet add package PiperPlus.Core
```

**Bibliothèque Rust (crates.io) :**

```toml
[dependencies]
piper-plus = "0.5"
```

### Construction depuis les sources (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Prérequis : compilateur C++17, CMake 3.15+

- **Linux** : les dépendances (ONNX Runtime, OpenJTalk, etc.) sont téléchargées automatiquement par CMake
- **Windows** : voir le [Guide d'installation Windows](docs/getting-started/windows-setup.md)
- **macOS** : les dépendances sont téléchargées automatiquement

### Construction depuis les sources (C#)

```bash
# Construction du CLI C#
dotnet build src/csharp/PiperPlus.sln -c Release
# Tests
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Prérequis : .NET 10 SDK ou supérieur

#### Exemples d'utilisation du CLI C\#

```bash
# Inference par nom de modele (telechargement automatique, sortie par defaut : output.wav)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# Anglais
piper-plus --model model.onnx --text "Hello world" --language en

# Multilingue (detection automatique de la langue)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Notation phonemique en ligne (specification directe des phonemes dans le texte)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Streaming (sortie PCM sequentielle par phrase)
piper-plus --model model.onnx --text "Premiere phrase. Deuxieme phrase." --language fr --streaming | aplay -r 22050 -f S16_LE

# Dictionnaire personnalise (JSON v1/v2 ou TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# Telechargement de modeles
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Mode test (verification des phoneme IDs sans inference ONNX)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

### Construction depuis les sources (Rust)

```bash
# Construction du CLI Rust
cargo build --release -p piper-plus-cli
# Tests
cargo test -p piper-plus
```

Prérequis : Rust 1.88+, cargo

#### Exemples d'utilisation du CLI Rust

```bash
# Inference par nom de modele (telechargement automatique)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# Anglais
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Telechargement et gestion de modeles
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Streaming (synthese sequentielle par phrase)
piper-plus-cli --model model.onnx --text "Premiere phrase. Deuxieme phrase." --stream --output-dir chunks/

# Dictionnaire personnalise
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# Inference GPU
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Mode test et mode silencieux
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Sortie PCM brute (sans en-tete WAV)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Note :** Le CLI C# s'installe via `dotnet tool install -g PiperPlus.Cli` et le CLI Rust via `cargo install piper-plus-cli`. Les deux fournissent le G2P/phonémisation en 8 langues ; les modèles entraînés actuels couvrent 6 langues, avec dictionnaires personnalisés et streaming.

---

## Utilisation

### CLI C++

#### Saisie directe de texte (recommandé)

L'option `--text` permet de saisir du texte directement sans pipe :

```sh
# Generer de l'audio depuis du texte
./bin/piper-plus --model model.onnx --text "Hello, how are you?" -f output.wav

# Texte japonais (evite les problemes d'encodage sous Windows)
bin\piper-plus.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# Specification du locuteur
./bin/piper-plus --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Entrée par pipe

```sh
# Utilisation de base
echo "こんにちは" | ./bin/piper-plus --model ja_model.onnx --output_file output.wav

# Streaming (faible latence)
echo "Texte long..." | ./bin/piper-plus --model ja_model.onnx --output_file output.wav --streaming

# Inference GPU
echo "Hello" | ./bin/piper-plus --model en_model.onnx --use-cuda --output_file output.wav

# Sortie de timing phonemique (pour lip-sync, sous-titres)
echo "Hello world" | ./bin/piper-plus --model en_model.onnx -f speech.wav --output-timing timing.json

# Dictionnaire personnalise
echo "DockerとGitHubを使います" | ./bin/piper-plus --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Saisie phonemique en ligne
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper-plus --model en_model.onnx -f output.wav

# Saisie de phonemes bruts
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper-plus --model en_model.onnx --raw-phonemes -f output.wav

# Streaming (sortie audio brute)
echo 'Long text...' | ./bin/piper-plus --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Options principales :

| Option | Description | Défaut |
|---|---|---|
| `--model PATH\|NAME` | Chemin du fichier modèle, ou nom du modèle (résolution automatique des modèles téléchargés) | - |
| `--text TEXT` | Saisie directe de texte (sans pipe) | - |
| `--streaming` | Mode streaming par morceaux | off |
| `--use-cuda` | Activer l'inférence GPU CUDA | off |
| `--gpu-device-id NUM` | ID du périphérique GPU | 0 |
| `--length-scale VAL` | Vitesse de parole (plus petit = plus rapide) | 1.0 |
| `--noise-scale VAL` | Contrôle de la variation audio | 0.4 |
| `--noise-w VAL` | Variation de la durée des phonèmes | 0.5 |
| `--sentence-silence SEC` | Silence entre les phrases | 0.2 |
| `--speaker NUM` | Numéro de locuteur pour les modèles multi-locuteurs | 0 |
| `--phoneme-silence PHONEME SEC` | Durée de silence pour des phonèmes spécifiques | - |
| `--raw-phonemes` | Interpréter l'entrée comme des phonèmes | off |
| `--output-timing FILE` | Sortie de timing phonémique (JSON/TSV) | - |
| `--custom-dict FILE` | Dictionnaire personnalisé (plusieurs avec virgule) | - |
| `--json-input` | Mode d'entrée JSON | off |
| `--list-models [LANG]` | Lister les modèles disponibles | - |
| `--download-model NAME` | Télécharger un modèle | - |
| `--model-dir DIR` | Répertoire de destination des modèles téléchargés | - |
| `--version` | Afficher la version | - |

Exécutez `piper-plus --help` pour toutes les options.

> **Réglage recommandé pour les modèles WavLM :** Les modèles entraînés avec WavLM Discriminator offrent une qualité optimale avec `--noise-scale 0.5` (défaut : 0.4).
>
> ```sh
> echo "こんにちは" | ./bin/piper-plus --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### Entrée JSON

Utilisez le drapeau `--json-input` pour l'entrée JSON :

```json
{ "text": "Premier locuteur.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second locuteur.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Gestion des modèles

#### Lister les modèles

```bash
# Lister les modeles disponibles
./bin/piper-plus --list-models

# Filtrer par langue
./bin/piper-plus --list-models ja
./bin/piper-plus --list-models en
```

#### Télécharger des modèles

```bash
# Telecharger par nom de modele (les alias sont egalement acceptes)
./bin/piper-plus --download-model tsukuyomi
./bin/piper-plus --download-model en_US-lessac-medium

# Specifier le repertoire de destination
./bin/piper-plus --download-model tsukuyomi --model-dir /path/to/models

# Apres telechargement, inferer par nom de modele (chemin complet inutile)
./bin/piper-plus --model tsukuyomi --text "こんにちは"
```

### Variables d'environnement (CLI C++)

| Variable | Description | Exemple |
|---|---|---|
| `PIPER_PLUS_DEFAULT_MODEL` | Chemin du modèle par défaut si `--model` n'est pas spécifié | `/path/to/model.onnx` |
| `PIPER_PLUS_DEFAULT_CONFIG` | Chemin du fichier de configuration par défaut si `--config` n'est pas spécifié | `/path/to/config.json` |
| `PIPER_PLUS_MODEL_DIR` | Répertoire de stockage des modèles téléchargés | `~/.local/share/piper-plus/models` |
| `PIPER_PLUS_GPU_DEVICE_ID` | ID du périphérique GPU CUDA | `0` |

### Scripts d'aide (Windows)

Des scripts d'aide pour les utilisateurs Windows sont fournis dans le répertoire `scripts/`.

**PowerShell :**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Invite de commandes :**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Entraînement

Voir le [Guide d'entraînement](docs/guides/training/training-guide.md) pour les instructions détaillées.

### Basique

```bash
uv sync --extra train

uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --accelerator gpu --devices 1 --precision 16-mixed \
  --max_epochs 200 --batch-size 16 \
  --quality medium \
  --prosody-dim 16 \
  --ema-decay 0.9995
```

### Multi-locuteurs / Multi-GPU

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

Le multi-GPU configure automatiquement le DDP (Distributed Data Parallel). Les variables d'environnement NCCL sont requises. Voir le Guide multi-GPU pour plus de détails.

### Export ONNX

La conversion FP16 est appliquée par défaut, réduisant la taille du modèle d'environ 50%. Utilisez `--no-fp16` pour désactiver.

```bash
# Modele standard (FP16 par defaut)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Modele sans FP16
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# Modele WavLM (--stochastic active par defaut)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Gestion des checkpoints

- `--resume_from_checkpoint` — Reprendre l'entraînement depuis un checkpoint
- `--resume_from_single_speaker_checkpoint` — Convertir un modèle mono-locuteur en multi-locuteurs
- `--resume-from-multispeaker-checkpoint` — Transfert multi-locuteurs vers mono-locuteur (active automatiquement `--freeze-dp`)

### Évaluation vocale

Des outils d'évaluation MCD, PESQ et UTMOS sont disponibles dans `scripts/evaluation/`.

---

## Modèles pré-entraînés

Des modèles de synthèse vocale pour l'inférence et le fine-tuning sont disponibles sur Hugging Face.

**Modèles pour l'inférence (prêts à l'emploi) :**

| Modèle | Langues | Locuteurs | Description | Téléchargement |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Voix Tsukuyomi-chan, 6 langues, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japonais 6lang | JA/EN/ZH/ES/FR/PT | 1 | Voix CSS10 japonaise, 6 langues, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Modèle de base Zero-Shot/FT (expérimental) :**

| Modèle | Langues | Locuteurs | Description | Téléchargement |
|---|---|---|---|---|
| Base `zs-v1` Zero-Shot/FT | JA/EN/ZH/ES/FR/PT | 571 | Expérimental, v7 epoch32, 173 phonèmes, embedding locuteur CAM++ de 192 dimensions | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) |

> `base.onnx` nécessite un embedding de référence extrait avec `campplus.onnx` pour le Zero-Shot ; `base.ckpt` sert au fine-tuning et doit être utilisé avec le `config.json` fourni. Les exemples publics ont été vérifiés fonctionnellement avec PyPI `piper-plus==2.0.0`. Le modèle reste expérimental : bruit et limites de transfert de voix ; aucune validation de qualité ou d’écoute humaine. Les alias `base` et `zero-shot-base-zs-v1` ciblent la branche source ou la prochaine release et ne sont pas encore présents dans 2.0.0/2.0.1. Le `model.ckpt` racine reste un fichier legacy distinct.

### Téléchargement des modèles

**Modèle Tsukuyomi-chan :**

> **Tsukuyomi FT (`zs-v1`, 2026-10-15) :** La [version publique épinglée](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1) utilise la même génération de base publique. Utilisez `releases/zs-v1/tsukuyomi.onnx` avec `tsukuyomi.onnx.json` ; cette voix fixe ne nécessite ni audio de référence ni CAM++. La revue humaine a été enregistrée et la publication expérimentale approuvée ; `quality_approval=false`. Les téléchargements `resolve/main` ci-dessous sont conservés uniquement comme exemple de compatibilité avec l’artefact root legacy.

**Windows (PowerShell) :**

```powershell
mkdir models
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx" -OutFile models/tsukuyomi.onnx
Invoke-WebRequest -Uri "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json" -OutFile models/config.json
```

**macOS / Linux :**

```bash
mkdir -p models
curl -L -o models/tsukuyomi.onnx https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx
curl -L -o models/config.json https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json
```

### Caractéristiques du modèle de base 6 langues (entraînement)

- `zs-v1` : base expérimentale Zero-Shot/FT de v7 epoch32
- Langues : JA/EN/ZH/ES/FR/PT ; 571 locuteurs
- Taux d'échantillonnage : 22 050 Hz ; 173 phonèmes
- Conditionnement locuteur : embedding CAM++ de 192 dimensions
- Le Zero-Shot nécessite un embedding de référence ; le fine-tuning utilise `base.ckpt` et le `config.json` correspondant

> **Note :** piper-plus intègre des extensions architecturales propres et reste incompatible avec les checkpoints/modèles ONNX de Piper upstream. Utilisez le `config.json` fourni avec le modèle choisi ; le `model.ckpt` racine est un fichier legacy distinct.

---

## TTS japonais

Synthèse vocale japonaise de haute qualité avec intégration OpenJTalk. Le dictionnaire et les fichiers vocaux sont téléchargés automatiquement lors de la première exécution.

**Variables d'environnement (optionnelles) :**

| Variable | Description |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | Chemin du dictionnaire OpenJTalk (téléchargement auto si non défini) |
| `PIPER_PLUS_AUTO_DOWNLOAD_DICT` | `0` pour désactiver le téléchargement automatique |
| `PIPER_PLUS_OFFLINE_MODE` | `1` pour le mode hors ligne |

Voir le Guide d'utilisation japonais et la [Référence de mappage phonémique](docs/api-reference/phoneme-mapping.md).

---

## Plateformes

### macOS

**Apple Silicon (M1/M2/M3+) uniquement.** Les utilisateurs d'Intel Mac doivent utiliser Docker ou construire depuis les sources.

Pour les avertissements de sécurité lors de la première exécution :

```bash
xattr -cr piper/
```

### Windows

Les artefacts C++ publiés sont x64 ; le CLI C# fournit aussi x64 / arm64. Le dictionnaire OpenJTalk est téléchargé automatiquement au premier lancement. Voir le [Guide d'installation Windows](docs/getting-started/windows-setup.md).

```cmd
piper-plus.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

TTS japonais fonctionnant directement dans le navigateur. Sans serveur, compatible hors ligne.

- **[Démo en ligne](https://ayutaz.github.io/piper-plus/)**
- **[Détails techniques et guide d'intégration](src/wasm/openjtalk-web/README.npm.md)**

---

## Liens associés

### Unity — uPiper

Plugin Unity pour Piper : [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japonais et anglais, API asynchrone, streaming

### piper-plus-g2p (Package G2P autonome)

G2P multilingue (Grapheme-to-Phoneme) disponible en packages autonomes :

- **Python** : `pip install piper-plus-g2p` — [Source](src/python/g2p/)
- **Rust** : `cargo add piper-plus-g2p` — [Source](src/rust/piper-plus-g2p/)
- **Go** : `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Source](src/go/phonemize/)
- **JavaScript/WASM** : `npm install @piper-plus/g2p` — [Source](src/wasm/g2p/)

### Modèles vocaux (Voices)

Modèles piper-plus : [base Zero-Shot/FT `zs-v1`](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note :** piper-plus utilise son propre système G2P et de phonèmes, les modèles Piper upstream (rhasspy/piper-voices) ne sont donc PAS compatibles.

### Articles (en japonais)

- [Créer un modèle Piper pré-entraîné en anglais avec LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Créer un modèle Piper japonais avec le dataset JVS](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Fine-tuning depuis un modèle Piper avec le dataset Tsukuyomi-chan](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Catégorie | Liens |
|---|---|
| TTS japonais | Guide d'utilisation japonais |
| Entraînement | [Guide d'entraînement](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Mappage phonémique](docs/api-reference/phoneme-mapping.md) · [Variables d'environnement](docs/getting-started/environment-variables.md) |
| Fonctionnalités | [WebUI](docs/features/webui.md) · CLI amélioré · Streaming · Phoneme Timing · SSML |
| Configuration | Démarrage rapide (japonais) · [Windows](docs/getting-started/windows-setup.md) · [Dépannage](docs/getting-started/troubleshooting.md) |
| Docker | [Environnements Docker](docker/README.md) |
| WebAssembly | [Détails techniques](src/wasm/openjtalk-web/README.npm.md) |

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les directives.

## Journal des modifications

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique des versions.
