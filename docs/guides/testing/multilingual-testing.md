# Multilingual TTS Testing Guide

piper-plus の多言語 TTS テストについて説明します。

## Overview

piper-plus は G2P コードで 8 言語に対応しています。学習済みモデルは 6 言語 (JA, EN, ZH, ES, FR, PT) をカバーし、スウェーデン語 (SV) と韓国語 (KO) はコード対応のみです。

各実装 (Python, C++, C#, Rust, Go, JavaScript) で言語間の一貫性を保つため、包括的なテストインフラを構築しています。

## 対応言語

| 言語 | コード | G2P | 学習済みモデル |
|------|--------|-----|---------------|
| 日本語 | ja | JapanesePhonemizer (OpenJTalk) | ✓ |
| 英語 | en | EnglishPhonemizer (CMU Dict) | ✓ |
| 中国語 | zh | ChinesePhonemizer (Pinyin) | ✓ |
| スペイン語 | es | SpanishPhonemizer (規則ベース) | ✓ |
| フランス語 | fr | FrenchPhonemizer (規則ベース) | ✓ |
| ポルトガル語 | pt | PortuguesePhonemizer (規則ベース) | ✓ |
| スウェーデン語 | sv | SwedishPhonemizer (規則ベース) | コード対応のみ |
| 韓国語 | ko | KoreanPhonemizer (g2pk2) | コード対応のみ |

## CI/CD Integration

### GitHub Actions Workflow

多言語テストは以下のトリガーで実行されます:
- dev ブランチ向けの pull request
- 手動実行 (`workflow_dispatch`)
- 他の workflow からの呼び出し (`workflow_call`)

## C# Tests (PiperPlus.Core.Tests)

The C# implementation has 958 tests using xUnit v3 in the `PiperPlus.Core.Tests` project. These tests cover:

- All 8 language phonemizers (Japanese, English, Chinese, Korean, Spanish, Portuguese, French, Swedish)
  - Note: The current trained model covers 6 languages (JA, EN, ZH, ES, FR, PT). Swedish (sv) and Korean (ko) are code-ready but not yet included in the trained model.
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
| OS | ubuntu-24.04, windows-latest, macos-14 |
| .NET | 10.0.x |

This gives a 3 OS x 1 .NET version matrix (3 combinations).

## Rust Tests (piper-plus)

The Rust `piper-plus` crate has 26 integration test files covering:

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

## Go Tests (piperplus)

The Go `piperplus` package has 793 unit tests and 10 integration tests covering:

- All 8 language phonemizers (Japanese, English, Chinese, Korean, Spanish, Portuguese, French, Swedish)
  - Note: Swedish (sv) and Korean (ko) are code-ready but not yet included in the current 6-language trained model.
- Unicode language detection and text segmentation
- PUA (Private Use Area) bidirectional mapping (96 entries)
- Config parsing, WAV output, error types
- ONNX inference engine, end-to-end synthesis (integration)
- HTTP API server handlers (/synthesize, /health, /info)
- Custom dictionary (text substitution, JSON v2.0)
- Dictionary loading (CMU, Pinyin, OpenJTalk 3-tier search)

### Running Go Tests Locally

Unit tests (no ONNX Runtime required):

```bash
cd src/go && go test -v -race -count=1 ./...
```

Integration tests (requires ONNX Runtime and test model):

```bash
cd src/go && ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so \
  PIPER_TEST_MODEL=/path/to/multilingual-test-medium.onnx \
  go test -v -race -count=1 -tags integration ./...
```

### Go CI Configuration

CI is defined in `.github/workflows/go-ci.yml` and runs:

| Job | OS | Requirements | Content |
|-----|----|-------------|---------|
| unit-test | Ubuntu, macOS, Windows | Go 1.26+ | Phonemizer, config, WAV, Unicode detection |
| integration-test | Ubuntu | Go 1.26+, ONNX Runtime 1.24.4 | ONNX inference, end-to-end synthesis |
| build | Ubuntu, macOS, Windows | Go 1.26+ | CLI binary generation, artifact upload |
| lint | Ubuntu | golangci-lint (unpinned, via golangci-lint-action@v7) | Static analysis |

## 6-Language Multilingual Model Testing

Piper Plus ships a 6-language multilingual model (571 speakers, 173 symbols) trained on JA, EN, ZH, ES, FR, PT. The G2P code supports 8 languages (including Swedish/sv and Korean/ko), but the current model was trained on 6. Use the following sample texts to verify all model languages work correctly.

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

- All 6 model languages produce audible, non-silent output
- Audio duration is reasonable (typically 1-3 seconds for the sample texts)
- No "beep" artifacts (indicates Duration Predictor failure)
- Language detection routes text to the correct phonemizer

## Troubleshooting

### よくある問題

1. **日本語テストが失敗する**
   - OpenJTalk 辞書のパスが正しいか確認 (`OPENJTALK_DICTIONARY_DIR`)
   - C API テストでは OpenJTalk 不在時に自動スキップ

2. **テストモデルのダウンロードに失敗する**
   - HuggingFace のモデル URL を確認
   - CI ではワークフロー定義でモデル取得方法やキャッシュ設定を確認

3. **プラットフォーム固有の問題**
   - **Linux**: `LD_LIBRARY_PATH` に ONNX Runtime ライブラリパスを設定
   - **macOS**: `DYLD_LIBRARY_PATH` でライブラリパスを指定
   - **Windows**: `PATH` に ONNX Runtime DLL パスを追加

## Related Documentation

- [Main README](../../README.md)
- [piper-plus Models on HuggingFace](https://huggingface.co/ayousanz/piper-plus-base)
- [Training Guide](../training/training-guide.md)