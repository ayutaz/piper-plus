"""Docker images must install piper-train together with its in-repo deps.

A Docker build context never holds the whole uv workspace, yet uv applies
``[tool.uv.sources]`` (``{ workspace = true }``) from the member and from the
root pyproject whenever it installs ``src/python``. When piper-train gained the
in-repo ``piper-plus`` dependency (for ``piper_plus.embedding``), every image
failed with ``Failed to parse entry: `piper-plus```: ``src/python_run`` was not
copied, so it was "not a workspace member". Dropping the source is not enough
either: PyPI ``piper-plus`` lacks ``piper_plus.embedding`` and piper-train
would install but fail at import time. And with the root pyproject in the
context, uv turns workspace deps into editable links into the build directory,
which the distroless final stages do not copy.

So each ``uv pip install`` that installs piper-train must pass
``--no-sources`` and name every in-repo dependency's local path (or built
wheel) on the same command, and the Dockerfile must COPY those directories.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TRAIN_DIR = "src/python"


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    assert match, requirement
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def workspace_members() -> dict[str, str]:
    """Map normalized project name -> member directory (repo-relative)."""
    members = _load(ROOT / "pyproject.toml")["tool"]["uv"]["workspace"]["members"]
    result = {}
    for member in members:
        project = _load(ROOT / member / "pyproject.toml")["project"]
        result[_name(project["name"])] = member
    return result


def in_repo_deps_of_train() -> dict[str, str]:
    """In-repo packages piper-train depends on (base deps and every extra)."""
    project = _load(ROOT / TRAIN_DIR / "pyproject.toml")["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    members = workspace_members()
    names = {_name(r) for r in requirements} & set(members)
    names.discard(_name(project["name"]))
    return {name: members[name] for name in sorted(names)}


def _instructions(text: str) -> list[str]:
    joined = re.sub(r"\\\r?\n", " ", text)
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _wheel_glob(name: str) -> str:
    return name.replace("-", "_") + "-"


def _mentions(command: str, directory: str, name: str) -> bool:
    path = re.escape(directory) + r"(?:/)?(?:\[[^\]]*\])?(?=[\"'\s]|$)"
    return bool(re.search(r"/" + path, command)) or _wheel_glob(name) in command


def check_dockerfile(text: str, deps: dict[str, str]) -> list[str]:
    """Return human-readable problems; empty when the Dockerfile is sound."""
    instructions = _instructions(text)
    copied = []
    for line in instructions:
        if re.match(r"COPY\s", line, re.IGNORECASE) and "--from" not in line:
            tokens = [t for t in line.split()[1:] if not t.startswith("--")]
            copied.extend(t.rstrip("/") for t in tokens[:-1])

    problems = []
    for line in instructions:
        if not re.match(r"RUN\s", line, re.IGNORECASE):
            continue
        for command in re.split(r"&&|;", line):
            if "uv pip install" not in command:
                continue
            if not _mentions(command, TRAIN_DIR, "piper-train"):
                continue
            if "--no-sources" not in command:
                problems.append(
                    f"`{command.strip()}` installs piper-train without "
                    "--no-sources (workspace sources cannot resolve in a "
                    "Docker build context)"
                )
            for name, directory in deps.items():
                if not _mentions(command, directory, name):
                    problems.append(
                        f"`{command.strip()}` installs piper-train but not the "
                        f"in-repo {name} ({directory}) on the same command"
                    )
                if not any(
                    directory == source or directory.startswith(source + "/")
                    for source in copied
                ):
                    problems.append(f"{directory} is not COPY'd into the context")
    return sorted(set(problems))


def _dockerfiles_installing_train() -> list[Path]:
    found = []
    for path in sorted((ROOT / "docker").rglob("Dockerfile*")):
        text = path.read_text(encoding="utf-8")
        if any(
            "uv pip install" in line and _mentions(line, TRAIN_DIR, "piper-train")
            for line in _instructions(text)
        ):
            found.append(path)
    return found


def test_discovers_in_repo_dependencies_and_dockerfiles():
    deps = in_repo_deps_of_train()
    assert deps == {
        "piper-plus": "src/python_run",
        "piper-plus-g2p": "src/python/g2p",
    }
    names = {p.relative_to(ROOT).as_posix() for p in _dockerfiles_installing_train()}
    assert {
        "docker/python-inference/Dockerfile",
        "docker/python-inference/Dockerfile.cpu",
        "docker/python-inference/Dockerfile.cpu.distroless",
        "docker/python-train/Dockerfile",
        "docker/webui/Dockerfile",
        "docker/webui/Dockerfile.distroless",
        "docker/wyoming/Dockerfile",
    } <= names


@pytest.mark.parametrize(
    "dockerfile",
    _dockerfiles_installing_train(),
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_dockerfile_installs_train_with_in_repo_deps(dockerfile):
    problems = check_dockerfile(
        dockerfile.read_text(encoding="utf-8"), in_repo_deps_of_train()
    )
    assert problems == []


def test_member_pyprojects_do_not_declare_workspace_sources():
    # The root pyproject applies workspace sources to every member; a member
    # copy is redundant in the workspace and breaks standalone installs.
    for member in workspace_members().values():
        sources = (
            _load(ROOT / member / "pyproject.toml")
            .get("tool", {})
            .get("uv", {})
            .get("sources", {})
        )
        workspace = [
            name
            for name, spec in sources.items()
            if isinstance(spec, dict) and spec.get("workspace")
        ]
        assert workspace == [], f"{member}/pyproject.toml: {workspace}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            'COPY src/python/ /app/src/python/\n'
            'RUN uv pip install --system "/app/src/python[inference]"\n',
            [
                "--no-sources",
                "in-repo piper-plus (src/python_run)",
                "src/python_run is not COPY'd",
            ],
        ),
        (
            "COPY src/python /tmp/src/python\n"
            "COPY src/python_run /tmp/src/python_run\n"
            'RUN uv pip install --no-sources \\\n'
            '    "/tmp/src/python/g2p" "/tmp/src/python_run" "/tmp/src/python[train]"\n',
            [],
        ),
    ],
)
def test_checker_flags_the_regression_shape(text, expected):
    problems = check_dockerfile(
        text,
        {"piper-plus": "src/python_run", "piper-plus-g2p": "src/python/g2p"},
    )
    joined = "\n".join(problems)
    if not expected:
        assert problems == []
    for fragment in expected:
        assert fragment in joined
