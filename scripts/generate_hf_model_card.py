#!/usr/bin/env python3
"""HuggingFace Model Card frontmatter + README.md 自動生成 (Wave 3, T10).

config.json (piper-plus ONNX model 用) と model-sha256-manifest.toml から、
HF Hub にアップロードする README.md (YAML frontmatter + 本文) を生成する。

YAML frontmatter:
  - language: [ja, en, zh, ...]  (config.json の language_id_map から)
  - pipeline_tag: text-to-speech
  - license: mit
  - tags: [piper, vits, tts, multilingual]
  - library_name: piper-plus
  - model-index: (sha256 / bytes)

Usage:
  uv run python scripts/generate_hf_model_card.py \
    --config /path/to/model.onnx.json \
    --name "multilingual-6lang-mb-istft" \
    --output /path/to/README.md

Exit codes:
  0 -- 生成成功
  1 -- config 不在 / parse error
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "docs" / "spec" / "model-sha256-manifest.toml"

LANG_NAMES = {
    "ja": "Japanese",
    "en": "English",
    "zh": "Chinese (Mandarin)",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "pt": "Portuguese",
    "pt-BR": "Portuguese (Brazilian)",
    "pt-PT": "Portuguese (European)",
    "sv": "Swedish",
    "de": "German",
}


def read_model_manifest_entry(name: str) -> dict | None:
    if not MANIFEST.exists():
        return None
    with MANIFEST.open("rb") as fh:
        spec = tomllib.load(fh)
    for entry in spec.get("models", []):
        if entry.get("name") == name:
            return entry
    return None


def extract_languages(config: dict) -> list[str]:
    """Try several config schemas to extract the language list."""
    lang_map = (
        config.get("language_id_map")
        or config.get("languages")
        or (config.get("language") and {config["language"]: 0})
        or {}
    )
    if isinstance(lang_map, dict):
        return sorted(lang_map.keys())
    if isinstance(lang_map, list):
        return sorted(lang_map)
    return []


def build_frontmatter(name: str, languages: list[str], manifest: dict | None) -> str:
    lines: list[str] = ["---"]
    if languages:
        lines.append("language:")
        for lang in languages:
            # HF uses ISO 639-1 codes; pt-BR / pt-PT are emitted as `pt`
            iso = lang.split("-", 1)[0]
            lines.append(f"  - {iso}")
    lines.extend(
        [
            "pipeline_tag: text-to-speech",
            "license: mit",
            "library_name: piper-plus",
            "tags:",
            "  - piper",
            "  - piper-plus",
            "  - vits",
            "  - tts",
            "  - text-to-speech",
        ]
    )
    if len(languages) > 1:
        lines.append("  - multilingual")
    if manifest:
        sha = manifest.get("sha256")
        size = manifest.get("bytes")
        if sha and sha != "<computed-on-publish>":
            lines.append("model-index:")
            lines.append(f"  - name: {name}")
            lines.append("    results:")
            lines.append("      - task:")
            lines.append("          type: text-to-speech")
            lines.append("        dataset:")
            lines.append(f"          name: {name}")
            lines.append("          type: tts")
            lines.append("        metrics:")
            lines.append("          - type: sha256")
            lines.append(f"            value: {sha}")
            if size and size != 0:
                lines.append("          - type: bytes")
                lines.append(f"            value: {size}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def build_body(name: str, languages: list[str], manifest: dict | None) -> str:
    lang_lines = (
        "".join(f"- **{lang}** — {LANG_NAMES.get(lang, lang)}\n" for lang in languages)
        or "- (language list not detected — populate manually)\n"
    )

    quality = "medium"
    if manifest and "quality" in manifest:
        quality = manifest["quality"]

    return f"""# {name}

VITS-based neural TTS model published as part of [piper-plus](https://github.com/ayutaz/piper-plus).

## Languages

{lang_lines}

## Usage

```python
from piper import PiperVoice

voice = PiperVoice.load("{name}.onnx", config_path="{name}.onnx.json")
audio = voice.synthesize_array("Hello, world!", speaker_id=0)
```

For Rust / C# / Go / WASM / C++ usage see the
[piper-plus runtimes](https://github.com/ayutaz/piper-plus#runtimes) section.

## Model details

- **Architecture**: VITS (MB-iSTFT decoder where applicable)
- **Quality**: {quality}
- **Library**: piper-plus
- **License**: MIT

## SHA-256 verification

The official SHA-256 of this model is pinned in
[`docs/spec/model-sha256-manifest.toml`](https://github.com/ayutaz/piper-plus/blob/dev/docs/spec/model-sha256-manifest.toml).
All piper-plus runtimes verify the downloaded artifact against this value
before loading. A hash mismatch is a hard error.

## Citation

If you use piper-plus, please cite the original piper project:

```bibtex
@misc{{piper2023,
  author = {{Hood, Michael}},
  title  = {{piper: A fast, local neural text to speech system}},
  year   = {{2023}},
  url    = {{https://github.com/rhasspy/piper}}
}}
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HF Model Card README.md")
    parser.add_argument(
        "--config", type=Path, required=True, help="path to <model>.onnx.json"
    )
    parser.add_argument(
        "--name", required=True, help="model name (matches model-sha256-manifest.toml)"
    )
    parser.add_argument(
        "--output", type=Path, help="output path (default: print to stdout)"
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"error: config not found: {args.config}", file=sys.stderr)
        return 1
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {args.config}: {exc}", file=sys.stderr)
        return 1

    languages = extract_languages(config)
    manifest = read_model_manifest_entry(args.name)

    frontmatter = build_frontmatter(args.name, languages, manifest)
    body = build_body(args.name, languages, manifest)
    full = frontmatter + "\n" + body

    if args.output:
        args.output.write_text(full, encoding="utf-8")
        print(
            f"wrote {args.output} ({len(languages)} language(s), "
            f"manifest={'found' if manifest else 'absent'})"
        )
    else:
        print(full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
