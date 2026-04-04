![Piper logo](etc/logo.png)

[English](README_EN.md) | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md) | [Русский](README_RU.md) | [Svenska](README_SV.md) | हिन्दी

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

तेज़ और उच्च गुणवत्ता वाली न्यूरल टेक्स्ट-टू-स्पीच (TTS) प्रणाली। [VITS](https://github.com/jaywalnut310/vits/) आर्किटेक्चर पर आधारित, जापानी, अंग्रेज़ी, चीनी, कोरियाई, स्पेनी, फ़्रेंच, पुर्तगाली और स्वीडिश — 8 भाषाओं में मल्टी-स्पीकर वाक् संश्लेषण का समर्थन। [Piper](https://github.com/rhasspy/piper) का फ़ोर्क, जिसमें जापानी समर्थन, ध्वनि गुणवत्ता और प्रशिक्षण क्षमताओं में व्यापक सुधार किया गया है।

**[Hugging Face डेमो](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly डेमो](https://ayutaz.github.io/piper-plus/)** (ब्राउज़र में चलता है, सर्वर की आवश्यकता नहीं)

---

## विषय-सूची

- [प्रमुख विशेषताएँ](#प्रमुख-विशेषताएँ)
- [त्वरित प्रारंभ](#त्वरित-प्रारंभ)
- [पूर्व-प्रशिक्षित मॉडल](#पूर्व-प्रशिक्षित-मॉडल)
- [इंस्टॉलेशन](#इंस्टॉलेशन)
- [उपयोग विधि](#उपयोग-विधि)
- [प्रशिक्षण](#प्रशिक्षण)
- [जापानी TTS](#जापानी-tts)
- [प्लेटफ़ॉर्म](#प्लेटफ़ॉर्म)
- [संबंधित लिंक](#संबंधित-लिंक)

---

## प्रमुख विशेषताएँ

### वाक् संश्लेषण

- **8 भाषाओं का समर्थन** — जापानी, अंग्रेज़ी, चीनी, कोरियाई, स्पेनी, फ़्रेंच, पुर्तगाली, स्वीडिश (ja=0, en=1, zh=2, ko=3, es=4, fr=5, pt=6, sv=7)
- **जापानी TTS** — OpenJTalk एकीकरण, प्रोसोडी जानकारी (A1/A2/A3), प्रश्नवाचक मार्कर (#204), संदर्भ-निर्भर "ん" वेरिएंट (#207)
- **अंग्रेज़ी TTS** — GPL-मुक्त G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), espeak-ng अनावश्यक
- **मल्टी-स्पीकर** — 571 वक्ता समर्थन (प्रशिक्षण बेस मॉडल), SpeakerBalancedBatchSampler, भाषा समूह संतुलित नमूनाकरण
- **कस्टम शब्दकोश** — 200+ तकनीकी शब्दों का अंतर्निहित उच्चारण शब्दकोश
- **फ़ोनीम इनपुट** — `[[ phonemes ]]` संकेतन द्वारा सीधे निर्दिष्ट — [गाइड](docs/features/phoneme-input.md)

### प्रशिक्षण

- **WavLM Discriminator** — MOS +0.15-0.25 सुधार (डिफ़ॉल्ट रूप से सक्षम, केवल प्रशिक्षण में उपयोग)
- **FP16 Mixed Precision** — प्रशिक्षण गति 2-3 गुना, मेमोरी ~50% कम (डिफ़ॉल्ट रूप से सक्षम)
- **EMA** — Exponential Moving Average द्वारा प्रशिक्षण स्थिरता में सुधार (डिफ़ॉल्ट रूप से सक्षम)
- **मल्टी-GPU** — DDP समर्थन, स्वचालित लर्निंग रेट स्केलिंग
- **Prosody Features** — Duration Predictor में प्रोसोडी जानकारी इंजेक्शन (`--prosody-dim 16`)
- **Wandb एकीकरण** — रियल-टाइम मेट्रिक्स मॉनिटरिंग

### इंटरफ़ेस

- **[WebUI (Gradio)](docs/features/webui.md)** — अनुमान और प्रशिक्षण समर्थन, Docker समर्थन
- **C++ CLI** — स्ट्रीमिंग, CUDA अनुमान, फ़ोनीम टाइमिंग आउटपुट, कस्टम शब्दकोश
- **[WebAssembly](src/wasm/openjtalk-web/README.md)** — ब्राउज़र में पूर्ण संचालन, सर्वर अनावश्यक
- **[Docker](docker/README.md)** — अनुमान, प्रशिक्षण, WebUI, C++ के 5 इमेज उपलब्ध
- **PyPI** — `pip install piper-plus` से आसान इंस्टॉलेशन
- **C# CLI** — .NET 8/9 क्रॉस-प्लेटफ़ॉर्म, 8 भाषा मल्टीलिंगुअल, ONNX अनुमान
- **Rust CLI** — piper-plus/piper-plus-cli, स्ट्रीमिंग, CUDA/CoreML/DirectML समर्थन, शब्दकोश स्वचालित डाउनलोड
- **[Go CLI](src/go/README.md)** — HTTP API सर्वर, सेशन पूलिंग, Docker समर्थन, सिंगल बाइनरी

### प्लेटफ़ॉर्म

| प्लेटफ़ॉर्म | आर्किटेक्चर | टिप्पणी |
|---|---|---|
| Linux | x86_64 / ARM64 | पूर्ण समर्थन |
| macOS | ARM64 (Apple Silicon) केवल | M1/M2/M3+ |
| Windows | x64 | पूर्ण समर्थन |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9, Linux/macOS/Windows |
| Rust | x64 / ARM64 | Linux/macOS/Windows, CUDA/CoreML/DirectML |
| Go | x64 / ARM64 | Linux/macOS/Windows, HTTP API, Docker |

---

## त्वरित प्रारंभ

### प्रीबिल्ट बाइनरी (बिल्ड अनावश्यक)

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases) से प्रीबिल्ट बाइनरी डाउनलोड करके तुरंत वाक् संश्लेषण शुरू करें।

**1. बाइनरी डाउनलोड करें**

अपने OS के अनुसार डाउनलोड और एक्सट्रैक्ट करें।

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

**2. मॉडल डाउनलोड करें और ऑडियो जनरेट करें**

```sh
# त्सुकुयोमी-चान मॉडल डाउनलोड करें
./bin/piper --download-model tsukuyomi

# ऑडियो जनरेट करें (केवल मॉडल नाम — डाउनलोड किया हुआ मॉडल स्वचालित रूप से रिज़ॉल्व)
./bin/piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd कोडपेज के बारे में:** `--text` विकल्प आंतरिक रूप से `GetCommandLineW()` (UTF-16) का उपयोग करता है, इसलिए यह कोडपेज से स्वतंत्र रूप से काम करता है। पाइप इनपुट (`echo ... | piper`) का उपयोग करते समय ही, पहले `chcp 65001` से UTF-8 में बदलें।
>
> **output.wav का आउटपुट स्थान:** वर्तमान डायरेक्टरी (`cd piper` का स्थान) में जनरेट होता है।

### Python अनुमान

```bash
# इंस्टॉल
uv pip install ".[inference]"

# जापानी अनुमान
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# अंग्रेज़ी अनुमान
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

मुख्य विकल्प: `--speaker-id` (वक्ता ID), `--device auto|cpu|gpu`, `--noise-scale` (ध्वनि भिन्नता), `--length-scale` (बोलने की गति)

> **WavLM मॉडल के लिए अनुशंसित सेटिंग:** WavLM Discriminator से प्रशिक्षित मॉडल (त्सुकुयोमी-चान आदि) के लिए `--noise-scale 0.5` पर सर्वोत्तम ध्वनि गुणवत्ता प्राप्त होती है (डिफ़ॉल्ट 0.667 है)।

#### Python CLI मॉडल प्रबंधन

```bash
# मॉडल सूची दिखाएँ
python -m piper --list-models
python -m piper --list-models ja

# मॉडल डाउनलोड
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# डाउनलोड के बाद उपयोग
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

# Python अनुमान (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# GPU अनुमान (--gpus all जोड़ें)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

CI/CD द्वारा बिल्ट इमेज:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main
docker pull ghcr.io/ayutaz/piper-plus/python-train:main
docker pull ghcr.io/ayutaz/piper-plus/webui:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

विवरण के लिए [docker/README.md](docker/README.md) देखें।

---

## इंस्टॉलेशन

### Python

Python 3.11+ आवश्यक है। निर्भरता प्रबंधन के लिए [uv](https://docs.astral.sh/uv/) की अनुशंसा की जाती है।

```bash
# CPU अनुमान
uv pip install ".[inference]"

# GPU अनुमान (CUDA वातावरण आवश्यक)
uv pip install ".[inference-gpu]"

# प्रशिक्षण
uv pip install ".[train]"

# विकास (परीक्षण और लिंटर सहित)
uv pip install ".[dev]"
```

PyPI पैकेज से भी इंस्टॉल किया जा सकता है:

```bash
pip install piper-plus
```

### पैकेज से इंस्टॉल

**Python (PyPI):**
```bash
pip install piper-plus
```

**npm (ब्राउज़र WASM):**
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

**C# लाइब्रेरी (NuGet):**
```bash
dotnet add package PiperPlus.Core
```

**Rust लाइब्रेरी (crates.io):**
```toml
[dependencies]
piper-plus = "0.1.0"
```

### सोर्स से बिल्ड (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

पूर्वापेक्षाएँ: C++17 संगत कंपाइलर, CMake 3.15+

- **Linux**: बिल्ड से पहले [piper-phonemize](https://github.com/rhasspy/piper-phonemize) को `lib/Linux-$(uname -m)/piper_phonemize` में रखें
- **Windows**: [Windows सेटअप गाइड](docs/getting-started/windows-setup.md) देखें
- **macOS**: निर्भरताएँ स्वचालित डाउनलोड होती हैं

### सोर्स से बिल्ड (C#)

```bash
# C# CLI बिल्ड
dotnet build src/csharp/PiperPlus.sln -c Release
# परीक्षण
dotnet test src/csharp/PiperPlus.Core.Tests/
```

पूर्वापेक्षाएँ: .NET 8 SDK या उच्चतर

#### C# CLI उपयोग उदाहरण

```bash
# मॉडल नाम से अनुमान (स्वचालित डाउनलोड समर्थन, --output-file छोड़ने पर output.wav में आउटपुट)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# अंग्रेज़ी
piper-plus --model model.onnx --text "Hello world" --language en

# मल्टीलिंगुअल (स्वचालित भाषा पहचान)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# इनलाइन फ़ोनीम संकेतन (टेक्स्ट में सीधे फ़ोनीम निर्दिष्ट करें)
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# स्ट्रीमिंग (वाक्य दर वाक्य क्रमिक PCM आउटपुट)
piper-plus --model model.onnx --text "最初の文。次の文。" --language ja --streaming | aplay -r 22050 -f S16_LE

# कस्टम शब्दकोश (JSON v1/v2 या TSV)
piper-plus --model model.onnx --text "AI技術" --language ja --custom-dict my_dict.json

# मॉडल डाउनलोड
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# परीक्षण मोड (ONNX अनुमान के बिना phoneme IDs की जाँच)
piper-plus --model model.onnx --test-mode --text "こんにちは" --language ja
```

#### Rust CLI उपयोग उदाहरण

```bash
# मॉडल नाम से अनुमान (स्वचालित डाउनलोड समर्थन)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# अंग्रेज़ी
piper-plus-cli --model model.onnx --text "Hello world" --language en

# मॉडल डाउनलोड और प्रबंधन
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# स्ट्रीमिंग (वाक्य दर वाक्य क्रमिक संश्लेषण)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# कस्टम शब्दकोश
piper-plus-cli --model model.onnx --text "AI技術" --custom-dict my_dict.json

# GPU अनुमान
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# परीक्षण मोड और शांत मोड
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# raw PCM आउटपुट (WAV हेडर रहित)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **नोट:** C# CLI को `dotnet tool install -g PiperPlus.Cli` से और Rust CLI को `cargo install piper-plus-cli` से इंस्टॉल किया जा सकता है। दोनों 8 भाषाओं, कस्टम शब्दकोश और स्ट्रीमिंग का समर्थन करते हैं।

### सोर्स से बिल्ड (Rust)

```bash
# Rust CLI बिल्ड
cargo build --release -p piper-plus-cli
# परीक्षण
cargo test -p piper-plus
```

पूर्वापेक्षाएँ: Rust 1.88+, cargo

---

## उपयोग विधि

### C++ CLI

#### सीधा टेक्स्ट इनपुट (अनुशंसित)

`--text` विकल्प से पाइप के बिना सीधे टेक्स्ट इनपुट किया जा सकता है:

```sh
# टेक्स्ट से ऑडियो जनरेट करें
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# जापानी टेक्स्ट (Windows पर एन्कोडिंग समस्याओं से बचें)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# वक्ता निर्दिष्ट करें
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### पाइप इनपुट

```sh
# बुनियादी
echo "こんにちは" | ./bin/piper --model ja_model.onnx --output_file output.wav

# स्ट्रीमिंग (कम विलंबता)
echo "長いテキスト..." | ./bin/piper --model ja_model.onnx --output_file output.wav --streaming

# GPU अनुमान
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# फ़ोनीम टाइमिंग आउटपुट (लिप सिंक और उपशीर्षक समन्वय के लिए)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# कस्टम शब्दकोश
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# इनलाइन फ़ोनीम इनपुट
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# raw फ़ोनीम इनपुट
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# स्ट्रीमिंग (raw audio आउटपुट)
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

मुख्य विकल्प:

| विकल्प | विवरण | डिफ़ॉल्ट |
|---|---|---|
| `--model PATH\|NAME` | मॉडल फ़ाइल का पथ, या मॉडल नाम (डाउनलोड किए गए मॉडल को स्वचालित रिज़ॉल्व) | - |
| `--text TEXT` | सीधा टेक्स्ट इनपुट (पाइप अनावश्यक) | - |
| `--streaming` | चंक-आधारित स्ट्रीमिंग मोड | बंद |
| `--use-cuda` | CUDA GPU अनुमान सक्षम करें | बंद |
| `--gpu-device-id NUM` | GPU डिवाइस ID | 0 |
| `--length-scale VAL` | बोलने की गति समायोजन (छोटा=तेज़) | 1.0 |
| `--noise-scale VAL` | ध्वनि भिन्नता नियंत्रण | 0.667 |
| `--noise-w VAL` | फ़ोनीम अवधि भिन्नता नियंत्रण | 0.8 |
| `--sentence-silence SEC` | वाक्यों के बीच मौन (सेकंड) | 0.2 |
| `--speaker NUM` | मल्टी-स्पीकर मॉडल की वक्ता संख्या | 0 |
| `--phoneme-silence PHONEME SEC` | विशिष्ट फ़ोनीम का मौन समय सेटिंग | - |
| `--raw-phonemes` | इनपुट को फ़ोनीम के रूप में व्याख्या करें | बंद |
| `--output-timing FILE` | फ़ोनीम टाइमिंग जानकारी फ़ाइल में आउटपुट (JSON/TSV) | - |
| `--custom-dict FILE` | कस्टम शब्दकोश (कॉमा से अलग करके एक से अधिक निर्दिष्ट कर सकते हैं) | - |
| `--json-input` | JSON इनपुट मोड | बंद |
| `--list-models [LANG]` | उपलब्ध मॉडल की सूची दिखाएँ | - |
| `--download-model NAME` | मॉडल डाउनलोड करें | - |
| `--model-dir DIR` | मॉडल डाउनलोड गंतव्य डायरेक्टरी | - |
| `--version` | संस्करण दिखाएँ | - |

सभी विकल्प देखने के लिए `piper --help` चलाएँ।

> **WavLM मॉडल के लिए अनुशंसित सेटिंग:** WavLM Discriminator से प्रशिक्षित मॉडल के लिए `--noise-scale 0.5` की अनुशंसा की जाती है (डिफ़ॉल्ट 0.667 है)।
>
> ```sh
> echo "こんにちは" | ./bin/piper --model tsukuyomi.onnx --config config.json --noise-scale 0.5 -f output.wav
> ```

### JSON इनपुट

`--json-input` फ़्लैग से JSON इनपुट स्वीकार करता है:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### मॉडल प्रबंधन

#### मॉडल सूची दिखाएँ

```bash
# उपलब्ध मॉडल की सूची दिखाएँ
./bin/piper --list-models

# भाषा से फ़िल्टर करें
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### मॉडल डाउनलोड

```bash
# मॉडल नाम निर्दिष्ट करके डाउनलोड करें (एलियास भी उपयोग योग्य)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# डाउनलोड गंतव्य डायरेक्टरी निर्दिष्ट करें
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# डाउनलोड के बाद, मॉडल नाम से अनुमान (पूर्ण पथ अनावश्यक)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### पर्यावरण चर (C++ CLI)

| चर नाम | विवरण | उदाहरण |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | `--model` अनिर्दिष्ट होने पर डिफ़ॉल्ट मॉडल पथ | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | `--config` अनिर्दिष्ट होने पर डिफ़ॉल्ट कॉन्फ़िग फ़ाइल पथ | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | डाउनलोड किए गए मॉडल का संग्रहण डायरेक्टरी | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | CUDA GPU डिवाइस ID | `0` |

### हेल्पर स्क्रिप्ट (Windows)

Windows उपयोगकर्ताओं के लिए `scripts/` डायरेक्टरी में हेल्पर स्क्रिप्ट उपलब्ध हैं।

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**कमांड प्रॉम्प्ट:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## प्रशिक्षण

विवरण के लिए [प्रशिक्षण गाइड](docs/guides/training/training-guide.md) देखें।

### बुनियादी

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

### मल्टी-स्पीकर और मल्टी-GPU

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

मल्टी-GPU में DDP (Distributed Data Parallel) स्वचालित रूप से कॉन्फ़िगर होता है। NCCL पर्यावरण चर सेट करना आवश्यक है। विवरण के लिए मल्टी-GPU प्रशिक्षण गाइड देखें।

### ONNX रूपांतरण

डिफ़ॉल्ट रूप से FP16 रूपांतरण लागू होता है, जिससे मॉडल का आकार ~50% कम हो जाता है। `--no-fp16` से अक्षम किया जा सकता है। संख्यात्मक स्थिरता के लिए LayerNormalization, Sigmoid, Softmax को FP32 में रखा जाता है।

```bash
# मानक मॉडल (FP16 आउटपुट)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# FP32 आउटपुट
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM मॉडल (--stochastic आवश्यक)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### चेकपॉइंट प्रबंधन

- `--resume_from_checkpoint` — चेकपॉइंट से प्रशिक्षण पुनः आरंभ
- `--resume_from_single_speaker_checkpoint` — सिंगल-स्पीकर मॉडल से मल्टी-स्पीकर में रूपांतरण

### ध्वनि मूल्यांकन

`scripts/evaluation/` में MCD, PESQ, UTMOS मूल्यांकन उपकरण उपलब्ध हैं।

---

## पूर्व-प्रशिक्षित मॉडल

अनुमान के लिए वाक् संश्लेषण मॉडल Hugging Face पर प्रकाशित हैं।

**अनुमान मॉडल (तुरंत उपयोग योग्य):**

| मॉडल | भाषा | वक्ता संख्या | विवरण | डाउनलोड |
|---|---|---|---|---|
| त्सुकुयोमी-चान 6lang | JA/EN/ZH/ES/FR/PT | 1 | त्सुकुयोमी-चान ध्वनि, 6 भाषा समर्थन, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 जापानी 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 जापानी ध्वनि, 6 भाषा समर्थन, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**प्रशिक्षण बेस मॉडल (फ़ाइन-ट्यूनिंग के लिए):**

| मॉडल | भाषा | वक्ता संख्या | विवरण | डाउनलोड |
|---|---|---|---|---|
| 6 भाषा बेस मॉडल | JA/EN/ZH/ES/FR/PT | 571 | मल्टीलिंगुअल पूर्व-प्रशिक्षित (508,187 उच्चारण, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

### मॉडल डाउनलोड

**त्सुकुयोमी-चान मॉडल:**

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

### 6 भाषा बेस मॉडल की विशेषताएँ (प्रशिक्षण के लिए)

- आर्किटेक्चर: VITS + Prosody Features
- प्रशिक्षण डेटा: 508,187 उच्चारण (571 वक्ता, 6 भाषाएँ)
- सैंपलिंग रेट: 22,050 Hz
- सिंबल संख्या: 173
- Prosody Features: A1/A2/A3 प्रोसोडी जानकारी (जापानी)
- भाषा समूह संतुलित नमूनाकरण: स्वचालित सक्षम

**समर्थित भाषाएँ:**

| भाषा | कोड | language_id | वक्ता संख्या | उच्चारण संख्या | स्रोत |
|---|---|---|---|---|---|
| जापानी | ja | 0 | 20 | 60,148 | MOE-Speech |
| अंग्रेज़ी | en | 1 | 310 | 74,912 | LibriTTS-R |
| चीनी | zh | 2 | 142 | 63,223 | AISHELL-3 |
| स्पेनी | es | 3 | 63 | 168,374 | CML-TTS |
| फ़्रेंच | fr | 4 | 28 | 107,464 | CML-TTS |
| पुर्तगाली | pt | 5 | 8 | 34,066 | CML-TTS |

> **नोट:** piper-plus का अपना विशेष आर्किटेक्चर विस्तार (मल्टीलिंगुअल एम्बेडिंग, Prosody A1/A2/A3, 173 सिंबल) है, इसलिए upstream Piper के चेकपॉइंट/ONNX मॉडल के साथ संगतता नहीं है। कृपया piper-plus के विशेष मॉडल का उपयोग करें।

---

## जापानी TTS

OpenJTalk एकीकरण द्वारा उच्च गुणवत्ता वाला जापानी वाक् संश्लेषण। शब्दकोश और वॉइस फ़ाइल पहले चलाने पर स्वचालित रूप से डाउनलोड होती हैं।

**पर्यावरण चर (वैकल्पिक):**

| चर नाम | विवरण |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk शब्दकोश पथ (असेट न होने पर स्वचालित डाउनलोड) |
| `PIPER_AUTO_DOWNLOAD_DICT` | `0` से स्वचालित डाउनलोड अक्षम |
| `PIPER_OFFLINE_MODE` | `1` से ऑफ़लाइन मोड |

विवरण के लिए जापानी वाक् संश्लेषण गाइड और [फ़ोनीम मैपिंग संदर्भ](docs/api-reference/phoneme-mapping.md) देखें।

---

## प्लेटफ़ॉर्म

### macOS

**केवल Apple Silicon (M1/M2/M3+) समर्थित।** Intel Mac के लिए Docker या सोर्स बिल्ड का उपयोग करें।

पहली बार चलाने पर सुरक्षा चेतावनी:

```bash
xattr -cr piper/
```

### Windows

espeak-ng-data डायरेक्टरी आवश्यक है। विवरण के लिए [Windows सेटअप गाइड](docs/getting-started/windows-setup.md) देखें।

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

ब्राउज़र में सीधे चलने वाला जापानी TTS। सर्वर अनावश्यक, ऑफ़लाइन समर्थन।

- **[ऑनलाइन डेमो](https://ayutaz.github.io/piper-plus/)**
- **[तकनीकी विवरण और एकीकरण गाइड](src/wasm/openjtalk-web/README.md)**

---

## संबंधित लिंक

### Unity — uPiper

Unity में Piper उपयोग के लिए प्लगइन: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android समर्थन
- जापानी और अंग्रेज़ी समर्थन, एसिंक्रोनस API, स्ट्रीमिंग

### ध्वनि मॉडल (Voices)

upstream Piper के ध्वनि मॉडल (30+ भाषाएँ) भी उपलब्ध हैं: [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

प्रत्येक ध्वनि के लिए `.onnx` मॉडल और `.onnx.json` कॉन्फ़िग फ़ाइल आवश्यक है। [ध्वनि नमूने](https://rhasspy.github.io/piper-samples) | [वीडियो ट्यूटोरियल](https://youtu.be/rjq5eZoWWSo)

### संबंधित लेख

- [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### Piper का उपयोग करने वाले लोग

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## दस्तावेज़

| श्रेणी | लिंक |
|---|---|
| जापानी TTS | जापानी वाक् संश्लेषण गाइड |
| प्रशिक्षण | [प्रशिक्षण गाइड](docs/guides/training/training-guide.md) · मल्टी-GPU |
| API | [फ़ोनीम मैपिंग](docs/api-reference/phoneme-mapping.md) · [पर्यावरण चर](docs/getting-started/environment-variables.md) |
| विशेषताएँ | [WebUI](docs/features/webui.md) · CLI संवर्धन · स्ट्रीमिंग |
| सेटअप | त्वरित प्रारंभ (जापानी) · [Windows](docs/getting-started/windows-setup.md) · [समस्या निवारण](docs/getting-started/troubleshooting.md) |
| Docker | [Docker वातावरण](docker/README.md) |
| WebAssembly | [तकनीकी विवरण](src/wasm/openjtalk-web/README.md) |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) देखें।

## Changelog

[CHANGELOG.md](CHANGELOG.md) देखें।
