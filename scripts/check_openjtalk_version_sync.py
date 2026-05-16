#!/usr/bin/env python3
"""Validate that the C++ OpenJTalk pin and the Python pyopenjtalk-plus
dependency reference the same upstream version.

Background:
    ``cmake/ExternalDeps.cmake`` downloads the OpenJTalk library + the JA
    dictionary directly from a pyopenjtalk-plus tarball URL with a hardcoded
    version (e.g., ``pyopenjtalk_plus-0.4.1.post7.tar.gz``). The Python
    runtime separately ``import pyopenjtalk`` from the installed package.
    The Python pin comes from two possible places:

      - ``pyproject.toml::project.dependencies`` (static list), or
      - ``pyproject.toml::dynamic = ["dependencies"]`` resolved by setup.py
        from a sibling ``requirements*.txt`` (the runtime package's pattern).

    If the pyproject/requirements pin and the cmake URL drift apart, then:

      - Training (Python) sees one OpenJTalk dictionary / behaviour.
      - Inference (C++) sees a different one.

    The drift can change accent-phrase rules (NJD), fullcontext labels, and
    in extreme cases phoneme output — silently making the pretrained model
    underperform on the C++ runtime.

Detection rule (severity-tiered):

  1. Extract the version from the cmake URL.
  2. Walk every ``pyproject.toml`` and every ``requirements*.txt`` in the
     repo and collect every line / spec mentioning ``pyopenjtalk-plus``.
  3. For each spec, evaluate the cmake version against its constraint set
     using ``packaging.specifiers.SpecifierSet``:

       - Constraint includes ``==`` or ``~=`` and is violated → ERROR
         (explicit pin mismatch — definite drift).
       - Constraint uses only range operators (``>=`` ``<=`` ``>`` ``<``
         ``!=``) and is violated → WARN (range violation, may be
         intentional — e.g., requirements.txt requests a newer post-release
         than cmake currently bundles).
       - Bare name (no constraint) → noted, no fail.

Exit codes:
    0 -- no explicit-pin mismatch (warnings allowed)
    1 -- explicit-pin mismatch detected (== / ~= violated)
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMAKE_FILE = REPO_ROOT / "cmake" / "ExternalDeps.cmake"

try:
    from packaging.specifiers import SpecifierSet  # type: ignore[import-not-found]
    from packaging.version import Version  # type: ignore[import-not-found]

    HAS_PACKAGING = True
except ImportError:
    HAS_PACKAGING = False


def _find_pyprojects() -> list[Path]:
    return [
        p
        for p in REPO_ROOT.rglob("pyproject.toml")
        if not any(
            part in {".venv", "venv", "node_modules", "target", "build", ".tox"}
            for part in p.parts
        )
    ]


def _find_requirements() -> list[Path]:
    """Find requirements*.txt files (excluding common vendored locations)."""
    out: list[Path] = []
    for pattern in ("requirements*.txt",):
        for p in REPO_ROOT.rglob(pattern):
            if any(
                part in {".venv", "venv", "node_modules", "target", "build", ".tox"}
                for part in p.parts
            ):
                continue
            out.append(p)
    return out


_CMAKE_URL_RE = re.compile(
    r"pyopenjtalk_plus-(\d+\.\d+\.\d+(?:\.post\d+)?)\.tar\.gz"
)


def _extract_cmake_version(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = _CMAKE_URL_RE.search(text)
    return m.group(1) if m else None


_PYOPENJTALK_NAME_RE = re.compile(r"^\s*(pyopenjtalk[a-zA-Z0-9_-]*)", re.IGNORECASE)


def _extract_constraint(spec: str) -> tuple[str, str]:
    """Split ``pyopenjtalk-plus>=0.4.1.post8`` into ``("pyopenjtalk-plus",
    ">=0.4.1.post8")``. Returns ``("", "")`` if not parseable.
    """
    s = spec.strip()
    # Strip environment markers like "pkg>=1; python_version >= '3.10'"
    s = s.split(";", 1)[0].strip()
    # Strip inline comments
    s = s.split("#", 1)[0].strip()
    if not s:
        return ("", "")
    m = _PYOPENJTALK_NAME_RE.match(s)
    if not m:
        return ("", "")
    name = m.group(1)
    constraint = s[len(m.group(0)) :].strip()
    # constraint may have square brackets for extras: pyopenjtalk-plus[foo]>=1
    constraint = re.sub(r"^\[[^\]]*\]", "", constraint).strip()
    return (name, constraint)


def _extract_pyproject_specs(pyproject: Path) -> list[tuple[str, str]]:
    """Return ``(spec_string, location_hint)`` for every pyopenjtalk-plus
    mention in a pyproject.toml file.
    """
    if not pyproject.exists():
        return []
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return []

    specs: list[tuple[str, str]] = []
    project = data.get("project", {})

    # Static dependencies (only present when dependencies is NOT in dynamic).
    for dep in project.get("dependencies", []):
        if "pyopenjtalk" in dep.lower():
            specs.append((dep, "project.dependencies"))

    for group, deps in (project.get("optional-dependencies") or {}).items():
        for dep in deps:
            if "pyopenjtalk" in dep.lower():
                specs.append((dep, f"project.optional-dependencies.{group}"))

    # dependency-groups (PEP 735)
    for group, deps in (data.get("dependency-groups") or {}).items():
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str) and "pyopenjtalk" in dep.lower():
                    specs.append((dep, f"dependency-groups.{group}"))

    # tool.poetry.dependencies / tool.uv.dependencies (uncommon but possible)
    tool = data.get("tool", {})
    for tooltable_key in ("poetry", "uv"):
        tooltable = tool.get(tooltable_key, {})
        deps = tooltable.get("dependencies", {})
        if isinstance(deps, dict):
            for name, val in deps.items():
                if "pyopenjtalk" in name.lower():
                    specs.append((f"{name}{val!s}", f"tool.{tooltable_key}.dependencies"))

    return specs


def _extract_requirements_specs(path: Path) -> list[tuple[str, str]]:
    """Return ``(spec_string, line_no_hint)`` for every pyopenjtalk-plus
    line in a requirements*.txt file.
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    out: list[tuple[str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # `-r other.txt` inclusion is not recursed; treat as out of scope.
        if stripped.startswith("-"):
            continue
        if "pyopenjtalk" in stripped.lower():
            out.append((stripped, f"line {line_no}"))
    return out


def _classify_drift(spec: str, cmake_version: str) -> tuple[str, str]:
    """Return ``(severity, detail)`` for a single spec.

    ``severity`` is one of:
      - ``"ok"``: cmake_version satisfies the constraint.
      - ``"unconstrained"``: no version constraint at all.
      - ``"error"``: explicit pin (== / ~=) violated by cmake_version.
      - ``"warn"``: range constraint (>=, <=, >, <, !=) violated.
      - ``"parse-error"``: could not interpret the constraint.
    """
    _, constraint = _extract_constraint(spec)
    if not constraint:
        return ("unconstrained", "")

    if not HAS_PACKAGING:
        # Degraded mode: handle only == and ~=, log everything else as warn.
        m_eq = re.search(r"==\s*(\d+\.\d+\.\d+(?:\.post\d+)?)", constraint)
        if m_eq and m_eq.group(1) != cmake_version:
            return ("error", f"== {m_eq.group(1)} vs cmake {cmake_version}")
        m_compat = re.search(r"~=\s*(\d+)\.(\d+)\.(\d+)", constraint)
        if m_compat:
            major, minor = int(m_compat.group(1)), int(m_compat.group(2))
            cm_parts = cmake_version.split(".post", 1)[0].split(".")
            if int(cm_parts[0]) != major or int(cm_parts[1]) != minor:
                return ("error", f"~= mismatch ({m_compat.group(0)} vs cmake {cmake_version})")
        return ("warn", f"packaging library unavailable; only == / ~= checked for {constraint!r}")

    try:
        spec_set = SpecifierSet(constraint)
        cmake_v = Version(cmake_version)
    except Exception as e:  # noqa: BLE001
        return ("parse-error", f"could not parse {constraint!r}: {e}")

    if cmake_v in spec_set:
        return ("ok", "")

    # Constraint violated. Determine severity by operator type.
    has_strict = any(s.operator in ("==", "~=") for s in spec_set)
    if has_strict:
        return ("error", f"cmake {cmake_version} violates strict pin {constraint!r}")
    return ("warn", f"cmake {cmake_version} does not satisfy range constraint {constraint!r}")


def main() -> int:
    cmake_version = _extract_cmake_version(CMAKE_FILE)
    if cmake_version is None:
        print(
            f"ERROR: could not extract pyopenjtalk_plus version from "
            f"{CMAKE_FILE.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1

    pyprojects = _find_pyprojects()
    reqfiles = _find_requirements()
    if not pyprojects and not reqfiles:
        print("WARN: no pyproject.toml or requirements.txt found anywhere")
        return 0

    # Collect every (source, spec, location) tuple.
    all_specs: list[tuple[Path, str, str]] = []
    for p in pyprojects:
        for spec, loc in _extract_pyproject_specs(p):
            all_specs.append((p, spec, loc))
    for p in reqfiles:
        for spec, loc in _extract_requirements_specs(p):
            all_specs.append((p, spec, loc))

    if not all_specs:
        print(
            "WARN: no pyopenjtalk-plus references found in any "
            "pyproject.toml / requirements*.txt. cmake pin is unpaired."
        )
        return 0

    errors: list[tuple[Path, str, str, str]] = []
    warnings: list[tuple[Path, str, str, str]] = []
    unconstrained: list[tuple[Path, str, str]] = []

    for p, spec, loc in all_specs:
        severity, detail = _classify_drift(spec, cmake_version)
        if severity == "ok":
            continue
        if severity == "unconstrained":
            unconstrained.append((p, spec, loc))
        elif severity in {"warn", "parse-error"}:
            warnings.append((p, spec, loc, detail))
        else:  # error
            errors.append((p, spec, loc, detail))

    print(f"INFO: cmake/ExternalDeps.cmake pins pyopenjtalk-plus == {cmake_version}")
    print(
        f"INFO: scanned {len(all_specs)} reference(s) across "
        f"{len(pyprojects)} pyproject.toml + {len(reqfiles)} requirements*.txt"
    )
    if not HAS_PACKAGING:
        print(
            "INFO: `packaging` library not importable — running in degraded "
            "mode (only == / ~= checked; other constraints reported as warn)."
        )

    if warnings:
        print(f"\nWARN: {len(warnings)} range-constraint violation(s) (informational):")
        for p, spec, loc, detail in warnings:
            print(f"  {p.relative_to(REPO_ROOT)}: [{loc}] {spec!r}")
            print(f"    {detail}")
        print(
            "\nNote: range violations are tolerated to avoid disrupting "
            "intentional bound choices (e.g., requirements.txt asking for a "
            "newer post-release than cmake currently bundles). Investigate "
            "if the drift was unintentional."
        )

    if unconstrained:
        print(f"\nINFO: {len(unconstrained)} unconstrained reference(s):")
        for p, spec, loc in unconstrained:
            print(f"  {p.relative_to(REPO_ROOT)}: [{loc}] {spec!r}")

    if errors:
        print(
            f"\nERROR: {len(errors)} explicit-pin mismatch(es) "
            "(== / ~= constraints violated by cmake version):",
            file=sys.stderr,
        )
        for p, spec, loc, detail in errors:
            print(f"  {p.relative_to(REPO_ROOT)}: [{loc}] {spec!r}", file=sys.stderr)
            print(f"    {detail}", file=sys.stderr)
        print(
            f"\nFix: align both sides. cmake currently pins "
            f"{cmake_version}; adjust either the cmake URL or the "
            "pin to match.",
            file=sys.stderr,
        )
        return 1

    print(f"\nOK: no explicit-pin mismatch against cmake {cmake_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
