# Contributing to Piper

## Requirements

- Python 3.11 or higher

## Development Setup

### Python Development

This project uses [Ruff](https://github.com/astral-sh/ruff) for Python linting and formatting.

#### Installing Development Dependencies

```bash
# For src/python
pip install -r src/python/requirements_dev.txt

# For src/python_run
pip install -r src/python_run/requirements_dev.txt

# For tests
pip install -r src/python/requirements_test.txt
```

#### Running Ruff

```bash
# Check for linting issues
ruff check

# Auto-fix issues
ruff check --fix

# Check formatting
ruff format --check

# Auto-format code
ruff format
```

#### Pre-commit Hook (Optional)

To automatically run Ruff before each commit:

```bash
pip install pre-commit
pre-commit install
```

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.5
    hooks:
      - id: ruff
        args: [ --fix ]
      - id: ruff-format
```

## Code Style

- Python code follows PEP 8 with a line length of 88 characters (Black default)
- Use type hints where possible
- Write docstrings for all public functions and classes
- Keep functions focused and modular

## Testing

Run tests before submitting PRs:

```bash
# Run tests for piper_train
cd src/python
python -m pytest

# Run tests for piper runtime
cd src/python_run
python -m pytest
```

## Pull Requests

1. Create a feature branch from `dev`
2. Make your changes
3. Run linting and tests
4. Submit a PR to the `dev` branch
5. Ensure all CI checks pass