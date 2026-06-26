"""Regression guard for pyproject.toml torch / torchaudio cu128 source marker.

Issue history:

- PR #239 inadvertently restricted the `pytorch-cu128` index to
  `sys_platform == 'linux'`, forcing Windows + GPU developers to
  manually install torch via `uv pip install --index-url`. This was
  documented as a workaround in
  `docs/migration/v1.12-to-v2.0.md` ("Windows local dev" section)
  but it is friction we no longer need: PyTorch upstream publishes
  `torch-2.11.0+cu128-cp*-cp*-win_amd64.whl` wheels.
- This guard asserts the marker is symmetric (`!= 'darwin'`) so the
  regression cannot silently return.

If you intentionally change the marker (e.g. introduce a separate
`[gpu]` extra), update this test in the same commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject_data() -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover — Python 3.10 not supported by piper-plus
        import tomli as tomllib  # type: ignore[import-not-found, no-redef]
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def _cu128_source_entries(pyproject_data: dict, pkg: str) -> list[dict]:
    sources = pyproject_data.get("tool", {}).get("uv", {}).get("sources", {})
    entries = sources.get(pkg, [])
    return [e for e in entries if e.get("index") == "pytorch-cu128"]


@pytest.mark.parametrize("pkg", ["torch", "torchaudio"])
def test_cu128_source_not_linux_only(pyproject_data: dict, pkg: str) -> None:
    """`{torch,torchaudio}` cu128 source must NOT be restricted to Linux.

    Linux-only restriction means Windows + GPU developers fall through
    to PyPI CPU wheels and must manually install GPU wheels — UX bug.
    """
    entries = _cu128_source_entries(pyproject_data, pkg)
    assert entries, f"pyproject.toml missing pytorch-cu128 source for {pkg!r}"
    for entry in entries:
        marker = entry.get("marker", "")
        assert "sys_platform == 'linux'" not in marker, (
            f"{pkg} cu128 source is Linux-only (PR #239 regression). "
            "Windows + GPU dev requires automatic cu128 install — use "
            "\"sys_platform != 'darwin'\" or split into an opt-in [gpu] "
            "extra. See docs/migration/v1.12-to-v2.0.md."
        )


@pytest.mark.parametrize("pkg", ["torch", "torchaudio"])
def test_cu128_source_excludes_macos(pyproject_data: dict, pkg: str) -> None:
    """macOS must be excluded from the cu128 source (no CUDA support).

    Without the exclusion, `uv sync` on macOS would try to resolve the
    non-existent darwin cu128 wheel and fail.
    """
    entries = _cu128_source_entries(pyproject_data, pkg)
    assert entries, f"pyproject.toml missing pytorch-cu128 source for {pkg!r}"
    for entry in entries:
        marker = entry.get("marker", "")
        assert marker, (
            f"{pkg} cu128 source has no marker — would attempt resolve on "
            "macOS where no cu128 wheel exists."
        )
        # Accepted forms: `sys_platform != 'darwin'` or `sys_platform == 'linux'`
        # (the second is what we are guarding AGAINST in the test above, but
        # we still want some form of macOS exclusion).
        assert "darwin" in marker or "linux" in marker, (
            f"{pkg} cu128 marker {marker!r} does not appear to exclude macOS. "
            "Use \"sys_platform != 'darwin'\" to include Linux + Windows."
        )
