#!/usr/bin/env python3
"""Build the Chinese pinyin dictionaries shared by the non-Python runtimes.

Writes `pinyin_single.json` and `pinyin_phrases.json` from pypinyin's bundled
tables, converted to the numeric-tone form the Python canonical path produces
(`pinyin(text, style=Style.TONE3, neutral_tone_with_five=True)`): `ni3`,
`ma5`, `lv4` (v for u-umlaut).

Every runtime parser (Rust, Go, C++, and through them WASM / Swift / Android)
reads the tone as a trailing digit. The previous files were a raw dump of
pypinyin's tone-marked tables (`nǐ`), so every syllable parsed as tone 5 and
lost its final: 你好 came out as `n tone5 x o tone5`.

Usage:
    uv run --with pypinyin==0.55.0 python scripts/build_pinyin_dicts.py          # write
    uv run --with pypinyin==0.55.0 python scripts/build_pinyin_dicts.py --check  # verify

The output goes to the canonical copy under src/rust/piper-plus-g2p/data/;
`scripts/check_dictionary_consistency.py --fix` then copies it to the
mirrors declared in docs/spec/dictionary-mirrors.toml.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "src" / "rust" / "piper-plus-g2p" / "data"
# Keep in sync with docs/spec/dictionary-versions.toml [chinese.pypinyin].
PYPINYIN_VERSION = "0.55.0"


def to_tone3(syllable: str) -> str:
    from pypinyin.contrib.tone_convert import to_tone3 as convert

    return convert(syllable, neutral_tone_with_five=True)


def build() -> dict[str, bytes]:
    import pypinyin
    from pypinyin.phrases_dict import phrases_dict
    from pypinyin.pinyin_dict import pinyin_dict

    if pypinyin.__version__ != PYPINYIN_VERSION:
        raise SystemExit(
            f"pypinyin {pypinyin.__version__} found, {PYPINYIN_VERSION} required "
            "(docs/spec/dictionary-versions.toml)"
        )
    single = {
        str(codepoint): ",".join(to_tone3(s) for s in readings.split(","))
        for codepoint, readings in pinyin_dict.items()
    }
    phrases = {
        phrase: [[to_tone3(s) for s in item] for item in readings]
        for phrase, readings in phrases_dict.items()
    }
    return {
        "pinyin_single.json": _dump(single),
        "pinyin_phrases.json": _dump(phrases),
    }


def _dump(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the checked-in files differ from a fresh build",
    )
    args = parser.parse_args(argv)
    stale = []
    for name, content in build().items():
        path = OUTPUT_DIR / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                stale.append(path)
        else:
            path.write_bytes(content)
            print(f"wrote {path.relative_to(REPO_ROOT)}")
    for path in stale:
        print(
            f"STALE: {path.relative_to(REPO_ROOT)} (run scripts/build_pinyin_dicts.py)"
        )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
