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

### Python

- Formatter: `ruff format`
- Linter: `ruff check`
- No Black, no isort (Ruff handles both)
- Line length: 88 characters
- Use type hints where possible
- Write docstrings for all public functions and classes
- Keep functions focused and modular

### Rust

- `cargo fmt` and `cargo clippy`

### C#

- Follow existing code style (no editorconfig enforced yet)

### Go

- `gofmt` and `go vet`

## Running Tests

Run tests before submitting PRs. Each platform has its own test suite:

### Python

```bash
# piper_train tests
uv run pytest src/python/tests/ -v

# G2P tests
uv run pytest src/python/g2p/tests/ -v

# piper runtime tests
cd src/python_run && uv run python -m pytest
```

### Rust

```bash
cd src/rust && cargo test --workspace
```

### C#

```bash
dotnet test src/csharp/PiperPlus.Core.Tests/
```

### C++ (requires build)

```bash
mkdir build && cd build && cmake .. && cmake --build .
ctest --output-on-failure
```

### Go

```bash
cd src/go && go test ./...
```

### WASM/npm

```bash
cd src/wasm/openjtalk-web && node --test test/js/
```

## License Policy

piper-plus is MIT licensed. **All contributions must be compatible with the MIT license.**

### Allowed Licenses

When adding a new dependency, verify that it uses one of the following (or similarly permissive) licenses:

- MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Zlib, CC0-1.0

### Prohibited Licenses

The following licenses are **not allowed**:

- GPL, LGPL, AGPL (any version)
- SSPL, BSL, Commons Clause

### espeak-ng Policy

piper-plus does **NOT** depend on espeak-ng. This is a deliberate design decision to avoid GPL contamination. **Do not introduce espeak-ng as a dependency in any form** (direct, transitive, or optional).

### Rationale

piper-plus is designed for commercial and embedded use. GPL dependencies would impose copyleft obligations ("GPL contamination") on downstream users, which is incompatible with the project's goals.

### Checking Dependencies

Before adding a new dependency, verify its license:

```bash
# Python
pip-licenses --from=mixed --with-system | grep <package>

# Rust
cargo license -d | grep <crate>

# npm
npx license-checker --summary
```

If you are unsure whether a license is compatible, ask in the PR or open an issue.

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

## Contributing Models

If you want to contribute a **trained model** (rather than code), see [CONTRIBUTING_MODELS.md](CONTRIBUTING_MODELS.md) for the full guide on model submission, quality requirements, and licensing.

## Your First Pull Request

1. Fork the repository and create a branch from `dev`
2. Make your changes in the appropriate `src/<language>/` directory
3. Add or update tests
4. Run the relevant test suite (see [Running Tests](#running-tests))
5. Ensure `ruff check` and `ruff format --check` pass for Python changes
6. Create a PR against the `dev` branch
7. Ensure all CI checks pass

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/ayutaz/piper-plus/labels/good%20first%20issue) for beginner-friendly tasks.

## Pull Requests

1. Create a feature branch from `dev`
2. Make your changes
3. Run linting and tests
4. Submit a PR to the `dev` branch
5. Ensure all CI checks pass

## Package Versioning Policy

piper-plus ships **as several independent packages**, each released and versioned on its own schedule. There is **no single project-wide version number** — the value displayed in the README header (e.g. "v1.12.0") tracks the **PyPI** package only.

| Package | Registry | Source | Tag prefix | Versioning |
|---|---|---|---|---|
| `piper-plus` (Python TTS) | PyPI | `src/python/`, `src/python_run/` | `v<X.Y.Z>` (e.g. `v1.12.0`) | SemVer |
| `piper-plus-g2p` (Python G2P) | PyPI | `src/python/g2p/` | `g2p-py-v<X.Y.Z>` | SemVer |
| `piper-plus-cli` / `piper-plus` (Rust crate) | crates.io | `src/rust/` | `rust-v<X.Y.Z>` | SemVer |
| `PiperPlus.Core` / `PiperPlus.Cli` (NuGet) | NuGet | `src/csharp/` | `csharp-v<X.Y.Z>` | SemVer |
| `piper-plus` (npm) | npm | `src/wasm/openjtalk-web/` | `npm-v<X.Y.Z>` (e.g. `npm-v0.5.0`) | SemVer |
| `@piper-plus/g2p` (npm) | npm | `src/wasm/g2p/` | `wasm-g2p-v<X.Y.Z>` (e.g. `wasm-g2p-v0.4.0`) | SemVer |
| `github.com/ayutaz/piper-plus/src/go` | Go module | `src/go/` | (none — uses commit SHA via `go get`) | Go module versioning |
| C API shared library (`libpiper_plus`) | GitHub Releases | `src/cpp/` | `shared-lib-v<X.Y.Z>` | SemVer |

### Why independent versioning

- A bug fix in the Rust runtime should not force a Python/PyPI release.
- A breaking change in the npm package (e.g. removing HTS voice support, npm 0.3.0) should not bump the entire project to a new major.
- Per-language ecosystems have different stability expectations (e.g. crates.io is stricter about breaking changes than internal Python releases).

### Ground rules

1. Each package keeps its own `CHANGELOG.md` (root `CHANGELOG.md` mirrors the **Python** package + project-wide highlights).
2. Each release has a tag matching the prefix scheme above; do not reuse a generic `v<X.Y.Z>` tag for non-Python releases.
3. Cross-package compatibility is documented in the relevant package README (e.g. npm `piper-plus` declares its required `@piper-plus/g2p` range in `package.json`).
4. When making a change that affects multiple packages (e.g. adding a new language), bump each affected package's version individually and document the relationship in the root CHANGELOG.

### Release order (dependency-aware)

Some packages depend on others published to the **same registry**. Publishing them in the wrong order breaks fresh installs.

| Registry | Required publish order | Reason |
|---|---|---|
| npm | `@piper-plus/g2p` → `piper-plus` | `piper-plus/package.json` lists `@piper-plus/g2p` as a runtime dependency, so the g2p version must already exist on npm. |
| crates.io | `piper-plus-g2p` → `piper-plus` (core) → `piper-plus-cli` | `piper-plus` depends on `piper-plus-g2p`; `piper-plus-cli` depends on `piper-plus`. The `dev-create-release.yml` automation already handles this with `sleep 30` between steps. |
| PyPI | `piper-plus-g2p` → `piper-plus` → `piper-tts-plus` (stub) | Same dependency chain. Manual Release workflow chains `publish_pypi` → `publish_pypi_stub`. |
| NuGet | `PiperPlus.Core` → `PiperPlus.Cli` | CLI references Core. |

**Manual operation needed for npm:** the GitHub Actions Manual Release workflow handles PyPI / NuGet / crates.io automatically, but **npm publishes are gated by separate tag triggers**: `g2p-wasm-ci.yml` listens on `wasm-g2p-v*` tags (publishes `@piper-plus/g2p`), and `npm-publish.yml` listens on `npm-v*` tags (publishes `piper-plus`). To publish a coordinated npm release:

```bash
# 1. Publish @piper-plus/g2p first (triggered by g2p-wasm-ci.yml)
git tag wasm-g2p-v0.4.0 <COMMIT>
git push origin wasm-g2p-v0.4.0

# 2. Wait for g2p-wasm-ci to finish publishing to npm
# 3. Then publish piper-plus (triggered by npm-publish.yml)
git tag npm-v0.6.0 <COMMIT>
git push origin npm-v0.6.0
```

Skipping step 1 will cause `npm install piper-plus@0.6.0` to fail with `notarget No matching version found for @piper-plus/g2p@^0.4.0`.