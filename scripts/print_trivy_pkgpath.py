#!/usr/bin/env python3
"""Print PkgPath for setuptools / msgpack findings in a Trivy JSON report.

Temporary diagnostic for the long-standing ``trivy-python-inference`` /
``trivy-webui-distroless`` findings:

    setuptools 70.3.0  (CVE-2025-47273 / CVE-2026-59890)
    msgpack    1.1.2   (GHSA-6v7p-g79w-8964)

Their Trivy rule name is ``LanguageSpecificPackageVulnerability``, i.e. the
``python-pkg`` analyzer, which reads ``*.dist-info`` / ``*.egg-info`` metadata
actually present in the image.  But scanning the built image for every
``METADATA`` / ``PKG-INFO`` whose ``Name:`` is setuptools or msgpack turned up
only ``setuptools 84.0.0`` -- the reported versions are nowhere to be found.

SARIF cannot settle this: it sets Target to the class name ``Python`` and
carries no ``PkgPath``.  Trivy's JSON report does carry ``PkgPath``, so this
script prints it.

Delete this script together with the workflow steps that call it once the
provenance is known.

Usage:
    python scripts/print_trivy_pkgpath.py <trivy-report.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


WATCHED = ("setuptools", "msgpack")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <trivy-report.json>", file=sys.stderr)
        return 2

    report_path = Path(sys.argv[1])
    if not report_path.is_file():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = report.get("Results") or []

    print(f"=== {report_path}: {', '.join(WATCHED)} findings ===")
    hits = 0
    for result in results:
        for vuln in result.get("Vulnerabilities") or []:
            if vuln.get("PkgName") not in WATCHED:
                continue
            hits += 1
            print(f"  Target={result.get('Target')!r}")
            print(f"    Class={result.get('Class')!r} Type={result.get('Type')!r}")
            print(f"    PkgName={vuln.get('PkgName')}")
            print(f"    InstalledVersion={vuln.get('InstalledVersion')}")
            print(f"    PkgPath={vuln.get('PkgPath')!r}")
            print(f"    PkgIdentifier={vuln.get('PkgIdentifier')}")
            print(f"    VulnerabilityID={vuln.get('VulnerabilityID')}")
    if hits == 0:
        print(f"  (no {' / '.join(WATCHED)} finding in this report)")

    # Vulnerabilities 側の PkgPath が空だった場合に備えて、 Packages 側の
    # FilePath も出す。 `list-all-pkgs: true` を付けたときだけ埋まる。
    print(f"=== {', '.join(WATCHED)} entries in Results[].Packages ===")
    pkg_hits = 0
    for result in results:
        for pkg in result.get("Packages") or []:
            if pkg.get("Name") not in WATCHED:
                continue
            pkg_hits += 1
            print(f"  Target={result.get('Target')!r} Type={result.get('Type')!r}")
            print(f"    Name={pkg.get('Name')} Version={pkg.get('Version')}")
            print(f"    FilePath={pkg.get('FilePath')!r}")
            print(f"    Licenses={pkg.get('Licenses')}")
            print(f"    Identifier={pkg.get('Identifier')}")
    if pkg_hits == 0:
        print("  (Packages に該当なし / list-all-pkgs が無効)")

    # 全 Result を並べると、 どの analyzer が何件出しているかが一目で分かる。
    print("=== all Results ===")
    for result in results:
        n = len(result.get("Vulnerabilities") or [])
        print(
            f"  Target={result.get('Target')!r} "
            f"Class={result.get('Class')!r} "
            f"Type={result.get('Type')!r} vulns={n}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
