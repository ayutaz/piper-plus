#!/usr/bin/env python3
"""Generate a self-contained HTML form for MOS (Mean Opinion Score) evaluation.

The generated HTML file embeds all audio samples as base64 data URIs and
contains inline JavaScript for randomization, scoring, and CSV export.
No external CDN or network access is required.

Usage:
    uv run python tools/benchmark/generate_mos_survey.py \
        --samples-dir /tmp/mos_samples/ \
        --output survey.html \
        --evaluators 20 \
        --randomize
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import random
import sys
from pathlib import Path


_LOGGER = logging.getLogger("benchmark.generate_mos_survey")


def _encode_wav_base64(wav_path: Path) -> str:
    """Read a WAV file and return its base64-encoded data URI."""
    data = wav_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:audio/wav;base64,{b64}"


def _scan_samples(samples_dir: Path) -> list[dict]:
    """Scan the samples directory and return sample metadata.

    Expected structure: {samples_dir}/{model_name}/{lang}/{text_id}.wav
    """
    samples = []
    for model_dir in sorted(samples_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        for lang_dir in sorted(model_dir.iterdir()):
            if not lang_dir.is_dir():
                continue
            lang = lang_dir.name
            for wav_file in sorted(lang_dir.glob("*.wav")):
                text_id = wav_file.stem
                samples.append(
                    {
                        "model": model_name,
                        "language": lang,
                        "text_id": text_id,
                        "wav_path": wav_file,
                    }
                )
    return samples


def _load_texts(samples_dir: Path, samples: list[dict]) -> dict[str, str]:
    """Try to load text for each sample from generation_results.json."""
    gen_results = samples_dir / "generation_results.json"
    if not gen_results.exists():
        return {}
    with open(gen_results, encoding="utf-8") as f:
        data = json.load(f)
    texts: dict[str, str] = {}
    for r in data.get("results", []):
        key = f"{r['model']}/{r['language']}/{r['text_id']}"
        texts[key] = r.get("text", "")
    return texts


def _generate_html(
    samples: list[dict],
    texts: dict[str, str],
    evaluator_id_hint: int,
    randomize: bool,
    blind: bool,
) -> str:
    """Generate the complete HTML survey page."""

    # Build sample entries with embedded audio
    entries = []
    for i, sample in enumerate(samples):
        wav_path = sample["wav_path"]
        data_uri = _encode_wav_base64(wav_path)
        text_key = f"{sample['model']}/{sample['language']}/{sample['text_id']}"
        text = texts.get(text_key, "")

        entry = {
            "id": i,
            "model": sample["model"],
            "language": sample["language"],
            "text_id": sample["text_id"],
            "text": text,
            "audio_data": data_uri,
        }
        entries.append(entry)

    if randomize:
        random.shuffle(entries)

    # Assign display IDs after shuffle
    for idx, entry in enumerate(entries):
        entry["display_id"] = idx + 1

    # Serialize entries for JavaScript (without audio data in the JSON blob)
    js_entries = []
    for entry in entries:
        js_entries.append(
            {
                "id": entry["id"],
                "display_id": entry["display_id"],
                "model": entry["model"],
                "language": entry["language"],
                "text_id": entry["text_id"],
                "text": entry["text"],
            }
        )

    # Build sample cards HTML
    sample_cards = []
    for entry in entries:
        display_id = entry["display_id"]
        label = f"Sample {display_id}"
        if not blind:
            label += f" ({entry['model']} / {entry['language']})"

        text_html = ""
        if entry["text"]:
            escaped_text = (
                entry["text"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            text_html = f'<p class="sample-text">{escaped_text}</p>'

        lang_tag = ""
        if not blind:
            lang_tag = f'<span class="lang-tag">{entry["language"].upper()}</span>'

        card = f"""
    <div class="sample-card" id="card-{display_id}">
      <div class="sample-header">
        <h3>{label}</h3>
        {lang_tag}
      </div>
      {text_html}
      <audio controls preload="none">
        <source src="{entry["audio_data"]}" type="audio/wav">
        Your browser does not support the audio element.
      </audio>
      <div class="rating-group" data-sample-id="{entry["id"]}" data-display-id="{display_id}">
        <span class="rating-label">Rating:</span>
        <label><input type="radio" name="rating-{display_id}" value="1"> 1 (Bad)</label>
        <label><input type="radio" name="rating-{display_id}" value="2"> 2 (Poor)</label>
        <label><input type="radio" name="rating-{display_id}" value="3"> 3 (Fair)</label>
        <label><input type="radio" name="rating-{display_id}" value="4"> 4 (Good)</label>
        <label><input type="radio" name="rating-{display_id}" value="5"> 5 (Excellent)</label>
      </div>
      <textarea class="comment-box" placeholder="Comments (optional)" rows="2"
                data-display-id="{display_id}"></textarea>
    </div>"""
        sample_cards.append(card)

    cards_html = "\n".join(sample_cards)
    entries_json = json.dumps(js_entries, ensure_ascii=False)
    n_samples = len(entries)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MOS Evaluation Survey - Piper Plus TTS</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f5f5; color: #333; line-height: 1.6;
    max-width: 800px; margin: 0 auto; padding: 20px;
  }}
  h1 {{ text-align: center; margin-bottom: 10px; color: #1a1a2e; }}
  .subtitle {{ text-align: center; color: #666; margin-bottom: 30px; }}
  .instructions {{
    background: #e8f4fd; border-left: 4px solid #2196f3;
    padding: 16px; margin-bottom: 24px; border-radius: 4px;
  }}
  .instructions h2 {{ font-size: 1.1em; margin-bottom: 8px; }}
  .instructions ul {{ padding-left: 20px; }}
  .instructions li {{ margin-bottom: 4px; }}
  .evaluator-section {{
    background: white; padding: 16px; margin-bottom: 20px;
    border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  .evaluator-section label {{ font-weight: bold; margin-right: 8px; }}
  .evaluator-section input {{ padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; }}
  .progress-bar {{
    background: #e0e0e0; border-radius: 8px; height: 24px;
    margin-bottom: 20px; position: relative; overflow: hidden;
  }}
  .progress-fill {{
    background: linear-gradient(90deg, #4caf50, #66bb6a);
    height: 100%; border-radius: 8px; transition: width 0.3s;
  }}
  .progress-text {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 0.85em; font-weight: bold;
  }}
  .sample-card {{
    background: white; padding: 20px; margin-bottom: 16px;
    border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    transition: border-color 0.2s;
    border: 2px solid transparent;
  }}
  .sample-card.rated {{ border-color: #4caf50; }}
  .sample-header {{ display: flex; justify-content: space-between; align-items: center; }}
  .sample-header h3 {{ font-size: 1em; }}
  .lang-tag {{
    background: #e3f2fd; color: #1565c0; padding: 2px 8px;
    border-radius: 12px; font-size: 0.8em; font-weight: bold;
  }}
  .sample-text {{
    background: #fafafa; padding: 8px 12px; margin: 8px 0;
    border-radius: 4px; font-style: italic; color: #555;
  }}
  audio {{ width: 100%; margin: 10px 0; }}
  .rating-group {{
    display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap; margin-top: 8px;
  }}
  .rating-label {{ font-weight: bold; color: #555; }}
  .rating-group label {{
    cursor: pointer; padding: 4px 8px; border-radius: 4px;
    transition: background 0.2s;
  }}
  .rating-group label:hover {{ background: #e8f5e9; }}
  .rating-group input[type="radio"] {{ margin-right: 4px; }}
  .comment-box {{
    width: 100%; margin-top: 8px; padding: 8px;
    border: 1px solid #ddd; border-radius: 4px;
    font-family: inherit; resize: vertical;
  }}
  .actions {{
    text-align: center; margin: 30px 0;
    display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;
  }}
  button {{
    padding: 12px 24px; border: none; border-radius: 6px;
    font-size: 1em; cursor: pointer; transition: background 0.2s;
  }}
  .btn-primary {{ background: #2196f3; color: white; }}
  .btn-primary:hover {{ background: #1976d2; }}
  .btn-success {{ background: #4caf50; color: white; }}
  .btn-success:hover {{ background: #388e3c; }}
  .btn-secondary {{ background: #757575; color: white; }}
  .btn-secondary:hover {{ background: #616161; }}
  button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .status {{ text-align: center; margin: 10px 0; font-weight: bold; }}
  .status.success {{ color: #4caf50; }}
  .status.warning {{ color: #ff9800; }}
  .status.error {{ color: #f44336; }}
  footer {{
    text-align: center; color: #999; margin-top: 40px;
    padding: 20px 0; border-top: 1px solid #eee;
  }}
</style>
</head>
<body>

<h1>MOS Evaluation Survey</h1>
<p class="subtitle">Piper Plus TTS - Speech Quality Assessment</p>

<div class="instructions">
  <h2>Instructions</h2>
  <ul>
    <li>Listen to each audio sample carefully (use headphones if possible).</li>
    <li>Rate each sample on a scale of 1-5:</li>
    <li><strong>1 (Bad)</strong> - Very unnatural, difficult to understand</li>
    <li><strong>2 (Poor)</strong> - Unnatural, somewhat understandable</li>
    <li><strong>3 (Fair)</strong> - Somewhat natural, understandable</li>
    <li><strong>4 (Good)</strong> - Mostly natural, clear</li>
    <li><strong>5 (Excellent)</strong> - Very natural, human-like quality</li>
    <li>You may add optional comments for each sample.</li>
    <li>All {n_samples} samples must be rated before submitting.</li>
  </ul>
</div>

<div class="evaluator-section">
  <label for="evaluator-id">Evaluator ID:</label>
  <input type="text" id="evaluator-id" placeholder="Enter your name or ID" value="">
</div>

<div class="progress-bar">
  <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
  <span class="progress-text" id="progress-text">0 / {n_samples} rated</span>
</div>

{cards_html}

<div class="actions">
  <button class="btn-primary" onclick="validateAndDownload()">Download Results (CSV)</button>
  <button class="btn-success" onclick="downloadJSON()">Download Results (JSON)</button>
  <button class="btn-secondary" onclick="resetAll()">Reset All</button>
</div>

<div class="status" id="status-message"></div>

<footer>
  <p>Piper Plus TTS - MOS Evaluation Survey</p>
  <p>Generated for {evaluator_id_hint} evaluators | {n_samples} samples</p>
</footer>

<script>
const SAMPLE_METADATA = {entries_json};
const TOTAL_SAMPLES = {n_samples};

function getEvaluatorId() {{
  return document.getElementById('evaluator-id').value.trim() || 'anonymous';
}}

function getRatings() {{
  const ratings = {{}};
  for (let i = 1; i <= TOTAL_SAMPLES; i++) {{
    const radios = document.querySelectorAll('input[name="rating-' + i + '"]');
    for (const radio of radios) {{
      if (radio.checked) {{
        ratings[i] = parseInt(radio.value);
        break;
      }}
    }}
  }}
  return ratings;
}}

function getComments() {{
  const comments = {{}};
  for (let i = 1; i <= TOTAL_SAMPLES; i++) {{
    const ta = document.querySelector('textarea[data-display-id="' + i + '"]');
    if (ta && ta.value.trim()) {{
      comments[i] = ta.value.trim();
    }}
  }}
  return comments;
}}

function updateProgress() {{
  const ratings = getRatings();
  const count = Object.keys(ratings).length;
  const pct = Math.round((count / TOTAL_SAMPLES) * 100);
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-text').textContent = count + ' / ' + TOTAL_SAMPLES + ' rated';

  // Highlight rated cards
  for (let i = 1; i <= TOTAL_SAMPLES; i++) {{
    const card = document.getElementById('card-' + i);
    if (card) {{
      if (ratings[i]) {{
        card.classList.add('rated');
      }} else {{
        card.classList.remove('rated');
      }}
    }}
  }}
}}

function showStatus(msg, cls) {{
  const el = document.getElementById('status-message');
  el.textContent = msg;
  el.className = 'status ' + cls;
}}

function buildResults() {{
  const ratings = getRatings();
  const comments = getComments();
  const evaluatorId = getEvaluatorId();
  const results = [];

  for (const meta of SAMPLE_METADATA) {{
    const displayId = meta.display_id;
    results.push({{
      evaluator_id: evaluatorId,
      sample_id: meta.id,
      display_id: displayId,
      model: meta.model,
      language: meta.language,
      text_id: meta.text_id,
      text: meta.text,
      rating: ratings[displayId] || null,
      comment: comments[displayId] || '',
    }});
  }}
  return results;
}}

function validateAndDownload() {{
  const ratings = getRatings();
  const missing = TOTAL_SAMPLES - Object.keys(ratings).length;
  if (missing > 0) {{
    showStatus('Please rate all samples. ' + missing + ' remaining.', 'warning');
    // Scroll to first unrated
    for (let i = 1; i <= TOTAL_SAMPLES; i++) {{
      if (!ratings[i]) {{
        document.getElementById('card-' + i).scrollIntoView({{ behavior: 'smooth' }});
        break;
      }}
    }}
    return;
  }}

  const results = buildResults();
  const evaluatorId = getEvaluatorId();

  // Build CSV
  const headers = ['evaluator_id','sample_id','display_id','model','language','text_id','text','rating','comment'];
  let csv = headers.join(',') + '\\n';
  for (const r of results) {{
    const row = headers.map(h => {{
      let val = r[h];
      if (val === null || val === undefined) val = '';
      val = String(val).replace(/"/g, '""');
      if (val.includes(',') || val.includes('"') || val.includes('\\n')) {{
        val = '"' + val + '"';
      }}
      return val;
    }});
    csv += row.join(',') + '\\n';
  }}

  downloadFile(csv, 'mos_results_' + evaluatorId + '.csv', 'text/csv');
  showStatus('CSV downloaded successfully!', 'success');
}}

function downloadJSON() {{
  const ratings = getRatings();
  const missing = TOTAL_SAMPLES - Object.keys(ratings).length;
  if (missing > 0) {{
    showStatus('Please rate all samples. ' + missing + ' remaining.', 'warning');
    return;
  }}

  const results = buildResults();
  const evaluatorId = getEvaluatorId();
  const output = {{
    evaluator_id: evaluatorId,
    timestamp: new Date().toISOString(),
    total_samples: TOTAL_SAMPLES,
    results: results,
  }};

  downloadFile(
    JSON.stringify(output, null, 2),
    'mos_results_' + evaluatorId + '.json',
    'application/json'
  );
  showStatus('JSON downloaded successfully!', 'success');
}}

function downloadFile(content, filename, mimeType) {{
  const blob = new Blob([content], {{ type: mimeType }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}

function resetAll() {{
  if (!confirm('Reset all ratings and comments?')) return;
  for (let i = 1; i <= TOTAL_SAMPLES; i++) {{
    const radios = document.querySelectorAll('input[name="rating-' + i + '"]');
    for (const radio of radios) radio.checked = false;
    const ta = document.querySelector('textarea[data-display-id="' + i + '"]');
    if (ta) ta.value = '';
  }}
  updateProgress();
  showStatus('All ratings cleared.', '');
}}

// Attach change listeners for progress tracking
document.addEventListener('change', function(e) {{
  if (e.target.type === 'radio') updateProgress();
}});

// Initial progress
updateProgress();
</script>
</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a self-contained HTML form for MOS evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    uv run python tools/benchmark/generate_mos_survey.py \\
        --samples-dir /tmp/mos_samples/ \\
        --output survey.html \\
        --evaluators 20 \\
        --randomize
""",
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        required=True,
        help="Directory containing generated WAV samples",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("survey.html"),
        help="Output HTML file path (default: survey.html)",
    )
    parser.add_argument(
        "--evaluators",
        type=int,
        default=20,
        help="Expected number of evaluators (shown in footer, default: 20)",
    )
    parser.add_argument(
        "--randomize",
        action="store_true",
        help="Randomize sample presentation order",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible ordering (use with --randomize)",
    )
    parser.add_argument(
        "--no-blind",
        action="store_true",
        help="Show model names in the survey (default: blind evaluation)",
    )
    parser.add_argument(
        "--languages",
        default=None,
        help="Filter to specific languages (comma-separated, e.g. 'ja,en')",
    )
    parser.add_argument(
        "--models",
        default=None,
        help="Filter to specific models (comma-separated)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.seed is not None:
        random.seed(args.seed)

    # Scan samples
    samples = _scan_samples(args.samples_dir)
    if not samples:
        _LOGGER.error("No WAV files found in %s", args.samples_dir)
        sys.exit(1)

    # Apply filters
    if args.languages:
        lang_filter = {lang.strip() for lang in args.languages.split(",")}
        samples = [s for s in samples if s["language"] in lang_filter]
    if args.models:
        model_filter = {m.strip() for m in args.models.split(",")}
        samples = [s for s in samples if s["model"] in model_filter]

    if not samples:
        _LOGGER.error("No samples remaining after filtering")
        sys.exit(1)

    _LOGGER.info("Generating survey with %d samples", len(samples))

    # Load texts from generation results
    texts = _load_texts(args.samples_dir, samples)

    # Generate HTML
    html = _generate_html(
        samples,
        texts,
        evaluator_id_hint=args.evaluators,
        randomize=args.randomize,
        blind=not args.no_blind,
    )

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    file_size_mb = args.output.stat().st_size / (1024 * 1024)
    _LOGGER.info(
        "Survey written to %s (%.1f MB, %d samples)",
        args.output,
        file_size_mb,
        len(samples),
    )

    # Summary
    models = sorted({s["model"] for s in samples})
    languages = sorted({s["language"] for s in samples})
    print(f"\nSurvey: {args.output}")
    print(f"Samples: {len(samples)}")
    print(f"Models: {', '.join(models)}")
    print(f"Languages: {', '.join(languages)}")
    print(f"Blind: {not args.no_blind}")
    print(f"Randomized: {args.randomize}")
    print(f"File size: {file_size_mb:.1f} MB")


if __name__ == "__main__":
    main()
