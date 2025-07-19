# Piper Python Requirements

This directory contains the Python package requirements for Piper TTS.

## File Structure

- **requirements.txt** - Core dependencies needed to run Piper TTS
- **requirements_dev.txt** - Development dependencies (includes requirements.txt)
- **requirements_test.txt** - Testing dependencies for CI/CD (includes requirements.txt)

## Installation

### Using uv (Recommended - Fast)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# For Training/Inference
uv pip install -r requirements.txt

# For Development
uv pip install -r requirements_dev.txt

# For Testing Only
uv pip install -r requirements_test.txt
```

### Using pip (Traditional)

```bash
# For Training/Inference
pip install -r requirements.txt

# For Development
pip install -r requirements_dev.txt

# For Testing Only
pip install -r requirements_test.txt
```

## Notes

- Always use the requirements files in this directory (`/piper/src/python/`) for installations.
- Python 3.8+ is required for PyTorch Lightning 2.x compatibility.
- For GPU support, install PyTorch with appropriate CUDA version after installing base requirements.

## Dependency Highlights

- **PyTorch Lightning 2.x** - Modern training framework
- **PyTorch 2.x** - Deep learning framework
- **pyopenjtalk-plus** - Japanese TTS support
- **piper-phonemize** - Phoneme conversion