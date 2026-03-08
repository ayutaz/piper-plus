# WebUI Technical Design Document

## Overview

This document describes the technical implementation of the Gradio-based WebUI for Piper TTS, as implemented in Issue #114.

## Architecture

### Component Structure

```
src/python_run/piper/
├── webui.py           # Main WebUI application
├── sample_texts.py    # Sample text collections
└── requirements_webui.txt

docker/webui/
├── Dockerfile         # Container definition
├── docker-compose.yml # Orchestration config
└── run.sh            # Helper script
```

### Key Design Decisions

1. **Gradio Framework**
   - Chosen for ML-optimized UI components
   - Built-in audio playback/download
   - Minimal code for rich functionality
   - Active development and community

2. **Language Detection**
   - Automatic model-to-language mapping
   - Template system adapts to selected model
   - Fallback to English for unknown languages

3. **Docker Integration**
   - Multi-stage build for size optimization
   - Volume mounts for models and output
   - Health checks for production readiness

## Implementation Details

### Model Management

```python
def get_available_models(data_dir: Path) -> List[Tuple[str, str]]:
    """Scan directory for ONNX models with user-friendly names"""
    # Returns: [(display_name, model_path), ...]
```

- Automatic model detection from directory
- User-friendly naming (e.g., "Japanese (Medium)")
- Quality indicators from filename
- Alphabetical sorting for UX

### Template System

```python
TEMPLATES = {
    "en_US": {
        "greeting": "Hello! Welcome...",
        "news": "In today's news...",
        # ... more templates
    },
    "ja_JP": {
        "greeting": "こんにちは...",
        "announcement": "お客様各位...",
        # ... more templates
    }
}
```

- Language-specific template collections
- 10+ templates for English
- 12+ templates for Japanese
- Easy extension for new languages

### Example Management

- Automatic language matching for examples
- English texts → English models
- Japanese texts → Japanese models
- Graceful fallback if language model unavailable

## API Reference

### WebUI Launch

```python
python -m piper.webui [options]

Options:
  --data-dir PATH    Directory containing ONNX models
  --host HOST        Server host (default: 127.0.0.1)
  --port PORT        Server port (default: 7860)
  --share            Create public Gradio link
  --debug            Enable debug logging
```

### Gradio Interface

#### Inference Tab
- Text input with templates
- Model selection dropdown
- Speaker ID (multi-speaker models)
- Speed control (0.5-2.0x)
- Noise parameters
- Audio output with playback

#### Training Tab
- Dataset path validation
- Base model selection
- Training parameters
- Progress monitoring (placeholder)

## Testing Strategy

### Unit Tests
- Model detection
- Language identification
- Template application
- Sample text retrieval

### Integration Tests
- Interface creation
- Component interaction
- Error handling

### CI/CD Pipeline
- Multi-platform (Ubuntu, macOS, Windows)
- Python 3.11, 3.12
- Docker build verification

## Performance Considerations

1. **Model Loading**
   - Lazy loading on synthesis
   - No preloading to reduce memory

2. **UI Responsiveness**
   - Asynchronous synthesis
   - Progress indicators
   - Error boundaries

3. **Docker Optimization**
   - Multi-stage builds
   - Minimal runtime dependencies
   - Layer caching

## Security

1. **Input Validation**
   - Text length limits
   - Path traversal prevention
   - Model file verification

2. **Network Security**
   - Local-only by default
   - Optional public sharing
   - No authentication (local use)

## Future Enhancements

### Short Term
- Streaming synthesis
- Batch processing UI
- Model info display

### Medium Term
- Model download UI
- Training progress
- Multi-language UI

### Long Term
- Cloud deployment
- API authentication
- Plugin system

## Troubleshooting

### Common Issues

1. **No models found**
   - Check data-dir path
   - Ensure .onnx and .onnx.json pairs

2. **Import errors**
   - Install dependencies: `uv pip install -r src/python_run/requirements_webui.txt`
   - Python 3.11+ required

3. **Docker issues**
   - Check volume mounts
   - Verify port availability

## Contributing

To extend the WebUI:

1. Add new templates in `TEMPLATES` dict
2. Create new tabs with `gr.TabItem`
3. Add tests in `test_webui.py`
4. Update documentation

## References

- [Gradio Documentation](https://gradio.app)
- [Piper TTS Documentation](../README.md)
- [Issue #114](https://github.com/rhasspy/piper/issues/114)