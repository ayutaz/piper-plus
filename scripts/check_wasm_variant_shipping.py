#!/usr/bin/env python3
"""WASM variant shipping-chain gate.

Declaring a subpath in ``exports`` is not enough to publish it.  A variant
only reaches the registry if **three independent places agree**:

  1. ``src/wasm/openjtalk-web/package.json``
     ``exports["./wasm/<name>"].import`` -> ``./dist/<subdir>/...``
  2. ``.github/workflows/build-wasm-reusable.yml``
     a ``matrix.include`` entry with ``dist_subdir: <subdir>`` (so the
     variant is actually built) and an ``artifact:`` name
  3. ``.github/workflows/npm-publish.yml``
     a ``download-artifact`` step that pulls that artifact into
     ``src/wasm/openjtalk-web/dist/<subdir>/`` before ``npm pack`` runs

Link 3 is the one that silently rotted.  ``./wasm/ja`` and ``./wasm/ja-lite``
were added to ``exports`` in #301 (2026-04-04) and both variants **were**
built by the matrix, but the publish job only ever downloaded the
``piper-plus-wasm`` artifact.  Every release from 0.3.1 through 0.6.0
therefore shipped those two subpaths with zero files behind them, and
nothing anywhere failed.

The JS-side gate in ``test/js/test-npm-package.js``
("exports↔files 整合バリデーション") catches the *other* half of that bug —
an exports target that no ``files`` entry covers — but it cannot see the CI
shipping chain at all, because that lives entirely in workflow YAML.  Both
gates are needed; neither subsumes the other.

Exit 0 when every ``./wasm/*`` export has a complete chain, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

PACKAGE_JSON = REPO_ROOT / "src" / "wasm" / "openjtalk-web" / "package.json"
BUILD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-wasm-reusable.yml"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "npm-publish.yml"

# Where npm-publish.yml must place a downloaded artifact for `npm pack` to see
# it.  Paths in the workflow are relative to the repository root even though
# the job sets a `working-directory` default.
DOWNLOAD_PREFIX = "src/wasm/openjtalk-web/dist/"


def exported_variants(pkg: dict) -> dict[str, str]:
    """Map ``./wasm/<name>`` exports to the ``dist/`` subdirectory they need.

    Returns ``{subpath: subdir}``.  Subpaths that do not resolve into
    ``dist/`` are ignored -- they are plain source exports with no build step.
    """
    found: dict[str, str] = {}
    for subpath, value in (pkg.get("exports") or {}).items():
        if not subpath.startswith("./wasm/"):
            continue
        targets = value.values() if isinstance(value, dict) else [value]
        for target in targets:
            if not isinstance(target, str):
                continue
            rel = target.removeprefix("./")
            if not rel.startswith("dist/"):
                continue
            found[subpath] = rel.split("/")[1]
    return found


def built_variants(workflow: dict) -> dict[str, str]:
    """Map ``dist_subdir`` to the artifact name the build matrix uploads."""
    built: dict[str, str] = {}
    for job in (workflow.get("jobs") or {}).values():
        include = ((job.get("strategy") or {}).get("matrix") or {}).get("include") or []
        for entry in include:
            subdir = entry.get("dist_subdir")
            artifact = entry.get("artifact")
            if subdir and artifact:
                built[subdir] = artifact
    return built


def downloaded_variants(workflow: dict) -> dict[str, str]:
    """Map ``dist/`` subdirectory to the artifact the publish job downloads."""
    downloads: dict[str, str] = {}
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            uses = step.get("uses") or ""
            if not uses.startswith("actions/download-artifact"):
                continue
            with_ = step.get("with") or {}
            path = str(with_.get("path") or "")
            name = with_.get("name")
            if not name or not path.startswith(DOWNLOAD_PREFIX):
                continue
            subdir = path[len(DOWNLOAD_PREFIX) :].strip("/")
            if subdir:
                downloads[subdir] = name
    return downloads


def main() -> int:
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    build_wf = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    publish_wf = yaml.safe_load(PUBLISH_WORKFLOW.read_text(encoding="utf-8"))

    exported = exported_variants(pkg)
    built = built_variants(build_wf)
    downloaded = downloaded_variants(publish_wf)

    if not exported:
        print("ERROR: no ./wasm/* exports found -- gate would vacuously pass.")
        print(f"       Checked {PACKAGE_JSON.relative_to(REPO_ROOT)}")
        return 1

    errors: list[str] = []
    for subpath, subdir in sorted(exported.items()):
        if subdir not in built:
            errors.append(
                f'exports["{subpath}"] -> dist/{subdir}/ but '
                f"build-wasm-reusable.yml has no matrix entry with "
                f"dist_subdir: {subdir}"
            )
            continue
        if subdir not in downloaded:
            errors.append(
                f'exports["{subpath}"] -> dist/{subdir}/ but '
                f"npm-publish.yml has no download-artifact step with path "
                f"{DOWNLOAD_PREFIX}{subdir}/"
            )
            continue
        if downloaded[subdir] != built[subdir]:
            errors.append(
                f'exports["{subpath}"] -> dist/{subdir}/ downloads artifact '
                f'"{downloaded[subdir]}" but the build matrix uploads it as '
                f'"{built[subdir]}"'
            )

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        print()
        print("A ./wasm/* export only ships when it is declared, built, AND")
        print("downloaded into dist/ before `npm pack`. See #301.")
        return 1

    print(f"OK  {len(exported)} ./wasm/* export(s) have a complete shipping chain:")
    for subpath, subdir in sorted(exported.items()):
        print(f"      {subpath} -> dist/{subdir}/ (artifact: {built[subdir]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
