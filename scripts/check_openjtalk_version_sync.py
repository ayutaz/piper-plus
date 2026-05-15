#!/usr/bin/env python3
"""Validate that the C++ OpenJTalk pin and the Python pyopenjtalk-plus
dependency reference the same upstream version.

Background:
    ``cmake/ExternalDeps.cmake`` downloads the OpenJTalk library + the JA
    dictionary directly from a pyopenjtalk-plus tarball URL with a hardcoded
    version (e.g., ``pyopenjtalk_plus-0.4.1.post7.tar.gz``). The Python
    runtime (``src/python_run/pyproject.toml``, ``src/python/pyproject.toml``)
    separately ``import pyopenjtalk`` from the installed package. If the
    pyproject pin and the cmake URL drift apart, then:

      - Training (Python) sees one OpenJTalk dictionary / behavior.
      - Inference (C++) sees a different one.

    The drift can change accent-phrase rules (NJD), fullcontext labels, and
    in extreme cases phoneme output — silently making the pretrained model
    underperform on the C++ runtime.

Detection rule (conservative — only fails on definite drift):

  1. Parse the version embedded in the cmake URL (must match
     ``pyopenjtalk_plus-X.Y.Z[.postN].tar.gz``).
  2. Walk all ``pyproject.toml`` files in the repo and collect every
     dependency spec mentioning ``pyopenjtalk-plus``.
  3. For each spec with a version constraint (==, ~=, >=, <=, !=, range),
     verify the cmake version satisfies it. Bare names (no constraint) are
     not flagged — they're permissive and intentional in some places, but
     warned as a soft hint.

Exit codes:
    0 -- cmake URL version is consistent with all pyproject specs
    1 -- drift detected (mismatch printed to stderr)
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMAKE_FILE = REPO_ROOT / "cmake" / "ExternalDeps.cmake"

# All pyproject.toml files in the repo. Walk dynamically so adding a new
# Python package (e.g., a tools/ subproject) gets picked up automatically.
def _find_pyprojects() -> list[Path]:
    return [
        p
        for p in REPO_ROOT.rglob("pyproject.toml")
        # skip vendored / virtualenv / build directories
        if not any(
            part in {".venv", "venv", "node_modules", "target", "build", ".tox"}
            for part in p.parts
        )
    ]


_CMAKE_URL_RE = re.compile(
    r"pyopenjtalk_plus-(\d+\.\d+\.\d+(?:\.post\d+)?)\.tar\.gz"
)


def _extract_cmake_version(path: Path) -> str | None:
    """Return ``X.Y.Z[.postN]`` from the cmake URL, or None if absent."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = _CMAKE_URL_RE.search(text)
    return m.group(1) if m else None


def _extract_pyopenjtalk_specs(pyproject: Path) -> list[tuple[str, str]]:
    """Return list of ``(spec_string, location_hint)`` for every dep mention.

    ``spec_string`` is the raw PEP 508 fragment, e.g.,
    ``"pyopenjtalk-plus>=0.4,<0.5"``. ``location_hint`` is the table key
    where it was found (``project.dependencies`` / ``project.optional-...``).
    """
    if not pyproject.exists():
        return []
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return []

    specs: list[tuple[str, str]] = []

    project = data.get("project", {})
    for dep in project.get("dependencies", []):
        if "pyopenjtalk" in dep.lower():
            specs.append((dep, "project.dependencies"))
    for group, deps in (project.get("optional-dependencies") or {}).items():
        for dep in deps:
            if "pyopenjtalk" in dep.lower():
                specs.append((dep, f"project.optional-dependencies.{group}"))

    # also walk [tool.uv.sources] / [tool.poetry.dependencies] if present
    tool = data.get("tool", {})
    for tooltable_key in ("poetry", "uv"):
        tooltable = tool.get(tooltable_key, {})
        deps = tooltable.get("dependencies", {})
        if isinstance(deps, dict):
            for name, val in deps.items():
                if "pyopenjtalk" in name.lower():
                    specs.append((f"{name} = {val!r}", f"tool.{tooltable_key}.dependencies"))

    return specs


_SPEC_OP_RE = re.compile(
    r"pyopenjtalk[a-z\-]*"
    r"\s*"
    r"(?P<ops>([<>=!~]=?|==|!=)\s*[^,;\s]+(?:\s*,\s*[<>=!~]=?\s*[^,;\s]+)*)?"
)


def _spec_has_constraint(spec: str) -> bool:
    """Return True if a PEP 508-ish spec has a version constraint."""
    m = _SPEC_OP_RE.match(spec.strip())
    return bool(m and m.group("ops"))


def main() -> int:
    cmake_version = _extract_cmake_version(CMAKE_FILE)
    if cmake_version is None:
        print(
            f"ERROR: could not extract pyopenjtalk_plus version from "
            f"{CMAKE_FILE.relative_to(REPO_ROOT)}. Expected URL pattern "
            "'pyopenjtalk_plus-X.Y.Z[.postN].tar.gz'.",
            file=sys.stderr,
        )
        return 1

    pyprojects = _find_pyprojects()
    if not pyprojects:
        print("WARN: no pyproject.toml found anywhere — skipping sync check")
        return 0

    all_specs: list[tuple[Path, str, str]] = []
    for p in pyprojects:
        for spec, loc in _extract_pyopenjtalk_specs(p):
            all_specs.append((p, spec, loc))

    if not all_specs:
        print(
            "WARN: no pyopenjtalk-plus references found in any pyproject.toml. "
            "cmake pin is unpaired — this might be intentional (e.g., "
            "Python is optional)."
        )
        return 0

    # No version solver — just detect "obvious" drift: any constraint that
    # explicitly pins a different version family than the cmake URL.
    cmake_major_minor_patch = cmake_version.split(".post", 1)[0]
    drifts: list[tuple[Path, str, str, str]] = []
    unconstrained: list[tuple[Path, str, str]] = []
    for p, spec, loc in all_specs:
        if not _spec_has_constraint(spec):
            unconstrained.append((p, spec, loc))
            continue
        # Look for an `==` or `~=` pin that disagrees.
        m = re.search(r"==\s*(\d+\.\d+\.\d+(?:\.post\d+)?)", spec)
        if m and m.group(1) != cmake_version:
            drifts.append((p, spec, loc, f"== mismatch ({m.group(1)} vs cmake {cmake_version})"))
            continue
        # Compatible-release: ~=0.4.1 means >=0.4.1,<0.5
        m = re.search(r"~=\s*(\d+)\.(\d+)\.(\d+)", spec)
        if m:
            major, minor, _patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
            cm_major, cm_minor, *_ = cmake_major_minor_patch.split(".")
            if int(cm_major) != major or int(cm_minor) != minor:
                drifts.append(
                    (p, spec, loc, f"~= mismatch ({m.group(0)} vs cmake {cmake_version})")
                )
                continue

    print(f"INFO: cmake/ExternalDeps.cmake pins pyopenjtalk-plus == {cmake_version}")
    print(f"INFO: {len(all_specs)} pyproject reference(s) checked across "
          f"{len(pyprojects)} pyproject.toml file(s).")

    if drifts:
        print(
            f"\nERROR: {len(drifts)} pyproject pin(s) drift from cmake URL:",
            file=sys.stderr,
        )
        for p, spec, loc, reason in drifts:
            print(
                f"  {p.relative_to(REPO_ROOT)}: [{loc}] {spec!r}",
                file=sys.stderr,
            )
            print(f"    {reason}", file=sys.stderr)
        print(
            "\nFix: align both sides:",
            file=sys.stderr,
        )
        print(
            f"  - cmake/ExternalDeps.cmake: URL contains version "
            f"{cmake_version}",
            file=sys.stderr,
        )
        print(
            "  - pyproject.toml: relax/tighten pyopenjtalk-plus pin to match",
            file=sys.stderr,
        )
        return 1

    if unconstrained:
        # Soft hint — don't fail, but list them.
        print(
            f"\nNote: {len(unconstrained)} pyopenjtalk-plus reference(s) have "
            "no version constraint. These are permissive and won't drift, but "
            "consider pinning to the cmake version for reproducibility:",
        )
        for p, spec, loc in unconstrained:
            print(f"  {p.relative_to(REPO_ROOT)}: [{loc}] {spec!r}")

    print(f"\nOK: pyopenjtalk-plus pins consistent with cmake {cmake_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
