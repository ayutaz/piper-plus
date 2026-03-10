# Piper WebUI

Gradio-based web interface for piper-plus inference and training.

## Quick Start

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

### Inference Tab

- **Model Selection**: Auto-detects all .onnx models in the data directory
- **Template System**: Language-specific templates (English, Japanese, German, French)
- **Speaker ID**: For multi-speaker models
- **Speed Control**: 0.5-2.0x
- **Noise Parameters**: Expressiveness and phoneme width variation
- **Audio Output**: Play and download generated speech

### Training Tab

- Dataset path validation with structure check
- Base model selection or new model training
- Quality selection (low/medium/high)
- Training parameters (batch size, learning rate, epochs)
- Start/Stop controls with real-time log display

## Architecture

```
src/python_run/piper/
├── webui.py           # Main WebUI application
├── sample_texts.py    # Sample text collections
└── requirements_webui.txt

docker/webui/
├── Dockerfile
├── docker-compose.yml
└── run.sh
```

### Key Design Decisions

- **Gradio Framework**: ML-optimized UI components with built-in audio playback
- **Language Detection**: Automatic model-to-language mapping with template adaptation
- **Lazy Model Loading**: Models loaded on synthesis, not on startup

## Docker Usage

```bash
# Build
docker build -t piper-webui -f docker/webui/Dockerfile .

# Run
docker run -p 7860:7860 -v ./models:/models piper-webui

# Or docker-compose
cd docker/webui && docker-compose up
```

Environment variables: `MODELS_DIR`, `OUTPUT_DIR`, `PORT`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No models found | Check `--data-dir` path; ensure .onnx and .onnx.json pairs exist |
| Import errors | `uv pip install -r src/python_run/requirements_webui.txt` |
| Port in use | Use `--port 8080` |
| Docker issues | Check volume mounts and port availability |
