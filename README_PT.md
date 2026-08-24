![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | Português | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Pacotes:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 O único fork do Piper sob licença MIT** — O projeto original [rhasspy/piper](https://github.com/rhasspy/piper) foi arquivado em outubro de 2025 e o [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) migrou para a licença GPL-3.0. O piper-plus é o único fork compatível com MIT sem dependência do espeak-ng. Seu G2P próprio oferece suporte a 8 idiomas (JA/EN/ZH/KO/ES/FR/PT/SV), tornando-o adequado para uso comercial e embarcado.

> **📢 v2.0.0 Mudanças incompatíveis (2026-05, em preparação no branch `dev`; a tag de release mais recente é a v1.13.0):** Imagens Docker padrão unificadas para CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (driver NVIDIA do host **R570+** obrigatório; drivers mais antigos não conseguem iniciar as novas imagens) / treinamento atualizado para torch 2.11+cu128 (checkpoints criados com torch 2.2 não podem mais ser retomados) / TF32 + bf16-mixed são os novos padrões de treinamento. Detalhes: [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md)

Sistema neural de texto para fala (TTS) de alta velocidade e alta qualidade. Utiliza a arquitetura [VITS](https://github.com/jaywalnut310/vits/) e suporta 8 idiomas com multi-falantes: japonês, inglês, chinês, coreano, espanhol, francês, português e sueco. Fork do [Piper](https://github.com/rhasspy/piper), com melhorias significativas no suporte ao japonês, qualidade de voz e funcionalidades de treinamento.

**[Demo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (funciona no navegador, sem servidor)

---

## Sumário

- [Benchmark](#benchmark)
- [Funcionalidades Principais](#funcionalidades-principais)
- [Início Rápido](#início-rápido)
- [Instalação](#instalação)
- [Uso](#uso)
- [Treinamento](#treinamento)
- [Modelos Pré-treinados](#modelos-pré-treinados)
- [Plataformas](#plataformas)
- [Links Relacionados](#links-relacionados)

---

## Benchmark

> **Ambiente de medição**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 núcleos / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Frase de teste**: "Hello, how are you doing today?" (inglês, 25 fonemas)
> **Parâmetros de medição**: 5 execuções de warmup / 30 execuções medidas (intra-op threads = auto)
> **Modelos utilizados**:
>
> - piper-plus: ONNX 6lang MB-iSTFT 75epoch (decodificador unificado introduzido no PR #320)
> - Piper original: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (release do k2-fsa)
>
> **Reprodução**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| Sistema | RTF ↓ | Latência P50 (ms) | Tamanho (MB) | RAM (MB) | Inicialização a frio (ms) | Parâmetros | Idiomas | Licença |
|---------|-------|-------------------|--------------|----------|---------------------------|------------|---------|---------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (arquivado) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/modelo | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/modelo | Apache-2.0 |
| piper1-gpl (fork OHF) † | 0.06 | — | 75 | 150 | 400 | — | 1/modelo | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Nota**: RTF (Real-Time Factor) — quanto menor, mais rápido. `Latência P50` é a mediana de uma inferência única e o indicador mais direto da capacidade de resposta real. Com o decodificador unificado MB-iSTFT, o piper-plus atinge a menor latência P50 (27 ms; -23% vs. os 35 ms do Piper original, -49% vs. os 53 ms do sherpa-onnx), com um dos menores tamanhos de modelo (38 MB). Também é -38% mais rápido que o antigo piper-plus baseado em HiFi-GAN (P50 43.3 ms).
>
> **†** As linhas marcadas com † não foram remedidas neste PR (o `piper1-gpl` compartilha a arquitetura e o formato ONNX com o Piper original, portanto deve ficar aproximadamente equivalente à linha do Piper original; o `Kokoro-82M` usa outra arquitetura e o `eSpeak-NG` é uma CLI não neural, de modo que nenhum dos dois se encaixa no contrato de tensores do `scripts/benchmark.py` — seriam necessários harnesses separados). Esses valores vêm da medição anterior (Apple M2 Max).

### Benchmark RTF multi-runtime (valores mais recentes)

Publicamos os resultados mais recentes de RTF e latência dos 6 runtimes (Python / Rust / Go / C# / C++ / WASM), medidos de forma unificada com o `multilingual-test-medium.onnx`. Os valores são atualizados automaticamente a cada merge no branch dev.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Funcionalidades Principais

### Síntese de Voz

- **Suporte a 8 idiomas** — Japonês, inglês, chinês, espanhol, francês, português, sueco e coreano (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Para o português há alternância de dialeto BR/EU: `pt`/`pt-BR` selecionam o português brasileiro e `pt-PT` o português europeu. *O modelo treinado cobre 6 idiomas (JA/EN/ZH/ES/FR/PT)*
- **TTS em japonês** — Integração com OpenJTalk, informações prosódicas (A1/A2/A3), marcadores de interrogação (#204), variantes contextuais de "ん" (#207)
- **TTS em inglês** — G2P livre de GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), sem necessidade de espeak-ng
- **Multi-falante** — Suporte a 571 falantes (modelo base para treinamento), SpeakerBalancedBatchSampler, amostragem balanceada por grupo linguístico
- **Dicionário personalizado** — Suporte à adição de dicionários de pronúncia do usuário via JSON (v1/v2) / TSV
- **Entrada de fonemas** — Especificação direta com a notação `[[ fonemas ]]` — [Guia](docs/features/phoneme-input.md)

### Treinamento

- **WavLM Discriminator** — Melhoria de MOS +0.15-0.25 (habilitado por padrão, usado apenas durante o treinamento)
- **Decodificador MB-iSTFT-VITS2** — Decodificador unificado em MB-iSTFT + PQMF, inferência em CPU 2.21x mais rápida. Formato ONNX inalterado, compatível com os runtimes existentes
- **BF16 Mixed Precision** — `--precision bf16-mixed` (padrão) + TF32 aceleram o treinamento, com redução de memória de ~50%
- **EMA** — Estabilidade de treinamento com Exponential Moving Average (habilitado por padrão)
- **Multi-GPU** — Suporte a DDP, escalonamento automático da taxa de aprendizado
- **Prosody Features** — Injeção de informações prosódicas no Duration Predictor (`--prosody-dim 16`)
- **Integração Wandb** — Monitoramento de métricas em tempo real

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inferência e treinamento, compatível com Docker
- **C++ CLI** — Streaming, inferência CUDA, **saída de Phoneme Timing (JSON/TSV/SRT)**, dicionário personalizado
- **[Biblioteca compartilhada C API](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatível com FFI (Flutter/Godot/Swift etc.), API de streaming
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package); o motor de síntese é distribuído como xcframework universal para iOS arm64 (device + simulator)
- **[Swift G2P para iOS (SPM)](docs/guides/platform/swift-g2p-integration.md)** — Biblioteca independente `PiperPlusG2P`: G2P de 8 idiomas no iOS sem depender do ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Funciona completamente no navegador, **saída de Phoneme Timing (JSON/TSV/SRT)**, sem servidor
- **[Docker](docker/README.md)** — 7 famílias de imagens: inferência, treinamento, WebUI, C++, Wyoming (Home Assistant) e mais
- **PyPI** — Instalação simples com `pip install piper-plus`, multilíngue com 8 idiomas, **saída de Phoneme Timing (JSON/TSV/SRT)**, streaming, HTTP API
- **C# CLI** — .NET 10 multiplataforma, multilíngue com 8 idiomas, inferência ONNX, **saída de Phoneme Timing (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, suporte a CUDA/CoreML/DirectML, **saída de Phoneme Timing (JSON/TSV/SRT)**, download automático de dicionário
- **[Go CLI](src/go/README.md)** — Servidor HTTP API, pool de sessões, compatível com Docker, binário único, **saída de Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — Disponível em todos os 6 runtimes (Python/Rust/C#/Go/WASM/C++). Em C++, tanto no binário CLI quanto na biblioteca C API `libpiper_plus`. Extração do embedding de falante a partir de um áudio de referência com ECAPA-TDNN (`--reference-audio`)
- **Suporte a SSML** — `<speak>`, `<break>`, `<prosody rate="...">` implementados nos 6 runtimes Python/Rust/C#/Go/WASM/C++ (em C++ via CLI `--ssml`)
- **Melhoria de qualidade para textos curtos (Estratégia A/B/C)** — Silence Padding, Dynamic Scales e injeção automática de SSML `<break>` em todos os 6 runtimes (`docs/spec/short-text-contract.toml`)

### Suporte a funcionalidades por runtime

Síntese multilíngue equivalente em 8 idiomas nos 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++). Phoneme Timing, streaming (incluindo divisão por frases), Voice Cloning e dicionários personalizados estão disponíveis em todos os runtimes. SSML é suportado nos 6 runtimes (em C++ via CLI `--ssml`; não exportado na C API) e a API HTTP em 2 runtimes (Python/Go).

---

## Início Rápido

### Binários pré-compilados (sem necessidade de compilação)

Baixe os binários pré-compilados em [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) e comece a sintetizar voz imediatamente.

**1. Baixar o binário**

Baixe e extraia de acordo com o seu sistema operacional.

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

**2. Baixar o modelo e gerar áudio**

```sh
# Baixar o modelo Tsukuyomi-chan
./bin/piper-plus --download-model tsukuyomi

# Gerar audio (basta o nome do modelo -- modelos baixados sao resolvidos automaticamente)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Sobre o code page do cmd no Windows:** A opção `--text` utiliza `GetCommandLineW()` (UTF-16) internamente, portanto funciona independentemente do code page. Apenas ao usar entrada por pipe (`echo ... | piper-plus`), mude para UTF-8 previamente com `chcp 65001`.
>
> **Destino do output.wav:** O arquivo é gerado no diretório atual (onde foi executado `cd piper-plus`).

> **Qual binário devo escolher?** Além do `piper-plus-cpp-*` (C++), as releases também incluem as CLIs `piper-plus-cli-*` (C# .NET) e `piper-plus-rs-cli-*` (Rust). A **CLI C++ (`piper-plus-cpp-*`)** usada no Início Rápido acima tem o suporte de plataforma mais amplo e é a recomendada. Consulte [Escolhendo um binário CLI](docs/getting-started/binary-selection.md) para mais detalhes.

### Inferência Python

```bash
# Instalacao
uv pip install ".[inference]"

# Inferencia em japones
uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --config /path/to/config.json \
    --output-dir ./output \
    --text "こんにちは、今日は良い天気ですね。"

# Inferencia em ingles
uv run python -m piper_train.infer_onnx \
    --model /path/to/en_model.onnx \
    --config /path/to/en_model.onnx.json \
    --output-dir ./output \
    --text "Hello, how are you today?" \
    --language en
```

Opções principais: `--speaker-id` (ID do falante), `--device auto|cpu|gpu`, `--noise-scale` (variação de voz), `--length-scale` (velocidade da fala), `--noise-scale-w` (variação da duração dos fonemas, padrão: 0.5)

> **Configuração recomendada para modelos WavLM:** Modelos treinados com o WavLM Discriminator (como o da Tsukuyomi-chan) obtêm a melhor qualidade de áudio com `--noise-scale 0.5` (o padrão é 0.4).

#### Gerenciamento de modelos via Python CLI

```bash
# Listar modelos
python -m piper_plus --list-models
python -m piper_plus --list-models ja

# Baixar modelo
python -m piper_plus --download-model tsukuyomi
python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Usar apos o download
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

# Inferencia Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device cpu

# Inferencia GPU (adicionar --gpus all)
docker run --rm --gpus all \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device gpu
```

Imagens pré-compiladas via CI/CD:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

Para mais detalhes, consulte [docker/README.md](docker/README.md).

---

## Instalação

### Python

Python 3.13+ recomendado (3.11+ suportado). Recomenda-se [uv](https://docs.astral.sh/uv/) para o gerenciamento de dependências.

```bash
# Inferencia CPU
uv pip install ".[inference]"

# Inferencia GPU (requer ambiente CUDA)
uv pip install ".[inference-gpu]"

# Treinamento
uv pip install ".[train]"

# Desenvolvimento (inclui testes e linters)
uv pip install ".[dev]"
```

Também disponível via pacote PyPI:

```bash
pip install piper-plus
```

### Instalação via pacotes

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm (WASM para navegador):**

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

**Biblioteca C# (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Biblioteca Rust (crates.io):**

```toml
[dependencies]
piper-plus = "0.5"
```

### Compilação a partir do código-fonte

Se não houver binários pré-compilados para a sua plataforma, ou se você quiser modificar o piper-plus, é possível compilar a partir do código-fonte. Para as instruções de build dos runtimes C++ / C# / Rust, consulte o **[Guia de compilação a partir do código-fonte](docs/guides/development/building-from-source.md)**.

---

## Uso

Para os detalhes das opções de linha de comando da CLI C++, o formato de entrada JSON, o gerenciamento de modelos, as variáveis de ambiente e os scripts auxiliares para Windows, consulte o **[Guia de uso da CLI](docs/guides/development/cli-usage.md)**.

Exemplo simples de uso:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Treinamento

Para treinar e fazer fine-tuning de modelos piper-plus (configuração básica, multi-falante / multi-GPU, conversão ONNX, gerenciamento de checkpoints, avaliação de áudio), consulte o **[Guia de treinamento](docs/guides/training/training-guide.md)**.

Os templates de comando usados em produção para o pré-treinamento em 6 idiomas e para o fine-tuning da Tsukuyomi-chan estão em [CLAUDE.md](CLAUDE.md).

---

## Modelos Pré-treinados

Para a lista dos modelos piper-plus publicados, as instruções de download, as características do modelo base de 6 idiomas e os detalhes do TTS em japonês, consulte o **[Guia de modelos](docs/guides/development/pretrained-models.md)**.

Modelos principais: `tsukuyomi` (japonês) e `css10-6lang` (obteníveis via `--download-model`), além do ckpt base de 6 idiomas (para treinamento / fine-tuning) — consulte no HuggingFace [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) e [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

---

## Plataformas

- **macOS**: Suporte nativo a Apple Silicon (arm64). Detalhes em [Configuração do macOS](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: x64 / arm64 suportados. Para a configuração do OpenJTalk, consulte o [Guia de configuração do Windows](docs/getting-started/windows-setup.md)
- **WebAssembly**: Execução totalmente offline no navegador. [Demo](https://ayutaz.github.io/piper-plus/) | [Pacote npm](https://www.npmjs.com/package/piper-plus)

---

## Links Relacionados

### Unity — uPiper

Plugin para usar o Piper no Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.3.11f1+, Unity.InferenceEngine
- Suporte a Windows / macOS (Apple Silicon) / Linux / Android / iOS / WebGL (WebGPU/WebGL2)
- 7 idiomas (ja/en/zh/es/fr/pt/ko), API assíncrona, streaming

### Modelos de voz (Voices)

Modelos exclusivos do piper-plus: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (base de 6 idiomas) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Nota:** O piper-plus utiliza seu próprio sistema G2P e de fonemas, portanto os modelos do Piper upstream (rhasspy/piper-voices) NÃO são compatíveis.

### Artigos relacionados

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (Pacote G2P independente)

G2P multilíngue (Grapheme-to-Phoneme) disponível como pacotes independentes:

- **Python**: `pip install piper-plus-g2p` — [Código-fonte](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Código-fonte](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Código-fonte](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Código-fonte](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` — [Código-fonte](android/piper-plus-g2p/) · [Guia de distribuição do dicionário](docs/guides/platform/android-g2p-dictionary.md)
- **Swift (iOS/macOS)**: Produto SPM `PiperPlusG2P` — [Guia de integração](docs/guides/platform/swift-g2p-integration.md) · [Código-fonte](Sources/PiperPlusG2P/)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentação

| Categoria | Links |
|---|---|
| Treinamento | [Guia de treinamento](docs/guides/training/training-guide.md) (inclui multi-GPU) |
| API | [Mapeamento de fonemas](docs/api-reference/phoneme-mapping.md) · [Variáveis de ambiente](docs/getting-started/environment-variables.md) |
| Funcionalidades | [WebUI](docs/features/webui.md) · [Phoneme Timing](docs/features/phoneme-timing.md) · [CLI](docs/guides/development/cli-usage.md) |
| Configuração | [Windows](docs/getting-started/windows-setup.md) · [Solução de problemas](docs/getting-started/troubleshooting.md) |
| Docker | [Ambiente Docker](docker/README.md) |
| WebAssembly | [Detalhes técnicos](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Consulte [CONTRIBUTING.md](CONTRIBUTING.md). Perguntas e relatos de bugs são bem-vindos nas [Issues](https://github.com/ayutaz/piper-plus/issues). O código de conduta está em [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Changelog

Consulte [CHANGELOG.md](CHANGELOG.md).
