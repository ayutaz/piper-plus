![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | Français

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

Systeme de synthese vocale neuronale (TTS) rapide et de haute qualite. Base sur l'architecture [VITS](https://github.com/jaywalnut310/vits/), il prend en charge la synthese vocale multi-locuteurs en 6 langues (japonais, anglais, chinois mandarin, espagnol, francais, portugais). Fork de [Piper](https://github.com/rhasspy/piper) avec un support japonais, une qualite audio et des fonctionnalites d'entrainement considerablement ameliores.

**[Demo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (fonctionne dans le navigateur, sans serveur)

---

## Table des matieres

- [Fonctionnalites principales](#fonctionnalites-principales)
- [Demarrage rapide](#demarrage-rapide)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Entrainement](#entrainement)
- [Modeles pre-entraines](#modeles-pre-entraines)
- [TTS japonais](#tts-japonais)
- [Plateformes](#plateformes)
- [Liens associes](#liens-associes)

---

## Fonctionnalites principales

### Synthese vocale

- **TTS japonais** — Integration OpenJTalk, caracteristiques prosodiques (A1/A2/A3), marqueurs interrogatifs (#204), variantes contextuelles du "N" (#207)
- **TTS anglais** — G2P sans GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), pas de dependance a espeak-ng
- **Multilingue 6 langues** — Japonais, anglais, chinois mandarin, espagnol, francais, portugais (ja=0, en=1, zh=2, es=3, fr=4, pt=5)
- **Multi-locuteurs** — 571 locuteurs dans le modele de base 6 langues, SpeakerBalancedBatchSampler
- **Dictionnaire personnalise** — 200+ termes techniques integres — [Guide](docs/features/custom_dictionary.md)
- **Saisie phonemique** — Specification directe avec la notation `[[ phonemes ]]` — [Guide](docs/features/phoneme-input.md)

### Entrainement

- **WavLM Discriminator** — Amelioration MOS +0.15-0.25 (active par defaut, uniquement a l'entrainement)
- **FP16 Mixed Precision** — Entrainement 2-3x plus rapide, ~50% de memoire en moins (active par defaut)
- **EMA** — Moyenne mobile exponentielle pour la stabilite (active par defaut)
- **Multi-GPU** — Support DDP, mise a l'echelle automatique du taux d'apprentissage
- **Caracteristiques prosodiques** — Injection de prosodie dans le Duration Predictor (`--prosody-dim 16`)
- **Integration Wandb** — Surveillance des metriques en temps reel

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inference et entrainement, compatible Docker
- **CLI C++** — Streaming, inference CUDA, sortie de timing phonemique, dictionnaire personnalise
- **[WebAssembly](src/wasm/openjtalk-web/README.md)** — Fonctionne entierement dans le navigateur, sans serveur
- **[Docker](docker/README.md)** — 5 images pour l'inference, l'entrainement, WebUI et C++
- **PyPI** — `pip install piper-tts-plus`

### Plateformes

| Plateforme | Architecture | Notes |
|---|---|---|
| Linux | x86_64 / ARM64 | Support complet |
| macOS | ARM64 (Apple Silicon) uniquement | M1/M2/M3+ |
| Windows | x64 | Support complet |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |

---

## Demarrage rapide

### Inference Python

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

Options principales : `--speaker-id` (ID locuteur), `--device auto|cpu|gpu`, `--noise-scale` (variation audio), `--length-scale` (vitesse)

### WebUI

```bash
uv pip install -r src/python_run/requirements_webui.txt
cd src/python_run
python -m piper.webui --data-dir /path/to/models
# → http://localhost:7860
```

### Binaire C++

Telecharger depuis [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) (amd64 / arm64).

```sh
echo 'Welcome to the world of speech synthesis!' | \
  ./piper --model en_US-lessac-medium.onnx --output_file welcome.wav
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

Images pre-construites CI/CD :

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main
docker pull ghcr.io/ayutaz/piper-plus/python-train:main
docker pull ghcr.io/ayutaz/piper-plus/webui:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

Voir [docker/README.md](docker/README.md) pour plus de details.

---

## Installation

### Python

Python 3.11+ requis. [uv](https://docs.astral.sh/uv/) est recommande pour la gestion des dependances.

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

Egalement disponible sur PyPI :

```bash
pip install piper-tts-plus
```

### Construction depuis les sources (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Prerequis : compilateur C++17, CMake 3.13+

- **Linux** : placer [piper-phonemize](https://github.com/rhasspy/piper-phonemize) dans `lib/Linux-$(uname -m)/piper_phonemize` avant la construction
- **Windows** : voir le [Guide d'installation Windows](docs/getting-started/windows-setup.md)
- **macOS** : les dependances sont telechargees automatiquement

---

## Utilisation

### CLI C++

```sh
# Utilisation de base
echo "こんにちは" | ./piper --model ja_model.onnx --output_file output.wav

# Streaming (faible latence)
echo "Texte long..." | ./piper --model ja_model.onnx --output_file output.wav --streaming

# Inference GPU
echo "Hello" | ./piper --model en_model.onnx --use-cuda --output_file output.wav

# Sortie de timing phonemique (pour lip-sync, sous-titres)
echo "Hello world" | ./piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Dictionnaire personnalise
echo "DockerとGitHubを使います" | ./piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Saisie phonemique en ligne
echo 'Hello [[ h ə l oʊ ]] world' | ./piper --model en_model.onnx -f output.wav

# Saisie de phonemes bruts
echo 'h ə l oʊ _ w ɜː l d' | ./piper --model en_model.onnx --raw-phonemes -f output.wav
```

Options principales :

| Option | Description | Defaut |
|---|---|---|
| `--streaming` | Mode streaming par morceaux | off |
| `--use-cuda` | Activer l'inference GPU CUDA | off |
| `--gpu-device-id NUM` | ID du peripherique GPU | 0 |
| `--length-scale VAL` | Vitesse de parole (plus petit = plus rapide) | 1.0 |
| `--noise-scale VAL` | Controle de la variation audio | 0.667 |
| `--noise-w VAL` | Variation de la duree des phonemes | 0.8 |
| `--sentence-silence SEC` | Silence entre les phrases | 0.2 |
| `--speaker NUM` | Numero de locuteur pour les modeles multi-locuteurs | 0 |
| `--phoneme-silence PHONEME SEC` | Duree de silence pour des phonemes specifiques | - |
| `--raw-phonemes` | Interpreter l'entree comme des phonemes | off |
| `--output-timing FILE` | Sortie de timing phonemique (JSON/TSV) | - |
| `--custom-dict FILE` | Dictionnaire personnalise (plusieurs avec virgule) | - |
| `--json-input` | Mode d'entree JSON | off |

Executez `piper --help` pour toutes les options.

### Entree JSON

Utilisez le drapeau `--json-input` pour l'entree JSON :

```json
{ "text": "Premier locuteur.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second locuteur.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

---

## Entrainement

Voir le [Guide d'entrainement](docs/guides/training/training-guide.md) pour les instructions detaillees.

### Basique

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

Le multi-GPU configure automatiquement le DDP (Distributed Data Parallel). Les variables d'environnement NCCL sont requises. Voir le [Guide multi-GPU](docs/guides/training/multi-gpu-training.md).

### Export ONNX

La conversion FP16 est appliquee par defaut, reduisant la taille du modele d'environ 50%. Utilisez `--no-fp16` pour desactiver.

```bash
# Modele standard (FP16 par defaut)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Modele sans FP16
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# Modele WavLM (--stochastic requis)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Gestion des checkpoints

- `--resume_from_checkpoint` — Reprendre l'entrainement depuis un checkpoint
- `--resume_from_single_speaker_checkpoint` — Convertir un modele mono-locuteur en multi-locuteurs
- `--resume-from-multispeaker-checkpoint` — Transfert multi-locuteurs vers mono-locuteur (active automatiquement `--freeze-dp`)

### Evaluation vocale

Des outils d'evaluation MCD, PESQ et UTMOS sont disponibles dans `scripts/evaluation/`.

---

## Modeles pre-entraines

Des modeles de base pour le fine-tuning TTS japonais sont disponibles sur Hugging Face.

| Modele | Description | Licence |
|---|---|---|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | Modele de base 6 langues (571 locuteurs, 508 187 enonces, 173 symboles) | CC-BY-SA-4.0 |
| [piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | Modele fine-tune Tsukuyomi-chan 6 langues (FP16) | Voir la fiche modele |
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | Modele de base TTS japonais (VITS + WavLM + Prosody, 20 locuteurs) | CC-BY-SA-4.0 |

**Caracteristiques du modele de base 6 langues :**

- Architecture : VITS + WavLM Discriminator + Prosody
- Donnees d'entrainement : 508 187 enonces (571 locuteurs, 6 langues)
- Langues : ja (20 locuteurs), en (310 locuteurs), zh (142 locuteurs), es (63 locuteurs), fr (28 locuteurs), pt (8 locuteurs)
- Codes de langue : ja=0, en=1, zh=2, es=3, fr=4, pt=5
- Taux d'echantillonnage : 22 050 Hz
- Symboles : 173 phonemes
- Entrainement : 75 epochs, ~282K gradient steps, ~92 heures (4x V100)
- Caracteristiques prosodiques : informations prosodiques A1/A2/A3
- Phonemes etendus : marqueurs interrogatifs, variantes contextuelles du "N"

Les checkpoints Piper upstream sont egalement disponibles : [piper-checkpoints](https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main)

---

## TTS japonais

Synthese vocale japonaise de haute qualite avec integration OpenJTalk. Le dictionnaire et les fichiers vocaux sont telecharges automatiquement lors de la premiere execution.

**Variables d'environnement (optionnelles) :**

| Variable | Description |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | Chemin du dictionnaire OpenJTalk (telechargement auto si non defini) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` pour desactiver le telechargement automatique |
| `PIPER_OFFLINE_MODE` | `1` pour le mode hors ligne |

Voir le [Guide d'utilisation japonais](docs/guides/japanese/japanese-usage.md) et la [Reference de mappage phonemique](docs/api-reference/phoneme-mapping.md).

---

## Plateformes

### macOS

**Apple Silicon (M1/M2/M3+) uniquement.** Les utilisateurs d'Intel Mac doivent utiliser Docker ou construire depuis les sources.

Pour les avertissements de securite lors de la premiere execution :

```bash
xattr -cr piper/
```

### Windows

Le repertoire espeak-ng-data est requis. Voir le [Guide d'installation Windows](docs/getting-started/windows-setup.md).

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

TTS japonais fonctionnant directement dans le navigateur. Sans serveur, compatible hors ligne.

- **[Demo en ligne](https://ayutaz.github.io/piper-plus/)**
- **[Details techniques et guide d'integration](src/wasm/openjtalk-web/README.md)**

---

## Liens associes

### Unity — uPiper

Plugin Unity pour Piper : [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japonais et anglais, API asynchrone, streaming

### Modeles vocaux (Voices)

Les modeles vocaux Piper upstream (30+ langues) sont egalement disponibles : [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

Chaque voix necessite un fichier `.onnx` et un fichier de configuration `.onnx.json`. [Echantillons vocaux](https://rhasspy.github.io/piper-samples) | [Tutoriel video](https://youtu.be/rjq5eZoWWSo)

### Articles (en japonais)

- [Creer un modele Piper pre-entraine en anglais avec LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Creer un modele Piper japonais avec le dataset JVS](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Fine-tuning depuis un modele Piper avec le dataset Tsukuyomi-chan](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://www.nvaccess.org/post/in-process-8th-may-2023/#voices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Categorie | Liens |
|---|---|
| TTS japonais | [Guide d'utilisation japonais](docs/guides/japanese/japanese-usage.md) |
| Entrainement | [Guide d'entrainement](docs/guides/training/training-guide.md) · [Multi-GPU](docs/guides/training/multi-gpu-training.md) |
| API | [Mappage phonemique](docs/api-reference/phoneme-mapping.md) · [Variables d'environnement](docs/getting-started/environment-variables.md) |
| Fonctionnalites | [WebUI](docs/features/webui.md) · [CLI ameliore](docs/features/cli-enhancements.md) · [Streaming](docs/features/streaming-mode.md) |
| Configuration | [Demarrage rapide (japonais)](docs/guides/japanese/japanese-usage.md) · [Windows](docs/getting-started/windows-setup.md) · [Depannage](docs/getting-started/troubleshooting.md) |
| Docker | [Environnements Docker](docker/README.md) |
| WebAssembly | [Details techniques](src/wasm/openjtalk-web/README.md) |

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les directives.

## Journal des modifications

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique des versions.

[![A library from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-library.png)](https://www.openhomefoundation.org/)
