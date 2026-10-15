"""Audit the installed dependency closure, not just newly changed lock entries.

Run in a clean wheel consumer environment. Repeat --root to select extras,
for example --root 'piper-plus[cpu,http]' --root 'piper-plus-g2p[all]'.
Reports declared license metadata; it does not replace archive license review.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


FORBIDDEN_DISTRIBUTIONS = {"distance", "g2p-en"}
COPYLEFT = re.compile(
    r"\b(?:AGPL|LGPL|GPL)(?:\b|(?=v?\d))|GNU (?:LESSER |AFFERO )?GENERAL PUBLIC", re.I
)


def audit(distributions, roots: list[str]) -> dict:
    index = {}
    errors = []
    for dist in distributions:
        name = canonicalize_name(dist.metadata["Name"])
        if name in index:
            errors.append(f"Duplicate installed distribution: {name}")
        index[name] = dist
        if name in FORBIDDEN_DISTRIBUTIONS:
            errors.append(f"Forbidden installed distribution: {name}")

    queue = [(Requirement(root), "requested root") for root in roots]
    visited = set()
    packages = {}
    environment = default_environment()
    while queue:
        requirement, parent = queue.pop()
        name = canonicalize_name(requirement.name)
        if name not in index:
            errors.append(f"Missing dependency: {parent} -> {requirement}")
            continue
        dist = index[name]
        if requirement.specifier and dist.version not in requirement.specifier:
            errors.append(
                f"Version mismatch: {parent} -> {requirement}; installed {dist.version}"
            )
        key = (name, tuple(sorted(requirement.extras)))
        if key in visited:
            continue
        visited.add(key)
        metadata = dist.metadata
        expression = metadata.get("License-Expression", "")
        license_text = metadata.get("License", "")
        classifiers = metadata.get_all("Classifier", [])
        license_classifiers = [c for c in classifiers if c.startswith("License ::")]
        declared = [
            expression,
            license_text if len(license_text) < 300 else license_text.splitlines()[0],
            *license_classifiers,
        ]
        if not any(s and s.upper() != "UNKNOWN" for s in declared):
            errors.append(f"Unreviewed license metadata: {name}")
        if any(COPYLEFT.search(s) for s in declared):
            errors.append(
                f"GPL/LGPL/AGPL license in dependency closure: {parent} -> {name}: {declared}"
            )
        packages[name] = {
            "version": dist.version,
            "license_expression": expression,
            "license": license_text[:300],
            "license_classifiers": license_classifiers,
        }
        for dependency in dist.requires or []:
            child = Requirement(dependency)
            contexts = {"", *requirement.extras}
            if child.marker and not any(
                child.marker.evaluate({**environment, "extra": extra})
                for extra in contexts
            ):
                continue
            queue.append((child, name))
    return {
        "roots": roots,
        "packages": dict(sorted(packages.items())),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(importlib.metadata.distributions(), args.root)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for error in result["errors"]:
        print(f"ERROR: {error}")
    print(
        f"Audited {len(result['packages'])} installed runtime dependencies; {len(result['errors'])} errors"
    )
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
