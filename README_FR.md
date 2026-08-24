![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | Français | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Paquets :**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 Le seul fork de Piper sous licence MIT** — Le projet original [rhasspy/piper](https://github.com/rhasspy/piper) a été archivé en octobre 2025 et [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) est passé sous licence GPL-3.0. piper-plus est le seul fork compatible MIT sans dépendance à espeak-ng. Son G2P maison prend en charge 8 langues (JA/EN/ZH/KO/ES/FR/PT/SV), ce qui le rend adapté à un usage commercial et embarqué.

> **📢 v2.0.0 Changements incompatibles (2026-05, en préparation sur `dev` — dernier tag publié : v1.13.0) :** Images Docker par défaut unifiées vers CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (pilote NVIDIA hôte **R570+** requis ; les pilotes plus anciens ne peuvent pas démarrer les nouvelles images) / entraînement mis à jour vers torch 2.11+cu128 (les checkpoints produits avec torch 2.2 ne peuvent plus être repris) / TF32 + bf16-mixed sont les nouvelles valeurs par défaut de l'entraînement. Détails : [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

Système de synthèse vocale neuronale (TTS) rapide et de haute qualité. Basé sur l'architecture [VITS](https://github.com/jaywalnut310/vits/), il prend en charge la synthèse vocale multi-locuteurs en 8 langues (japonais, anglais, chinois mandarin, coréen, espagnol, français, portugais, suédois). Fork de [Piper](https://github.com/rhasspy/piper) avec un support japonais, une qualité audio et des fonctionnalités d'entraînement considérablement améliorés.

**[Démo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Démo WebAssembly](https://ayutaz.github.io/piper-plus/)** (fonctionne dans le navigateur, sans serveur)

---

## Table des matières

- [Benchmark](#benchmark)
- [Fonctionnalités principales](#fonctionnalités-principales)
- [Démarrage rapide](#démarrage-rapide)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Entraînement](#entraînement)
- [Modèles pré-entraînés](#modèles-pré-entraînés)
- [Plateformes](#plateformes)
- [Liens associés](#liens-associés)

---

## Benchmark

> **Environnement de mesure** : Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cœurs / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Texte de test** : "Hello, how are you doing today?" (anglais, 25 phonèmes)
> **Paramètres de mesure** : 5 itérations de warmup + 30 itérations mesurées (intra-op threads = auto)
> **Modèles utilisés** :
>
> - piper-plus : 6lang MB-iSTFT 75epoch ONNX (décodeur unifié introduit dans la PR #320)
> - Piper original : `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx : `vits-piper-en_US-amy-low` (release k2-fsa)
>
> **Reproduction** : `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| Système | RTF ↓ | Latence P50 (ms) | Taille (MB) | RAM (MB) | Démarrage à froid (ms) | Paramètres | Langues | Licence |
|---------|-------|------------------|-------------|----------|------------------------|------------|---------|---------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (archivé) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/modèle | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/modèle | Apache-2.0 |
| piper1-gpl (fork OHF) † | 0.06 | — | 75 | 150 | 400 | — | 1/modèle | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Note** : RTF (Real-Time Factor) — plus la valeur est basse, plus la synthèse est rapide. `Latence P50` est la médiane du temps d'une inférence unitaire et mesure directement la réactivité réelle. Grâce au décodeur unifié MB-iSTFT, piper-plus obtient la latence P50 la plus faible (27 ms ; -23 % vs Piper original à 35 ms, -49 % vs sherpa-onnx à 53 ms), avec une taille de modèle parmi les plus compactes (38 MB). C'est également une amélioration de -38 % par rapport à l'ancienne base piper-plus HiFi-GAN (P50 43.3 ms).
>
> **†** Les lignes marquées † n'ont pas été re-mesurées dans cette PR (`piper1-gpl` partage l'architecture et le format ONNX du Piper original, et devrait donc être quasi équivalent à la ligne Piper original ; `Kokoro-82M` utilise une architecture différente et `eSpeak-NG` est un CLI non neuronal — ni l'un ni l'autre ne rentre dans le contrat de tenseurs supposé par `scripts/benchmark.py`, un harnais séparé serait nécessaire). Ces valeurs proviennent de la mesure précédente (Apple M2 Max).

### Benchmark RTF multi-runtime (dernières valeurs)

Les derniers résultats RTF / latence mesurés sur les 6 runtimes Python / Rust / Go / C# / C++ / WASM avec `multilingual-test-medium.onnx` sont publiés, et mis à jour automatiquement à chaque merge dans la branche dev.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Fonctionnalités principales

### Synthèse vocale

- **8 langues** — japonais, anglais, chinois mandarin, espagnol, français, portugais (bascule de dialecte BR/EU : `pt`/`pt-BR`/`pt-PT`), suédois, coréen (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *Le modèle entraîné couvre 6 langues (JA/EN/ZH/ES/FR/PT)*
- **TTS japonais** — intégration OpenJTalk, caractéristiques prosodiques (A1/A2/A3), marqueurs interrogatifs (#204), variantes contextuelles du « N » (#207)
- **TTS anglais** — G2P sans GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), pas de dépendance à espeak-ng
- **Multi-locuteurs** — 571 locuteurs (modèle de base pour l'entraînement), SpeakerBalancedBatchSampler, échantillonnage équilibré par groupe de langues
- **Dictionnaire personnalisé** — ajout de dictionnaires de prononciation utilisateur au format JSON (v1/v2) / TSV
- **Saisie phonémique** — spécification directe avec la notation `[[ phonemes ]]` — [Guide](docs/features/phoneme-input.md)

### Entraînement

- **WavLM Discriminator** — amélioration MOS +0.15-0.25 (activé par défaut, uniquement à l'entraînement)
- **Décodeur MB-iSTFT-VITS2** — décodeur unifié MB-iSTFT + PQMF, inférence CPU 2,21x plus rapide. Format ONNX inchangé, compatible avec les runtimes existants
- **BF16 Mixed Precision** — `--precision bf16-mixed` (par défaut) + TF32 pour un entraînement plus rapide, ~50 % de mémoire en moins
- **EMA** — moyenne mobile exponentielle pour la stabilité de l'entraînement (activé par défaut)
- **Multi-GPU** — support DDP, mise à l'échelle automatique du taux d'apprentissage
- **Caractéristiques prosodiques** — injection de prosodie dans le Duration Predictor (`--prosody-dim 16`)
- **Intégration Wandb** — surveillance des métriques en temps réel

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — inférence et entraînement, compatible Docker
- **CLI C++** — streaming, inférence CUDA, **sortie de timing phonémique (JSON/TSV/SRT)**, dictionnaire personnalisé
- **[Bibliothèque partagée C API](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatible FFI (Flutter/Godot/Swift, etc.), API de streaming
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), moteur de synthèse distribué en xcframework universel iOS arm64 (device + simulateur)
- **[G2P Swift iOS (SPM)](docs/guides/platform/swift-g2p-integration.md)** — bibliothèque autonome `PiperPlusG2P` : G2P 8 langues sur iOS sans ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — fonctionne entièrement dans le navigateur, **sortie de timing phonémique (JSON/TSV/SRT)**, sans serveur
- **[Docker](docker/README.md)** — 7 familles d'images : inférence, entraînement, WebUI, C++, Wyoming (Home Assistant), etc.
- **PyPI** — installation simple via `pip install piper-plus`, multilingue 8 langues, **sortie de timing phonémique (JSON/TSV/SRT)**, streaming, API HTTP
- **CLI C#** — .NET 10 multiplateforme, multilingue 8 langues, inférence ONNX, **sortie de timing phonémique (JSON/TSV/SRT)**
- **CLI Rust** — piper-plus/piper-plus-cli, streaming, support CUDA/CoreML/DirectML, **sortie de timing phonémique (JSON/TSV/SRT)**, téléchargement automatique des dictionnaires
- **[CLI Go](src/go/README.md)** — serveur API HTTP, pooling de sessions, Docker, binaire unique, **sortie de timing phonémique (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — pris en charge par les 6 runtimes (Python/Rust/C#/Go/WASM/C++). Pour C++, disponible à la fois via le binaire CLI et la bibliothèque C API `libpiper_plus`. Extraction de l'embedding de locuteur depuis un audio de référence via ECAPA-TDNN (`--reference-audio`)
- **Support SSML** — `<speak>`, `<break>`, `<prosody rate="...">` implémentés dans les 6 runtimes Python/Rust/C#/Go/WASM/C++ (C++ via le CLI `--ssml`)
- **Amélioration de la qualité des textes courts (Stratégie A/B/C)** — Silence Padding, Dynamic Scales et injection automatique de SSML `<break>` dans les 6 runtimes (`docs/spec/short-text-contract.toml`)

### Support des fonctionnalités par runtime

Les 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++) offrent une synthèse multilingue 8 langues équivalente. Le timing phonémique, le streaming (avec division par phrases), le Voice Cloning et les dictionnaires personnalisés sont disponibles sur tous les runtimes. SSML est pris en charge par les 6 runtimes (C++ via le CLI `--ssml`, non exporté dans la C API), et l'API HTTP par les 2 runtimes Python/Go.

---

## Démarrage rapide

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

### Inférence Python

```bash
# Installation
uv pip install ".[inference]"

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

Options principales : `--speaker-id` (ID de locuteur), `--device auto|cpu|gpu`, `--noise-scale` (variation audio), `--length-scale` (vitesse de parole), `--noise-scale-w` (variation de durée des phonèmes, défaut : 0.5)

> **Réglage recommandé pour les modèles WavLM :** Les modèles entraînés avec WavLM Discriminator (comme Tsukuyomi-chan) offrent une qualité optimale avec `--noise-scale 0.5` (défaut : 0.4).

#### Gestion des modèles (CLI Python)

```bash
# Lister les modeles disponibles
python -m piper_plus --list-models
python -m piper_plus --list-models ja

# Telecharger un modele
python -m piper_plus --download-model tsukuyomi
python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Utiliser apres telechargement
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
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

Voir [docker/README.md](docker/README.md) pour plus de détails.

---

## Installation

### Python

Python 3.13+ recommandé (3.11+ supporté). [uv](https://docs.astral.sh/uv/) est recommandé pour la gestion des dépendances.

```bash
# Inference CPU
uv pip install ".[inference]"

# Inference GPU (necessite CUDA)
uv pip install ".[inference-gpu]"

# Entrainement
uv pip install ".[train]"

# Developpement (inclut tests et linting)
uv pip install ".[dev]"
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

**npm (navigateur WASM) :**

```bash
npm install piper-plus onnxruntime-web
```

**CLI C# (outil global .NET) :**

```bash
dotnet tool install -g PiperPlus.Cli
```

**CLI Rust (crates.io) :**

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

### Compilation depuis les sources

Si aucun binaire pré-compilé n'est disponible pour votre plateforme, ou si vous souhaitez modifier piper-plus, vous pouvez compiler depuis les sources. Les instructions de compilation des runtimes C++ / C# / Rust se trouvent dans le **[Guide de compilation depuis les sources](docs/guides/development/building-from-source.md)**.

---

## Utilisation

Pour le détail des options en ligne de commande du CLI C++, le format d'entrée JSON, la gestion des modèles, les variables d'environnement et les scripts d'aide Windows, voir le **[Guide d'utilisation du CLI](docs/guides/development/cli-usage.md)**.

Exemple simple :

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Entraînement

Pour l'entraînement et le fine-tuning des modèles piper-plus (configuration de base, multi-locuteurs / multi-GPU, export ONNX, gestion des checkpoints, évaluation vocale), voir le **[Guide d'entraînement](docs/guides/training/training-guide.md)**.

Les modèles de commandes pour un usage en production (pré-entraînement 6 langues, fine-tuning Tsukuyomi-chan) se trouvent dans [CLAUDE.md](CLAUDE.md).

---

## Modèles pré-entraînés

Pour la liste des modèles piper-plus publiés, les instructions de téléchargement, les caractéristiques du modèle de base 6 langues et les détails du TTS japonais, voir le **[Guide des modèles](docs/guides/development/pretrained-models.md)**.

Modèles principaux : `tsukuyomi` (japonais) et `css10-6lang` (récupérables via `--download-model`), ainsi que le checkpoint de base 6 langues (pour l'entraînement / le fine-tuning) — voir sur HuggingFace [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) et [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

---

## Plateformes

- **macOS** : support natif Apple Silicon (arm64). Voir la [configuration macOS](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません) pour plus de détails
- **Windows** : x64 / arm64 pris en charge. Pour la configuration d'OpenJTalk, voir le [Guide d'installation Windows](docs/getting-started/windows-setup.md)
- **WebAssembly** : exécution entièrement hors ligne dans le navigateur. [Démo](https://ayutaz.github.io/piper-plus/) | [Paquet npm](https://www.npmjs.com/package/piper-plus)

---

## Liens associés

### Unity — uPiper

Plugin Unity pour Piper : [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2)
- 7 langues (ja/en/zh/es/fr/pt/ko), API asynchrone, streaming

### Modèles vocaux (Voices)

Modèles spécifiques à piper-plus : [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (base 6 langues) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note :** piper-plus utilise son propre système G2P et de phonèmes, les modèles Piper upstream (rhasspy/piper-voices) ne sont donc PAS compatibles.

### Articles associés (en japonais)

- [Créer un modèle Piper pré-entraîné en anglais avec LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Créer un modèle Piper japonais avec le dataset JVS](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Fine-tuning depuis un modèle Piper avec le dataset Tsukuyomi-chan](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (paquet G2P autonome)

G2P multilingue (Grapheme-to-Phoneme) disponible en paquets autonomes :

- **Python** : `pip install piper-plus-g2p` — [Code source](src/python/g2p/)
- **Rust** : `cargo add piper-plus-g2p` — [Code source](src/rust/piper-plus-g2p/)
- **Go** : `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Code source](src/go/phonemize/)
- **JavaScript/WASM** : `npm install @piper-plus/g2p` — [Code source](src/wasm/g2p/)
- **Kotlin/Android** : `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` — [Code source](android/piper-plus-g2p/) · [Guide de distribution du dictionnaire](docs/guides/platform/android-g2p-dictionary.md)
- **Swift (iOS/macOS)** : produit SPM `PiperPlusG2P` — [Guide d'intégration](docs/guides/platform/swift-g2p-integration.md) · [Code source](Sources/PiperPlusG2P/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Catégorie | Liens |
|---|---|
| Entraînement | [Guide d'entraînement](docs/guides/training/training-guide.md) (multi-GPU inclus) |
| API | [Mappage phonémique](docs/api-reference/phoneme-mapping.md) · [Variables d'environnement](docs/getting-started/environment-variables.md) |
| Fonctionnalités | [WebUI](docs/features/webui.md) · [Timing phonémique](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| Configuration | [Windows](docs/getting-started/windows-setup.md) · [Dépannage](docs/getting-started/troubleshooting.md) |
| Docker | [Environnements Docker](docker/README.md) |
| WebAssembly | [Détails techniques](src/wasm/openjtalk-web/README.npm.md) |

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les directives. Pour les questions et les rapports de bug, ouvrez une [Issue](https://github.com/ayutaz/piper-plus/issues). Le code de conduite est décrit dans [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Journal des modifications

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique des versions.
