#!/usr/bin/env python3
"""PUA-encode multi-codepoint phoneme_id_map keys in a model config.json.

Lightweight, dependency-free companion to
``piper_train.update_model_config`` / ``scripts/regenerate_tsukuyomi_config.py``:
it reads the canonical PUA table from
``src/python/g2p/piper_plus_g2p/data/pua.json`` and rewrites any raw
multi-codepoint phoneme_id_map key (e.g. ɔɪ / œ̃ / ɐ̃) to its single PUA
codepoint, in place. Idempotent — a config that is already all single-codepoint
is left untouched.

Why this exists: the v1.12.0 export leaked those three IPA tokens as raw
multi-codepoint keys into the distributed configs, which the C++ runtime
rejects (``"…" is not a single codepoint`` → Windows inference crash).
``regenerate_tsukuyomi_config.py`` fixes it but pulls in the g2p package (and
pyopenjtalk); this script needs only the stdlib, so it runs in minimal CI / e2e
environments and serves as a quick local fix for users who already downloaded a
stale config.

Usage::

    python scripts/fix_config_pua.py CONFIG [CONFIG ...]

Exit code: 0 = fixed or already clean; 2 = an unmappable multi-codepoint key
remained (a real PUA-table gap that must be investigated, not silently passed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PUA_JSON = REPO_ROOT / "src" / "python" / "g2p" / "piper_plus_g2p" / "data" / "pua.json"


def load_pua_mapping() -> dict[str, int]:
    data = json.loads(PUA_JSON.read_text(encoding="utf-8"))
    return {entry["token"]: int(entry["codepoint"], 16) for entry in data["entries"]}


def _cps(s: str) -> str:
    return "+".join(f"U+{ord(c):04X}" for c in s)


def fix_config(path: Path, tok2cp: dict[str, int]) -> int:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    id_map = cfg.get("phoneme_id_map")
    if not isinstance(id_map, dict):
        print(f"{path}: no phoneme_id_map - skipping")
        return 0

    new_map: dict[str, object] = {}
    fixed: list[str] = []
    unmapped: list[str] = []
    for key, ids in id_map.items():
        if len(key) > 1:
            cp = tok2cp.get(key)
            if cp is None:
                unmapped.append(_cps(key))
                new_map[key] = ids
            else:
                new_map[chr(cp)] = ids
                fixed.append(f"{_cps(key)}->U+{cp:04X}")
        else:
            new_map[key] = ids

    if unmapped:
        print(
            f"{path}: ERROR - unmappable multi-codepoint key(s): {unmapped}. "
            "These are not in pua.json; investigate the PUA table.",
            file=sys.stderr,
        )
        return 2
    if not fixed:
        print(f"{path}: already single-codepoint ({len(new_map)} keys) - no change")
        return 0

    cfg["phoneme_id_map"] = new_map
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{path}: PUA-encoded {len(fixed)} key(s): {fixed}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    tok2cp = load_pua_mapping()
    rc = 0
    for arg in argv:
        p = Path(arg)
        if not p.is_file():
            print(f"{p}: not found - skipping")
            continue
        rc = max(rc, fix_config(p, tok2cp))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
