# Fuzz / Property-Based Tests

This directory hosts Python `hypothesis` property tests for high-input-diversity
modules. They run in CI under `.github/workflows/fuzz-smoke.yml` on PRs that
touch the fuzz targets or any of the source modules listed in that workflow.

These tests are intentionally placed OUTSIDE the per-package `tests/` directories
(`src/python_run/tests/`, `src/python/g2p/tests/`) so that:

* the default `pytest` invocation of those packages is unchanged (no extra
  dependency on `hypothesis` for the regular unit-test run),
* a single dedicated CI job can collect and budget the slower property runs.

## Targets

| File | Module under test | Why |
|------|-------------------|-----|
| `test_ssml_fuzz.py` | `piper_plus_g2p.ssml.SSMLParser` | XML parse + regex fallback |
| `test_text_splitter_fuzz.py` | `piper_plus.text_splitter.split_sentences` | Unicode boundary edge cases |
| `test_pua_fuzz.py` | `piper_plus_g2p.encode.pua.map_token` | token -> codepoint mapping invariants |

## Running locally

```bash
pip install hypothesis pytest
uv run pytest tests/fuzz/ -c tests/fuzz/pytest.ini --hypothesis-profile=dev
```

The CI job installs `hypothesis>=6.0` and `pytest>=7.0`, then runs the repository-root command below. It uses the local config so the repository coverage gate is not applied, disables the cache provider, and enforces the workflow's process timeout:

```bash
timeout 180s pytest tests/fuzz/ \
  -c tests/fuzz/pytest.ini \
  --hypothesis-profile=ci \
  -p no:cacheprovider -v
```
