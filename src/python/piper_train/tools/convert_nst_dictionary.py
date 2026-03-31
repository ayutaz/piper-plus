#!/usr/bin/env python3
"""Convert NST Swedish dictionary (SAMPA) to IPA JSON for piper-plus.

Downloads are NOT handled by this tool. Obtain ``lexicon-sv.tgz`` from
OpenSLR 29 (https://www.openslr.org/29/) and extract ``lexicon.txt``.

Usage:
    python -m piper_train.tools.convert_nst_dictionary \
        -i lexicon.txt \
        -o sv_lexicon_core.json.gz \
        --gzip --tier core --validate
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import unicodedata
from collections import Counter
from pathlib import Path


_LOGGER = logging.getLogger("convert_nst_dictionary")

# =========================================================================
# SAMPA → IPA mapping table (43 phonemes)
# Reference: docs/design/swedish-fr01-fr02-spec.md Section 2.2
# =========================================================================

NST_SAMPA_TO_IPA: dict[str, str] = {
    # Long vowels (9)
    "A:": "\u0251\u02d0",  # ɑː
    "e:": "e\u02d0",  # eː
    "E:": "\u025b\u02d0",  # ɛː
    "i:": "i\u02d0",  # iː
    "o:": "o\u02d0",  # oː
    "u:": "u\u02d0",  # uː
    "}:": "\u0289\u02d0",  # ʉː
    "y:": "y\u02d0",  # yː
    "2:": "\u00f8\u02d0",  # øː
    # Short vowels (9)
    "a": "a",
    "e": "e",
    "E": "\u025b",  # ɛ
    "I": "\u026a",  # ɪ
    "O": "\u0254",  # ɔ
    "U": "\u028a",  # ʊ
    "u0": "\u0289",  # ʉ
    "Y": "\u028f",  # ʏ
    "9": "\u0153",  # œ
    # Basic consonants (16)
    "b": "b",
    "d": "d",
    "f": "f",
    "g": "\u0261",  # ɡ  (U+0261, NOT ASCII g)
    "h": "h",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "v": "v",
    "N": "\u014b",  # ŋ
    # Special consonants (2)
    "S": "\u0267",  # ɧ  sj-sound
    "s'": "\u0255",  # ɕ  tj-sound
    # Retroflex consonants (5)
    "n`": "\u0273",  # ɳ
    "t`": "\u0288",  # ʈ
    "d`": "\u0256",  # ɖ
    "l`": "\u026d",  # ɭ
    "s`": "\u0282",  # ʂ
    # Diphthongs (2)
    "a*U": "a\u028a",  # aʊ
    "E*U": "\u025b\u028a",  # ɛʊ
}

# =========================================================================
# Spot-check table (V-1 .. V-20)
# Reference: docs/design/swedish-fr01-fr02-spec.md Section 2.7.1
# =========================================================================

SPOT_CHECK: list[tuple[str, str, str]] = [
    # (word, sampa, expected_ipa)
    ("barn", '"b A: n`', "\u02c8b\u0251\u02d0\u0273"),  # ˈbɑːɳ
    ("sked", '"S e: d', "\u02c8\u0267e\u02d0d"),  # ˈɧeːd
    ("skola", '"s k u: l a', "\u02c8sku\u02d0la"),  # ˈskuːla
    ("kind", "\"s' I n d", "\u02c8\u0255\u026and"),  # ˈɕɪnd
    ("sjuk", '"S }: k', "\u02c8\u0267\u0289\u02d0k"),  # ˈɧʉːk
    ("flicka", '"f l I k a', "\u02c8fl\u026aka"),  # ˈflɪka
    ("station", 's t a "S u: n', "sta\u02c8\u0267u\u02d0n"),  # staˈɧuːn
    ("chef", '"S e: f', "\u02c8\u0267e\u02d0f"),  # ˈɧeːf
    ("bord", '"b u: d`', "\u02c8bu\u02d0\u0256"),  # ˈbuːɖ
    ("fors", '"f O s`', "\u02c8f\u0254\u0282"),  # ˈfɔʂ
    ("kung", '"k u0 N', "\u02c8k\u0289\u014b"),  # ˈkʉŋ
    ("hus", '"h }: s', "\u02c8h\u0289\u02d0s"),  # ˈhʉːs
    ("gata", '"g A: t a', "\u02c8\u0261\u0251\u02d0ta"),  # ˈɡɑːta
    ("fest", '"f E s t', "\u02c8f\u025bst"),  # ˈfɛst
    ("sol", '"s u: l', "\u02c8su\u02d0l"),  # ˈsuːl
    ("son", '"s o: n', "\u02c8so\u02d0n"),  # ˈsoːn
    ("kort", '"k O t`', "\u02c8k\u0254\u0288"),  # ˈkɔʈ
    ("öl", '"2: l', "\u02c8\u00f8\u02d0l"),  # ˈøːl
    ("syn", '"s y: n', "\u02c8sy\u02d0n"),  # ˈsyːn
    ("ost", '"U s t', "\u02c8\u028ast"),  # ˈʊst
]


# =========================================================================
# Core functions
# =========================================================================


def parse_nst_line(line: str) -> tuple[str, str] | None:
    """Parse one NST dictionary line.

    Returns (lowercase_word, sampa) or None for invalid lines.
    """
    line = line.rstrip("\n\r")
    if not line:
        return None

    parts = line.split("\t")
    if len(parts) != 2:
        _LOGGER.warning("Skipping malformed line (expected 2 columns): %r", line)
        return None

    word = parts[0].strip()
    sampa = parts[1].strip()

    if not word or not sampa:
        _LOGGER.warning("Skipping empty word or pronunciation: %r", line)
        return None

    # NFC normalize + lowercase
    word_lower = unicodedata.normalize("NFC", word.lower())
    return (word_lower, sampa)


def convert_sampa_to_ipa(sampa: str) -> str:
    """Convert space-delimited SAMPA pronunciation to IPA string."""
    ipa_parts: list[str] = []

    for token in sampa.split():
        stress_prefix = ""

        # Stress prefix: %"  before "  before %
        if token.startswith('%"'):
            stress_prefix = "\u02cc\u02c8"  # ˌˈ
            token = token[2:]
        elif token.startswith('"'):
            stress_prefix = "\u02c8"  # ˈ
            token = token[1:]
        elif token.startswith("%"):
            stress_prefix = "\u02cc"  # ˌ
            token = token[1:]

        # Stress-only token (no phoneme after prefix)
        if not token:
            if stress_prefix:
                ipa_parts.append(stress_prefix)
            continue

        ipa = NST_SAMPA_TO_IPA.get(token)
        if ipa is not None:
            ipa_parts.append(stress_prefix + ipa)
        else:
            _LOGGER.warning("Unknown SAMPA token: %r (passing through)", token)
            ipa_parts.append(stress_prefix + token)

    return "".join(ipa_parts)


def should_skip_entry(word: str, sampa: str, seen: set[str]) -> tuple[bool, str]:
    """Determine if an entry should be filtered out.

    Returns (should_skip, reason).
    """
    word_upper = word.upper().strip()

    # F-1: silence marker
    if word_upper == "!SIL":
        return (True, "silence_marker")

    # F-2: unknown marker
    if word_upper == "<UNK>":
        return (True, "unknown_marker")

    # F-3: hyphen-prefixed fragment
    if word.startswith("-"):
        return (True, "hyphen_prefix")

    # F-4: empty pronunciation
    if not sampa.strip():
        return (True, "empty_pronunciation")

    # F-5: duplicate (keep first variant)
    word_lower = word.lower().strip()
    if word_lower in seen:
        return (True, "duplicate")

    return (False, "")


def is_simple_word(sampa: str) -> bool:
    """Core tier filter: word has no secondary stress (%)."""
    return "%" not in sampa


def run_spot_check(dictionary: dict[str, str]) -> bool:
    """Validate 20 spot-check words against the converted dictionary.

    Returns True if all pass.
    """
    all_ok = True
    for word, _sampa, expected_ipa in SPOT_CHECK:
        actual = dictionary.get(word)
        if actual is None:
            _LOGGER.error("Spot check FAIL: %r not found in dictionary", word)
            all_ok = False
        elif actual != expected_ipa:
            _LOGGER.error(
                "Spot check FAIL: %r expected %r, got %r",
                word,
                expected_ipa,
                actual,
            )
            all_ok = False
        else:
            _LOGGER.info("Spot check OK: %r -> %r", word, actual)
    return all_ok


# =========================================================================
# CLI
# =========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert NST Swedish dictionary (SAMPA) to IPA JSON.",
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="NST dictionary input file (lexicon.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Output JSON file path (.json or .json.gz)",
    )
    parser.add_argument(
        "--gzip",
        action="store_true",
        help="Compress output with gzip",
    )
    parser.add_argument(
        "-t",
        "--tier",
        choices=["core", "full"],
        default="full",
        help="Output tier: core (simple words only) or full (default: full)",
    )
    parser.add_argument(
        "-v",
        "--validate",
        action="store_true",
        help="Run spot-check validation on 20 reference words",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Suppress conversion statistics output",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress warning-level log messages",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # 1. Check input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 2. Convert
    result: dict[str, str] = {}
    seen: set[str] = set()
    stats: Counter[str] = Counter()
    unknown_tokens: set[str] = set()

    # Track unknown SAMPA via temporary handler
    original_warning = _LOGGER.warning

    def _track_unknown(msg: str, *a: object, **kw: object) -> None:
        if "Unknown SAMPA token" in msg and a:
            unknown_tokens.add(str(a[0]))
        original_warning(msg, *a, **kw)

    _LOGGER.warning = _track_unknown  # type: ignore[assignment]

    try:
        with open(args.input, encoding="utf-8") as fp:
            for _line_num, line in enumerate(fp, 1):
                stats["input_lines"] += 1

                parsed = parse_nst_line(line)
                if parsed is None:
                    stats["malformed"] += 1
                    continue

                word, sampa = parsed

                skip, reason = should_skip_entry(word, sampa, seen)
                if skip:
                    stats[reason] += 1
                    continue

                # Core tier filter
                if args.tier == "core" and not is_simple_word(sampa):
                    stats["compound_filtered"] += 1
                    seen.add(word)
                    continue

                ipa = convert_sampa_to_ipa(sampa)
                result[word] = ipa
                seen.add(word)
                stats["converted"] += 1
    except UnicodeDecodeError as e:
        print(f"Error: Failed to decode input file: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        _LOGGER.warning = original_warning  # type: ignore[assignment]

    # 3. Validate
    if args.validate:
        if not run_spot_check(result):
            print("Error: Spot check validation failed!", file=sys.stderr)
            sys.exit(4)
        _LOGGER.info("Spot check passed (20/20)")

    # 4. Write output
    sorted_result = dict(sorted(result.items()))
    try:
        if args.gzip:
            with gzip.open(args.output, "wt", encoding="utf-8") as fp:
                json.dump(sorted_result, fp, ensure_ascii=False, separators=(",", ":"))
        else:
            with open(args.output, "w", encoding="utf-8", newline="\n") as fp:
                json.dump(sorted_result, fp, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        print(f"Error: Failed to write output: {e}", file=sys.stderr)
        sys.exit(3)

    # 5. Stats
    if not args.no_stats:
        total_skipped = (
            stats["silence_marker"]
            + stats["unknown_marker"]
            + stats["hyphen_prefix"]
            + stats["empty_pronunciation"]
            + stats["duplicate"]
        )
        print(
            f"\nNST Dictionary Conversion Summary:\n"
            f"  Input lines:     {stats['input_lines']:,}\n"
            f"  Valid entries:    {stats['converted']:,}\n"
            f"  Skipped (filter): {total_skipped:,}\n"
            f"    !SIL:           {stats['silence_marker']:,}\n"
            f"    <UNK>:          {stats['unknown_marker']:,}\n"
            f"    Hyphen prefix:  {stats['hyphen_prefix']:,}\n"
            f"    Empty pron:     {stats['empty_pronunciation']:,}\n"
            f"    Duplicate:      {stats['duplicate']:,} (first variant kept)\n"
            f"  Malformed lines:  {stats['malformed']:,}\n"
            f"  Compound filtered:{stats['compound_filtered']:,}\n"
            f"  Unknown SAMPA:    {len(unknown_tokens)}\n"
            f"  Output entries:   {len(sorted_result):,}\n"
            f"  Output file:      {args.output}"
            f" ({args.output.stat().st_size / 1024 / 1024:.1f} MB)\n",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
