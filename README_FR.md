![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | Français | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Paquets :**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 Le seul fork de Piper sous licence MIT** — Le projet original [rhasspy/piper](https://github.com/rhasspy/piper) a été archivé en octobre 2025 et [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) est passé sous licence GPL-3.0. piper-plus est le seul fork compatible MIT sans dépendance à espeak-ng. Son G2P maison prend en charge 8 langues (JA/EN/ZH/KO/ES/FR/PT/SV), ce qui le rend adapté à un usage commercial et embarqué.

> **📢 v2.0.0 Changements incompatibles :** L'image Docker par défaut utilise CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (pilote NVIDIA hôte **R570+** requis). L'entraînement utilise torch **2.11.0** + CUDA 12.8, avec TF32 + bf16-mixed par défaut. La reprise des checkpoints produits avec torch 2.2 n'est pas prise en charge. L'import Python et la CLI deviennent `piper_plus` / `piper-plus`. Pour passer de 1.13.0 à la version publique actuelle, exécutez `pip install --upgrade "piper-plus[cpu]==2.0.2"`. Détails : [guide de migration](docs/migration/v1.12-to-v2.0.md).

Système de synthèse vocale neuronale (TTS) rapide et de haute qualité. Basé sur l'architecture [VITS](https://github.com/jaywalnut310/vits/), il fournit un G2P/une phonémisation en 8 langues et une synthèse multi-locuteurs avec les modèles entraînés actuels en 6 langues. Fork de [Piper](https://github.com/rhasspy/piper) avec un support du japonais, une qualité audio et des fonctionnalités d'entraînement considérablement améliorés.

**[Démo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Démo WebAssembly](https://ayutaz.github.io/piper-plus/)** (fonctionne dans le navigateur, sans serveur)

---

## Table des matières

- [Benchmark](#benchmark)
- [Fonctionnalités principales](#fonctionnalités-principales)
- [Démarrage rapide](#démarrage-rapide)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Entraînement](#entraînement-1)
- [Modèles pré-entraînés](#modèles-pré-entraînés)
- [Plateformes](#plateformes)
- [Liens associés](#liens-associés)

---

## Benchmark

> **Environnement de mesure** : Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cœurs / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Phrase de test** : "Hello, how are you doing today?" (anglais, 25 phonèmes)
> **Paramètres de mesure** : 5 itérations d'échauffement / 30 itérations mesurées (intra-op threads = auto)
> **Modèles utilisés** :
>
> - piper-plus : ONNX 6lang MB-iSTFT 75 epochs (décodeur unifié introduit dans la PR #320)
> - Piper original : `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx : `vits-piper-en_US-amy-low` (release k2-fsa)
>
> **Reproduction** : `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| Système | RTF ↓ | Latency P50 (ms) | Taille (MB) | RAM (MB) | Premier démarrage (ms) | Paramètres | Langues | Licence |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (archivé) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/modèle | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/modèle | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/modèle | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Note** : plus le RTF (Real-Time Factor) est bas, plus la synthèse est rapide. `Latency P50` est la médiane d'une inférence unique et mesure directement la réactivité réelle. Grâce au décodeur unifié MB-iSTFT, piper-plus atteint la latence P50 la plus faible avec 27 ms (-23 % par rapport aux 35 ms de Piper original, -49 % par rapport aux 53 ms de sherpa-onnx), tout en ayant l'un des plus petits modèles (38 MB). Par rapport à l'ancien piper-plus basé sur HiFi-GAN (P50 43,3 ms), l'amélioration est de -38 %.
>
> **†** Les lignes marquées n'ont pas été remesurées dans cette PR (`piper1-gpl` partage l'architecture et le format ONNX de Piper original et devrait donc être quasi équivalent à la ligne Piper original ; `Kokoro-82M` a une architecture différente et `eSpeak-NG` est une CLI non neuronale, qui ne respectent pas le contrat de tenseurs de `scripts/benchmark.py` et nécessitent un autre banc de mesure). Ces valeurs proviennent de la mesure précédente (Apple M2 Max).

### Benchmark RTF multi-runtime (dernières valeurs)

Les derniers résultats RTF et de latence, mesurés de manière transversale sur les 6 runtimes Python / Rust / Go / C# / C++ / WASM avec `multilingual-test-medium.onnx`, sont publiés. Ils sont mis à jour automatiquement à chaque fusion dans la branche dev.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Fonctionnalités principales

### Synthèse vocale

- **G2P/phonémisation en 8 langues** — Japonais, anglais, chinois, espagnol, français, portugais, suédois, coréen (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Les modèles entraînés actuels couvrent 6 langues (JA/EN/ZH/ES/FR/PT)
- **TTS japonais** — Intégration OpenJTalk, informations prosodiques (A1/A2/A3), marqueurs interrogatifs (#204), variantes contextuelles du « ん » (#207)
- **TTS anglais** — v2.0.2 inclut un G2P dérivé de [g2p-en](https://github.com/Kyubyong/g2p), avec le code d'inférence sous Apache-2.0 et la notice de licence MIT de Tacotron. Aucune dépendance externe à `g2p-en` / `Distance` ni à espeak-ng n'est nécessaire. Les métadonnées de dépendances de l'ancienne version PyPI 2.0.1 restent inchangées. Voir le [guide de migration](docs/migration/python-g2p-license.md)
- **Multi-locuteurs** — 571 locuteurs (modèle de base pour l'entraînement), SpeakerBalancedBatchSampler, échantillonnage équilibré par groupe de langues
- **Dictionnaire personnalisé** — Dictionnaire de prononciation intégré de plus de 200 termes techniques
- **Saisie phonémique** — Spécification directe avec la notation `[[ phonemes ]]` — [Guide](docs/features/phoneme-input.md)

### Entraînement

- **WavLM Discriminator** — Amélioration du MOS de +0,15 à 0,25 (activé par défaut, utilisé uniquement à l'entraînement)
- **Décodeur MB-iSTFT-VITS2** — Décodeur unifié en MB-iSTFT + PQMF, inférence CPU 2,21x plus rapide. Format ONNX inchangé, compatible avec les runtimes existants
- **BF16 Mixed Precision** — `--precision bf16-mixed` par défaut (TF32 également activé par défaut). Numériquement plus stable que FP16, sans besoin de loss scaling. Sur les GPU sans prise en charge de BF16 (T4, etc.), indiquez `--precision 16-mixed`
- **EMA** — Exponential Moving Average pour une meilleure stabilité de l'entraînement (activé par défaut)
- **Multi-GPU** — Prise en charge de DDP, mise à l'échelle automatique du taux d'apprentissage
- **Prosody Features** — Injection d'informations prosodiques dans le Duration Predictor (`--prosody-dim 16`)
- **Intégration Wandb** — Suivi des métriques en temps réel

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inférence et prise en charge de Docker. L'onglet Training local envoie encore d'anciens arguments CLI ; pour l'entraînement, utilisez le [guide d'entraînement](docs/guides/training/training-guide.md).
- **CLI C++** — Streaming, inférence CUDA, **sortie Phoneme Timing (JSON/TSV/SRT)**, dictionnaire personnalisé
- **[Bibliothèque partagée C API](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatible FFI (Flutter/Godot/Swift, etc.), API de streaming
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), moteur de synthèse distribué en binaire universel iOS arm64 device + simulator
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — Bibliothèque autonome `PiperPlusG2P`, G2P en 8 langues utilisable sur iOS sans dépendance à ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Fonctionne entièrement dans le navigateur, **sortie Phoneme Timing (JSON/TSV/SRT)**, sans serveur
- **[Docker](docker/README.md)** — 6 images : inférence, entraînement, WebUI, C++ (inférence/développement) et Wyoming (Home Assistant)
- **PyPI** — Installation simple avec `pip install piper-plus`, G2P/phonémisation en 8 langues (modèles entraînés actuels : 6 langues), **sortie Phoneme Timing (JSON/TSV/SRT)**, streaming, API HTTP
- **CLI C#** — .NET 10 multiplateforme, G2P/phonémisation en 8 langues (modèles entraînés actuels : 6 langues), inférence ONNX, **sortie Phoneme Timing (JSON/TSV/SRT)**
- **CLI Rust** — piper-plus/piper-plus-cli, streaming, prise en charge CUDA/CoreML/DirectML, **sortie Phoneme Timing (JSON/TSV/SRT)**, téléchargement automatique des dictionnaires
- **[CLI Go](src/go/README.md)** — Serveur d'API HTTP, pooling de sessions, prise en charge de Docker, binaire unique, **sortie Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — Les 6 runtimes (Python/Rust/C#/Go/WASM/C++) acceptent une entrée `speaker_embedding` pré-calculée et compatible avec le modèle. La CLI et l'API C++ n'acceptent que des embeddings pré-calculés ; l'extraction via `--reference-audio` n'est pas implémentée. L'inférence réelle avec le `zs-v1` public n'a été vérifiée qu'avec Python `piper-plus==2.0.0`. Le CI public `38189966578` a vérifié l'inférence dans les 6 runtimes à partir des phoneme IDs partagés produits par Python ; le G2P natif et la qualité d'écoute humaine sont hors périmètre, et aucune validation de qualité n'a été effectuée.
- **Prise en charge SSML** — Le contrat du parseur SSML est implémenté en Python/Rust/Go/C#/WASM/C++. Côté synthèse, Python/Rust/Go/WASM/C++ sont pris en charge ; C# Core contient le parseur, mais il n'est pas encore relié à l'option `--text` de la CLI. C++ passe par l'option CLI `--ssml` (non exportée dans l'API C).
- **Amélioration des textes courts (Strategy A/B/C)** — Les stratégies A/B sont implémentées dans chaque runtime. La stratégie C (injection automatique de SSML `<break>`) couvre l'inférence Python/Rust/Go/C# ; le Python d'entraînement, WASM et C++ sont hors périmètre. Détails : [contrat des textes courts](docs/spec/short-text-contract.toml).

### Prise en charge des fonctionnalités par runtime

Les 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++) assurent la synthèse dans les 6 langues des modèles entraînés actuels et fournissent aussi le G2P/la phonémisation en 8 langues. Phoneme Timing, streaming (y compris la division par phrases), Voice Cloning à partir d'embeddings pré-calculés compatibles avec le modèle et dictionnaires personnalisés sont pris en charge en tant que fonctionnalités des runtimes. C++ n'accepte que des embeddings pré-calculés et `--reference-audio` n'est pas implémenté. L'inférence réelle avec le `zs-v1` public n'a été vérifiée qu'avec Python `piper-plus==2.0.0`. Le CI public `38189966578` vérifie l'inférence dans les 6 runtimes à partir des phoneme IDs partagés produits par Python, mais le G2P natif et la qualité d'écoute humaine sont hors périmètre, et aucune validation de qualité n'a été effectuée. La synthèse SSML est prise en charge par Python/Rust/Go/WASM/C++ (C++ via l'option CLI `--ssml`, non exportée dans l'API C). Le parseur de C# Core n'est pas relié à l'option CLI `--text`, et l'API HTTP est prise en charge par 2 runtimes (Python/Go).

---

## Démarrage rapide

### Binaires précompilés (aucune compilation requise)

Téléchargez les binaires précompilés depuis [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) et commencez immédiatement la synthèse vocale.

**1. Télécharger le binaire**

Téléchargez et extrayez l'archive correspondant à votre système d'exploitation.

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

**Compatibilité ARM64 :** l'archive C++ Linux ARM64 v2.0.2 est contrôlée avec glibc 2.31 comme plafond ABI. Le démarrage et la synthèse japonaise sont vérifiés sous QEMU avec Debian Bullseye / Bookworm / Trixie (64 bits). Le matériel Raspberry Pi et Raspberry Pi OS lui-même ne sont pas testés. L'ancienne archive v2.0.1 nécessite glibc 2.38 ou plus récent ; utilisez donc v2.0.2.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, ARM 32 bits) :**

Pour ARMv7, seule la CLI C++ est distribuée. La CI vérifie la compilation et la synthèse japonaise sous QEMU avec Debian Trixie (ARM 32 bits). Le matériel Raspberry Pi n'est pas testé.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Télécharger un modèle et générer de l'audio**

```sh
# Telecharger le modele Tsukuyomi-chan
./bin/piper-plus --download-model tsukuyomi

# Generer l'audio (le nom du modele suffit : les modeles telecharges sont resolus automatiquement)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Page de code de Windows cmd :** l'option `--text` utilise `GetCommandLineW()` (UTF-16) en interne et fonctionne donc quelle que soit la page de code. Seule l'entrée par pipe (`echo ... | piper-plus`) nécessite de passer d'abord en UTF-8 avec `chcp 65001`.
>
> **Emplacement de output.wav :** le fichier est créé dans le répertoire courant (celui où vous avez exécuté `cd piper-plus`).

> **Quel binaire choisir ?** Outre `piper-plus-cpp-*` (C++), les Releases contiennent aussi les CLI `piper-plus-cli-*` (C# .NET) et `piper-plus-rs-cli-*` (Rust). La **CLI C++ (`piper-plus-cpp-*`)** utilisée dans le démarrage rapide ci-dessus prend en charge le plus grand nombre de plateformes et est recommandée. Voir [Choisir un binaire CLI](docs/getting-started/binary-selection.md) pour plus de détails.

### Inférence Python

```bash
# Installation
# Executer depuis la racine du depot (source checkout)
uv sync --extra inference

# Inference en japonais
uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --config /path/to/config.json \
    --output-dir ./output \
    --text "こんにちは、今日は良い天気ですね。"

# Inference en anglais
uv run python -m piper_train.infer_onnx \
    --model /path/to/en_model.onnx \
    --config /path/to/en_model.onnx.json \
    --output-dir ./output \
    --text "Hello, how are you today?" \
    --language en
```

Options principales : `--speaker-id` (ID du locuteur), `--device auto|cpu|gpu`, `--noise-scale` (variation de la voix), `--length-scale` (débit de parole), `--noise-scale-w` (variation de la durée des phonèmes, défaut : 0.5)

> **Réglage recommandé pour les modèles WavLM :** les modèles entraînés avec WavLM Discriminator (Tsukuyomi-chan, etc.) offrent la meilleure qualité avec `--noise-scale 0.5` (défaut : 0.4).

#### Gestion des modèles avec la CLI Python

```bash
# Lister les modeles
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# Telecharger un modele
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Utiliser le modele apres telechargement
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

Images précompilées par la CI/CD :

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

Python 3.13+ recommandé (3.11+ pris en charge). [uv](https://docs.astral.sh/uv/) est recommandé pour la gestion des dépendances.

```bash
# Inference CPU
uv sync --extra inference

# Inference GPU (environnement CUDA requis)
uv sync --no-group cpu --extra inference-gpu

# Entrainement
uv sync --extra train

# Developpement (tests et linters inclus)
uv sync --extra dev
```

Installation également possible depuis le paquet PyPI :

```bash
pip install piper-plus
```

### Installation depuis les gestionnaires de paquets

**Python (PyPI) :**

```bash
pip install piper-plus
```

**npm (WASM pour navigateur) :**

```bash
npm install piper-plus onnxruntime-web
```

**CLI C# (.NET Global Tool) :**

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

Si vous utilisez une plateforme pour laquelle aucun binaire précompilé n'est fourni, ou si vous souhaitez modifier piper-plus, vous pouvez compiler depuis les sources. Les instructions de compilation des runtimes C++ / C# / Rust se trouvent dans le **[guide de compilation depuis les sources](docs/guides/development/building-from-source.md)**.

---

## Utilisation

Les options détaillées de la CLI C++, le format d'entrée JSON, la gestion des modèles, les variables d'environnement et l'utilisation des scripts d'aide Windows sont décrits dans le **[guide d'utilisation de la CLI](docs/guides/development/cli-usage.md)**.

Exemple simple :

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Entraînement

Pour entraîner et affiner (fine-tuning) des modèles piper-plus (configuration de base, multi-locuteurs / multi-GPU, conversion ONNX, gestion des checkpoints, évaluation vocale), consultez le **[guide d'entraînement](docs/guides/training/training-guide.md)**.

Les modèles de commandes pour le pré-entraînement en 6 langues et le fine-tuning de Tsukuyomi-chan utilisés en pratique se trouvent dans [CLAUDE.md](CLAUDE.md).

---

## Modèles pré-entraînés

La liste des modèles piper-plus publiés, les méthodes de téléchargement, les caractéristiques du modèle de base en 6 langues et les détails du TTS japonais sont décrits dans le **[guide des modèles](docs/guides/development/pretrained-models.md)**.

Modèles principaux : `tsukuyomi` (japonais), `zs-v1` (base expérimentale Zero-Shot/FT en 6 langues), `bilingual-ja-en-v4` (bilingue japonais-anglais) — pour plus de détails, voir le [bundle public épinglé zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) et [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) sur Hugging Face.

> **Base Zero-Shot/FT (`zs-v1`, 2026-10-10) :** le bundle public épinglé est la version de référence expérimentale existante issue de v7 epoch 32 (JA/EN/ZH/ES/FR/PT, 571 locuteurs, 173 phonèmes, CAM++ 192 dimensions). Pour l'inférence Zero-Shot, utilisez `base.onnx` avec un embedding de référence extrait par le `campplus.onnx` fourni ; pour l'entraînement complémentaire, utilisez `base.ckpt` avec le `config.json` fourni. Le fonctionnement a été vérifié avec les exemples publics de PyPI `piper-plus==2.0.0`, mais cela ne signifie ni validation de qualité, ni réussite d'une écoute humaine, ni qualité la plus récente ou la meilleure. Les alias `base` / `zero-shot-base-zs-v1` sont inclus dans v2.0.2 (absents de 2.0.0 / 2.0.1). Le `model.ckpt` à la racine est traité séparément comme une génération legacy.

> **Fine-tuning Tsukuyomi-chan (`zs-v1`, 2026-10-15) :** un [modèle public épinglé](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1), affiné à partir de la même génération de base publique, est disponible. En combinant `tsukuyomi.onnx` et `tsukuyomi.onnx.json`, vous pouvez générer de l'audio sans audio de référence ni CAM++. Une vérification humaine sur 3 phrases japonaises a été enregistrée et la publication en tant que version expérimentale a été approuvée (quality_approval=false ; il ne s'agit pas d'une validation de qualité). L'alias `tsukuyomi` existant sélectionne toujours l'ancien modèle racine ; récupérez donc le nouveau modèle depuis l'URL épinglée indiquée dans le [guide des modèles](docs/guides/development/pretrained-models.md).

---

## Plateformes

- **macOS** : prise en charge native d'Apple Silicon (arm64). Voir la [configuration macOS](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません) pour plus de détails
- **Windows** : les artefacts C++ sont en x64 ; la CLI C# est disponible en x64 / arm64. Pour la configuration d'OpenJTalk, voir le [guide d'installation Windows](docs/getting-started/windows-setup.md)
- **WebAssembly** : exécution entièrement hors ligne dans le navigateur. [Démo](https://ayutaz.github.io/piper-plus/) | [Paquet npm](https://www.npmjs.com/package/piper-plus)

---

## Liens associés

### Unity — uPiper

Plugin pour utiliser Piper dans Unity : [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Prise en charge de Windows / macOS (Apple Silicon) / Linux / Android
- Japonais et anglais, API asynchrone, streaming

### Modèles vocaux (Voices)

Modèles dédiés à piper-plus : [base Zero-Shot/FT zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note :** piper-plus utilise son propre G2P et son propre système de phonèmes ; il n'est donc pas compatible avec les modèles de Piper upstream (rhasspy/piper-voices).

### Articles (en japonais)

- [Créer un modèle Piper anglais pré-entraîné avec LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Créer un modèle Piper japonais avec le jeu de données JVS](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Entraînement complémentaire d'un modèle Piper avec le jeu de données Tsukuyomi-chan](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (paquet G2P autonome)

Le G2P (Grapheme-to-Phoneme) multilingue est fourni sous forme de paquets autonomes :

- **Python** : `pip install piper-plus-g2p` — [code source](src/python/g2p/)
- **Rust** : `cargo add piper-plus-g2p` — [code source](src/rust/piper-plus-g2p/)
- **Go** : `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [code source](src/go/phonemize/)
- **JavaScript/WASM** : `npm install @piper-plus/g2p` — [code source](src/wasm/g2p/)
- **Kotlin/Android** : `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [code source](android/piper-plus-g2p/) · [guide de distribution des dictionnaires](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Catégorie | Liens |
|---|---|
| TTS japonais | Guide de synthèse vocale japonaise |
| Entraînement | [Guide d'entraînement](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Mappage des phonèmes](docs/api-reference/phoneme-mapping.md) · [Variables d'environnement](docs/getting-started/environment-variables.md) |
| Fonctionnalités | [WebUI](docs/features/webui.md) · CLI améliorée · Streaming |
| Configuration | Démarrage rapide (japonais) · [Windows](docs/getting-started/windows-setup.md) · [Dépannage](docs/getting-started/troubleshooting.md) |
| Docker | [Environnements Docker](docker/README.md) |
| WebAssembly | [Détails techniques](src/wasm/openjtalk-web/README.npm.md) |

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md). Pour les questions et les rapports de bugs, utilisez les [Issues](https://github.com/ayutaz/piper-plus/issues). Le code de conduite se trouve dans [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Journal des modifications

Voir [CHANGELOG.md](CHANGELOG.md).

## Remerciements

Les expériences de piper-plus utilisant des GPU bénéficient du soutien de l'AI Builder Grant (crédits GPU) de [CloudRift](https://www.cloudrift.ai/).
