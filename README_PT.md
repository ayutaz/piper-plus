![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | Português | [Deutsch](README_DE.md) | [Русский](README_RU.md) | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

Sistema neural de texto para fala (TTS) de alta velocidade e alta qualidade. Utiliza a arquitetura [VITS](https://github.com/jaywalnut310/vits/) e suporta 8 idiomas com multi-falantes: japonês, inglês, chinês, coreano, espanhol, francês, português e sueco. Fork do [Piper](https://github.com/rhasspy/piper), com melhorias significativas no suporte ao japonês, qualidade de voz e funcionalidades de treinamento.

**[Demo Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[Demo WebAssembly](https://ayutaz.github.io/piper-plus/)** (funciona no navegador, sem servidor)

---

## Sumario

- [Funcionalidades Principais](#funcionalidades-principais)
- [Inicio Rapido](#inicio-rapido)
- [Modelos Pre-treinados](#modelos-pre-treinados)
- [Instalacao](#instalacao)
- [Uso](#uso)
- [Treinamento](#treinamento)
- [TTS em Japones](#tts-em-japones)
- [Plataformas](#plataformas)
- [Links Relacionados](#links-relacionados)

---

## Funcionalidades Principais

### Sintese de Voz

- **Suporte a 8 idiomas** — Japonês, inglês, chinês, espanhol, francês, português, sueco e coreano (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *O modelo treinado cobre 6 idiomas (JA/EN/ZH/ES/FR/PT)*
- **TTS em japonês** — Integração com OpenJTalk, informações prosódicas (A1/A2/A3), marcadores de interrogação (#204), variantes contextuais de "ん" (#207)
- **TTS em inglês** — G2P livre de GPL ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), sem necessidade de espeak-ng
- **Multi-falante** — Suporte a 571 falantes (modelo base para treinamento), SpeakerBalancedBatchSampler, amostragem balanceada por grupo linguístico
- **Dicionário personalizado** — Dicionário de pronúncia integrado com mais de 200 termos técnicos
- **Entrada de fonemas** — Especificação direta com notação `[[ fonemas ]]` — [Guia](docs/features/phoneme-input.md)

### Treinamento

- **WavLM Discriminator** — Melhoria de MOS +0.15-0.25 (habilitado por padrão, usado apenas durante treinamento)
- **MB-iSTFT-VITS2 (`--mb-istft`)** — Substitui o decodificador HiFi-GAN por MB-iSTFT + PQMF para inferência CPU ~2,21x mais rápida (apenas qualidade medium, compatível com ONNX)
- **FP16 Mixed Precision** — Velocidade de treinamento 2-3x, redução de memória ~50% (habilitado por padrão)
- **EMA** — Estabilidade de treinamento com Exponential Moving Average (habilitado por padrão)
- **Multi-GPU** — Suporte DDP, escalonamento automático da taxa de aprendizado
- **Prosody Features** — Injeção de informações prosódicas no Duration Predictor (`--prosody-dim 16`)
- **Integração Wandb** — Monitoramento de métricas em tempo real

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inferência e treinamento, compatível com Docker
- **C++ CLI** — Streaming, inferência CUDA, **saída de Phoneme Timing (JSON/TSV/SRT)**, dicionário personalizado
- **[C API Biblioteca compartilhada](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, compatível com FFI (Flutter/Godot/Swift etc.), API de streaming
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Funciona completamente no navegador, **saída de Phoneme Timing (JSON/TSV/SRT)**, sem servidor
- **[Docker](docker/README.md)** — 5 imagens disponíveis para inferência, treinamento, WebUI e C++
- **PyPI** — `pip install piper-plus`, 8 idiomas multilíngue, **saída de Phoneme Timing (JSON/TSV/SRT)**, streaming, **HTTP API baseada em FastAPI**
- **C# CLI** — .NET 8/9 multiplataforma, 8 idiomas multilíngue, inferência ONNX, **saída de Phoneme Timing (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, suporte CUDA/CoreML/DirectML, **saída de Phoneme Timing (JSON/TSV/SRT)**, download automático de dicionário
- **[Go CLI](src/go/README.md)** — Servidor HTTP API, pool de sessões, compatível com Docker, binário único, **saída de Phoneme Timing (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — disponível em todos os 6 runtimes (Python/Rust/C#/Go/WASM/C++)
- **Suporte SSML** — `<speak>`, `<break>`, `<prosody rate="...">` disponíveis em 4 runtimes (Python/Rust/C#/Go)
- **Melhoria de qualidade para textos curtos (Estratégia A/B/C)** — Silence Padding, Dynamic Scales e SSML `<break>` automático em todos os 6 runtimes

### Suporte a funcionalidades por runtime

Síntese multilíngue equivalente em 8 idiomas em 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++). Phoneme Timing, streaming (incluindo divisão por frases), Voice Cloning e dicionários personalizados estão disponíveis em todos os runtimes. SSML é suportado em 4 runtimes (Python/Rust/C#/Go) e a API HTTP em 2 runtimes (Python/Go).

### Plataformas

| Plataforma | Arquitetura | Observações |
|---|---|---|
| Linux | x86_64 / ARM64 / ARMv7 | Suporte completo |
| macOS | ARM64 (Apple Silicon) apenas | M1/M2/M3+ |
| Windows | x64 | Suporte completo |
| C API (FFI) | Linux x64/ARM64, macOS ARM64, Windows x64 | Biblioteca compartilhada, Android AAR |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9, Linux/macOS/Windows |
| Rust | x64 | Linux x64, macOS ARM64, Windows x64 |
| Go | x64 | Linux x64, macOS ARM64, Windows x64 |

---

## Inicio Rapido

### Binários pré-compilados (sem necessidade de compilação)

Baixe os binários pré-compilados em [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) e comece a sintetizar voz imediatamente.

**1. Baixar o binário**

Baixe e extraia de acordo com o seu sistema operacional.

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

**2. Baixar o modelo e gerar áudio**

```sh
# Baixar o modelo Tsukuyomi-chan
./bin/piper --download-model tsukuyomi

# Gerar áudio (apenas o nome do modelo é necessário — modelos baixados são resolvidos automaticamente)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Sobre o code page do cmd no Windows:** A opção `--text` utiliza `GetCommandLineW()` (UTF-16) internamente, portanto funciona independentemente do code page. Apenas ao usar entrada por pipe (`echo ... | piper`), mude para UTF-8 previamente com `chcp 65001`.
>
> **Destino do output.wav:** O arquivo é gerado no diretório atual (onde foi executado `cd piper`).

> **Qual binário devo escolher?** As releases também incluem as CLIs `piper-plus-cli-*` (C# .NET) e `piper-plus-rs-cli-*` (Rust). O Início Rápido acima utiliza a **CLI C++ (`piper-*`)**, que tem o suporte de plataforma mais amplo e é recomendada para a maioria dos usuários. Consulte [Escolhendo um binário CLI](docs/getting-started/binary-selection.md) para mais detalhes.

### Inferência Python

```bash
# Instalação
uv pip install ".[inference]"

# Inferência em japonês
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# Inferência em inglês
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

Opções principais: `--speaker-id` (ID do falante), `--device auto|cpu|gpu`, `--noise-scale` (variação de voz), `--noise-scale-w` (variação de comprimento de fonema, padrão: 0.8), `--length-scale` (velocidade da fala)

> **Configuração recomendada para modelos WavLM:** Modelos treinados com WavLM Discriminator (como Tsukuyomi-chan etc.) obtêm qualidade de áudio ideal com `--noise-scale 0.5` (padrão: 0.667).

#### Gerenciamento de modelos Python CLI

```bash
# Listar modelos
python -m piper --list-models
python -m piper --list-models ja

# Baixar modelo
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# Usar após o download
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

# Inferência Python (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# Inferência GPU (adicionar --gpus all)
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
```

> **Nota:** A imagem webui não é construída automaticamente pelo CI. Construa manualmente com: `docker build -t piper-webui -f docker/webui/Dockerfile .`

```bash
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

Para mais detalhes, consulte [docker/README.md](docker/README.md).

---

## Instalacao

### Python

Requer Python 3.11+. Recomenda-se [uv](https://docs.astral.sh/uv/) para gerenciamento de dependências.

```bash
# Inferência CPU
uv pip install ".[inference]"

# Inferência GPU (requer ambiente CUDA)
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
piper-plus = "0.2.0"
```

### Compilação a partir do código-fonte (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Pré-requisitos: Compilador com suporte a C++17, CMake 3.15+

- **Linux**: As dependências (ONNX Runtime, OpenJTalk, etc.) são baixadas automaticamente pelo CMake
- **Windows**: Consulte o [Guia de configuração do Windows](docs/getting-started/windows-setup.md)
- **macOS**: Dependências são baixadas automaticamente

### Compilação a partir do código-fonte (C#)

```bash
# Compilar C# CLI
dotnet build src/csharp/PiperPlus.sln -c Release
# Testes
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Pré-requisitos: .NET 8 SDK ou superior

#### Exemplos de uso do C# CLI

```bash
# Inferência por nome do modelo (download automático, output.wav por padrão quando --output-file é omitido)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# Inglês
piper-plus --model model.onnx --text "Hello world" --language en

# Multilíngue (detecção automática de idioma)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Notação de fonemas inline (especificação direta de fonemas no texto)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Streaming (saída PCM sequencial por frase)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# Dicionário personalizado (JSON v1/v2 ou TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# Download de modelo
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Modo de teste (verifica phoneme IDs sem inferência ONNX)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Exemplos de uso do Rust CLI

```bash
# Inferência por nome do modelo (download automático)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# Inglês
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Download e gerenciamento de modelos
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Streaming (síntese sequencial por frase)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# Dicionário personalizado
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# Inferência GPU
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Modo de teste e modo silencioso
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Saída PCM raw (sem cabeçalho WAV)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Nota:** O C# CLI pode ser instalado com `dotnet tool install -g PiperPlus.Cli` e o Rust CLI com `cargo install piper-plus-cli`. Ambos suportam 8 idiomas, dicionário personalizado e streaming.

### Compilação a partir do código-fonte (Rust)

```bash
# Compilar Rust CLI
cargo build --release -p piper-plus-cli
# Testes
cargo test -p piper-plus
```

Pré-requisitos: Rust 1.88+, cargo

---

## Uso

### C++ CLI

#### Entrada de texto direto (recomendado)

Com a opção `--text`, você pode inserir texto diretamente sem usar pipes:

```sh
# Gerar áudio a partir de texto
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# Texto em japonês (evita problemas de codificação no Windows)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# Especificação de falante
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Entrada via pipe

```sh
# Básico
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# Streaming (baixa latência)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# Inferência GPU
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# Saída de temporização de fonemas (para lip sync e sincronização de legendas)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Dicionário personalizado
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Entrada de fonemas inline
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# Entrada de fonemas raw
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# Streaming (saída de áudio raw)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Opções principais:

| Opção | Descrição | Padrão |
|---|---|---|
| `--model PATH\|NAME` | Caminho do arquivo de modelo ou nome do modelo (resolução automática de modelos baixados) | - |
| `--config/-c PATH` | Caminho do arquivo de configuração | - |
| `--output_file/-f PATH` | Caminho do arquivo WAV de saída | - |
| `--output_dir/-d DIR` | Diretório de saída | - |
| `--output-raw` | Saída de áudio PCM raw para stdout | off |
| `--text TEXT` | Entrada de texto direto (sem pipe) | - |
| `--streaming` | Modo de streaming baseado em chunks | off |
| `--use-cuda` | Habilitar inferência CUDA GPU | off |
| `--gpu-device-id NUM` | ID do dispositivo GPU | 0 |
| `--length-scale VAL` | Ajuste de velocidade da fala (menor = mais rápido) | 1.0 |
| `--noise-scale VAL` | Controle de variação de voz | 0.667 |
| `--noise-w VAL` | Controle de variação de duração de fonemas | 0.8 |
| `--sentence-silence SEC` | Silêncio entre frases (segundos) | 0.2 |
| `--speaker NUM` | Número do falante para modelos multi-falante | 0 |
| `--phoneme-silence PHONEME SEC` | Definição de tempo de silêncio para fonema específico | - |
| `--raw-phonemes` | Interpretar entrada como fonemas | off |
| `--output-timing FILE` | Saída de informações de temporização de fonemas para arquivo (JSON/TSV) | - |
| `--custom-dict FILE` | Dicionário personalizado (múltiplos separados por vírgula) | - |
| `--language/-l CODE` | Código do idioma | - |
| `--timing-format FORMAT` | Formato de saída de temporização (json/tsv) | - |
| `--test-mode` | Modo de teste, pular inferência ONNX | off |
| `--debug` | Ativar log de depuração | off |
| `--quiet/-q` | Desativar log | off |
| `--json-input` | Modo de entrada JSON | off |
| `--list-models [LANG]` | Exibir lista de modelos disponíveis | - |
| `--download-model NAME` | Baixar modelo | - |
| `--model-dir DIR` | Diretório de destino para download de modelos | - |
| `--version` | Exibir versão | - |

Execute `piper --help` para ver todas as opções.

> **Configuração recomendada para modelos WavLM:** Para modelos treinados com WavLM Discriminator, recomenda-se `--noise-scale 0.5` (padrão: 0.667).
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### Entrada JSON

Com o flag `--json-input`, aceita entrada em JSON:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Gerenciamento de Modelos

#### Listar modelos

```bash
# Exibir lista de modelos disponíveis
./bin/piper --list-models

# Filtrar por idioma
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### Download de modelos

```bash
# Baixar especificando nome do modelo (aliases também disponíveis)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# Especificar diretório de destino do download
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# Após o download, inferência por nome do modelo (caminho completo desnecessário)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### Variáveis de ambiente (C++ CLI)

| Variável | Descrição | Exemplo |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | Caminho do modelo padrão quando `--model` não é especificado | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | Caminho do arquivo de configuração padrão quando `--config` não é especificado | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | Diretório de armazenamento de modelos baixados | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | ID do dispositivo CUDA GPU | `0` |

### Scripts auxiliares (Windows)

Scripts auxiliares estão disponíveis no diretório `scripts/` para usuários Windows.

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Prompt de Comando:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Treinamento

Para mais detalhes, consulte o [Guia de treinamento](docs/guides/training/training-guide.md).

### Básico

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

### Multi-falante e Multi-GPU

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

Com multi-GPU, o DDP (Distributed Data Parallel) é configurado automaticamente. É necessário definir as variáveis de ambiente NCCL. Consulte o guia de treinamento multi-GPU para mais detalhes.

### Conversão ONNX

Por padrão, a conversão FP16 é aplicada, reduzindo o tamanho do modelo em aproximadamente 50%. Pode ser desabilitada com `--no-fp16`. Para estabilidade numérica, LayerNormalization, Sigmoid e Softmax são mantidos em FP32.

```bash
# Modelo padrão (saída FP16)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Saída FP32
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# Modelo WavLM (--stochastic ativado por padrão)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Gerenciamento de checkpoints

- `--resume_from_checkpoint` — Retomar treinamento a partir de um checkpoint
- `--resume_from_single_speaker_checkpoint` — Converter modelo de falante único para multi-falante

### Avaliação de áudio

`scripts/evaluation/` contém textos de teste para avaliação.

---

## Modelos Pre-treinados

Modelos de síntese de voz para inferência estão disponíveis no Hugging Face.

**Modelos para inferência (prontos para uso):**

| Modelo | Idiomas | Falantes | Descrição | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Voz Tsukuyomi-chan, 6 idiomas, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japonês 6lang | JA/EN/ZH/ES/FR/PT | 1 | Voz CSS10 japonês, 6 idiomas, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Modelos base para treinamento (para fine-tuning):**

| Modelo | Idiomas | Falantes | Descrição | Download |
|---|---|---|---|---|
| Modelo base 6 idiomas | JA/EN/ZH/ES/FR/PT | 571 | Pré-treinado multilíngue (508.187 enunciados, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### Download de modelos

**Modelo Tsukuyomi-chan:**

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

### Características do modelo base 6 idiomas (para treinamento)

- Arquitetura: VITS + Prosody Features
- Dados de treinamento: 508.187 enunciados (571 falantes, 6 idiomas)
- Taxa de amostragem: 22.050 Hz
- Número de símbolos: 173
- Prosody Features: Informações prosódicas A1/A2/A3 (japonês)
- Amostragem balanceada por grupo linguístico: habilitada automaticamente

**Idiomas suportados:**

| Idioma | Código | language_id | Falantes | Enunciados | Fonte |
|---|---|---|---|---|---|
| Japonês | ja | 0 | 20 | 60.148 | MOE-Speech |
| Inglês | en | 1 | 310 | 74.912 | LibriTTS-R |
| Chinês | zh | 2 | 142 | 63.223 | AISHELL-3 |
| Espanhol | es | 3 | 63 | 168.374 | CML-TTS |
| Francês | fr | 4 | 28 | 107.464 | CML-TTS |
| Português | pt | 5 | 8 | 34.066 | CML-TTS |

> **Nota:** O piper-plus realiza extensões de arquitetura proprietárias (embedding multilíngue, Prosody A1/A2/A3, 173 símbolos), portanto não é compatível com checkpoints/modelos ONNX do Piper upstream. Utilize modelos exclusivos do piper-plus.

---

## TTS em Japones

Síntese de voz em japonês de alta qualidade com integração OpenJTalk. O dicionário e os arquivos de voz são baixados automaticamente na primeira execução.

**Variáveis de ambiente (opcionais):**

| Variável | Descrição |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | Caminho do dicionário OpenJTalk (download automático quando não definido) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` para desabilitar o download automático |
| `PIPER_OFFLINE_MODE` | `1` para modo offline |

Para mais detalhes, consulte o guia de síntese de voz em japonês e a [Referência de mapeamento de fonemas](docs/api-reference/phoneme-mapping.md).

---

## Plataformas

### macOS

**Suporte apenas para Apple Silicon (M1/M2/M3+).** Para Intel Mac, use Docker ou compilação a partir do código-fonte.

Aviso de segurança na primeira execução:

```bash
xattr -cr piper/
```

### Windows

O diretório espeak-ng-data é necessário. Para mais detalhes, consulte o [Guia de configuração do Windows](docs/getting-started/windows-setup.md).

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

TTS em japonês que funciona diretamente no navegador. Sem servidor, compatível com modo offline.

- **[Demo online](https://ayutaz.github.io/piper-plus/)**
- **[Detalhes técnicos e guia de integração](src/wasm/openjtalk-web/README.npm.md)**

---

## Links Relacionados

### piper-plus-g2p (Pacote G2P independente)

G2P multilíngue (Grapheme-to-Phoneme) disponível como pacotes independentes:

- **Python**: `pip install piper-plus-g2p` — [Código-fonte](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Código-fonte](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Código-fonte](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Código-fonte](src/wasm/g2p/)

### Unity — uPiper

Plugin para usar o Piper no Unity: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Suporte a Windows / macOS (Apple Silicon) / Linux / Android
- Japonês e inglês, API assíncrona, streaming

### Voices

Modelos piper-plus: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (base 6 idiomas) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Nota:** O piper-plus utiliza seu próprio sistema G2P e de fonemas, portanto os modelos do Piper upstream (rhasspy/piper-voices) NÃO são compatíveis.

### Artigos relacionados

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentacao

| Categoria | Links |
|---|---|
| TTS em japonês | Guia de síntese de voz em japonês |
| Treinamento | [Guia de treinamento](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Mapeamento de fonemas](docs/api-reference/phoneme-mapping.md) · [Variáveis de ambiente](docs/getting-started/environment-variables.md) |
| Funcionalidades | [WebUI](docs/features/webui.md) · Melhorias CLI · Streaming · Phoneme Timing · SSML |
| Configuração | Início rápido (japonês) · [Windows](docs/getting-started/windows-setup.md) · [Solução de problemas](docs/getting-started/troubleshooting.md) |
| Docker | [Ambiente Docker](docker/README.md) |
| WebAssembly | [Detalhes técnicos](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

Consulte [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

Consulte [CHANGELOG.md](CHANGELOG.md).
