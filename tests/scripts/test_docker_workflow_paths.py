"""A pull request that changes a file an image copies must build that image.

``docker-build.yml`` and ``docker-test.yml`` start only on their
``pull_request.paths``. The python-inference and webui images copy
``src/python_run/requirements_webui.txt``, ``overrides_webui.txt`` and
``VERSION``, and the C++ inference image copies
``src/rust/piper-plus-g2p/data/``, but none of them was in the paths: a pull
request that broke the image through one of those files built no image, and
the failure appeared only after merge.

These tests read each workflow's Dockerfiles from the workflow itself and
check that every file a ``COPY``/``ADD`` reads from the repository matches the
workflow's pull request paths, apart from the gaps listed in ``KNOWN_GAPS``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from test_docker_scan_build_context import copy_sources

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# (workflow, Dockerfile, source prefix) -> why a change there may build no
# image in that workflow.
KNOWN_GAPS = {
    **{
        ("docker-build.yml", dockerfile, src): (
            "docker-test.yml builds docker/cpp-inference/Dockerfile from the same "
            "sources on every pull request that changes them"
        )
        for dockerfile in (
            "docker/cpp-inference/Dockerfile",
            "docker/cpp-inference/Dockerfile.distroless",
        )
        for src in (
            "LICENSE.md",
            "cmake",
            "src/cpp",
            "src/rust/piper-plus-g2p/data",
            "src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md",
        )
    },
    ("docker-build.yml", "docker/wyoming/Dockerfile", "src/python_run/piper_plus"): (
        "python-tests.yml runs the wyoming tests on these files; adding "
        "src/python_run/** here would build all nine images on most Python "
        "runtime pull requests"
    ),
}

DOCKERFILE_RE = re.compile(r"^\s*(?:file|dockerfile):\s*\.?/?(\S*Dockerfile[^\s'\"]*)\s*$", re.M)


def _glob_re(pattern: str) -> re.Pattern[str]:
    """GitHub Actions ``paths`` glob as a regex (``*``, ``**`` and ``**/``)."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + "$")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return out.splitlines()


def _files_read_by(src: str, tracked: list[str]) -> list[str]:
    src = src.removeprefix("./").rstrip("/")
    if src in ("", "."):
        return []
    pattern = _glob_re(src)
    return [f for f in tracked if f == src or f.startswith(src + "/") or pattern.match(f)]


def _dockerfiles(workflow: str) -> list[str]:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    return sorted(set(DOCKERFILE_RE.findall(text)))


WORKFLOWS_UNDER_TEST = ("docker-build.yml", "docker-test.yml")


@pytest.mark.parametrize("workflow", WORKFLOWS_UNDER_TEST)
def test_workflow_builds_some_dockerfiles(workflow):
    dockerfiles = _dockerfiles(workflow)
    assert dockerfiles, f"{workflow}: no Dockerfile found; update DOCKERFILE_RE"
    for dockerfile in dockerfiles:
        assert (REPO_ROOT / dockerfile).is_file(), f"{workflow}: {dockerfile} does not exist"


@pytest.mark.parametrize("workflow", WORKFLOWS_UNDER_TEST)
def test_pull_request_paths_cover_every_copied_file(workflow):
    config = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    paths = [_glob_re(p) for p in config[True]["pull_request"]["paths"]]
    tracked = _tracked_files()
    missing = []
    for dockerfile in _dockerfiles(workflow):
        text = (REPO_ROOT / dockerfile).read_text(encoding="utf-8")
        for src in copy_sources(text):
            key = (workflow, dockerfile, src.removeprefix("./").rstrip("/"))
            if key in KNOWN_GAPS:
                continue
            for f in _files_read_by(src, tracked):
                if not any(p.match(f) for p in paths):
                    missing.append(f"{dockerfile}: COPY {src} reads {f}")
    assert not missing, (
        f"{workflow}: a pull request changing these files builds no image. Add "
        "them to pull_request.paths (and push.paths), or to KNOWN_GAPS with the "
        "reason:\n  " + "\n  ".join(sorted(set(missing)))
    )


def test_known_gaps_are_still_copied():
    for workflow, dockerfile, src in KNOWN_GAPS:
        assert dockerfile in _dockerfiles(workflow), (workflow, dockerfile)
        sources = {
            s.removeprefix("./").rstrip("/")
            for s in copy_sources((REPO_ROOT / dockerfile).read_text(encoding="utf-8"))
        }
        assert src in sources, f"{dockerfile} no longer copies {src}; remove the entry"
