"""Docker image scans must build the image they claim to scan.

``security-audit.yml``'s ``trivy-docker`` job built each image with the
Dockerfile's own directory as the build context, while every Dockerfile
copies from the repository root (``COPY src/python/ ...``). Every build
failed (18 of 18 measured), ``continue-on-error`` hid it, and the image
scan was skipped on ``if: steps.build.outcome == 'success'``: the job was
green without scanning a single image.

These tests resolve each scan's (Dockerfile, context) pair from the workflow
itself and check that every ``COPY``/``ADD`` source exists in that context,
and that a failed build fails the job.
"""

from __future__ import annotations

import glob
import json
import re
import shlex
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SECURITY_AUDIT = WORKFLOWS / "security-audit.yml"
TRIVY_SCAN = WORKFLOWS / "trivy-container-scan.yml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _logical_lines(text: str) -> list[str]:
    """Dockerfile instructions with line continuations joined."""
    lines: list[str] = []
    buf = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        lines.append(buf + stripped)
        buf = ""
    if buf:
        lines.append(buf)
    return lines


def copy_sources(dockerfile: str) -> list[str]:
    """Sources of every COPY/ADD that reads from the build context."""
    sources: list[str] = []
    for line in _logical_lines(dockerfile):
        m = re.match(r"(?i)^(COPY|ADD)\s+(.*)$", line)
        if not m:
            continue
        rest = m.group(2).strip()
        if rest.startswith("["):
            args = json.loads(rest)
        else:
            args = shlex.split(rest)
        flags = [a for a in args if a.startswith("--")]
        if any(f.startswith("--from=") for f in flags):
            continue
        paths = [a for a in args if not a.startswith("--")]
        for src in paths[:-1]:
            if re.match(r"^[a-z]+://", src):
                continue
            sources.append(src)
    return sources


def missing_sources(dockerfile: Path, context: Path) -> list[str]:
    missing = []
    for src in copy_sources(dockerfile.read_text(encoding="utf-8")):
        if not glob.glob(str(context / src)):
            missing.append(src)
    return missing


def _security_audit_pairs() -> list[tuple[str, str]]:
    job = _load(SECURITY_AUDIT)["jobs"]["trivy-docker-scan"]
    build = next(s for s in job["steps"] if s.get("id") == "build")
    pairs = []
    for image in job["strategy"]["matrix"]["image"]:
        cmd = build["run"].replace("\\\n", " ").replace("${{ matrix.image }}", image)
        argv = shlex.split(cmd)
        assert argv[:2] == ["docker", "build"], argv
        args = argv[2:]
        dockerfile, positional, i = None, [], 0
        while i < len(args):
            if args[i] in ("-f", "--file"):
                dockerfile = args[i + 1]
                i += 2
            elif args[i] in ("-t", "--tag", "--target"):
                i += 2
            elif args[i].startswith("-"):
                i += 1
            else:
                positional.append(args[i])
                i += 1
        assert dockerfile and len(positional) == 1, argv
        pairs.append((dockerfile, positional[0]))
    return pairs


def _trivy_scan_pairs() -> list[tuple[str, str]]:
    jobs = _load(TRIVY_SCAN)["jobs"]
    pairs = []
    for name in ("scan", "scan-heavy"):
        for target in jobs[name]["strategy"]["matrix"]["target"]:
            pairs.append((target["dockerfile"], target.get("context", ".")))
    return pairs


SCAN_PAIRS = _security_audit_pairs() + _trivy_scan_pairs()


@pytest.mark.parametrize(("dockerfile", "context"), SCAN_PAIRS)
def test_every_copy_source_exists_in_the_build_context(dockerfile, context):
    missing = missing_sources(REPO_ROOT / dockerfile, REPO_ROOT / context)
    assert not missing, f"{dockerfile} with context {context!r} cannot copy {missing}"


def test_detects_a_context_that_misses_the_copied_tree(tmp_path):
    (tmp_path / "docker" / "x").mkdir(parents=True)
    (tmp_path / "src" / "python").mkdir(parents=True)
    dockerfile = tmp_path / "docker" / "x" / "Dockerfile"
    dockerfile.write_text(
        "FROM scratch AS b\n"
        "COPY --chown=1:1 src/python/ /app/src/python/\n"
        'COPY ["docker/x/Dockerfile", "/app/"]\n'
        "COPY --from=b /usr/local /usr/local\n",
        encoding="utf-8",
    )
    assert missing_sources(dockerfile, tmp_path) == []
    assert missing_sources(dockerfile, tmp_path / "docker" / "x") == [
        "src/python/",
        "docker/x/Dockerfile",
    ]


def test_copy_parsing_joins_continuations_and_skips_stage_copies():
    text = "COPY a \\\n     b /dst/\nCOPY --from=builder /x /y\nADD https://e.x/f /f\n"
    assert copy_sources(text) == ["a", "b"]


def test_a_failed_build_fails_the_security_audit_scan():
    job = _load(SECURITY_AUDIT)["jobs"]["trivy-docker-scan"]
    assert "continue-on-error" not in job
    for step in job["steps"]:
        assert "continue-on-error" not in step, step.get("name")
        assert "steps.build.outcome" not in str(step.get("if", "")), step.get("name")
