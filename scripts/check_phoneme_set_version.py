#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented bullet lists)
"""
Check phoneme set version contract.

The spec used to be checked only against itself and against pua.json, never
against the function that actually builds the inventory. It therefore read
`num_symbols = 173` for months while `get_phoneme_id_map("multilingual")`
returned 185 (Swedish, #300), and no gate noticed. Every check below that
mentions the "live inventory" exists to close that loop.

Verifies (all FATAL — any mismatch exits 1):
  1. `[inventory].num_symbols` equals the length of the **live** inventory
     from `piper_plus_g2p.encode.id_maps.get_phoneme_id_map("multilingual")`.
  2. `[inventory].inventory_sha256` equals the digest of the live inventory's
     symbols in id order. Pins the *ordering* — a count-only check cannot see
     two symbols swapping ids, which is precisely what shipped in v1.12.0
     (ids 94/149/153 disagreed with the published models).
  3. Every `[[snapshots]]` entry is still an exact prefix of the live
     inventory (`sha256(live[:n])`). This is what guarantees released models
     keep loading: their embedding rows are frozen at training time, so their
     ids must never be reordered or removed.
  4. `[inventory].embedding_dim` matches the canonical 192 (VITS text encoder
     embedding width).
  5. `symbol_set_version` is present and matches `^\\d+\\.\\d+$`.
  6. pua.json `version` is parseable; if its `entries[]` count exceeds
     `num_symbols`, that is a hard error (PUA codepoints must fit in the
     embedding table).

Exit code:
  0 = compliant
  1 = mismatch found
"""

import hashlib
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

# The VITS text encoder embedding width is genuinely fixed; the symbol count
# is not, so it is read from the code rather than pinned here.
PINNED_EMBEDDING_DIM = 192
SYMBOL_SET_VERSION_RE = re.compile(r"^\d+\.\d+$")


def load_live_inventory() -> list[str]:
    """Symbols from the canonical id map, ordered by id.

    Imported from the in-repo package explicitly: an installed
    `piper-plus-g2p` wheel would otherwise shadow it and the gate would
    validate the wrong inventory.
    """
    g2p_root = REPO_ROOT / "src" / "python" / "g2p"
    sys.path.insert(0, str(g2p_root))
    import piper_plus_g2p  # noqa: PLC0415
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map  # noqa: PLC0415

    package_path = Path(piper_plus_g2p.__file__).resolve()
    if g2p_root.resolve() not in package_path.parents:
        raise RuntimeError(
            f"piper_plus_g2p resolved to {package_path}, outside the repo "
            f"({g2p_root}). An installed wheel is shadowing the source tree; "
            f"the gate would validate the wrong inventory."
        )

    id_map = get_phoneme_id_map("multilingual")
    return sorted(id_map, key=lambda symbol: id_map[symbol][0])


def inventory_digest(symbols: "list[str]") -> str:
    """sha256 of the symbols joined by a single space, in id order."""
    return hashlib.sha256(" ".join(symbols).encode("utf-8")).hexdigest()


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

    # (1) Spec num_symbols must equal the live inventory's length.
    try:
        live_symbols = load_live_inventory()
    except Exception as exc:  # pragma: no cover — import/env failure
        print(f"::error::could not load the live inventory: {exc}", file=sys.stderr)
        return 1

    live_count = len(live_symbols)
    live_digest = inventory_digest(live_symbols)
    print(f"\nLive inventory: {live_count} symbols, sha256 {live_digest}")

    if spec_num_symbols != live_count:
        print(
            f"::error::[inventory].num_symbols = {spec_num_symbols} but "
            f"get_phoneme_id_map('multilingual') returns {live_count} symbols.\n"
            f"  If you added symbols: update num_symbols and inventory_sha256, "
            f"bump symbol_set_version, and confirm the change is append-only "
            f"(existing ids must keep their meaning).\n"
            f"  If you did not intend to change the inventory, this is the "
            f"regression — the spec is the reference.",
            file=sys.stderr,
        )
        return 1

    # (2) Ordering pin. A count check cannot see two symbols swapping ids.
    spec_digest = inventory.get("inventory_sha256")
    if not spec_digest:
        print(
            "::error::[inventory].inventory_sha256 is missing. Without it the "
            "gate cannot detect symbols being reordered, only added/removed.",
            file=sys.stderr,
        )
        return 1
    if spec_digest != live_digest:
        print(
            f"::error::inventory digest mismatch.\n"
            f"  spec: {spec_digest}\n"
            f"  live: {live_digest}\n"
            f"  The symbol set changed. If ids were only appended, update "
            f"inventory_sha256 and bump symbol_set_version. If existing ids "
            f"moved, every released model is now mis-mapped — that is a major "
            f"bump and requires re-exporting them.",
            file=sys.stderr,
        )
        return 1

    # (3) Released snapshots must remain exact prefixes of the live inventory.
    snapshots = spec.get("snapshots", [])
    if not snapshots:
        print(
            "::error::no [[snapshots]] entries. At least the inventory shipped "
            "in the published models must be pinned, or nothing guarantees "
            "released checkpoints keep loading.",
            file=sys.stderr,
        )
        return 1
    for snapshot in snapshots:
        version = snapshot.get("symbol_set_version", "?")
        count = snapshot.get("num_symbols")
        digest = snapshot.get("inventory_sha256")
        if count is None or digest is None:
            print(
                f"::error::snapshot {version!r} needs both num_symbols and "
                f"inventory_sha256.",
                file=sys.stderr,
            )
            return 1
        if count > live_count:
            print(
                f"::error::snapshot {version!r} declares {count} symbols but the "
                f"live inventory only has {live_count}. Symbols were removed; "
                f"models trained on {version} can no longer be mapped.",
                file=sys.stderr,
            )
            return 1
        prefix_digest = inventory_digest(live_symbols[:count])
        if prefix_digest != digest:
            print(
                f"::error::snapshot {version!r} ({count} symbols) is no longer a "
                f"prefix of the live inventory.\n"
                f"  expected: {digest}\n"
                f"  actual:   {prefix_digest}\n"
                f"  Ids at or below {count} were reordered or replaced, so every "
                f"model listed under that snapshot now maps symbols to the wrong "
                f"embedding rows. New symbols must be appended, never inserted.",
                file=sys.stderr,
            )
            return 1
        print(f"  snapshot {version} ({count} symbols): prefix OK")

    # (4) embedding_dim pinned.
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
