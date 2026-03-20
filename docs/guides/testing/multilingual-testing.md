# Multilingual TTS Testing Guide

This document describes how to test Piper's multilingual text-to-speech capabilities.

## Overview

Piper supports TTS for over 40 languages. To ensure quality across all supported languages, we have implemented comprehensive testing infrastructure that:

- Tests multiple languages on all supported platforms (Linux, Windows, macOS)
- Downloads voice models from HuggingFace during testing
- Validates output quality and performance
- Supports different test modes (basic, comprehensive, performance)

## Supported Languages

The following languages are tested in our CI/CD pipeline:

| Language | Code | Model | Quality |
|----------|------|-------|---------|
| English (US) | en_US | lessac | medium |
| English (UK) | en_GB | alan | medium |
| German | de_DE | thorsten | medium |
| French | fr_FR | upmc | medium |
| Spanish | es_ES | mls_9972 | low |
| Italian | it_IT | riccardo | x_low |
| Portuguese (Brazil) | pt_BR | faber | medium |
| Russian | ru_RU | denis | medium |
| Chinese (Simplified) | zh_CN | huayan | medium |
| Dutch | nl_NL | nathalie | x_low |
| Polish | pl_PL | gosia | medium |
| Swedish | sv_SE | nst | medium |

Additional languages are available and can be tested using the local test script.

## Running Tests Locally

### Prerequisites

1. Download or build Piper binary for your platform
2. Python 3.11+ installed
3. Internet connection for downloading voice models

### Basic Testing

Run the test script to test all default languages:

```bash
python test_multilingual_tts.py --piper ./piper/bin/piper
```

### Test Specific Languages

```bash
python test_multilingual_tts.py --piper ./piper/bin/piper --languages en_US de_DE fr_FR
```

### Performance Testing

Run comprehensive performance tests:

```bash
python test_multilingual_tts.py --piper ./piper/bin/piper --test-type performance
```

### Test Output

The script generates:
- Individual WAV files for each language tested
- Performance metrics (characters per second)
- Detailed error reports for failed tests
- Summary report of all test results

## CI/CD Integration

### GitHub Actions Workflow

The multilingual tests run automatically on:
- Pull requests to master or dev branches
- Pushes to dev, feat/*, and fix/* branches
- Manual workflow dispatch

### Running CI/CD Tests Manually

1. Go to Actions tab in GitHub
2. Select "Test Multilingual TTS" workflow
3. Click "Run workflow"
4. Optionally specify:
   - Languages to test (comma-separated)
   - Test type (basic, comprehensive, performance)

### Test Matrix

Tests run on the following matrix:
- **Operating Systems**: Ubuntu (latest), Windows (latest), macOS (latest)
- **Languages**: 12 major languages by default
- **Architectures**: x64, ARM64 (where applicable)

Note: Chinese (zh_CN) tests are skipped on Windows due to phonemizer limitations.

## C# Tests (PiperPlus.Core.Tests)

The C# implementation has 721 tests using xUnit v3 in the `PiperPlus.Core.Tests` project. These tests cover:

- All 6 language phonemizers (Japanese, English, Chinese, Spanish, Portuguese, French)
- `PostProcessIds` logic
- PUA (Private Use Area) mapping
- IPA tokenizer
- Multilingual phonemizer integration
- Custom dictionaries, model management, streaming, and inference

### Running C# Tests Locally

```bash
dotnet test src/csharp/PiperPlus.Core.Tests/
```

To run in Release mode with code coverage (matching CI):

```bash
dotnet test src/csharp/PiperPlus.sln -c Release \
  --filter "Category!=CLI" \
  --collect:"XPlat Code Coverage" \
  --settings src/csharp/PiperPlus.runsettings
```

### C# CI Configuration

CI is defined in `.github/workflows/csharp-ci.yml` and runs on:

| Dimension | Values |
|-----------|--------|
| OS | ubuntu-22.04, windows-latest, macos-14 |
| .NET | 8.0.x, 9.0.x |

This gives a 3 OS x 2 .NET versions matrix (6 combinations).

## Rust Tests (piper-plus)

The Rust `piper-plus` crate has 21 integration test files covering:

- Multilingual phonemization (`test_multilingual.rs`, `test_romance_languages.rs`)
- Per-language phonemizers (`test_japanese_phonemize.rs`, `test_english.rs`, `test_chinese.rs`, `test_korean.rs`)
- Japanese-specific features: N-variant rules (`test_n_variants.rs`), question markers (`test_question_markers.rs`)
- Streaming synthesis (`test_streaming.rs`)
- Model management and download (`test_model_download.rs`, `test_voice_api.rs`)
- Audio format, batch processing, timing, device selection, error handling
- Token map parity with Python (`test_token_map_parity.rs`)

### Running Rust Tests Locally

```bash
cargo test -p piper-plus
```

To run with verbose output and no failure short-circuit:

```bash
cargo test -p piper-plus --no-fail-fast -- --nocapture
```

### Rust CI Configuration

CI is defined in `.github/workflows/rust-tests.yml` and runs on:

| Dimension | Values |
|-----------|--------|
| OS | ubuntu-24.04, macos-latest, windows-latest |

The workflow also includes `cargo check`, `cargo fmt`, and `cargo clippy` jobs on ubuntu-24.04.

## 6-Language Multilingual Model Testing

Piper Plus ships a 6-language multilingual model (571 speakers, 173 symbols) trained on JA, EN, ZH, ES, FR, PT. Use the following sample texts to verify all languages work correctly.

### Sample Texts by Language

| Language | Code | Sample Text |
|----------|------|-------------|
| Japanese | ja | こんにちは、今日は良い天気ですね。 |
| English | en | Hello, how are you today? |
| Chinese | zh | 你好，今天天气很好。 |
| Spanish | es | Hola, como estas hoy? |
| French | fr | Bonjour, comment allez-vous? |
| Portuguese | pt | Ola, como voce esta hoje? |

### Testing with infer_onnx.py

Test a specific language against the 6-language model:

```bash
# Japanese (speaker_id=0, JA speaker)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/multilingual-6lang.onnx \
  --config /path/to/config.json \
  --output-dir ./test-output \
  --text "こんにちは、今日は良い天気ですね。" \
  --language ja-en-zh-es-fr-pt --speaker-id 0 --noise-scale 0.667

# English (speaker_id=20, EN speaker)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/multilingual-6lang.onnx \
  --config /path/to/config.json \
  --output-dir ./test-output \
  --text "Hello, how are you today?" \
  --language ja-en-zh-es-fr-pt --speaker-id 20 --noise-scale 0.667

# Chinese
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/multilingual-6lang.onnx \
  --config /path/to/config.json \
  --output-dir ./test-output \
  --text "你好，今天天气很好。" \
  --language ja-en-zh-es-fr-pt --speaker-id 162 --noise-scale 0.667

# Spanish
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/multilingual-6lang.onnx \
  --config /path/to/config.json \
  --output-dir ./test-output \
  --text "Hola, como estas hoy?" \
  --language ja-en-zh-es-fr-pt --speaker-id 472 --noise-scale 0.667

# French
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/multilingual-6lang.onnx \
  --config /path/to/config.json \
  --output-dir ./test-output \
  --text "Bonjour, comment allez-vous?" \
  --language ja-en-zh-es-fr-pt --speaker-id 535 --noise-scale 0.667

# Portuguese
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/multilingual-6lang.onnx \
  --config /path/to/config.json \
  --output-dir ./test-output \
  --text "Ola, como voce esta hoje?" \
  --language ja-en-zh-es-fr-pt --speaker-id 563 --noise-scale 0.667
```

### What to Check

- All 6 languages produce audible, non-silent output
- Audio duration is reasonable (typically 1-3 seconds for the sample texts)
- No "beep" artifacts (indicates Duration Predictor failure)
- Language detection routes text to the correct phonemizer

## Adding New Languages

To add a new language to the test suite:

1. Find the model on [HuggingFace](https://huggingface.co/rhasspy/piper-voices)
2. Add language configuration to `test_multilingual_tts.py`:

```python
"lang_CODE": {
    "model": "lang_CODE-speaker-quality",
    "test_text": "Test text in the target language",
    "speaker": "speaker_name"
}
```

3. Add the language to the CI/CD workflow matrix in `.github/workflows/test-multilingual-tts.yml`

## Troubleshooting

### Common Issues

1. **Model download fails**
   - Check internet connection
   - Verify model exists on HuggingFace
   - Check URL structure matches the repository layout

2. **TTS fails for specific language**
   - Ensure proper phonemizer support
   - Check if language requires special dependencies
   - Verify model compatibility with Piper version

3. **Performance issues**
   - Some languages are computationally more intensive
   - Lower quality models (x_low, low) are faster
   - Consider using GPU acceleration if available

### Platform-Specific Notes

- **Linux**: Requires LD_LIBRARY_PATH to be set for shared libraries
- **macOS**: Requires DYLD_LIBRARY_PATH for dynamic libraries
- **Windows**: Some languages (e.g., Chinese, Arabic) may have limited support

## Model Quality Levels

Models are available in different quality levels:

- **x_low**: Fastest, lowest quality (good for testing)
- **low**: Fast, acceptable quality
- **medium**: Balanced speed and quality (recommended)
- **high**: Best quality, slower processing

## Performance Benchmarks

Typical performance on modern hardware:

| Language | Quality | Chars/Second |
|----------|---------|--------------|
| English | medium | 500-800 |
| German | medium | 400-700 |
| Chinese | medium | 200-400 |
| Arabic | medium | 300-500 |

Performance varies based on:
- CPU/GPU capabilities
- Model complexity
- Text content (numbers, special characters affect speed)

## Contributing

When contributing multilingual support:

1. Test your changes locally with multiple languages
2. Ensure CI/CD tests pass for all platforms
3. Document any language-specific requirements
4. Add appropriate test cases for edge cases

## Related Documentation

- [Main README](../../README.md)
- [Voice Models on HuggingFace](https://huggingface.co/rhasspy/piper-voices)
- [Training Guide](../training/training-guide.md)