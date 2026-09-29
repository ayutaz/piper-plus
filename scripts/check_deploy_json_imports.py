#!/usr/bin/env python3
"""Every relative JSON-module import in a deploy bundle must resolve (#733).

GitHub Pages returns its 404 HTML for a missing path, so a JSON module that
was not copied into the bundle fails with

    Loading JSON module from ".../g2p/data/sv_function_words.json" was blocked
    because of a disallowed MIME type ("text/html").

and the page breaks at runtime -- `deploy-pages` itself succeeds, which is why
the demo sat unusable until a user reported it.

`deploy-webassembly-demo.yml` already has a pre-deploy gate whose comment says
exactly this ("Pages 404s are silent"), but its list of required files is
hand-maintained. It listed `deploy/g2p/src/index.js` and was never updated
when `detect.js` started importing `../data/sv_function_words.json`, so the
gate passed on a bundle that could not load.

This script DERIVES the requirement from the source instead: it scans the
bundle's JavaScript for relative JSON-module imports and asserts each one
resolves inside the bundle. A new import cannot silently 404 because nobody
remembered to extend a list.

Only RELATIVE specifiers are checked. A bare specifier ("pkg/data.json") is
resolved by an import map, which the workflow's "Validate import maps" step
covers.

Usage:  check_deploy_json_imports.py <bundle-dir>
Exit:   0 = every import resolves, 1 = at least one does not, 2 = bad usage
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# import x from "./a.json" with { type: "json" }
#   also: assert { type: "json" } (the pre-2024 spelling), and side-effect
#   imports without a binding.
JSON_IMPORT = re.compile(
    r"""(?:import|export)\b[^;'"]*?from\s*['"](?P<spec>[^'"]+\.json)['"]"""
    r"""\s*(?:with|assert)\s*\{[^}]*\}""",
    re.DOTALL,
)

# A bare import with no `with`/`assert` clause is still a fetchable asset in
# some bundlers; catch it too so the check is not silently narrower than the
# thing it protects.
JSON_IMPORT_PLAIN = re.compile(
    r"""(?:import|export)\b[^;'"]*?from\s*['"](?P<spec>\.{1,2}/[^'"]+\.json)['"]""",
    re.DOTALL,
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <bundle-dir>", file=sys.stderr)
        return 2

    bundle = Path(argv[1])
    if not bundle.is_dir():
        print(f"ERROR: not a directory: {bundle}", file=sys.stderr)
        return 2

    sources = sorted(bundle.rglob("*.js"))
    missing: list[str] = []
    checked = 0

    for source in sources:
        text = source.read_text(encoding="utf-8", errors="replace")
        specs = {m.group("spec") for m in JSON_IMPORT.finditer(text)}
        specs |= {m.group("spec") for m in JSON_IMPORT_PLAIN.finditer(text)}
        for spec in sorted(specs):
            if not spec.startswith("."):
                continue  # bare specifier: import-map territory
            checked += 1
            resolved = (source.parent / spec).resolve()
            if not resolved.is_file():
                missing.append(
                    f"{source.relative_to(bundle)} imports {spec!r} -> "
                    f"{resolved} does not exist in the bundle"
                )

    if missing:
        print("Deploy JSON-module imports: FAIL")
        for line in missing:
            print(f"  - {line}")
        print()
        print(
            "Pages serves its 404 HTML for a missing path, so the browser "
            "rejects the module on MIME type and the page breaks at runtime "
            "(issue #733). Copy the file into the bundle."
        )
        return 1

    # Anti-vacuity: a bundle whose JS was not copied, or a regex that stopped
    # matching, would report success having verified nothing. The demo does
    # have such an import, so zero is a signal that this check went blind.
    if checked == 0:
        print("Deploy JSON-module imports: FAIL")
        print(
            f"  - scanned {len(sources)} .js file(s) in {bundle} and found no "
            "relative JSON-module import at all"
        )
        print()
        print(
            "The bundle is expected to contain at least one (g2p's detect.js "
            "imports ../data/sv_function_words.json). Zero means either the "
            "JavaScript was not copied into the bundle or this check's "
            "pattern no longer matches -- both hide exactly what it guards."
        )
        return 1

    print(
        f"Deploy JSON-module imports: OK "
        f"({checked} relative import(s) across {len(sources)} .js file(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
