# CLI Usage

This guide covers detailed usage of the C++ CLI (`piper-plus`), including command-line options, JSON input format, model management, environment variables, and Windows helper scripts.

## C++ CLI

### Direct Text Input (Recommended)

The `--text` option allows direct text input without piping:

```sh
# Simple text-to-speech
./bin/piper-plus --model model.onnx --text "Hello, how are you?" -f output.wav

# Japanese text (no encoding issues on Windows)
bin\piper-plus.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# With speaker selection
./bin/piper-plus --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

### Pipe Input

```sh
# Basic usage
echo "Hello world" | ./bin/piper-plus --model en_model.onnx --output_file output.wav

# Streaming (low latency)
echo "Long text..." | ./bin/piper-plus --model en_model.onnx --output_file output.wav --streaming

# GPU inference
echo "Hello" | ./bin/piper-plus --model en_model.onnx --use-cuda --output_file output.wav

# Phoneme timing output (for lip-sync, subtitles)
echo "Hello world" | ./bin/piper-plus --model en_model.onnx -f speech.wav --output-timing timing.json

# Custom dictionary
echo "DockerとGitHubを使います" | ./bin/piper-plus --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Inline phoneme input
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper-plus --model en_model.onnx -f output.wav

# Raw phoneme input
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper-plus --model en_model.onnx --raw-phonemes -f output.wav

# Streaming raw audio output
echo 'Long text...' | ./bin/piper-plus --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Key options:

| Option | Description | Default |
|---|---|---|
| `--model PATH\|NAME` | Model file path, or model name (auto-resolves downloaded models) | - |
| `--config/-c PATH` | Model config file path (auto-detected if not specified) | - |
| `--text TEXT` | Direct text input (no piping required) | - |
| `--output_file/-f FILE` | Output WAV file path | - |
| `--output_dir/-d DIR` | Output directory (one WAV per utterance) | - |
| `--output-raw` | Output raw PCM audio (no WAV header) | off |
| `--streaming` | Chunk-based streaming mode | off |
| `--use-cuda` | Enable CUDA GPU inference | off |
| `--gpu-device-id NUM` | GPU device ID | 0 |
| `--language/-l LANG` | Language code(s) (e.g. `ja`, `en`, `ja-en-zh`) | - |
| `--length-scale VAL` | Speech speed (smaller = faster) | 1.0 |
| `--noise-scale VAL` | Audio variation control | 0.4 |
| `--noise-w VAL` | Phoneme duration variation | 0.5 |
| `--sentence-silence SEC` | Silence between sentences | 0.2 |
| `--speaker NUM` | Speaker number for multi-speaker models | 0 |
| `--phoneme-silence PHONEME SEC` | Silence duration for specific phonemes | - |
| `--raw-phonemes` | Interpret input as phonemes | off |
| `--output-timing FILE` | Phoneme timing output (JSON/TSV) | - |
| `--timing-format FORMAT` | Timing output format (`json` or `tsv`) | json |
| `--custom-dict FILE` | Custom dictionary (comma-separated for multiple) | - |
| `--json-input` | JSON input mode | off |
| `--list-models [LANG]` | List available models | - |
| `--download-model NAME` | Download a model | - |
| `--model-dir DIR` | Model download directory | - |
| `--test-mode` | Verify phoneme IDs without running ONNX inference | off |
| `--debug` | Enable debug logging | off |
| `--quiet/-q` | Suppress non-essential output | off |
| `--version` | Show version | - |

Run `piper-plus --help` for all options.

## JSON Input

Use `--json-input` flag for JSON input:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

## Model Management

### List Available Models

```bash
# List all available models
./bin/piper-plus --list-models

# Filter by language
./bin/piper-plus --list-models ja
./bin/piper-plus --list-models en
```

### Download Models

```bash
# Download a model by name (aliases also work)
./bin/piper-plus --download-model tsukuyomi
./bin/piper-plus --download-model en_US-lessac-medium

# Specify download directory
./bin/piper-plus --download-model tsukuyomi --model-dir /path/to/models

# After download, use by model name (no full path needed)
./bin/piper-plus --model tsukuyomi --text "こんにちは"
```

## Environment Variables (C++ CLI)

| Variable | Description | Example |
|---|---|---|
| `PIPER_PLUS_DEFAULT_MODEL` | Default model path when `--model` is not specified | `/path/to/model.onnx` |
| `PIPER_PLUS_DEFAULT_CONFIG` | Default config path when `--config` is not specified | `/path/to/config.json` |
| `PIPER_PLUS_MODEL_DIR` | Directory for downloaded models | `~/.local/share/piper-plus/models` |
| `PIPER_PLUS_GPU_DEVICE_ID` | GPU device ID for CUDA | `0` |

## Helper Scripts (Windows)

For Windows users, helper scripts are provided in the `scripts/` directory:

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Command Prompt:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

→ Back to [README](../../../README_EN.md)
