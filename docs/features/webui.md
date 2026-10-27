# Piper-Plus WebUI

Gradio-based web interface for piper-plus inference, with a legacy local training tab.

There are two separate WebUI implementations: a **local development** version with inference and training tabs, and a **Docker** version for standalone inference deployment. The local training tab currently passes obsolete arguments to the training CLI; use the [training guide](../guides/training/training-guide.md) for training.

## Quick Start (Local)

### Requirements

- Python 3.11+ and uv
- A source checkout with the workspace dependencies installed
- ONNX models downloaded

### Installation

```bash
# From the repository root, install workspace and WebUI dependencies
uv sync
uv sync --project environments/webui --locked
```

### Running

```bash
uv run --project environments/webui --no-sync python -m piper_plus.webui --data-dir test/models

# Or with custom settings
uv run --project environments/webui --no-sync python -m piper_plus.webui \
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
- **言語指定**: local の `Auto` と明示的な言語選択、Docker の言語選択を使用。実際の出力言語はモデルの学習済み言語・設定に依存
- **話者選択**: マルチスピーカーモデルでの話者切り替え
- **Template System**: Language-specific templates (English, Japanese, Chinese, Spanish, French, Portuguese)
- **Speed Control**: 0.5-2.0x
- **Noise Parameters**: Expressiveness and phoneme width variation
- **Audio Output**: Play and download generated speech

### Training Tab (local only, legacy)

- Validation of a preprocessed dataset (`config.json` and `dataset.jsonl`):
  utterance count, speaker count, symbol count, language and sample rate
- Start: a new model, resuming a run, or fine-tuning from a base model
- Quality selection (`x-low` / `medium` / `high`, the `piper_train --quality` choices)
- Training parameters (batch size, learning rate, epochs, checkpoint interval, validation split)
- Start/Stop controls with real-time log display

`training_manager.py` starts `python -m piper_train` with these flags:

| UI field | Flag sent |
|----------|-----------|
| Dataset Directory Path | `--dataset-dir` |
| Model Quality | `--quality` |
| Batch Size | `--batch-size` |
| Learning Rate | `--base_lr` |
| Number of Epochs | `--max_epochs` |
| Checkpoint Interval (epochs) | `--checkpoint-epochs` |
| Validation Split | `--validation-split` |
| Output Directory | `--default_root_dir` |
| Start = Resume training, Checkpoint | `--resume_from_checkpoint` |
| Start = Fine-tune from a base model, Checkpoint | `--resume-from-multispeaker-checkpoint` |

It also sends `--accelerator auto` and `--devices 1`. The speaker count is
read from the dataset's `config.json`.

Start modes:

- **New model**: trains from scratch.
- **Resume training**: continues a run from one of its Lightning `.ckpt`
  files (optimizer state and epoch counter included). The Checkpoint list
  shows the `.ckpt` files under the Output Directory, newest first. Set
  Number of Epochs above the epoch the checkpoint reached.
- **Fine-tune from a base model**: trains a single-speaker voice from a
  multi-speaker base `.ckpt`, such as the public
  [`zs-v1` base](../guides/development/pretrained-models.md). `piper_train`
  loads the weights only (training starts at epoch 0), removes the speaker
  embedding table and freezes the duration predictor. The learning rate field
  changes to `2e-5`, the fine-tuning rate of the
  [training guide](../guides/training/training-guide.md).

Before it starts `piper_train`, the tab checks:

- The dataset directory has `config.json` and `dataset.jsonl`. A raw
  LJSpeech-style folder (`metadata.csv` + `wavs/`) is rejected with the
  `python -m piper_train.preprocess` command to run first.
- Resume and fine-tuning get an existing `.ckpt`. An ONNX voice cannot be
  trained further.
- Fine-tuning gets a single-speaker dataset (`--single-speaker` at
  preprocessing).
- When the base checkpoint has a `config.json` next to it (as
  `releases/zs-v1` does), the dataset's `phoneme_id_map` equals the base's.
  Otherwise the tab asks to align the dataset first:

```bash
uv run python scripts/prepare_single_speaker_finetune.py \
  --input-dir /path/to/preprocessed/dataset \
  --base-config /path/to/base/config.json \
  --output-dir /path/to/aligned/dataset
```

The same symbol count does not mean the same phoneme IDs; training an
unaligned dataset maps the phonemes to the wrong embeddings.

Neither WebUI exposes a reference-audio/speaker-embedding input for the public
`zs-v1/base.onnx`. Use a fixed-voice model for these UI examples; use the
[pretrained-model guide](../guides/development/pretrained-models.md) for
reference-conditioned Zero-Shot inference. The separate
[Hugging Face Space demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
has a Zero-shot tab that conditions the pinned `zs-v1` base on an
uploaded or recorded reference clip.

## Architecture

There are two independent WebUI implementations:

**Local development version** (`src/python_run/piper_plus/webui.py`) -- uses `PiperVoice` runtime for inference and includes a training management tab via `training_manager.py`.

**Docker version** (`docker/webui/app.py`) -- a standalone Gradio app that uses `piper_train.infer_onnx` and `piper_train.ort_utils` directly for ONNX inference. Inference only, no training tab. Includes session caching and warmup via `create_session_with_cache`.

```text
src/python_run/piper_plus/
├── webui.py              # Local WebUI (inference + training)
├── training_manager.py   # Training management backend
└── sample_texts.py       # Sample text collections

src/python_run/requirements_webui.txt  # WebUI dependencies (outside the package)

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
- **Two implementations**: Local version depends on the `piper-plus` runtime package; Docker version depends on `piper_train` directly, avoiding the runtime dependency

## Docker Usage

The Docker image uses `docker/webui/app.py` (not the local `webui.py`).

```bash
# Build
docker build -t piper-webui -f docker/webui/Dockerfile .

# Run
docker run -p 7860:7860 -v ./models:/models piper-webui

# Or Compose (from the repository root)
docker compose -f docker/webui/docker-compose.yml up --build
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODELS_DIR` | `./models` | Host path to model directory (docker-compose volume) |
| `OUTPUT_DIR` | `./output` | Host path to output directory (docker-compose volume) |
| `PIPER_PLUS_MODEL` | (none) | Specific model to load (passed to entrypoint) |
| `PIPER_PLUS_MODEL_DIR` | `/models` | Model directory inside the container |
| `PIPER_PLUS_OUTPUT_DIR` | `/output` | Output directory inside the container (used by entrypoint.sh) |

> **Note:** `docker-compose.yml` sets `GRADIO_SERVER_NAME` and `GRADIO_SERVER_PORT`, but `app.py` launches Gradio with explicit `--host` / `--port` CLI args (defaults: `0.0.0.0` and `7860`), so those env vars have no effect. To change the bind address or port, override the entrypoint command args instead.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No models found | Check `--data-dir` path (local) or volume mount (Docker); ensure .onnx and .onnx.json pairs exist |
| Import errors | `uv sync --project environments/webui --locked` |
| Port in use | Use `--port 8080` (local) or change the port mapping in docker-compose |
| Docker issues | Check volume mounts and port availability |

## UI と学習環境の分離

`environments/webui/uv.lock` は Gradio の HF Hub 1.x を固定します。root の Transformers 4.x 学習環境（HF Hub <1）へ `requirements_webui.txt` を直接インストールしないでください。

Training タブから学習を起動する場合は、root で `uv sync --extra train` を実行した後、UI 起動前に `PIPER_PLUS_TRAINING_PYTHON` を root `.venv` の Python の絶対パスへ設定します。PowerShell では次を使用します。

```powershell
$env:PIPER_PLUS_TRAINING_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
uv run --project environments/webui --no-sync python -m piper_plus.webui
```

Linux/macOS では `.venv/bin/python` の絶対パスを同じ環境変数へ設定します。
