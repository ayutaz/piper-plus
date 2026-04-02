# Contributing to piper-g2p

## Development Setup

```bash
cd src/python/g2p
uv sync --extra all --extra dev
uv run pytest                    # run the full test suite
uv run ruff check piper_plus_g2p/    # lint
uv run mypy piper_plus_g2p/          # type-check
```

## How to Add a New Language

1. **Create `piper_plus_g2p/<lang>.py`** -- subclass `Phonemizer` (from `piper_plus_g2p.base`).
2. **Implement `phonemize_with_prosody()`** -- return `(tokens, prosody)` where
   `tokens` is a list of IPA strings and `prosody` is a list of `ProsodyInfo | None`.
3. **Create `tests/test_<lang>.py`** with at least 4 tests: basic phonemization,
   prosody values, empty input, and edge cases. If the language needs an optional
   dependency, add a `requires_<lang>` skip marker in `tests/conftest.py`.
4. **Update `pyproject.toml`** -- add the language code under
   `[project.optional-dependencies]` and include any new dependency in the `all` extra.
5. **Register the phonemizer** -- add a `(code, module, class)` tuple to
   `_LANGUAGE_TABLE` in `piper_plus_g2p/registry.py`, then open a PR.

## Plugin System (entry_points)

External packages can register phonemizers without modifying this repo.
In your package's `pyproject.toml`:

```toml
[project.entry-points."piper_plus_g2p.phonemizers"]
xx = "my_package:MyPhonemizer"
```

The registry discovers these at import time via `importlib.metadata.entry_points`.

## Code Style

- **Formatter/linter**: ruff (line-length 88, target Python 3.11).
- **Type checking**: mypy with `ignore_missing_imports = true`.
- Keep each language module self-contained; shared utilities go in `base.py`.

## Testing

- Framework: **pytest**
- Skip markers: `requires_ja`, `requires_en`, `requires_zh`, `requires_ko`
  (defined in `tests/conftest.py`) for tests that need optional dependencies.
- CI runs on 3 OS (Linux, macOS, Windows) x 2 Python versions.

## Pull Requests

- One language per PR when possible.
- Include before/after phonemization examples in the PR description.
- All CI checks must pass before merge.
