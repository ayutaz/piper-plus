# Piper-Plus Environment Variables Reference

This document covers user-facing dictionary, model, and inference settings. Variables are runtime-specific: setting a variable does not enable a feature in a runtime that does not read it. Docker server and training settings are listed separately below.

## OpenJTalk Configuration

### OPENJTALK_DICTIONARY_PATH

- **Description**: Path to OpenJTalk dictionary directory
- **Used by**: C++, C#, Go, Rust (dictionary download manager)
- **Default**: Searched in runtime-specific locations; C++, C# and Rust can auto-download it, while Go requires a local dictionary.
- **Platform defaults**:
  - Windows: `%APPDATA%\piper-plus\open_jtalk_dic_utf_8-1.11`
  - Linux: `~/.local/share/piper-plus/open_jtalk_dic_utf_8-1.11`
  - macOS: `~/.local/share/piper-plus/open_jtalk_dic_utf_8-1.11`
- **Example**:

  ```bash
  # Windows
  set OPENJTALK_DICTIONARY_PATH=C:\openjtalk\dictionary

  # Linux/macOS
  export OPENJTALK_DICTIONARY_PATH=/usr/share/open_jtalk/dic
  ```

### OPENJTALK_DATA_DIR

- **Description**: Override the base directory for OpenJTalk data files
- **Used by**: C++, Rust (dictionary download manager). C# uses its platform data directory and does not read this override.
- **Default**: Platform-specific user data directory
- **Example**:

  ```bash
  # Windows
  set OPENJTALK_DATA_DIR=D:\piper-data

  # Linux/macOS
  export OPENJTALK_DATA_DIR=/opt/piper-data
  ```

## Dictionary Paths

### PIPER_PLUS_DICTIONARIES_PATH

- **Description**: Directory containing G2P data files such as `cmudict_data.json` and Pinyin dictionaries. This is a fallback when phonemization data is not found next to the model or executable; it does not select the JSON v1/v2 custom text-replacement dictionary passed through `--custom-dict`.
- **Used by**: C++, Go
- **Search order**: model directory -> executable-relative directory -> `PIPER_PLUS_DICTIONARIES_PATH`
- **Example**:

  ```bash
  export PIPER_PLUS_DICTIONARIES_PATH=/opt/piper/dictionaries
  ```

### PIPER_PLUS_CUSTOM_DICT_PATH

- **Description**: Directory of custom text-replacement JSON dictionaries, searched after model-relative and executable-relative locations.
- **Used by**: Go custom dictionary discovery. This is distinct from `PIPER_PLUS_DICTIONARIES_PATH`, which supplies G2P data files such as CMU/Pinyin dictionaries.

### JPREPROCESS_DICT

- **Description**: Path to a NAIST-JDIC dictionary directory for Japanese phonemization via jpreprocess. Uses lindera format (not OpenJTalk MeCab format).
- **Used by**: Rust (piper-plus, piper-plus-g2p)
- **Default**: Bundled `naist-jdic` feature, or auto-detected from known locations
- **Example**:

  ```bash
  export JPREPROCESS_DICT=/opt/naist-jdic
  ```

### CMUDICT_PATH

- **Description**: Path to the CMU pronunciation dictionary file (`cmudict_data.json`) for English phonemization
- **Used by**: Rust (piper-plus, piper-plus-g2p)
- **Default**: Auto-detected from known locations
- **Example**:

  ```bash
  export CMUDICT_PATH=/opt/piper/cmudict_data.json
  ```

### PINYIN_SINGLE_PATH / PINYIN_PHRASES_PATH

- **Description**: Paths to Chinese pinyin dictionary files for Mandarin phonemization
- **Used by**: Rust (piper-plus)
- **Default**: Auto-detected next to the model file
- **Example**:

  ```bash
  export PINYIN_SINGLE_PATH=/opt/piper/pinyin_single.json
  export PINYIN_PHRASES_PATH=/opt/piper/pinyin_phrases.json
  ```

### DOTNETG2P_NAIST_JDIC_PATH / NAIST_JDIC_PATH

- **Description**: Alternative paths to NAIST-JDIC dictionary for Japanese phonemization in the C# implementation. `DOTNETG2P_NAIST_JDIC_PATH` is checked first, then `NAIST_JDIC_PATH`.
- **Used by**: C# (PiperPlus.Core)
- **Default**: Auto-downloaded to user data directory
- **Example**:

  ```bash
  export DOTNETG2P_NAIST_JDIC_PATH=/opt/naist-jdic
  # or
  export NAIST_JDIC_PATH=/opt/naist-jdic
  ```

## Download Control

### PIPER_PLUS_AUTO_DOWNLOAD_DICT

- **Description**: Control automatic download of OpenJTalk dictionary files in C++, C#, and Rust. Go requires a locally available dictionary.
- **Values**:
  - `1` (default): Enable automatic download
  - `0`: Disable automatic download
- **Example**:

  ```bash
  # Disable auto-download
  export PIPER_PLUS_AUTO_DOWNLOAD_DICT=0
  ```

### PIPER_PLUS_OFFLINE_MODE

- **Description**: Disable automatic OpenJTalk dictionary downloads in C++, C#, and Rust. This is not a process-wide network sandbox; model download commands and other components have separate behavior.
- **Values**:
  - `0` (default): Allow network access
  - `1`: Prevent automatic dictionary downloads
- **Example**:

  ```bash
  # Enable offline mode
  export PIPER_PLUS_OFFLINE_MODE=1
  ```

## Model Configuration

### PIPER_PLUS_DEFAULT_MODEL

- **Description**: Default ONNX model path, used when `--model` is not specified on the command line
- **Used by**: C++ CLI, Rust CLI, C# CLI, Go CLI
- **Default**: None (must be specified via CLI or this variable)
- **Example**:

  ```bash
  # Windows
  set PIPER_PLUS_DEFAULT_MODEL=C:\models\ja_JP-tsukuyomi-medium.onnx

  # Linux/macOS
  export PIPER_PLUS_DEFAULT_MODEL=/opt/piper/models/ja_JP-tsukuyomi-medium.onnx
  ```

### PIPER_PLUS_DEFAULT_CONFIG

- **Description**: Default model configuration file path (JSON), used when `--config` is not specified on the command line
- **Used by**: C++ CLI, Rust CLI, C# CLI, Go config resolver
- **Default**: None (auto-detected from model path if not set)
- **Example**:

  ```bash
  # Windows
  set PIPER_PLUS_DEFAULT_CONFIG=C:\models\ja_JP-tsukuyomi-medium.onnx.json

  # Linux/macOS
  export PIPER_PLUS_DEFAULT_CONFIG=/opt/piper/models/ja_JP-tsukuyomi-medium.onnx.json
  ```

### PIPER_PLUS_MODEL_DIR

- **Description**: Directory where models are downloaded to, used when `--model-dir` is not specified on the command line
- **Used by**: C++, Rust, C#, Go model managers and Python training tools. Docker WebUI also uses it for its mounted model directory (default `/models`).
- **Default**: Platform-specific user data directory
  - Windows: `%APPDATA%\piper-plus\models`
  - Linux: `~/.local/share/piper-plus/models`
  - macOS: `~/Library/Application Support/piper-plus/models`
- **Example**:

  ```bash
  # Windows
  set PIPER_PLUS_MODEL_DIR=D:\piper-models

  # Linux/macOS
  export PIPER_PLUS_MODEL_DIR=/opt/piper/models
  ```

## Runtime Configuration

### ESPEAK_DATA_PATH

- **Description**: Path to espeak-ng data directory
- **Status**: **Legacy / preprocessing only** — the default piper-plus runtime no longer uses eSpeak-ng for phonemization, which is handled by the in-house G2P stack (Python/Rust/C#/Go). However, this variable may still be referenced by legacy, bundled, or preprocessing workflows that rely on `espeak-ng`.
- **Legacy note**: Historically required by upstream `piper`, and still relevant for any remaining espeak-based tooling or preprocessing paths in this repository.

### PIPER_PLUS_GPU_DEVICE_ID

- **Description**: GPU device ID to use for CUDA inference
- **Used by**: C++ CLI and C# CLI/session factory. It selects a device after a compatible provider is enabled; it does not install or activate CUDA.
- **Default**: `0` (first GPU)
- **Example**:

  ```bash
  # Use the second GPU
  export PIPER_PLUS_GPU_DEVICE_ID=1
  ```

### PIPER_PLUS_DISABLE_WARMUP

- **Description**: Disable ONNX Runtime warmup (dummy inference runs). Accepts `1`, `true`, or `yes` to disable. Default is enabled (warmup runs on startup).
- **Used by**: Python inference (`infer_onnx.py`, `voice.py`, Docker inference, WebUI) and C# `SessionFactory`
- **Use cases**: Reducing startup time in embedded environments, debugging
- **Example**:

  ```bash
  export PIPER_PLUS_DISABLE_WARMUP=1
  ```

### PIPER_PLUS_DISABLE_CACHE

- **Description**: Disable ONNX Runtime optimized model cache (`.opt.onnx` files). Accepts `1`, `true`, or `yes` to disable. Default is enabled (cache files are generated).
- **Used by**: Python inference scripts and C# `SessionFactory`
- **Use cases**: Read-only file systems, CI environments, debugging
- **Example**:

  ```bash
  export PIPER_PLUS_DISABLE_CACHE=1
  ```

### PIPER_PLUS_INTRA_THREADS

- **Description**: Explicitly set the number of ONNX Runtime intra-op threads (clamped to 1–4). When not set, uses `min(max(logical_cores // 2, 1), 4)`, respecting process CPU affinity where available.
- **Used by**: Python inference scripts/API and C# `SessionFactory`
- **Use cases**: Tuning performance with Docker `--cpus` constraints, manual thread control
- **Example**:

  ```bash
  export PIPER_PLUS_INTRA_THREADS=2
  ```

### PIPER_PLUS_G2P_PARALLELISM

- **Description**: Control sentence-level G2P workers. `1` forces serial processing; an integer greater than 1 selects that many workers, capped at the number of sentences. Unset or invalid values use automatic CPU-based selection.
- **Used by**: Python `PiperVoice`, Rust `PiperVoice`, C# `SentenceParallelEncoder`, Go's parallel phonemization helper, and the C++ C API streaming path. This does not control ONNX inference threads.

  ```bash
  export PIPER_PLUS_G2P_PARALLELISM=1
  ```

### ONNX_RUNTIME_SHARED_LIBRARY_PATH

- **Description**: Path to the ONNX Runtime shared library (`libonnxruntime.so` / `libonnxruntime.dylib`). Required for Go integration tests and applications.
- **Used by**: Go (piperplus)
- **Example**:

  ```bash
  export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/usr/lib/libonnxruntime.so
  ```

### PIPER_PLUS_PHONEMIZE_DEBUG

- **Description**: Enable debug output for the legacy bundled piper-phonemize module
- **Status**: **Legacy / preprocessing only** — only recognized by `src/piper_phonemize_bundled/` (used by `preprocess.py` for eSpeak-based phoneme types). Not available in the main Python inference path (`src/python_run/`) or any other runtime.
- **Used by**: Legacy preprocessing pipeline (`preprocess.py`) only
- **Values**: Any non-empty value enables debug output
- **Example**:

  ```bash
  export PIPER_PLUS_PHONEMIZE_DEBUG=1
  ```

### LD_LIBRARY_PATH (Linux)

- **Description**: Library search path for shared libraries
- **Usage**: May need to include piper/lib directory
- **Example**:

  ```bash
  export LD_LIBRARY_PATH=/path/to/piper/lib:$LD_LIBRARY_PATH
  ```

### DYLD_LIBRARY_PATH (macOS)

- **Description**: Library search path for dynamic libraries
- **Usage**: May need to include piper/lib directory
- **Example**:

  ```bash
  export DYLD_LIBRARY_PATH=/path/to/piper/lib:$DYLD_LIBRARY_PATH
  ```

## Usage Examples

### Basic Japanese TTS (auto-download enabled)

```bash
# No environment variables needed - will auto-download on first use
echo "こんにちは" | piper-plus --model ja_JP-model.onnx --output_file hello.wav
```

### Custom dictionary location

```bash
# Windows
set OPENJTALK_DICTIONARY_PATH=C:\my-dictionary
echo "テスト" | piper-plus --model ja_JP-model.onnx --output_file test.wav

# Linux/macOS
export OPENJTALK_DICTIONARY_PATH=/opt/my-dictionary
echo "テスト" | piper-plus --model ja_JP-model.onnx --output_file test.wav
```

### Offline dictionary use

```bash
# Dictionary and model files must already be installed locally
export PIPER_PLUS_OFFLINE_MODE=1
export OPENJTALK_DICTIONARY_PATH=/path/to/existing/dictionary
echo "オフライン" | piper-plus --model ja_JP-model.onnx --output_file offline.wav
```

## Precedence Order

Dictionary lookup depends on the runtime. Explicit paths are considered before automatic download, but executable-relative paths, model-relative paths and system locations differ. See the runtime README for its full search order. The general deployment sequence is:

1. Supply a valid explicit dictionary path where supported.
2. Otherwise let the runtime search its bundled/model/system locations.
3. C++, C# and Rust can download a missing dictionary when enabled; Go does not automatically download it.

## Server and training settings

- Docker FastAPI server: `PIPER_PLUS_API_KEYS` enables Bearer authentication for the documented synthesis/model routes when set to a comma-separated key list (`/health` and `/api/phoneme-timing` are outside that dependency); rate-limit settings are `PIPER_PLUS_RATE_LIMIT_ENABLED`, `PIPER_PLUS_RATE_LIMIT_SPEECH` and `PIPER_PLUS_RATE_LIMIT_LIGHT`. See [Docker usage](../../docker/README.md) and [Open WebUI integration](../guides/integration/open-webui-integration.md).
- Docker WebUI: `PIPER_PLUS_MODEL`, `PIPER_PLUS_MODEL_DIR` and `PIPER_PLUS_OUTPUT_DIR` select the model and mounted directories. See [WebUI](../features/webui.md).
- Training: `PIPER_PLUS_FORCE_CPU_ORT` controls the speaker-encoder ONNX provider and `PIPER_PLUS_DISABLE_SUPER_MAS` disables the optional Super-MAS path. See [training](../guides/training/training-guide.md).
- `ORT_USE_CUDA` and `ORT_USE_DML` are not piper-plus runtime switches. Select a supported execution provider through the relevant CLI/API and install the matching ONNX Runtime build.

## Troubleshooting

### Dictionary not found

1. Check if `PIPER_PLUS_AUTO_DOWNLOAD_DICT=0` is set
2. Verify `OPENJTALK_DICTIONARY_PATH` points to valid directory
3. Ensure dictionary files exist (sys.dic, unk.dic, etc.)

### Download failures

1. Check internet connection
2. Verify `PIPER_PLUS_OFFLINE_MODE` is not set to 1
3. Check write permissions to data directory
4. Look for proxy/firewall issues

### Wrong character encoding

1. Ensure terminal/console supports UTF-8
2. On Windows, use `chcp 65001` for UTF-8 support
3. Check file encoding when reading from files
