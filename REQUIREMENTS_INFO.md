# Requirements Files Information

## Requirements Files Location

All requirements files are located in `src/python/`:

- `src/python/requirements.txt` - Core dependencies for training and inference
- `src/python/requirements_dev.txt` - Development environment setup (includes requirements.txt)
- `src/python/requirements_test.txt` - Testing dependencies (includes requirements.txt)

## Installation

### Using uv (Recommended - Fast)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# For training/inference
cd src/python
uv pip install -r requirements.txt

# For development
cd src/python
uv pip install -r requirements_dev.txt
```

### Using pip

```bash
# For training/inference
cd src/python
pip install -r requirements.txt

# For development
cd src/python
pip install -r requirements_dev.txt
```

## Python Version

Python 3.8 or higher is required for PyTorch Lightning 2.x compatibility.

## Note

A backup of the old root requirements.txt is available at `requirements.txt.backup` for reference.