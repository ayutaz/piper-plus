#!/usr/bin/env python3
"""Compare two G2P golden JSON files for drift in `expected_phonemes`.

Used by the L4 parity-golden CI job: the committed golden may have been
generated on a host without all language deps installed (e.g. Windows
without eunjeon for KO), so we tolerate **missing** cases on either side
but fail loudly on any case present in both that disagrees on phonemes.

Exit codes:
  0 — agreement on every overlapping (language, input) pair
  1 — drift detected in at least one overlapping case
"""

from __future__ import annotations

import argparse
import json
import sys


def _build_map(root: dict) -> dict[tuple[str, str], str]:
    return {
        (c["language"], c["input"]): c["expected_phonemes"]
        for c in root.get("test_cases", [])
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("committed", help="Committed golden JSON (in repo)")
    parser.add_argument("regenerated", help="Just-regenerated golden JSON")
    args = parser.parse_args()

    with open(args.committed, encoding="utf-8") as f:
        committed = json.load(f)
    with open(args.regenerated, encoding="utf-8") as f:
        regen = json.load(f)

    ma = _build_map(committed)
    mb = _build_map(regen)

    overlap = sorted(set(ma) & set(mb))
    drift = [(k, ma[k], mb[k]) for k in overlap if ma[k] != mb[k]]

    if drift:
        print(
            f"::error::Committed golden disagrees with regen on {len(drift)} "
            f"of {len(overlap)} overlapping cases:",
            file=sys.stderr,
        )
        for (lang, text), a, b in drift:
            print(
                f"  [{lang}] {text!r}\n    committed: {a}\n    regen:     {b}",
                file=sys.stderr,
            )
        return 1

    extra_in_regen = sorted(set(mb) - set(ma))
    if extra_in_regen:
        print(
            f"::warning::Regen has {len(extra_in_regen)} cases the committed "
            "golden lacks (likely KO that needs Linux + eunjeon):",
            file=sys.stderr,
        )
        for lang, text in extra_in_regen:
            print(f"  - [{lang}] {text!r}", file=sys.stderr)

    extra_in_committed = sorted(set(ma) - set(mb))
    if extra_in_committed:
        print(
            f"::warning::Committed golden has {len(extra_in_committed)} cases "
            "the regen lacks (verify nothing was lost):",
            file=sys.stderr,
        )
        for lang, text in extra_in_committed:
            print(f"  - [{lang}] {text!r}", file=sys.stderr)

    print(f"OK: {len(overlap)} cases agree byte-for-byte (drift=0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
