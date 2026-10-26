![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | Português | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Pacotes:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 O único fork do Piper sob licença MIT** — O projeto original [rhasspy/piper](https://github.com/rhasspy/piper) foi arquivado em outubro de 2025 e o [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) migrou para a licença GPL-3.0. O piper-plus é o único fork compatível com MIT sem dependência do espeak-ng. Seu G2P próprio oferece suporte a 8 idiomas (JA/EN/ZH/KO/ES/FR/PT/SV), tornando-o adequado para uso comercial e embarcado.

> **📢 v2.0.0 Mudanças incompatíveis:** As imagens Docker padrão usam CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (driver NVIDIA do host **R570+** obrigatório). O treinamento usa torch **2.11.0** + CUDA 12.8, com TF32 + bf16-mixed por padrão. Não há suporte para retomar checkpoints gerados com torch 2.2. O import Python e a CLI passaram a ser `piper_plus` / `piper-plus`. Para atualizar da 1.13.0 para a versão pública atual, execute `pip install --upgrade "piper-plus[cpu]==2.0.2"`. Detalhes: [guia de migração](docs/migration/v1.12-to-v2.0.md).

Sistema neural de texto para fala (TTS) rápido e de alta qualidade. Utiliza a arquitetura [VITS](https://github.com/jaywalnut310/vits/) e oferece G2P/fonemização em 8 idiomas e síntese com vários falantes nos modelos treinados atuais em 6 idiomas. Fork do [Piper](https://github.com/rhasspy/piper), com melhorias significativas no suporte ao japonês, na qualidade de voz e nas funcionalidades de treinamento.

**[Demo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (funciona no navegador, sem servidor)

---

## Sumário

- [Benchmark](#benchmark)
- [Funcionalidades Principais](#funcionalidades-principais)
- [Início Rápido](#início-rápido)
- [Instalação](#instalação)
- [Uso](#uso)
- [Treinamento](#treinamento-1)
- [Modelos Pré-treinados](#modelos-pré-treinados)
- [Plataformas](#plataformas)
- [Links Relacionados](#links-relacionados)

---

## Benchmark

> **Ambiente de medição**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 núcleos / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Texto de teste**: "Hello, how are you doing today?" (inglês, 25 fonemas)
> **Parâmetros de medição**: 5 execuções de aquecimento / 30 execuções medidas (intra-op threads = auto)
> **Modelos utilizados**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (decodificador unificado introduzido no PR #320)
> - Piper original: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (release k2-fsa)
>
> **Reprodução**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| Sistema | RTF ↓ | Latency P50 (ms) | Tamanho (MB) | RAM (MB) | Inicialização (ms) | Parâmetros | Idiomas | Licença |
|---------|-------|------------------|-----------|---------|-------------|----------|--------|----------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (arquivado) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/modelo | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/modelo | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/modelo | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Nota**: RTF (Real-Time Factor) — quanto menor, mais rápido. `Latency P50` é a mediana de uma inferência única e mede diretamente a "responsividade real". Com o decodificador unificado MB-iSTFT, o piper-plus alcança a menor Latency P50, de 27 ms (-23% em relação aos 35 ms do Piper original e -49% em relação aos 53 ms do sherpa-onnx), com um modelo de apenas 38 MB, entre os menores. Em comparação com a versão anterior do piper-plus baseada em HiFi-GAN (P50 de 43,3 ms), a melhoria é de -38%.
>
> As linhas marcadas com **†** não foram medidas novamente neste PR (`piper1-gpl` usa a mesma arquitetura e o mesmo formato ONNX do Piper original, portanto deve ficar próximo da linha do Piper original; `Kokoro-82M` tem outra arquitetura e `eSpeak-NG` é uma CLI não neural, de modo que nenhum dos dois se encaixa no contrato de tensores do `scripts/benchmark.py` e exigiriam um harness separado). Esses valores são da medição anterior (Apple M2 Max).

### Benchmark RTF multi-runtime (valores mais recentes)

Publicamos os resultados mais recentes de RTF e latência medidos em 6 runtimes (Python / Rust / Go / C# / C++ / WASM) com `multilingual-test-medium.onnx`. Os valores são atualizados automaticamente a cada merge na branch dev.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Funcionalidades Principais

### Síntese de Voz

- **G2P/fonemização em 8 idiomas** — Japonês, inglês, chinês, espanhol, francês, português, sueco e coreano (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Os modelos treinados atuais cobrem 6 idiomas (JA/EN/ZH/ES/FR/PT)
- **TTS em japonês** — Integração com OpenJTalk, informações prosódicas (A1/A2/A3), marcadores de interrogação (#204), variantes contextuais de "ん" (#207)
- **TTS em inglês** — A v2.0.2 inclui G2P baseado em [g2p-en](https://github.com/Kyubyong/g2p), com código de inferência Apache-2.0 e o aviso de licença MIT do Tacotron. Não são necessários `g2p-en` / `Distance` externos nem espeak-ng. As definições de dependência do antigo PyPI 2.0.1 permanecem inalteradas. Consulte o [guia de migração](docs/migration/python-g2p-license.md)
- **Multi-falante** — 571 falantes (modelo base para treinamento), SpeakerBalancedBatchSampler, amostragem balanceada por grupo linguístico
- **Dicionário personalizado** — Dicionário de pronúncia integrado com mais de 200 termos técnicos
- **Entrada de fonemas** — Especificação direta com a notação `[[ phonemes ]]` — [Guia](docs/features/phoneme-input.md)

### Treinamento

- **WavLM Discriminator** — Melhoria de MOS de +0,15 a 0,25 (habilitado por padrão, usado apenas no treinamento)
- **Decodificador MB-iSTFT-VITS2** — Decodificador unificado em MB-iSTFT + PQMF, inferência em CPU 2,21x mais rápida. O formato ONNX não muda e é compatível com os runtimes existentes
- **BF16 Mixed Precision** — `--precision bf16-mixed` é o padrão (TF32 também habilitado por padrão). Numericamente mais estável que FP16 e dispensa loss scaling. Em GPUs sem suporte a BF16 (como a T4), especifique `--precision 16-mixed`
- **EMA** — Maior estabilidade de treinamento com Exponential Moving Average (habilitado por padrão)
- **Multi-GPU** — Suporte a DDP, escalonamento automático da taxa de aprendizado
- **Prosody Features** — Injeção de informações prosódicas no Duration Predictor (`--prosody-dim 16`)
- **Integração com Wandb** — Monitoramento de métricas em tempo real

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Suporte a inferência e a Docker. A aba de treinamento local ainda envia argumentos CLI obsoletos; para treinar, use o [guia de treinamento](docs/guides/training/training-guide.md).
- **C++ CLI** — Streaming, inferência CUDA, **saída de temporização de fonemas (JSON/TSV/SRT)**, dicionário personalizado
- **[Biblioteca compartilhada C API](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatível com FFI (Flutter/Godot/Swift etc.), API de streaming
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), motor de síntese distribuído como xcframework universal para dispositivo iOS arm64 + simulador
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — Biblioteca independente `PiperPlusG2P`, permite usar o G2P de 8 idiomas no iOS sem depender do ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Funciona inteiramente no navegador, **saída de temporização de fonemas (JSON/TSV/SRT)**, sem servidor
- **[Docker](docker/README.md)** — 6 imagens: inferência, treinamento, WebUI, C++ (inferência/desenvolvimento) e Wyoming (Home Assistant)
- **PyPI** — Instalação simples com `pip install piper-plus`, G2P/fonemização em 8 idiomas (modelos treinados atuais: 6 idiomas), **saída de temporização de fonemas (JSON/TSV/SRT)**, streaming, HTTP API
- **C# CLI** — .NET 10 multiplataforma, G2P/fonemização em 8 idiomas (modelos treinados atuais: 6 idiomas), inferência ONNX, **saída de temporização de fonemas (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, suporte a CUDA/CoreML/DirectML, **saída de temporização de fonemas (JSON/TSV/SRT)**, download automático de dicionário
- **[Go CLI](src/go/README.md)** — Servidor HTTP API, pool de sessões, suporte a Docker, binário único, **saída de temporização de fonemas (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — Os 6 runtimes (Python/Rust/C#/Go/WASM/C++) aceitam entrada `speaker_embedding` pré-computada e compatível com o modelo. A CLI e a C API do C++ aceitam apenas embeddings pré-computados; a extração via `--reference-audio` não está implementada. A inferência real do `zs-v1` público só foi verificada com Python `piper-plus==2.0.0`. O CI público run `38189966578` confirmou a inferência nos 6 runtimes usando os phoneme IDs compartilhados do Python como entrada; o G2P nativo e a qualidade de escuta humana ficaram fora do escopo, e não houve aprovação de qualidade.
- **Suporte a SSML** — O contrato do parser SSML está implementado em Python/Rust/Go/C#/WASM/C++. No lado da síntese, há suporte em Python/Rust/Go/WASM/C++; o C# Core tem o parser, mas ele ainda não está conectado ao `--text` da CLI. O C++ funciona pela CLI `--ssml` (não exportado pela C API).
- **Melhoria de qualidade para textos curtos (Strategy A/B/C)** — As Strategy A/B estão implementadas em cada runtime. A Strategy C (injeção automática de SSML `<break>`) abrange Python de inferência/Rust/Go/C#; Python de treinamento, WASM e C++ ficam fora do escopo. Detalhes no [contrato de textos curtos](docs/spec/short-text-contract.toml).

### Suporte a funcionalidades por runtime

Os 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++) oferecem síntese nos 6 idiomas dos modelos treinados atuais, além de G2P/fonemização em 8 idiomas. Temporização de fonemas, streaming (incluindo divisão por frases), Voice Cloning com embeddings pré-computados compatíveis com o modelo e dicionários personalizados são suportados como funcionalidades de runtime. O C++ aceita apenas embeddings pré-computados, e `--reference-audio` não está implementado. A inferência real do `zs-v1` público só foi verificada com Python `piper-plus==2.0.0`. O CI público run `38189966578` confirma a inferência nos 6 runtimes com phoneme IDs compartilhados do Python, mas o G2P nativo e a qualidade de escuta humana ficaram fora do escopo, e não houve aprovação de qualidade. A síntese SSML é suportada em Python/Rust/Go/WASM/C++ (no C++ pela CLI `--ssml`, não exportado pela C API). O parser do C# Core não está conectado ao `--text` da CLI, e a HTTP API é suportada em 2 runtimes (Python/Go).

---

## Início Rápido

### Binários pré-compilados (sem necessidade de compilação)

Baixe os binários pré-compilados em [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) e comece a sintetizar voz imediatamente.

**1. Baixe o binário**

Baixe e extraia o arquivo correspondente ao seu sistema operacional.

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

**Compatibilidade ARM64:** O pacote C++ Linux ARM64 da v2.0.2 é verificado com glibc 2.31 como limite de ABI. A inicialização e a síntese em japonês são verificadas no Debian Bullseye / Bookworm / Trixie (64 bits) sob QEMU. O hardware Raspberry Pi e o próprio Raspberry Pi OS não foram verificados. O pacote antigo da v2.0.1 exige glibc 2.38 ou superior; use a v2.0.2.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, ARM de 32 bits):**

Para ARMv7, apenas a C++ CLI é distribuída. O CI verifica a compilação e a síntese em japonês no Debian Trixie (ARM de 32 bits) sob QEMU. O hardware Raspberry Pi não foi verificado.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Baixe um modelo e gere a voz**

```sh
# Baixar o modelo Tsukuyomi-chan
./bin/piper-plus --download-model tsukuyomi

# Gerar audio (basta o nome do modelo; modelos ja baixados sao resolvidos automaticamente)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Sobre a página de código do Windows cmd:** A opção `--text` usa internamente `GetCommandLineW()` (UTF-16), portanto funciona independentemente da página de código. Somente ao usar entrada por pipe (`echo ... | piper-plus`) é preciso mudar antes para UTF-8 com `chcp 65001`.
>
> **Local do output.wav:** O arquivo é gerado no diretório atual (onde você executou `cd piper-plus`).

> **Qual binário devo escolher?** Além do `piper-plus-cpp-*` (C++), as Releases incluem as CLIs `piper-plus-cli-*` (C# .NET) e `piper-plus-rs-cli-*` (Rust). A **C++ CLI (`piper-plus-cpp-*`)** usada no Início Rápido acima é a que suporta mais plataformas e é a recomendada. Detalhes em [Como escolher o binário da CLI](docs/getting-started/binary-selection.md).

### Inferência Python

```bash
# Instalacao
# Execute a partir da raiz do repositorio (source checkout)
uv sync --extra inference

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

Principais opções: `--speaker-id` (ID do falante), `--device auto|cpu|gpu`, `--noise-scale` (variação da voz), `--length-scale` (velocidade da fala), `--noise-scale-w` (variação da duração dos fonemas, padrão: 0.5)

> **Configuração recomendada para modelos WavLM:** Modelos treinados com o WavLM Discriminator (como Tsukuyomi-chan) atingem a melhor qualidade com `--noise-scale 0.5` (o padrão é 0.4).

#### Gerenciamento de modelos Python CLI

```bash
# Listar modelos
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# Baixar modelos
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Usar apos o download
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

# Inferencia Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device cpu

# Inferencia em GPU (adicione --gpus all)
docker run --rm --gpus all \
    -v ./models:/app/models:ro -v ./output:/app/output \
    piper-inference \
    python -m piper_train.infer_onnx \
        --model /app/models/model.onnx --config /app/models/config.json \
        --output-dir /app/output --text "こんにちは" --device gpu
```

Imagens pré-construídas pelo CI/CD:

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

Recomenda-se Python 3.13+ (3.11+ é suportado). Para gerenciar dependências, recomenda-se o [uv](https://docs.astral.sh/uv/).

```bash
# Inferencia em CPU
uv sync --extra inference

# Inferencia em GPU (requer ambiente CUDA)
uv sync --no-group cpu --extra inference-gpu

# Treinamento
uv sync --extra train

# Desenvolvimento (inclui testes e linters)
uv sync --extra dev
```

Também é possível instalar a partir do pacote PyPI:

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

Se você usa uma plataforma para a qual não há binários pré-compilados ou quer modificar o piper-plus, é possível compilá-lo a partir do código-fonte. Para os procedimentos de compilação de cada runtime (C++ / C# / Rust), consulte o **[guia de compilação a partir do código-fonte](docs/guides/development/building-from-source.md)**.

---

## Uso

Para as opções detalhadas de linha de comando da C++ CLI, o formato de entrada JSON, o gerenciamento de modelos, as variáveis de ambiente e o uso dos scripts auxiliares do Windows, consulte o **[guia de uso da CLI](docs/guides/development/cli-usage.md)**.

Exemplo simples:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Treinamento

Para treinar e fazer fine-tuning de modelos piper-plus (configuração básica, multi-falante / multi-GPU, conversão para ONNX, gerenciamento de checkpoints e avaliação de áudio), consulte o **[guia de treinamento](docs/guides/training/training-guide.md)**.

Os templates de comando para uso em produção, como o pré-treinamento em 6 idiomas e o fine-tuning da Tsukuyomi-chan, estão em [CLAUDE.md](CLAUDE.md).

---

## Modelos Pré-treinados

Para a lista de modelos piper-plus publicados, como baixá-los, as características do modelo base de 6 idiomas e os detalhes do TTS em japonês, consulte o **[guia de modelos](docs/guides/development/pretrained-models.md)**.

Modelos principais: `tsukuyomi` (japonês), `zs-v1` (base experimental Zero-Shot/FT em 6 idiomas), `bilingual-ja-en-v4` (japonês e inglês). Para detalhes, consulte o [bundle público fixado zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) e [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) no HuggingFace.

> **Base Zero-Shot/FT (`zs-v1`, 2026-10-10):** O bundle público fixado é a base experimental existente da v7 epoch 32 (JA/EN/ZH/ES/FR/PT, 571 falantes, 173 fonemas, CAM++ de 192 dimensões). Para inferência Zero-Shot, use `base.onnx` com um embedding de referência extraído pelo `campplus.onnx` incluído; para treinamento adicional, use `base.ckpt` com o `config.json` incluído. O funcionamento foi verificado com os exemplos públicos do PyPI `piper-plus==2.0.0`, mas isso não significa aprovação de qualidade, aprovação em teste de escuta humana nem que seja o modelo mais recente ou de melhor qualidade. Os aliases `base` / `zero-shot-base-zs-v1` estão incluídos na v2.0.2 (ausentes na 2.0.0 / 2.0.1). O `model.ckpt` na raiz é tratado separadamente, como geração antiga.

> **Fine-tuning da Tsukuyomi-chan (`zs-v1`, 2026-10-15):** Publicamos um [modelo público fixado](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1) treinado a partir da mesma geração de base pública. Combinando `tsukuyomi.onnx` e `tsukuyomi.onnx.json`, é possível gerar voz sem áudio de referência nem CAM++. A verificação humana de 3 frases em japonês foi registrada e a publicação como versão experimental foi aprovada (quality_approval=false, ou seja, não há aprovação de qualidade). O alias `tsukuyomi` existente continua selecionando o modelo antigo da raiz; para obter o novo modelo, use as URLs fixadas no [guia de modelos](docs/guides/development/pretrained-models.md).

---

## Plataformas

- **macOS**: Suporte nativo a Apple Silicon (arm64). Detalhes em [configuração do macOS](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません)
- **Windows**: Os pacotes C++ são x64; a C# CLI é x64 / arm64. Para configurar o OpenJTalk, consulte o [guia de configuração do Windows](docs/getting-started/windows-setup.md)
- **WebAssembly**: Execução totalmente offline no navegador. [Demo](https://ayutaz.github.io/piper-plus/) | [Pacote npm](https://www.npmjs.com/package/piper-plus)

---

## Links Relacionados

### Unity — uPiper

Plugin para usar o Piper no Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Suporte a Windows / macOS (Apple Silicon) / Linux / Android
- Japonês e inglês, API assíncrona, streaming

### Modelos de voz (Voices)

Modelos exclusivos do piper-plus: [base Zero-Shot/FT zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Nota:** O piper-plus usa seu próprio G2P e sistema de fonemas, portanto não é compatível com os modelos do Piper upstream (rhasspy/piper-voices).

### Artigos relacionados

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (pacote G2P independente)

G2P (Grapheme-to-Phoneme) multilíngue disponível como pacote independente:

- **Python**: `pip install piper-plus-g2p` — [Código-fonte](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Código-fonte](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Código-fonte](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Código-fonte](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [Código-fonte](android/piper-plus-g2p/) · [Guia de distribuição do dicionário](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentação

| Categoria | Links |
|---|---|
| TTS em japonês | Guia de síntese de voz em japonês |
| Treinamento | [Guia de treinamento](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Mapeamento de fonemas](docs/api-reference/phoneme-mapping.md) · [Variáveis de ambiente](docs/getting-started/environment-variables.md) |
| Funcionalidades | [WebUI](docs/features/webui.md) · Melhorias da CLI · Streaming |
| Configuração | Início rápido (japonês) · [Windows](docs/getting-started/windows-setup.md) · [Solução de problemas](docs/getting-started/troubleshooting.md) |
| Docker | [Ambiente Docker](docker/README.md) |
| WebAssembly | [Detalhes técnicos](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Consulte [CONTRIBUTING.md](CONTRIBUTING.md). Envie dúvidas e relatos de bugs em [Issues](https://github.com/ayutaz/piper-plus/issues). O código de conduta está em [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Changelog

Consulte [CHANGELOG.md](CHANGELOG.md).

## Agradecimentos

Os experimentos do piper-plus que usam GPU contam com o apoio do AI Builder Grant (créditos de GPU) da [CloudRift](https://www.cloudrift.ai/).
