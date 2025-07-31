# Piper WebUI Usage Guide

## Quick Start

### Requirements

- Python 3.11 or higher
- Piper TTS installed
- ONNX models downloaded

### Installation

```bash
# Install WebUI dependencies
pip install -r src/python_run/requirements_webui.txt
```

### Running the WebUI

```bash
# From the piper directory
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

- `--data-dir`: Directory containing ONNX models (default: ./models)
- `--host`: Host to bind to (default: 127.0.0.1)
- `--port`: Port to run on (default: 7860)
- `--share`: Create a public shareable link (Gradio feature)
- `--debug`: Enable debug logging

## Features

### Inference Tab

1. **Model Selection**: Automatically detects all .onnx models in the data directory
2. **Template System**: Language-specific templates for quick testing
   - English, Japanese, German, French templates
   - Custom text input option
3. **Advanced Settings**:
   - Speaker ID (for multi-speaker models)
   - Speed control (0.5-2.0x)
   - Noise scale (expressiveness)
   - Noise width
4. **Audio Output**: Play and download generated speech

### Training Tab

1. **Dataset Configuration**:
   - Specify dataset directory path
   - Automatic validation of dataset structure
   - Expected format: metadata.csv with audio files

2. **Training Settings**:
   - Base model selection or new model training
   - Number of speakers configuration
   - Quality selection (low/medium/high)

3. **Advanced Parameters**:
   - Batch size, learning rate, epochs
   - Checkpoint intervals
   - Validation split ratio

## Examples

### Basic Usage

1. Start the WebUI:
   ```bash
   python -m piper.webui --data-dir ../../test/models
   ```

2. Open browser at http://localhost:7860

3. Select a model from the dropdown

4. Choose a template or enter custom text

5. Click "Generate Speech"

### Using Templates

Templates automatically switch based on the selected model's language:
- Japanese models get Japanese templates
- English models get English templates
- etc.

### Docker Usage

```bash
# Build Docker image
docker build -t piper-webui -f docker/webui/Dockerfile .

# Run container
docker run -p 7860:7860 -v ./models:/models piper-webui

# Or use the helper script
cd docker/webui
./run.sh

# Using docker-compose
cd docker/webui
docker-compose up
```

#### Environment Variables for Docker

- `MODELS_DIR`: Path to models directory (default: ./models)
- `OUTPUT_DIR`: Path to output directory (default: ./output)
- `PORT`: WebUI port (default: 7860)

## Troubleshooting

### No models found
- Ensure the `--data-dir` points to a directory with .onnx files
- Model files must have corresponding .onnx.json config files

### Import errors
- Install requirements: `pip install -r requirements_webui.txt`
- For full functionality, install piper: `pip install -e .`

### Port already in use
- Use a different port: `--port 8080`
- Check for other Gradio instances

## Future Enhancements

- Real-time streaming synthesis
- Model download integration
- Batch processing with progress bars
- Training progress visualization
- TensorBoard integration