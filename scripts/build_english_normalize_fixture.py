#!/usr/bin/env python3
"""Build the English text-normalization fixture shared by the non-Python runtimes.

Python's English G2P is g2p_en (vendored in
``src/python/g2p/piper_plus_g2p/_vendor/g2p_en``). Before its dictionary
lookup it rewrites the text:

1. ``normalize_numbers`` spells numbers out with inflect (``123`` -> ``one
   hundred twenty-three``, ``1984`` -> ``nineteen eighty-four``, ``$5`` ->
   ``five dollars``, ``2nd`` -> ``second``);
2. accents are stripped (NFD, combining marks removed) and the text is
   lowercased;
3. every character other than ``a-z ' . , ? ! -`` and space is removed;
4. ``i.e.`` / ``e.g.`` become ``that is`` / ``for example``;
5. nltk's ``TweetTokenizer`` splits the result into words.

The other runtimes cannot import inflect or nltk, so they port these steps.
This script records what Python produces, and the C++ and Rust tests compare
their ports with it:

* ``numbers``: ``normalize_numbers(input)``;
* ``tokens``: the lowercased words after all five steps.

Usage:
    uv run python scripts/build_english_normalize_fixture.py          # write
    uv run python scripts/build_english_normalize_fixture.py --check  # verify
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "tests" / "fixtures" / "g2p" / "english_normalize_cases.json"

NUMBER_INPUTS = [
    *[str(n) for n in range(0, 22)],
    *[
        str(n)
        for n in (
            30,
            40,
            42,
            45,
            50,
            60,
            70,
            80,
            90,
            99,
            100,
            101,
            110,
            115,
            123,
            200,
            999,
        )
    ],
    *[str(n) for n in (1000, 1001, 1009, 1010, 1099, 1100, 1234, 1900, 1984, 1999)],
    *[str(n) for n in (2000, 2001, 2009, 2010, 2024, 2100, 2999, 3000, 3001, 9999)],
    *[
        str(n)
        for n in (10000, 12345, 100000, 999999, 1000000, 1000001, 1234567, 1000000000)
    ],
    *[
        str(n)
        for n in (
            5005,
            5100,
            5110,
            10001,
            21000,
            100001,
            100100,
            100101,
            101000,
            1000010,
        )
    ],
    *[
        str(n)
        for n in (1000100, 1001001, 2000001, 1000000001, 123456789012, 10**15, 10**18)
    ],
    "007",
    "1st",
    "2nd",
    "3rd",
    "4th",
    "11th",
    "12th",
    "13th",
    "21st",
    "22nd",
    "101st",
    "111th",
    "1000th",
    "0th",
    "5th",
    "8th",
    "9th",
    "20th",
    "40th",
    "100th",
    "1100th",
    "5005th",
    "10001st",
    "1000001st",
    "$0",
    "$1",
    "$5",
    "$100",
    "$1.50",
    "$0.99",
    "$1.01",
    "$.5",
    "$1,000",
    "$1.2.3",
    "£5",
    "3.14",
    "0.5",
    "10.25",
    "1,234",
    "1,000,000",
    "R2D2",
    "COVID-19",
    "It's 3 o'clock.",
    "I have $250 in my pocket.",
    "x, 5",
    "5.",
    "a1b2",
]

TOKEN_INPUTS = [
    "Hello, world!",
    "don't",
    "It's 3 o'clock.",
    "'quote'",
    "cats' toys",
    "uh-huh",
    "a-b-c",
    "x - y",
    "hello--world",
    "-hello",
    "hello-",
    "wait...",
    "wait . . . now",
    "yes?!",
    "Really?!!!!",
    "e.g. and i.e.",
    "E.G. or I.E.",
    "Mr. Smith",
    "U.S.A.",
    "hi.there",
    "foo.bar.baz",
    "uh-huh.ok",
    "x.co",
    "a.b",
    "well.i",
    "it's.ok",
    "hello.abcdefghijklmn",
    "hello.there's",
    "a----b",
    "wait.....",
    "so''''",
    "x -- y",
    "café",
    "naïve",
    "résumé",
    "ChatGPT and GitHub",
    "iPhone",
    "rock'n'roll",
    "'90s",
    "123",
    "COVID-19",
    "R2D2",
    "2nd",
    "$5",
    "3.14",
    "(parens) [brackets] {braces}",
    '"double quotes"',
    "semi; colon: tab\tnew\nline",
    "a",
    "I",
    "",
]


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def build() -> dict:
    from nltk.tokenize import TweetTokenizer

    sys.path.insert(0, str(REPO_ROOT / "src" / "python" / "g2p"))
    from piper_plus_g2p._vendor.g2p_en.expand import normalize_numbers

    tokenize = TweetTokenizer().tokenize

    def tokens(text: str) -> list[str]:
        # Same steps, in the same order, as g2p_en's G2p.__call__.
        text = _strip_accents(normalize_numbers(text)).lower()
        text = re.sub(r"[^ a-z'.,?!\-]", "", text)
        text = text.replace("i.e.", "that is").replace("e.g.", "for example")
        return tokenize(text)

    return {
        "schema_version": 1,
        "description": (
            "g2p_en's text normalization, generated from the vendored Python code by "
            "scripts/build_english_normalize_fixture.py. 'numbers' is normalize_numbers(input); "
            "'tokens' is the lowercased words after normalize_numbers, accent stripping, "
            "the character filter, the i.e./e.g. replacement and nltk's TweetTokenizer."
        ),
        "numbers": [
            {"input": s, "output": normalize_numbers(s)} for s in NUMBER_INPUTS
        ],
        "tokens": [{"input": s, "tokens": tokens(s)} for s in TOKEN_INPUTS],
    }


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the fixture is out of date"
    )
    args = parser.parse_args(argv)

    text = render(build())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != text:
            print(
                f"{OUTPUT.relative_to(REPO_ROOT).as_posix()} is out of date; run without --check"
            )
            return 1
        print(f"OK: {OUTPUT.relative_to(REPO_ROOT).as_posix()} is up to date")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
