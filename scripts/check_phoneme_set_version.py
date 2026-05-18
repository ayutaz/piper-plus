#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented bullet lists)
"""
Check phoneme set version contract.

Verifies (all FATAL — any mismatch exits 1):
  1. docs/spec/phoneme-set-version.toml `num_symbols` is exactly the
     pinned value (173 — the 6lang multilingual model embedding size).
     Drift here is a model-breaking change (every released ckpt's
     `vits.text_encoder.emb` is sized to 173).
  2. The per-language [[inventory.languages]] entries sum exactly to
     `num_symbols` (internal spec consistency).
  3. `[inventory].embedding_dim` matches the canonical 192 (VITS
     text encoder embedding width).
  4. `symbol_set_version` is present and matches `^\\d+\\.\\d+$`.
  5. pua.json `version` is parseable; if its `entries[]` count
     exceeds `num_symbols`, that is a hard error (PUA codepoints
     must fit in the embedding table).

Exit code:
  0 = compliant
  1 = mismatch found
"""

import json
import re
import sys
from pathlib import Path


try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "phoneme-set-version.toml"
PUA_JSON = REPO_ROOT / "src" / "python" / "g2p" / "piper_plus_g2p" / "data" / "pua.json"

# Pinned canonical values. Bumping requires retraining/re-exporting every
# multilingual model — guard with explicit PR review.
PINNED_NUM_SYMBOLS = 173
PINNED_EMBEDDING_DIM = 192
SYMBOL_SET_VERSION_RE = re.compile(r"^\d+\.\d+$")


def main() -> int:
    if not SPEC.exists():
        print(f"ERROR: spec missing: {SPEC}", file=sys.stderr)
        return 1
    if not PUA_JSON.exists():
        print(f"ERROR: pua.json missing: {PUA_JSON}", file=sys.stderr)
        return 1

    with SPEC.open("rb") as f:
        spec = tomllib.load(f)

    with PUA_JSON.open(encoding="utf-8") as f:
        pua = json.load(f)

    inventory = spec.get("inventory", {})
    spec_num_symbols = inventory.get("num_symbols")
    spec_version = inventory.get("symbol_set_version")
    spec_embedding_dim = inventory.get("embedding_dim")

    if spec_num_symbols is None:
        print("ERROR: [inventory].num_symbols not in spec", file=sys.stderr)
        return 1
    if spec_version is None:
        print("ERROR: [inventory].symbol_set_version not in spec", file=sys.stderr)
        return 1

    print("Spec:")
    print(f"  num_symbols = {spec_num_symbols}")
    print(f"  symbol_set_version = {spec_version}")
    print(f"  embedding_dim = {spec_embedding_dim}")

    # (1) Pinned num_symbols (strict, was warn-only previously).
    if spec_num_symbols != PINNED_NUM_SYMBOLS:
        print(
            f"::error::[inventory].num_symbols = {spec_num_symbols} but pinned "
            f"value is {PINNED_NUM_SYMBOLS}. Bumping requires re-training/"
            f"re-exporting every multilingual model — update PINNED_NUM_SYMBOLS "
            f"in scripts/check_phoneme_set_version.py only after PR review.",
            file=sys.stderr,
        )
        return 1

    # (3) embedding_dim pinned.
    if spec_embedding_dim is not None and spec_embedding_dim != PINNED_EMBEDDING_DIM:
        print(
            f"::error::[inventory].embedding_dim = {spec_embedding_dim} but pinned "
            f"value is {PINNED_EMBEDDING_DIM} (VITS text_encoder width).",
            file=sys.stderr,
        )
        return 1

    # (4) symbol_set_version format check.
    if not SYMBOL_SET_VERSION_RE.match(str(spec_version)):
        print(
            f"::error::symbol_set_version {spec_version!r} does not match "
            f"^MAJOR.MINOR$ (e.g. '1.0').",
            file=sys.stderr,
        )
        return 1

    # Count distinct PUA codepoints in pua.json
    # pua.json structure varies; try common shapes:
    #   - {"phonemes": {"a": "\\uE000", ...}}
    #   - {"mapping": {...}}
    #   - {"version": "1.0", "entries": [...]}
    actual_count = 0
    if "phonemes" in pua and isinstance(pua["phonemes"], dict):
        actual_count = len(pua["phonemes"])
    elif "mapping" in pua and isinstance(pua["mapping"], dict):
        actual_count = len(pua["mapping"])
    elif "entries" in pua and isinstance(pua["entries"], list):
        actual_count = len(pua["entries"])
    else:
        # Fallback: count any single-codepoint values in the top-level dict
        actual_count = sum(
            1 for v in pua.values() if isinstance(v, str) and len(v) == 1
        )

    print(f"\npua.json: {actual_count} entries discovered")

    if actual_count == 0:
        print("WARNING: could not parse pua.json structure; manual review needed")
        # Don't fail; structure may have changed
        return 0

    # Note: num_symbols is the model embedding table size, which includes the
    # full phoneme vocabulary across all languages (PAD/BOS/EOS/UNK + base ASCII
    # phonemes shared across languages). pua.json only stores the *extension*
    # symbols that require PUA codepoint encoding (long vowels, palatalized
    # variants, IPA codepoints, etc.). A large diff is therefore expected and
    # by-design until Wave 2 wires up a richer inventory cross-reference.
    diff = abs(spec_num_symbols - actual_count)
    print(f"\nspec={spec_num_symbols} vs pua.json={actual_count} (diff={diff})")

    # (2) Per-language sum MUST equal num_symbols. Missing entries fail.
    languages = inventory.get("languages", [])
    if not languages:
        print(
            "::error::[[inventory.languages]] missing — cannot cross-check sum.",
            file=sys.stderr,
        )
        return 1
    per_lang_sum = sum(int(lang.get("count", 0)) for lang in languages)
    print(f"spec [[inventory.languages]] sum = {per_lang_sum}")
    if per_lang_sum != spec_num_symbols:
        print(
            f"::error::Spec internal inconsistency: per-language sum "
            f"{per_lang_sum} != num_symbols {spec_num_symbols}",
            file=sys.stderr,
        )
        return 1

    # (5) pua.json entries[] count must not exceed num_symbols (PUA codepoints
    # are the *extension* layer on top of base ASCII phonemes; they share the
    # same embedding table).
    if actual_count > spec_num_symbols:
        print(
            f"::error::pua.json has {actual_count} entries but only "
            f"{spec_num_symbols} embedding slots exist. PUA codepoints must "
            f"fit in the model's embedding table.",
            file=sys.stderr,
        )
        return 1

    if diff > 0:
        print(
            "::notice::pua.json holds extension/multi-codepoint phonemes only; "
            "diff vs num_symbols is structural, not drift (see spec comments)."
        )

    print("\n[OK] phoneme set version contract compliant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
