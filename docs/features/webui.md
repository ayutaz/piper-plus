# Piper WebUI

Gradio-based web interface for piper-plus inference and training.

There are two separate WebUI implementations: a **local development** version with inference and training tabs, and a **Docker** version optimized for standalone inference deployment.

## Quick Start (Local)

### Requirements

- Python 3.11+
- piper-plus installed
- ONNX models downloaded

### Installation

```bash
# Install WebUI dependencies
uv pip install -r src/python_run/requirements_webui.txt

# For training functionality (optional)
uv pip install ".[train]"
```

### Running

```bash
cd src/python_run
python -m piper.webui --data-dir ../../test/models

# Or with custom settings
python -m piper.webui \
  --data-dir /path/to/models \
  --host 0.0.0.0 \
  --port 8080 \
  --debug
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--data-dir` | `./models` | Directory containing ONNX models |
| `--host` | `127.0.0.1` | Host to bind to |
| `--port` | `7860` | Port to run on |
| `--share` | off | Create a public Gradio link |
| `--debug` | off | Enable debug logging |

## Features

### Inference Tab (both implementations)

- **Model Selection**: Auto-detects all .onnx models in the data directory
- **6言語マルチリンガルモデル対応** (ja, en, zh, es, fr, pt)
- **言語自動検出**: テキスト入力から言語を自動判定
- **話者選択**: マルチスピーカーモデルでの話者切り替え
- **Template System**: Language-specific templates (English, Japanese, Chinese, Spanish, French, Portuguese)
- **Speed Control**: 0.5-2.0x
- **Noise Parameters**: Expressiveness and phoneme width variation
- **Audio Output**: Play and download generated speech

### Training Tab (local only)

- Dataset path validation with structure check
- Base model selection or new model training
- Quality selection (low/medium/high)
- Training parameters (batch size, learning rate, epochs)
- Start/Stop controls with real-time log display

## Architecture

There are two independent WebUI implementations:

**Local development version** (`src/python_run/piper/webui.py`) -- uses `PiperVoice` runtime for inference and includes a training management tab via `training_manager.py`.

**Docker version** (`docker/webui/app.py`) -- a standalone Gradio app that uses `piper_train.infer_onnx` and `piper_train.ort_utils` directly for ONNX inference. Inference only, no training tab. Includes session caching and warmup via `create_session_with_cache`.

```
src/python_run/piper/
├── webui.py              # Local WebUI (inference + training)
├── training_manager.py   # Training management backend
├── sample_texts.py       # Sample text collections
└── requirements_webui.txt

docker/webui/
├── app.py                # Docker WebUI (inference only, standalone)
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── run.sh
```

### Key Design Decisions

- **Gradio Framework**: ML-optimized UI components with built-in audio playback
- **Language Detection**: Automatic model-to-language mapping with template adaptation
- **Lazy Model Loading**: Models loaded on synthesis, not on startup
- **Two implementations**: Local version depends on the `piper` runtime package; Docker version depends on `piper_train` directly, avoiding the runtime dependency

## Docker Usage

The Docker image uses `docker/webui/app.py` (not the local `webui.py`).

```bash
# Build
docker build -t piper-webui -f docker/webui/Dockerfile .

# Run
docker run -p 7860:7860 -v ./models:/models piper-webui

# Or docker-compose
cd docker/webui && docker-compose up
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODELS_DIR` | `./models` | Host path to model directory (docker-compose volume) |
| `OUTPUT_DIR` | `./output` | Host path to output directory (docker-compose volume) |
| `PIPER_MODEL` | (none) | Specific model to load (passed to entrypoint) |
| `PIPER_MODEL_DIR` | `/models` | Model directory inside the container |
| `PIPER_OUTPUT_DIR` | `/output` | Output directory inside the container (used by entrypoint.sh) |

> **Note:** `docker-compose.yml` sets `GRADIO_SERVER_NAME` and `GRADIO_SERVER_PORT`, but `app.py` launches Gradio with explicit `--host` / `--port` CLI args (defaults: `0.0.0.0` and `7860`), so those env vars have no effect. To change the bind address or port, override the entrypoint command args instead.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No models found | Check `--data-dir` path (local) or volume mount (Docker); ensure .onnx and .onnx.json pairs exist |
| Import errors | `uv pip install -r src/python_run/requirements_webui.txt` |
| Port in use | Use `--port 8080` (local) or change the port mapping in docker-compose |
| Docker issues | Check volume mounts and port availability |
