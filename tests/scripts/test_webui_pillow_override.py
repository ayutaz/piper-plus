"""Gradio environments must get Pillow >= 13.0.0 despite gradio's `pillow<13` cap.

Pillow 13.0.0 fixes 40+ advisories (5 CRITICAL, e.g. CVE-2026-112393 heap
overflow in the libtiff writer, CVE-2026-112900 Ghostscript argument
injection). gradio 6.26.0 (and 6.30.0, the latest) still declares
`pillow<13.0,>=8.0`, so a plain install resolves the vulnerable 12.3.0 and the
Trivy container scan fails. Every place that installs gradio overrides the cap:

  - Docker images install `src/python_run/requirements_webui.txt` with
    `uv pip install --override src/python_run/overrides_webui.txt`.
  - `environments/webui` (the documented WebUI install) declares the same
    override in `[tool.uv] override-dependencies`.

Remove the override (file, Dockerfile flags, pyproject entry, this test) once
gradio allows Pillow 13.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version


REPO_ROOT = Path(__file__).resolve().parents[2]
OVERRIDE_FILE = REPO_ROOT / "src" / "python_run" / "overrides_webui.txt"
WEBUI_PYPROJECT = REPO_ROOT / "environments" / "webui" / "pyproject.toml"
PILLOW_FLOOR = Version("13.0.0")


def _override_requirements() -> list[str]:
    lines = OVERRIDE_FILE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _floor_of(requirement: str) -> Version | None:
    req = Requirement(requirement)
    floors = [Version(s.version) for s in req.specifier if s.operator in (">=", "==")]
    return max(floors) if floors else None


def test_override_file_raises_pillow_to_13():
    reqs = _override_requirements()
    pillow = [r for r in reqs if Requirement(r).name.lower() == "pillow"]
    assert len(pillow) == 1, f"{OVERRIDE_FILE.name} must override pillow once: {reqs}"
    floor = _floor_of(pillow[0])
    assert floor is not None and floor >= PILLOW_FLOOR, pillow[0]


def test_webui_environment_declares_the_same_override():
    with WEBUI_PYPROJECT.open("rb") as f:
        overrides = tomllib.load(f)["tool"]["uv"].get("override-dependencies", [])
    assert sorted(overrides) == sorted(_override_requirements())


def _dockerfiles() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "docker"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / p for p in out.splitlines() if Path(p).name.startswith("Dockerfile")]


def _run_instructions(text: str) -> list[str]:
    """RUN instructions with line continuations joined."""
    joined = re.sub(r"\\\n", " ", text)
    return [ln.strip() for ln in joined.splitlines() if ln.strip().startswith("RUN ")]


WEBUI_DOCKERFILES = [
    p for p in _dockerfiles() if "requirements_webui.txt" in p.read_text(encoding="utf-8")
]


def test_webui_dockerfiles_are_found():
    """A gate that checks nothing must not pass."""
    assert len(WEBUI_DOCKERFILES) >= 5


@pytest.mark.parametrize(
    "dockerfile", WEBUI_DOCKERFILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_webui_install_passes_the_override(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")
    installs = [
        run
        for run in _run_instructions(text)
        if re.search(r"-r\s+\S*requirements_webui\.txt", run)
    ]
    assert installs, "requirements_webui.txt is copied but never installed"
    for run in installs:
        for command in run.split("&&"):
            if "requirements_webui.txt" not in command:
                continue
            m = re.search(r"--override\s+(\S*overrides_webui\.txt)", command)
            assert m, f"installs gradio without the Pillow override: {command.strip()}"
            assert re.search(
                rf"^COPY\s+src/python_run/overrides_webui\.txt\s+{re.escape(m.group(1))}\s*$",
                text,
                re.MULTILINE,
            ), f"{m.group(1)} is not copied from src/python_run/overrides_webui.txt"


@pytest.mark.parametrize(
    "lock", ["uv.lock", "environments/webui/uv.lock"], ids=lambda s: s
)
def test_lock_resolves_pillow_13(lock: str):
    text = (REPO_ROOT / lock).read_text(encoding="utf-8")
    m = re.search(r'^name = "pillow"\nversion = "([^"]+)"', text, re.MULTILINE)
    assert m, f"{lock} has no pillow"
    assert Version(m.group(1)) >= PILLOW_FLOOR, f"{lock} resolves pillow {m.group(1)}"
