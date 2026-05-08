# MOS Benchmark

## Overview

`tools/benchmark/` contains tooling for running **MOS (Mean Opinion Score)**
listening evaluations of piper-plus models against external TTS systems. The
pipeline has three stages:

1. **Generate audio samples** from each model x language x test sentence
   combination, recording RTF (Real-Time Factor) per utterance.
2. **Compute objective audio metrics** (RMS dB, peak dB, silence ratio,
   sample-rate sanity check) and, optionally, **UTMOS** automatic quality
   scores.
3. **Generate a self-contained HTML survey** that human evaluators can open
   directly in a browser to give 1-5 ratings, with results exportable as
   CSV / JSON.

MOS itself is collected from human evaluators via the HTML survey; the
objective metrics are sanity checks, not a substitute for MOS.

## Components

### `generate_samples.py`

Reads a `models.yaml` definition file and synthesises one WAV per
`{model, language, sentence}` triple under
`{samples_dir}/{model_name}/{lang}/{text_id}.wav`.

- Supports two model types:
  - `piper-plus`: in-process ONNX inference using
    `piper_train.ort_utils.create_session_with_cache` plus the standard
    warmup, falling back to a default `onnxruntime.InferenceSession` if the
    training package is unavailable.
  - `external`: arbitrary TTS systems invoked as a subprocess via a
    `command` template (e.g. `edge-tts --voice {voice} --text '{text}'
    --write-media {output}`, `gtts-cli '{text}' -l {lang} -o {output}`).
- `${MODELS_DIR}` and other `${VAR}` references in `path` / `config` /
  `command` are expanded from `os.environ` at load time so the same config
  file works on different hosts.
- Records wall-clock inference seconds and audio duration to derive RTF, and
  writes the aggregated `generation_results.json` next to the samples.

### `compute_metrics.py`

Walks `{samples_dir}/{model}/{lang}/*.wav` and emits a `metrics.json` with:

- `duration_sec` — derived from WAV header.
- `file_size_bytes`.
- `sample_rate`, `sample_rate_ok` — flags WAVs whose rate differs from the
  expected `22050 Hz`.
- `rms_db` — `20 * log10(RMS)` of the int16-decoded float32 audio.
- `peak_db` — `20 * log10(max(|x|))`.
- `silence_ratio` — fraction of 10 ms frames whose RMS falls below `-40 dB`.
- `rtf` — pulled from `generation_results.json` if present.
- `utmos` (optional, `--utmos`) — UTMOS automatic naturalness score from
  `tarepan/SpeechMOS:v1.2.0 / utmos22_strong` via `torch.hub`. Audio is
  resampled to 16 kHz internally; requires `torch` and `torchaudio`.

A per-`(model, language)` aggregate (mean / count) is emitted alongside the
per-file rows.

### `generate_mos_survey.py`

Produces a single-file `survey.html` containing all audio embedded as
`data:audio/wav;base64,...` URIs, so it can be opened offline without any
CDN, server, or network access.

- `--randomize` shuffles the sample order (use `--seed` for reproducible
  shuffles).
- Default mode is **blind** (model and language hidden); pass `--no-blind`
  to reveal them in the rendered card.
- Per-sample rating widget: 1 (Bad) / 2 (Poor) / 3 (Fair) / 4 (Good) /
  5 (Excellent), plus an optional free-text comment.
- "Download Results" buttons emit either CSV
  (`evaluator_id, sample_id, display_id, model, language, text_id, text,
  rating, comment`) or JSON, with the evaluator's chosen ID baked into the
  filename.

## Usage

The default fixtures cover **6 languages x 10 sentences each** under
`tools/benchmark/texts/{ja,en,zh,es,fr,pt}.txt`.

### 1. Configure `models.yaml`

```yaml
models:
  - name: piper-plus-6lang-base
    path: "${MODELS_DIR}/multilingual-6lang-75epoch.onnx"
    config: "${MODELS_DIR}/config.json"
    type: piper-plus
    description: "6-language base model (75 epoch, 571 speakers)"
    speaker_ids:
      ja: 0
      en: 20
      zh: 20
      es: 20
      fr: 20
      pt: 20

  - name: edge-tts
    type: external
    command: "edge-tts --voice {voice} --text '{text}' --write-media {output}"
    voices:
      ja: "ja-JP-NanamiNeural"
      en: "en-US-JennyNeural"
      zh: "zh-CN-XiaoxiaoNeural"
      es: "es-ES-ElviraNeural"
      fr: "fr-FR-DeniseNeural"
      pt: "pt-BR-FranciscaNeural"
```

### 2. Generate samples

```bash
export MODELS_DIR=/data/piper/output-multilingual-6lang
uv run python tools/benchmark/generate_samples.py \
    --models-config tools/benchmark/models.yaml \
    --texts-dir tools/benchmark/texts/ \
    --output-dir /tmp/mos_samples/ \
    --languages ja,en,zh,es,fr,pt \
    --speaker-ids "0,20"
```

### 3. Compute objective metrics

```bash
uv run python tools/benchmark/compute_metrics.py \
    --samples-dir /tmp/mos_samples/ \
    --output metrics.json

# Optional: UTMOS automatic naturalness score
uv run python tools/benchmark/compute_metrics.py \
    --samples-dir /tmp/mos_samples/ \
    --output metrics.json \
    --utmos
```

### 4. Generate the listening survey

```bash
uv run python tools/benchmark/generate_mos_survey.py \
    --samples-dir /tmp/mos_samples/ \
    --output survey.html \
    --evaluators 20 \
    --randomize
```

Open `survey.html` in any modern browser, rate each clip 1-5, then click
"Download Results (CSV)" to save the evaluator's responses.

### Example HTML output structure

```
<!DOCTYPE html>
<html>
  <head> ... inline <style> ... </head>
  <body>
    <div class="evaluator-section">Evaluator ID: [____]</div>
    <div class="sample-card" id="card-1">
      <h3>Sample 1</h3>                       <!-- model/lang hidden when blind -->
      <p class="sample-text">こんにちは、...</p>
      <audio controls preload="none">
        <source src="data:audio/wav;base64,UklGR..." type="audio/wav">
      </audio>
      <div class="rating-group"> 1 / 2 / 3 / 4 / 5 </div>
      <textarea class="comment-box"></textarea>
    </div>
    ...
    <button onclick="validateAndDownload()">Download Results (CSV)</button>
  </body>
</html>
```

## Known Limitations

- **No PESQ implementation.** Despite earlier docs referring to "PESQ/STOI",
  the current `compute_metrics.py` does not implement PESQ. Adding it is
  tracked as future work.
- **No STOI implementation.** STOI is similarly not wired up; only the basic
  level / silence / sample-rate checks plus optional UTMOS are produced.
- **UTMOS is optional and not a substitute for MOS.** UTMOS requires `torch`
  and `torchaudio`, downloads a model on first use, and is a learned proxy
  for naturalness — it should be reported alongside, not in place of, human
  MOS scores.
- **External TTS systems must be installed separately.** The `external`
  model type assumes binaries like `edge-tts` or `gtts-cli` are available on
  `$PATH`; this tooling does not vendor them.
- **Sample rate is hard-coded to 22050 Hz.** Files at other rates are still
  measured but flagged via `sample_rate_ok = false`.

## Related

- [`CONTRIBUTING_MODELS.md`](../CONTRIBUTING_MODELS.md) — guide for
  contributing new models that may then be benchmarked here.
- `tools/benchmark/test_benchmark.py` — pytest suite that exercises the
  three scripts with mock WAVs (no real TTS models required); run via
  `uv run python -m pytest tools/benchmark/test_benchmark.py -v`.
- `tools/benchmark/models.yaml` — current list of evaluation targets.
- `tools/benchmark/texts/{ja,en,zh,es,fr,pt}.txt` — 10-sentence fixtures
  per language (60 sentences total).
