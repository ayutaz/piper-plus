#!/usr/bin/env python3
"""Generate golden test outputs from the Python G2P (canonical implementation).

Usage:
    cd src/python/g2p
    uv run python tools/generate_golden.py

Outputs tests/fixtures/g2p/golden_outputs.json that Rust/JS tests can
validate against for rule-based languages (ES, FR, PT, SV).
"""

import json
import sys
from pathlib import Path


def main():
    from piper_plus_g2p import available_languages, get_phonemizer

    DETERMINISTIC_LANGUAGES = ["es", "fr", "pt", "sv"]

    test_texts = {
        "es": ["Hola, ¿cómo estás?", "Buenos días"],
        "fr": ["Bonjour, comment allez-vous?", "Merci beaucoup"],
        "pt": ["Olá, como você está?", "Bom dia"],
        "sv": ["Hej, hur mår du?", "God morgon"],
    }

    golden = {
        "version": 1,
        "generator": "piper-g2p Python v0.1.0",
        "generated_at": "2026-04-01",
        "description": "Golden outputs from Python (canonical). "
        "Rule-based languages must match exactly across all platforms.",
        "cases": [],
    }

    for lang in DETERMINISTIC_LANGUAGES:
        if lang not in available_languages():
            print(f"Skipping {lang}: not available", file=sys.stderr)
            continue
        p = get_phonemizer(lang)
        for text in test_texts.get(lang, []):
            tokens = p.phonemize(text)
            golden["cases"].append(
                {
                    "language": lang,
                    "input": text,
                    "expected_tokens": tokens,
                }
            )

    output_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "tests"
        / "fixtures"
        / "g2p"
        / "golden_outputs.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(golden, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(golden['cases'])} golden test cases -> {output_path}")


if __name__ == "__main__":
    main()
