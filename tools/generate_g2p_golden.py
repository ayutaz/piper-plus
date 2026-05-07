#!/usr/bin/env python3
"""Generate Python golden phonemes for cross-runtime parity (Issue #388).

Reads ``tests/fixtures/g2p/phoneme_test_cases.json`` and produces
``tests/fixtures/g2p/phoneme_test_cases_golden.json`` by running each
non-Japanese case through ``piper_plus_g2p.MultilingualPhonemizer``.

The Kotlin Android AAR's instrumented test then asserts byte-for-byte
equality against this golden file. JA cases are intentionally skipped
because they require the OpenJTalk dictionary (~102 MB) which is not
bundled in the test APK.

Run with::

    uv run --with-editable src/python/g2p \\
        python tools/generate_g2p_golden.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_LANGUAGES = ["en", "es", "fr", "ja", "ko", "pt", "sv", "zh"]
_LATIN_LANGS = frozenset({"en", "es", "fr", "pt", "sv"})


def _load_phonemizer(default_latin: str):
    """Build a MultilingualPhonemizer with the requested Latin fallback.

    The C API picks ``defaultLatin`` from ``synthesisConfig.languageId`` when
    that ID resolves to a Latin-script language (see piper.cpp around
    ``UnicodeLanguageDetector(multiLangs, defaultLatin)``). To stay
    byte-for-byte compatible we therefore must regenerate the phonemizer
    per case, threading the fixture's ``language`` through.
    """
    from piper_plus_g2p import MultilingualPhonemizer  # type: ignore

    return MultilingualPhonemizer(
        languages=_LANGUAGES,
        default_latin_language=default_latin,
    )


def _resolve_default_latin(case_lang: str) -> str:
    """Map the per-case language code to the Latin fallback C API would pick.

    Non-Latin languages (`ja`, `ko`, `zh`) don't influence the Latin segmenter
    on the C++ side, so we keep the standard `"en"` fallback for them.
    """
    return case_lang if case_lang in _LATIN_LANGS else "en"


def _phonemize_one(phonemizer, text: str) -> str:
    tokens = phonemizer.phonemize(text)
    return " ".join(tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="tests/fixtures/g2p/phoneme_test_cases.json",
        help="Input fixture path",
    )
    parser.add_argument(
        "--output",
        default="tests/fixtures/g2p/phoneme_test_cases_golden.json",
        help="Output golden fixture path",
    )
    parser.add_argument(
        "--include-ja",
        action="store_true",
        help="Also pre-compute JA cases (requires OpenJTalk dictionary).",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help=(
            "Exit 0 even when some cases failed (e.g. KO on Windows where "
            "g2pk2 cannot find eunjeon). By default failures cause exit 2 "
            "to gate the CI re-generator job."
        ),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    in_path = (repo_root / args.input).resolve()
    out_path = (repo_root / args.output).resolve()

    if not in_path.exists():
        print(f"Input fixture not found: {in_path}", file=sys.stderr)
        return 1

    fixture = json.loads(in_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = fixture.get("test_cases", [])

    # Cache phonemizers by `default_latin_language`; we only ever need a
    # handful (one per Latin-script language plus the generic ``en`` for
    # non-Latin cases).
    phonemizer_cache: dict[str, Any] = {}

    def get_phonemizer(default_latin: str):
        if default_latin not in phonemizer_cache:
            phonemizer_cache[default_latin] = _load_phonemizer(default_latin)
        return phonemizer_cache[default_latin]

    golden_cases: list[dict[str, Any]] = []
    skipped_ja = 0
    skipped_ko = 0
    failed: list[dict[str, str]] = []
    for case in cases:
        lang: str = case["language"]
        if lang == "ja" and not args.include_ja:
            skipped_ja += 1
            continue
        text: str = case["input"]
        try:
            phonemizer = get_phonemizer(_resolve_default_latin(lang))
            golden_str = _phonemize_one(phonemizer, text)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            print(
                f"WARN: phonemize failed for [{lang}] '{text}': {err}",
                file=sys.stderr,
            )
            failed.append({"language": lang, "input": text, "error": err})
            if lang == "ko":
                skipped_ko += 1
            continue
        golden_cases.append(
            {
                "language": lang,
                "input": text,
                "description": case.get("description", ""),
                "expected_phonemes": golden_str,
                "expected_token_count": len(golden_str.split(" ")) if golden_str else 0,
            }
        )

    out = {
        "version": 2,
        "source_fixture": str(in_path.relative_to(repo_root)).replace("\\", "/"),
        "generator": "tools/generate_g2p_golden.py",
        "description": (
            "Python pre-computed golden phonemes for byte-for-byte cross-runtime "
            "parity tests. Generated by piper_plus_g2p.MultilingualPhonemizer "
            "with default_latin_language threaded through the per-case "
            "language code, mirroring the C API's `defaultLatin` selection in "
            "piper.cpp around `UnicodeLanguageDetector(multiLangs, defaultLatin)`. "
            "Kotlin / Rust / Go / WASM / C# / C++ runtimes assert string equality "
            "against `expected_phonemes`."
        ),
        "skipped_ja_cases": skipped_ja,
        "skipped_ko_cases": skipped_ko,
        "failed_cases": failed,
        "test_cases": golden_cases,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(golden_cases)} golden cases "
        f"(skipped JA={skipped_ja}, skipped KO={skipped_ko}, failed={len(failed)}) "
        f"to {out_path}",
    )
    if failed and not args.allow_failures:
        print(
            "ERROR: some cases failed to phonemize. Re-run with --allow-failures "
            "if you intentionally want a partial golden, or install missing "
            "dependencies (e.g. eunjeon for Korean).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
