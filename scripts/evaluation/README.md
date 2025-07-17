# TTS Evaluation Tools for Piper-Plus

This directory contains evaluation tools for assessing the quality of text-to-speech models in piper-plus.

## Overview

The evaluation suite includes three main metrics:

1. **MCD (Mel-Cepstral Distortion)**: Measures spectral distortion between reference and synthesized speech
2. **PESQ (Perceptual Evaluation of Speech Quality)**: ITU-T standard for speech quality assessment
3. **UTMOS (Unified TTS MOS)**: Automatic MOS prediction using a pre-trained neural model

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Individual Metrics

#### MCD Evaluation
```bash
python evaluate_mcd.py \
  --reference_dir /path/to/reference/audio \
  --synthesized_dir /path/to/synthesized/audio \
  --output mcd_results.json
```

#### PESQ Evaluation
```bash
python evaluate_pesq.py \
  --reference_dir /path/to/reference/audio \
  --synthesized_dir /path/to/synthesized/audio \
  --output pesq_results.json \
  --mode wb  # wideband (16kHz) or nb for narrowband (8kHz)
```

#### UTMOS Evaluation
```bash
python evaluate_utmos.py \
  --audio_dir /path/to/synthesized/audio \
  --output utmos_results.json \
  --device cuda  # or cpu
```

### Unified Evaluation

Run all metrics at once and generate a comprehensive report:

```bash
python run_tts_evaluation.py \
  --reference_dir /path/to/reference/audio \
  --synthesized_dir /path/to/synthesized/audio \
  --output_dir /path/to/results \
  --metrics all \
  --generate_report
```

## Evaluation Workflow for PR Testing

1. **Prepare test data**:
   ```bash
   # Use the provided Japanese test texts
   cp evaluation_texts_ja.txt /path/to/test_texts.txt
   ```

2. **Generate baseline audio** (using current main branch):
   ```bash
   python -m piper_train.infer \
     --checkpoint /path/to/baseline/model.ckpt \
     --input test_texts.txt \
     --output_dir baseline_outputs/
   ```

3. **Generate test audio** (using PR branch):
   ```bash
   python -m piper_train.infer \
     --checkpoint /path/to/pr/model.ckpt \
     --input test_texts.txt \
     --output_dir pr_outputs/
   ```

4. **Run evaluation**:
   ```bash
   python run_tts_evaluation.py \
     --reference_dir baseline_outputs/ \
     --synthesized_dir pr_outputs/ \
     --output_dir evaluation_results/ \
     --generate_report
   ```

## Interpreting Results

### MCD (Mel-Cepstral Distortion)
- **Scale**: 0 to ∞ (lower is better)
- **Good**: < 4.0
- **Acceptable**: 4.0 - 5.0
- **Poor**: > 6.0

### PESQ (Perceptual Evaluation of Speech Quality)
- **Scale**: 1.0 to 4.5 (higher is better)
- **Excellent**: ≥ 4.0
- **Good**: 3.5 - 4.0
- **Fair**: 3.0 - 3.5
- **Poor**: < 3.0

### UTMOS (Unified TTS MOS)
- **Scale**: 1.0 to 5.0 (higher is better)
- **Excellent**: ≥ 4.5
- **Good**: 4.0 - 4.5
- **Fair**: 3.5 - 4.0
- **Poor**: < 3.5

## Notes

- MCD requires paired reference and synthesized audio files
- PESQ also requires paired audio but is more perceptually aligned
- UTMOS only needs synthesized audio (reference-free)
- For Japanese TTS evaluation, use the provided `evaluation_texts_ja.txt`
- Results are saved as JSON files and optionally as HTML reports

## Citation

If you use these evaluation tools, please cite:

- PESQ: ITU-T Recommendation P.862
- UTMOS: [sarulab-speech/UTMOS-22k](https://huggingface.co/sarulab-speech/UTMOS-22k)