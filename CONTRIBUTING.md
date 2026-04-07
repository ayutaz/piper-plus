# Contributing to Piper

## Requirements

- Python 3.11, 3.12, or 3.13

## Development Setup

### Python Development

This project uses [Ruff](https://github.com/astral-sh/ruff) for Python linting and formatting.

#### Installing Development Dependencies

Dependencies are managed via [uv](https://docs.astral.sh/uv/) and defined as optional-dependencies in `pyproject.toml`:

```bash
# Development tools (linting, formatting, type checking)
uv pip install ".[dev]"

# Test dependencies only
uv pip install ".[test]"

# For src/python_run
uv pip install -r src/python_run/requirements_dev.txt
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
uv pip install pre-commit
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

## License Policy

piper-plus is licensed under the **MIT License**. All contributions and dependencies must be compatible with this license.

### Prohibited Dependencies

- **GPL / LGPL libraries are not allowed.** In particular, **espeak-ng** (GPL-3.0) must not be used as a dependency in any part of the project.
- Any library licensed under GPL-2.0, GPL-3.0, AGPL, or similar copyleft licenses is prohibited.

### Acceptable Licenses

When adding a new dependency, verify that it uses one of the following (or similarly permissive) licenses:

- MIT
- Apache-2.0
- BSD-2-Clause / BSD-3-Clause
- ISC
- Zlib

### Rationale

piper-plus is designed for commercial and embedded use. GPL dependencies would impose copyleft obligations ("GPL contamination") on downstream users, which is incompatible with the project's goals.

### What to Do

- Before submitting a PR that adds a new dependency, check its license.
- If you are unsure whether a license is compatible, ask in the PR or open an issue.

## Adding New Language Support

piper-plus supports multiple languages via rule-based G2P (grapheme-to-phoneme) modules. If you want to add support for a new language, follow these guidelines.

### Preferred Approach

- **Rule-based G2P with no external dependencies** is strongly preferred. Languages like Spanish, French, Portuguese, and Swedish use purely rule-based phonemizers with zero runtime dependencies.
- If an external library is necessary, its license **must** be MIT / Apache-2.0 / BSD compatible (see License Policy above).

### Implementation Checklist

At minimum, provide a **Python** implementation. Ideally, implement across all four platforms:

| Platform | Location | Notes |
|----------|----------|-------|
| Python | `src/python/g2p/piper_plus_g2p/<lang>.py` | Required |
| Rust (G2P) | `src/rust/piper-plus-g2p/src/<lang>.rs` | Recommended |
| Rust (Engine) | `src/rust/piper-core/src/phonemize/<lang>.rs` | Recommended (inference engine side) |
| C# | `src/csharp/PiperPlus.Core/Phonemize/<Lang>Phonemizer.cs` | Recommended |
| Go | `src/go/phonemize/<lang>.go` | Recommended |
| WASM (JS) | `src/wasm/g2p/src/<lang>/` | Optional |

Each implementation should:

1. Implement the phonemizer interface / abstract base class for the platform.
2. Register the language code in the language registry.
3. Include unit tests with reasonable coverage.
4. Produce consistent phoneme output across platforms (use the cross-platform CI as a reference).

### Reference

See existing implementations (e.g., `spanish.py`, `french.py`) for examples of rule-based phonemizers with no external dependencies.

## Pull Requests

1. Create a feature branch from `dev`
2. Make your changes
3. Run linting and tests
4. Submit a PR to the `dev` branch
5. Ensure all CI checks pass