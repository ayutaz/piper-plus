#!/usr/bin/env python3
"""Tarball-level gate: every ``exports`` target must be inside the package.

``check_wasm_variant_shipping.py`` and the JS-side "exports↔files 整合" test
both compare *declarations* against other *declarations*.  Neither of them
opens the tarball, so both stay green in the one failure mode that actually
bit us most recently:

    A ``files`` entry can be silently nullified by a nested ``.gitignore``.

``wasm-pack`` writes a ``.gitignore`` containing ``*`` into its output
directory.  ``ci.yml`` and ``deploy-webassembly-demo.yml`` then ``mv`` that
directory wholesale into ``dist/rust-wasm/``.  Measured on this repo:

    dist/rust-wasm/ with 2 files, no nested .gitignore -> 25 files packed
    the same tree plus .gitignore containing "*"       ->  0 files packed

npm emits no warning in the second case.  Releases only work today because
``actions/upload-artifact`` happens to drop hidden files by default -- an
undocumented accident that nothing pins.

This gate runs ``npm pack --dry-run --json`` and asserts that every path an
``exports`` condition points at is genuinely listed in the tarball.  It has
to run *after* the WASM artifacts are in place, so it belongs in CI lanes
that build or download them -- not in pre-commit, where ``dist/`` is empty.

Exit 0 when every exports target is present, 1 otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = REPO_ROOT / "src" / "wasm" / "openjtalk-web"


def export_targets(pkg: dict) -> list[tuple[str, str, str]]:
    """Flatten ``exports`` into ``(subpath, condition, path)`` triples."""
    out: list[tuple[str, str, str]] = []
    for subpath, value in (pkg.get("exports") or {}).items():
        items = value.items() if isinstance(value, dict) else [("default", value)]
        for condition, target in items:
            if isinstance(target, str):
                out.append((subpath, condition, target.removeprefix("./")))
    return out


def packed_paths(pkg_dir: Path) -> set[str]:
    """Return the set of paths ``npm pack`` would place in the tarball."""
    proc = subprocess.run(
        ["npm", "pack", "--dry-run", "--json"],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("ERROR: `npm pack --dry-run --json` failed:")
        print(proc.stderr.strip() or proc.stdout.strip())
        raise SystemExit(1)

    # npm prints the JSON on stdout; notices go to stderr. The top-level shape
    # changed between majors and both are in play here: the publish workflow
    # upgrades to npm@latest for OIDC trusted publishing, while a developer's
    # local npm is whatever their Node ships.
    #
    #   npm 11.x -> [ { name, files: [...], ... } ]
    #   npm 12.x -> { "<pkg-name>": { name, files: [...], ... } }
    #
    # Only the envelope differs; each entry keeps the same keys.
    payload = json.loads(proc.stdout)
    if isinstance(payload, dict):
        entries = list(payload.values())
    else:
        entries = list(payload)

    if not entries:
        print("ERROR: `npm pack --dry-run --json` reported no package.")
        raise SystemExit(1)

    return {entry["path"] for entry in entries[0]["files"]}


def main() -> int:
    pkg = json.loads((PKG_DIR / "package.json").read_text(encoding="utf-8"))
    targets = export_targets(pkg)
    if not targets:
        print("ERROR: no exports targets found -- gate would vacuously pass.")
        return 1

    packed = packed_paths(PKG_DIR)
    missing = [(s, c, p) for s, c, p in targets if p not in packed]

    if missing:
        for subpath, condition, path in missing:
            print(f'ERROR: exports["{subpath}"].{condition} -> {path} is NOT in the tarball')
        print()
        print(f"Tarball contains {len(packed)} file(s).")
        print("A `files` entry can be nullified by a nested .gitignore without any")
        print("npm warning -- check for stray .gitignore files under dist/.")
        return 1

    print(f"OK  all {len(targets)} exports target(s) present in the tarball ({len(packed)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
