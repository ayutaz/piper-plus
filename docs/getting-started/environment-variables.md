# Piper Environment Variables Reference

This document lists all environment variables that can be used to configure Piper's behavior.

## OpenJTalk Configuration

### OPENJTALK_DICTIONARY_PATH
- **Description**: Path to OpenJTalk dictionary directory
- **Used by**: C++, C#, Go, Rust (dictionary download manager)
- **Default**: Auto-downloaded to user data directory
- **Platform defaults**:
  - Windows: `%APPDATA%\piper\open_jtalk_dic_utf_8-1.11`
  - Linux: `~/.local/share/piper/open_jtalk_dic_utf_8-1.11`
  - macOS: `~/.local/share/piper/open_jtalk_dic_utf_8-1.11`
- **Example**:
  ```bash
  # Windows
  set OPENJTALK_DICTIONARY_PATH=C:\openjtalk\dictionary

  # Linux/macOS
  export OPENJTALK_DICTIONARY_PATH=/usr/share/open_jtalk/dic
  ```

### OPENJTALK_DATA_DIR
- **Description**: Override the base directory for OpenJTalk data files
- **Used by**: C++, C#, Rust (dictionary download manager)
- **Default**: Platform-specific user data directory
- **Example**:
  ```bash
  # Windows
  set OPENJTALK_DATA_DIR=D:\piper-data
  
  # Linux/macOS
  export OPENJTALK_DATA_DIR=/opt/piper-data
  ```

## Dictionary Paths

### PIPER_DICTIONARIES_PATH
- **Description**: Path to a directory containing custom dictionary files (JSON v1.0/v2.0 format). Used as a fallback search location when dictionaries are not found next to the model or executable.
- **Used by**: C++, Go
- **Search order**: model directory -> executable-relative directory -> `PIPER_DICTIONARIES_PATH`
- **Example**:
  ```bash
  export PIPER_DICTIONARIES_PATH=/opt/piper/dictionaries
  ```

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

### PIPER_AUTO_DOWNLOAD_DICT
- **Description**: Control automatic download of OpenJTalk dictionary files
- **Values**:
  - `1` (default): Enable automatic download
  - `0`: Disable automatic download
- **Example**:
  ```bash
  # Disable auto-download
  export PIPER_AUTO_DOWNLOAD_DICT=0
  ```

### PIPER_OFFLINE_MODE
- **Description**: Enable offline mode (no network access)
- **Values**:
  - `0` (default): Allow network access
  - `1`: Offline mode - prevent all downloads
- **Example**:
  ```bash
  # Enable offline mode
  export PIPER_OFFLINE_MODE=1
  ```

## Model Configuration

### PIPER_DEFAULT_MODEL
- **Description**: Default ONNX model path, used when `--model` is not specified on the command line
- **Used by**: Rust, C#
- **Default**: None (must be specified via CLI or this variable)
- **Example**:
  ```bash
  # Windows
  set PIPER_DEFAULT_MODEL=C:\models\ja_JP-tsukuyomi-medium.onnx

  # Linux/macOS
  export PIPER_DEFAULT_MODEL=/opt/piper/models/ja_JP-tsukuyomi-medium.onnx
  ```

### PIPER_DEFAULT_CONFIG
- **Description**: Default model configuration file path (JSON), used when `--config` is not specified on the command line
- **Used by**: Rust, C#
- **Default**: None (auto-detected from model path if not set)
- **Example**:
  ```bash
  # Windows
  set PIPER_DEFAULT_CONFIG=C:\models\ja_JP-tsukuyomi-medium.onnx.json

  # Linux/macOS
  export PIPER_DEFAULT_CONFIG=/opt/piper/models/ja_JP-tsukuyomi-medium.onnx.json
  ```

### PIPER_MODEL_DIR
- **Description**: Directory where models are downloaded to, used when `--model-dir` is not specified on the command line
- **Used by**: Rust, C#
- **Default**: Platform-specific user data directory
  - Windows: `%APPDATA%\piper\models`
  - Linux: `~/.local/share/piper/models`
  - macOS: `~/.local/share/piper/models`
- **Example**:
  ```bash
  # Windows
  set PIPER_MODEL_DIR=D:\piper-models

  # Linux/macOS
  export PIPER_MODEL_DIR=/opt/piper/models
  ```

## Runtime Configuration

### ESPEAK_DATA_PATH
- **Description**: Path to espeak-ng data directory
- **Status**: **Legacy / preprocessing only** — the default piper-plus runtime no longer uses eSpeak-ng for phonemization, which is handled by the in-house G2P stack (Python/Rust/C#/Go). However, this variable may still be referenced by legacy, bundled, or preprocessing workflows that rely on `espeak-ng`.
- **Legacy note**: Historically required by upstream `piper`, and still relevant for any remaining espeak-based tooling or preprocessing paths in this repository.

### PIPER_GPU_DEVICE_ID
- **Description**: GPU device ID to use for CUDA inference
- **Default**: `0` (first GPU)
- **Example**:
  ```bash
  # Use the second GPU
  export PIPER_GPU_DEVICE_ID=1
  ```

### PIPER_DISABLE_WARMUP
- **Description**: Disable ONNX Runtime warmup (dummy inference runs). Accepts `1`, `true`, or `yes` to disable. Default is enabled (warmup runs on startup).
- **Used by**: Python inference scripts (`infer_onnx.py`, `voice.py`, Docker inference, WebUI)
- **Use cases**: Reducing startup time in embedded environments, debugging
- **Example**:
  ```bash
  export PIPER_DISABLE_WARMUP=1
  ```

### PIPER_DISABLE_CACHE
- **Description**: Disable ONNX Runtime optimized model cache (`.opt.onnx` files). Accepts `1`, `true`, or `yes` to disable. Default is enabled (cache files are generated).
- **Used by**: Python inference scripts
- **Use cases**: Read-only file systems, CI environments, debugging
- **Example**:
  ```bash
  export PIPER_DISABLE_CACHE=1
  ```

### PIPER_INTRA_THREADS
- **Description**: Explicitly set the number of ONNX Runtime intra-op threads. When not set, defaults to `min(logical_cores / 2, 4)`.
- **Used by**: Python inference scripts
- **Use cases**: Tuning performance with Docker `--cpus` constraints, manual thread control
- **Example**:
  ```bash
  export PIPER_INTRA_THREADS=2
  ```

### ONNX_RUNTIME_SHARED_LIBRARY_PATH
- **Description**: Path to the ONNX Runtime shared library (`libonnxruntime.so` / `libonnxruntime.dylib`). Required for Go integration tests and applications.
- **Used by**: Go (piperplus)
- **Example**:
  ```bash
  export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/usr/lib/libonnxruntime.so
  ```

### PIPER_PHONEMIZE_DEBUG
- **Description**: Enable debug output for the legacy bundled piper-phonemize module
- **Status**: **Legacy / preprocessing only** — only recognized by `src/piper_phonemize_bundled/` (used by `preprocess.py` for eSpeak-based phoneme types). Not available in the main Python inference path (`src/python_run/`) or any other runtime.
- **Used by**: Legacy preprocessing pipeline (`preprocess.py`) only
- **Values**: Any non-empty value enables debug output
- **Example**:
  ```bash
  export PIPER_PHONEMIZE_DEBUG=1
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
echo "こんにちは" | piper --model ja_JP-model.onnx --output_file hello.wav
```

### Custom dictionary location
```bash
# Windows
set OPENJTALK_DICTIONARY_PATH=C:\my-dictionary
echo "テスト" | piper --model ja_JP-model.onnx --output_file test.wav

# Linux/macOS
export OPENJTALK_DICTIONARY_PATH=/opt/my-dictionary
echo "テスト" | piper --model ja_JP-model.onnx --output_file test.wav
```

### Offline mode (no downloads)
```bash
# Must have dictionary files already installed
export PIPER_OFFLINE_MODE=1
export OPENJTALK_DICTIONARY_PATH=/path/to/existing/dictionary
echo "オフライン" | piper --model ja_JP-model.onnx --output_file offline.wav
```

## Precedence Order

Environment variables are checked in the following order:
1. User-specified paths (OPENJTALK_DICTIONARY_PATH, etc.)
2. System-installed locations (/usr/share/*, /usr/local/share/*)
3. Auto-download to user data directory (if enabled)

## Troubleshooting

### Dictionary not found
1. Check if `PIPER_AUTO_DOWNLOAD_DICT=0` is set
2. Verify `OPENJTALK_DICTIONARY_PATH` points to valid directory
3. Ensure dictionary files exist (sys.dic, unk.dic, etc.)

### Download failures
1. Check internet connection
2. Verify `PIPER_OFFLINE_MODE` is not set to 1
3. Check write permissions to data directory
4. Look for proxy/firewall issues

### Wrong character encoding
1. Ensure terminal/console supports UTF-8
2. On Windows, use `chcp 65001` for UTF-8 support
3. Check file encoding when reading from files
