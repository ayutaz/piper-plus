# MOS Benchmark - Evaluation Protocol

This document describes the MOS (Mean Opinion Score) evaluation protocol for Piper Plus TTS models.

## Overview

The benchmark suite consists of three tools:

1. **`generate_samples.py`** - Generate audio samples from multiple TTS models
2. **`compute_metrics.py`** - Compute automatic quality metrics
3. **`generate_mos_survey.py`** - Generate HTML evaluation forms

## Evaluation Protocol

### Test Sentences

- 10 sentences per language (6 languages: JA, EN, ZH, ES, FR, PT)
- Sentence types: short, medium, long, interrogative, containing numbers
- Located in `tools/benchmark/texts/{lang}.txt`

### Models Under Evaluation

Defined in `tools/benchmark/models.yaml`:
- **piper-plus-6lang-base**: 6-language base model (571 speakers)
- **piper-plus-tsukuyomi**: Tsukuyomi-chan fine-tuned model
- **edge-tts**: Microsoft Edge TTS (comparison baseline)
- **gtts**: Google TTS (comparison baseline)

### MOS Evaluation Scale

| Score | Label | Description |
|-------|-------|-------------|
| 5 | Excellent | Very natural, indistinguishable from human speech |
| 4 | Good | Mostly natural, minor artifacts |
| 3 | Fair | Somewhat natural, noticeable artifacts |
| 2 | Poor | Unnatural, but understandable |
| 1 | Bad | Very unnatural, difficult to understand |

### Evaluator Requirements

- Recommended: 20 or more evaluators
- Headphone use required
- Each evaluator rates all samples (blind evaluation)
- Sample presentation order is randomized per evaluator

### Automatic Metrics

| Metric | Description |
|--------|-------------|
| RTF (Real-Time Factor) | Synthesis time / audio duration (lower is better) |
| Audio duration | Length of generated audio in seconds |
| File size | WAV file size in bytes |
| RMS level (dB) | Average loudness |
| Peak level (dB) | Maximum signal level |
| Silence ratio | Proportion of silent frames |
| UTMOS (optional) | Automatic MOS prediction (1-5 scale) |

## Usage

### Step 1: Generate Audio Samples

```bash
# Set model directory
export MODELS_DIR=/data/piper/output-multilingual-6lang

# Generate for all languages
uv run python tools/benchmark/generate_samples.py \
    --models-config tools/benchmark/models.yaml \
    --texts-dir tools/benchmark/texts/ \
    --output-dir /tmp/mos_samples/ \
    --languages ja,en,zh,es,fr,pt

# Generate for specific languages and models
uv run python tools/benchmark/generate_samples.py \
    --models-config tools/benchmark/models.yaml \
    --texts-dir tools/benchmark/texts/ \
    --output-dir /tmp/mos_samples/ \
    --languages ja,en \
    --models piper-plus-tsukuyomi \
    --speaker-ids "0"
```

Output structure:
```
/tmp/mos_samples/
  piper-plus-6lang-base/
    ja/
      000.wav
      001.wav
      ...
    en/
      000.wav
      ...
  piper-plus-tsukuyomi/
    ja/
      000.wav
      ...
  generation_results.json
```

### Step 2: Compute Automatic Metrics

```bash
# Basic metrics
uv run python tools/benchmark/compute_metrics.py \
    --samples-dir /tmp/mos_samples/ \
    --output metrics.json

# With UTMOS automatic quality prediction
uv run python tools/benchmark/compute_metrics.py \
    --samples-dir /tmp/mos_samples/ \
    --output metrics.json \
    --utmos
```

### Step 3: Generate MOS Survey

```bash
# Blind evaluation with randomized order
uv run python tools/benchmark/generate_mos_survey.py \
    --samples-dir /tmp/mos_samples/ \
    --output survey.html \
    --evaluators 20 \
    --randomize \
    --seed 42

# Non-blind evaluation (for internal testing)
uv run python tools/benchmark/generate_mos_survey.py \
    --samples-dir /tmp/mos_samples/ \
    --output survey_debug.html \
    --no-blind
```

### Step 4: Collect and Analyze Results

Each evaluator opens `survey.html` in a browser, rates all samples, and
downloads results as CSV or JSON. Aggregate the downloaded CSV files for
statistical analysis.

## Results Template

### Automatic Metrics

| Model | Language | RTF | UTMOS | Avg Duration |
|-------|----------|-----|-------|--------------|
| piper-plus-6lang-base | JA | - | - | - |
| piper-plus-6lang-base | EN | - | - | - |
| piper-plus-tsukuyomi | JA | - | - | - |
| piper-plus-tsukuyomi | EN | - | - | - |
| edge-tts | JA | - | - | - |
| edge-tts | EN | - | - | - |

### MOS Results

| Model | JA | EN | ZH | ES | FR | PT | Overall |
|-------|----|----|----|----|----|----|----|
| piper-plus-6lang-base | - | - | - | - | - | - | - |
| piper-plus-tsukuyomi | - | - | - | - | - | - | - |
| edge-tts | - | - | - | - | - | - | - |
| gtts | - | - | - | - | - | - | - |

### Statistical Analysis

- Report mean and 95% confidence interval for each model x language pair.
- Use Wilcoxon signed-rank test for pairwise significance testing.
- Report inter-rater agreement using Krippendorff's alpha.

## Dependencies

Required (always available in piper-plus environment):
- `numpy`
- `pyyaml`
- `onnxruntime`

Optional:
- `torch`, `torchaudio` - for UTMOS computation (`--utmos` flag)
- `edge-tts` - for Edge TTS comparison baseline
- `gTTS` - for Google TTS comparison baseline
