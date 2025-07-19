# Using uv with Piper TTS

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver, written in Rust.

## Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pip
pip install uv
```

## Creating Virtual Environment

```bash
# Create a new virtual environment
uv venv

# Activate it
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

## Installing Dependencies

### For Training/Inference

```bash
# Using requirements.txt
uv pip install -r src/python/requirements.txt

# Or sync from pyproject.toml
uv pip sync src/python/requirements.txt
```

### For Development

```bash
# Install all dev dependencies
uv pip install -r src/python/requirements_dev.txt

# Or install with optional dependencies
uv pip install -e ".[dev]"
```

### For Testing Only

```bash
uv pip install -r src/python/requirements_test.txt
```

## Benefits of using uv

- **Speed**: 10-100x faster than pip
- **Reliability**: Better dependency resolution
- **Compatibility**: Drop-in replacement for pip
- **Memory efficient**: Lower memory usage

## Common Commands

```bash
# Install a package
uv pip install torch

# Upgrade a package
uv pip install --upgrade pytorch-lightning

# Show installed packages
uv pip list

# Freeze current environment
uv pip freeze > requirements-frozen.txt

# Compile requirements (resolve without installing)
uv pip compile src/python/requirements.txt -o requirements-locked.txt
```

## Working with CUDA

For GPU support with PyTorch:

```bash
# Install PyTorch with CUDA 11.8
uv pip install torch --index-url https://download.pytorch.org/whl/cu118

# Install PyTorch with CUDA 12.1
uv pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## Troubleshooting

If you encounter issues:

1. Clear uv cache:
   ```bash
   uv cache clean
   ```

2. Use verbose mode for debugging:
   ```bash
   uv pip install -v -r requirements.txt
   ```

3. Force reinstall:
   ```bash
   uv pip install --force-reinstall -r requirements.txt
   ```