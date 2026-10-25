"""Runtime Docker images must not ship pip (Issue #748).

pip 26.x carries a CycloneDX SBOM of its own vendored libraries at
``pip/_vendor/bom.cdx.json`` (msgpack 1.1.2, setuptools 70.3.0 for
``pkg_resources``, urllib3 2.7.0, ...). Trivy reads that SBOM in an image scan
and reports those versions as installed Python packages. Because they come
from an SBOM rather than from a ``METADATA`` file, the findings carry no
``FilePath`` and no license, which is why they were first suppressed in
``.trivyignore.yaml`` as entries "with no real package behind them". The code
is real: it is pip's vendored copy. Deleting only ``vendor.txt`` changes
nothing; deleting ``bom.cdx.json`` removes all of them (measured with Trivy
0.67.2 and 0.76.1, see docs/design/trivy-pip-vendor-findings-2026-10-24.md).

The images install everything with ``uv pip`` and never run pip after the
build, so the fix is to remove pip once the last ``pip install`` is done and
to fail the build if any ``pip/_vendor`` tree is left. These tests pin that:

* every Dockerfile stage that installs pip or starts from the official
  ``python:`` image (which ships pip) uninstalls pip after its last install
  and then runs the build-time check;
* a stage that installs Debian's ``python3-pip`` purges it again;
* every image the Trivy workflow scans is covered (the list is read from the
  workflow, so a new matrix entry is checked without editing this file);
* ``.trivyignore.yaml`` entries keep a versioned PURL and an ``expired_at``,
  and pip's vendored versions are not suppressed again.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "trivy-container-scan.yml"
TRIVYIGNORE = REPO_ROOT / ".trivyignore.yaml"

# Dockerfiles that are not held to the rule. Each entry needs a reason.
EXEMPT: dict[str, str] = {
    "docker/python-train/Dockerfile": (
        "学習用の開発 image。 研究者がコンテナ内で pip を使う前提で、 "
        "Trivy の scan 対象からも外している (trivy-container-scan.yml の "
        "scan-heavy コメント参照)。"
    ),
    "docker/cpp-dev/Dockerfile": (
        "C++ 開発用 image。 pip は Debian パッケージ python3-pip (dpkg 管理) "
        "のみで、 Trivy の言語パッケージ解析は dpkg 管理のファイルを読まない。"
    ),
}

# `pip install` / `pip3 install` / `python -m pip install`, but not `uv pip install`.
PIP_INSTALL_RE = re.compile(r"(?<!uv )(?<![\w-])pip3?(?:\.\d+)? install\b")
UV_PIP_INSTALL_RE = re.compile(r"\buv pip install\b")
# `pip uninstall [options] pip`; the options must include -y / --yes, or the
# build would stop at the confirmation prompt.
PIP_UNINSTALL_RE = re.compile(
    r"(?<![\w-])pip3?(?:\.\d+)? uninstall((?:\s+--?[\w-]+)*)\s+pip(?![\w.-])"
)


def is_pip_uninstall(args: str) -> bool:
    return any(
        re.search(r"(?:^|\s)(?:-y|--yes)(?=\s|$)", m.group(1))
        for m in PIP_UNINSTALL_RE.finditer(args)
    )


# A `pip install` command whose package list contains pip itself. With
# `--ignore-installed` this lays a second pip over the base image's pip in the
# same site-packages; when the versions differ, two dist-info directories are
# left and `pip uninstall` removes only one (measured on python:3.13.13 with
# base pip 26.0.1 and python:3.13.15 with 26.2.1, against pip 26.2.2).
PIP_REINSTALLS_PIP_RE = re.compile(
    r"(?<!uv )(?<![\w-])pip3?(?:\.\d+)? install\b[^;&|]*\s--ignore-installed\b[^;&|]*?"
    r"\spip(?:[<>=~!]\S*)?(?=\s|$)"
    r"|(?<!uv )(?<![\w-])pip3?(?:\.\d+)? install\b[^;&|]*?\spip(?:[<>=~!]\S*)?(?=\s|$)"
    r"[^;&|]*\s--ignore-installed\b"
)


APT_INSTALL_PIP_RE = re.compile(r"apt-get install\b.*\bpython3-pip\b")
APT_PURGE_PIP_RE = re.compile(r"apt-get (?:purge|remove)\b[^;&|]*\bpython3-pip\b")
PYTHON_BASE_RE = re.compile(r"^(?:docker\.io/)?(?:library/)?python:")


@dataclass
class Instruction:
    keyword: str
    args: str


@dataclass
class Stage:
    base: str
    name: str | None
    instructions: list[Instruction] = field(default_factory=list)


def logical_lines(text: str) -> list[str]:
    """Join `\\` continuations; drop comments and blank lines like Docker does."""
    out: list[str] = []
    buf = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            # Docker removes comment lines even inside a continuation, and a
            # blank line does not end one.
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1].rstrip() + " "
            continue
        out.append(buf + stripped)
        buf = ""
    if buf:
        out.append(buf.rstrip())
    return out


def parse_stages(text: str) -> list[Stage]:
    stages: list[Stage] = []
    for line in logical_lines(text):
        keyword, _, args = line.partition(" ")
        keyword = keyword.upper()
        if keyword == "FROM":
            tokens = [t for t in args.split() if not t.startswith("--")]
            name = tokens[2] if len(tokens) >= 3 and tokens[1].upper() == "AS" else None
            stages.append(Stage(base=tokens[0], name=name))
        elif stages:
            stages[-1].instructions.append(Instruction(keyword, args))
    return stages


def is_verification(args: str) -> bool:
    return "import pip" in args and "pip/_vendor" in args


def stage_violations(stage: Stage) -> list[str]:
    """Return why this stage may still ship pip (empty list = clean)."""
    runs = [
        (i, ins.args)
        for i, ins in enumerate(stage.instructions)
        if ins.keyword == "RUN"
    ]
    pip_installs = [i for i, a in runs if PIP_INSTALL_RE.search(a)]
    all_installs = pip_installs + [i for i, a in runs if UV_PIP_INSTALL_RE.search(a)]
    apt_pip = [i for i, a in runs if APT_INSTALL_PIP_RE.search(a)]
    python_base = bool(PYTHON_BASE_RE.search(stage.base))

    if not (pip_installs or apt_pip or python_base):
        return []

    label = stage.name or stage.base
    last_install = max(all_installs, default=-1)
    problems: list[str] = []
    removal_points: list[int] = []

    if pip_installs or python_base:
        uninstalls = [i for i, a in runs if is_pip_uninstall(a)]
        if not uninstalls or max(uninstalls) <= last_install:
            problems.append(
                f"stage {label!r}: no `pip uninstall -y pip` after the last "
                "`pip install` / `uv pip install`"
            )
        else:
            removal_points.append(max(uninstalls))
    if python_base and any(PIP_REINSTALLS_PIP_RE.search(a) for _, a in runs):
        problems.append(
            f"stage {label!r}: `pip install --ignore-installed ... pip` lays a second "
            "pip over the base image's pip; `pip uninstall` then leaves one behind"
        )
    if apt_pip:
        purges = [i for i, a in runs if APT_PURGE_PIP_RE.search(a)]
        if not purges or max(purges) < max(apt_pip) or max(purges) <= last_install:
            problems.append(
                f"stage {label!r}: Debian python3-pip is installed but not purged "
                "after the last install"
            )
        else:
            removal_points.append(max(purges))

    checks = [i for i, a in runs if is_verification(a)]
    first_needed = max(removal_points, default=last_install)
    if not checks or max(checks) < first_needed:
        problems.append(
            f"stage {label!r}: no build-time check (a RUN that tests `import pip` "
            "and searches for `pip/_vendor`) after pip is removed"
        )
    return problems


def scanned_dockerfiles() -> set[str]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    found: set[str] = set()
    for job in data["jobs"].values():
        matrix = job.get("strategy", {}).get("matrix", {})
        for entry in matrix.get("target", []) or []:
            if isinstance(entry, dict) and "dockerfile" in entry:
                found.add(entry["dockerfile"])
    return found


def checked_dockerfiles() -> list[str]:
    paths = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "docker").rglob("Dockerfile*")
    }
    paths |= scanned_dockerfiles()
    return sorted(p for p in paths if p not in EXEMPT)


# --------------------------------------------------------------------------
# The checker itself (synthetic Dockerfiles).
# --------------------------------------------------------------------------

GOOD = """\
FROM python:3.13-slim AS builder
RUN pip install --upgrade pip setuptools
RUN pip install uv
RUN uv pip install --system foo
# comment inside the file
RUN python -m pip uninstall -y pip \\
    && if python -c "import pip"; then exit 1; fi \\
    && ! find /usr/local/lib -path '*/pip/_vendor' | grep -q .
FROM gcr.io/distroless/python3-debian13
COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
"""


def test_checker_accepts_removal_after_last_install():
    assert [v for s in parse_stages(GOOD) for v in stage_violations(s)] == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "FROM python:3.13-slim\nRUN pip install uv\nRUN uv pip install --system foo\n",
            "no `pip uninstall -y pip`",
            id="never-uninstalled",
        ),
        pytest.param(
            "FROM python:3.13-slim\nRUN pip install uv\nRUN python -m pip uninstall -y pip\n"
            "RUN pip install bar\n",
            "no `pip uninstall -y pip`",
            id="installed-again-after-uninstall",
        ),
        pytest.param(
            "FROM python:3.13-slim\nRUN pip install uv\nRUN python -m pip uninstall -y pip\n",
            "no build-time check",
            id="no-verification",
        ),
        pytest.param(
            "FROM python:3.13-slim\nCOPY . /app\n",
            "no `pip uninstall -y pip`",
            id="python-base-ships-pip",
        ),
        pytest.param(
            "FROM ubuntu:24.04\nRUN apt-get install -y python3-pip\n"
            "RUN pip install uv\nRUN python -m pip uninstall -y pip\n"
            "RUN python -c 'import pip' || find / -path '*/pip/_vendor'\n",
            "python3-pip is installed but not purged",
            id="apt-pip-left",
        ),
        pytest.param(
            "FROM python:3.13-slim\nRUN pip install uv\n"
            "# RUN python -m pip uninstall -y pip\n",
            "no `pip uninstall -y pip`",
            id="commented-out-uninstall",
        ),
        pytest.param(
            "FROM python:3.13-slim\n"
            "RUN pip install --ignore-installed --upgrade pip setuptools wheel\n"
            "RUN python -m pip uninstall -y pip "
            "&& python -c 'import pip' || find / -path '*/pip/_vendor'\n",
            "lays a second pip",
            id="ignore-installed-pip-over-base-pip",
        ),
    ],
)
def test_checker_rejects(text, expected):
    violations = [v for s in parse_stages(text) for v in stage_violations(s)]
    assert any(expected in v for v in violations), violations


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ("python -m pip uninstall -y pip", True),
        ("python -m pip uninstall -y --break-system-packages pip", True),
        ("pip3 uninstall --yes pip && echo done", True),
        ("python -m pip uninstall pip", False),
        ("python -m pip uninstall -y pip-tools", False),
        ("python -m pip uninstall -y setuptools", False),
    ],
)
def test_pip_uninstall_detection(args, expected):
    assert is_pip_uninstall(args) is expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ("pip install --ignore-installed --upgrade pip setuptools wheel", True),
        ("pip install --upgrade pip --ignore-installed", True),
        ("pip install --ignore-installed pip==26.2.2", True),
        ("pip install --ignore-installed --upgrade setuptools wheel", False),
        ("pip install --upgrade pip setuptools", False),
        ("pip install --ignore-installed pip-tools", False),
        ("uv pip install --ignore-installed pip", False),
    ],
)
def test_reinstall_pip_detection(args, expected):
    assert bool(PIP_REINSTALLS_PIP_RE.search(args)) is expected


def test_uv_pip_install_is_not_a_pip_install():
    assert not PIP_INSTALL_RE.search("uv pip install --system foo")
    assert PIP_INSTALL_RE.search("python -m pip install foo")
    assert PIP_INSTALL_RE.search("pip3 install foo")


# --------------------------------------------------------------------------
# The real Dockerfiles.
# --------------------------------------------------------------------------


def test_every_scanned_dockerfile_exists_and_is_checked_or_exempt():
    scanned = scanned_dockerfiles()
    assert scanned, "no `dockerfile:` entries found in trivy-container-scan.yml"
    for path in sorted(scanned):
        assert (REPO_ROOT / path).is_file(), f"{path} is scanned but does not exist"
    assert scanned <= set(checked_dockerfiles()) | set(EXEMPT)


def test_exemptions_name_existing_files_and_have_reasons():
    for path, reason in EXEMPT.items():
        assert (REPO_ROOT / path).is_file(), f"EXEMPT names a missing file: {path}"
        assert reason.strip(), f"EXEMPT[{path}] has no reason"


@pytest.mark.parametrize("dockerfile", checked_dockerfiles())
def test_runtime_image_removes_pip(dockerfile):
    text = (REPO_ROOT / dockerfile).read_text(encoding="utf-8")
    violations = [v for s in parse_stages(text) for v in stage_violations(s)]
    assert violations == [], f"{dockerfile}:\n  " + "\n  ".join(violations)


# --------------------------------------------------------------------------
# Workflows that run commands inside the built runtime images.
# --------------------------------------------------------------------------

DOCKER_BUILD_RE = re.compile(r"docker (?:buildx )?build\b[^\n]*")
EXPRESSION_RE = re.compile(r"\$\{\{(.*?)\}\}", re.S)
IMAGE_LITERAL_RE = re.compile(r"'([\w./-]+:[\w.-]+)'")


def _tags_input(value: object) -> set[str]:
    """Tags in a build-push-action `tags:` input. An expression such as
    `${{ cond && 'img:test' || '' }}` contributes the image names quoted in it."""
    text = str(value)
    tags = {t for e in EXPRESSION_RE.findall(text) for t in IMAGE_LITERAL_RE.findall(e)}
    plain = EXPRESSION_RE.sub("", text)
    return tags | {t.strip() for t in re.split(r"[,\n]", plain) if t.strip()}


def _built_tags(job: dict, runtime: set[str]) -> set[str]:
    """Image tags a job builds from a Dockerfile that must not ship pip."""
    tags: set[str] = set()
    for step in job.get("steps") or []:
        uses = step.get("uses") or ""
        if uses.startswith("docker/build-push-action"):
            with_ = step.get("with") or {}
            dockerfile = with_.get("file") or f"{with_.get('context', '.')}/Dockerfile"
            dockerfile = re.sub(r"^\./", "", str(dockerfile))
            if dockerfile in runtime:
                tags |= _tags_input(with_.get("tags", ""))
        for m in DOCKER_BUILD_RE.finditer(step.get("run") or ""):
            f = re.search(r"(?:-f|--file)[ =](\S+)", m.group(0))
            t = re.findall(r"(?:-t|--tag)[ =](\S+)", m.group(0))
            if f and re.sub(r"^\./", "", f.group(1)) in runtime:
                tags |= set(t)
    return tags


def pip_inside_runtime_containers(workflows: dict[str, dict], runtime: set[str]) -> list[str]:
    """`docker run <runtime image> ... pip install` fails once pip is gone."""
    problems = []
    for name, data in sorted(workflows.items()):
        for job_id, job in (data.get("jobs") or {}).items():
            tags = _built_tags(job, runtime)
            for step in job.get("steps") or []:
                run = step.get("run") or ""
                if "docker run" not in run or not any(t in run for t in tags):
                    continue
                if PIP_INSTALL_RE.search(run):
                    problems.append(
                        f"{name} job {job_id!r} step {step.get('name')!r}: runs pip "
                        "inside a runtime image that ships without pip; use "
                        "`uv pip install --system` (as root)"
                    )
    return problems


def test_pip_inside_runtime_container_is_detected():
    job = {
        "steps": [
            {
                "uses": "docker/build-push-action@v6",
                "with": {"file": "docker/a/Dockerfile", "tags": "img:test"},
            },
            {"run": 'docker run --rm img:test bash -c "pip install pytest && pytest"'},
            {"run": 'docker run --rm -u root img:test bash -c "uv pip install --system pytest"'},
            {"run": 'docker run --rm other:test bash -c "pip install pytest"'},
        ]
    }
    problems = pip_inside_runtime_containers({"w.yml": {"jobs": {"j": job}}}, {"docker/a/Dockerfile"})
    assert len(problems) == 1 and "w.yml" in problems[0]


def test_a_tag_added_by_an_expression_is_detected():
    job = {
        "steps": [
            {
                "uses": "docker/build-push-action@v6",
                "with": {
                    "file": "docker/a/Dockerfile",
                    "tags": "${{ steps.meta.outputs.tags }}\n"
                    "${{ github.event_name == 'pull_request' && 'img:test' || '' }}\n",
                },
            },
            {"run": 'docker run --rm img:test bash -c "pip install pytest"'},
        ]
    }
    problems = pip_inside_runtime_containers({"w.yml": {"jobs": {"j": job}}}, {"docker/a/Dockerfile"})
    assert len(problems) == 1


def test_workflows_do_not_run_pip_inside_runtime_images():
    """docker-test.yml installed pytest with pip inside python-inference and
    failed with `pip: command not found` once pip was removed (PR #853)."""
    workflows = {
        p.name: yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
    }
    runtime = set(checked_dockerfiles())
    assert any(_built_tags(j, runtime) for w in workflows.values() for j in (w.get("jobs") or {}).values())
    # The python-inference checks run in the job that builds the image.
    build = workflows["docker-build.yml"]["jobs"]["build-python-inference"]
    assert "piper-python-inference:test" in _built_tags(build, runtime)
    assert pip_inside_runtime_containers(workflows, runtime) == []


# --------------------------------------------------------------------------
# .trivyignore.yaml
# --------------------------------------------------------------------------

VERSIONED_PURL_RE = re.compile(r"^pkg:[a-z0-9.+-]+/[^@\s]+@[^@\s]+$")

# Versions that only exist inside pip's vendored SBOM. They are fixed by not
# shipping pip, never by suppressing them (#748).
PIP_VENDORED_PURLS = {"pkg:pypi/msgpack@1.1.2", "pkg:pypi/setuptools@70.3.0"}


def _ignore_entries() -> list[dict]:
    data = yaml.safe_load(TRIVYIGNORE.read_text(encoding="utf-8"))
    assert isinstance(data, dict), ".trivyignore.yaml must be a mapping"
    entries = data.get("vulnerabilities")
    assert isinstance(entries, list), (
        "`vulnerabilities` must be a list (use [] when empty)"
    )
    return entries


def test_trivyignore_is_wired_into_the_workflow():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "trivyignores: .trivyignore.yaml" in text
    assert TRIVYIGNORE.is_file()


def test_trivyignore_entries_are_narrow_and_expire():
    for entry in _ignore_entries():
        vid = entry.get("id")
        assert vid, f"entry without id: {entry}"
        assert str(entry.get("statement", "")).strip(), f"{vid}: statement is required"
        purls = entry.get("purls") or []
        assert purls, f"{vid}: suppress by versioned PURL, not by id alone"
        for purl in purls:
            assert VERSIONED_PURL_RE.match(purl), (
                f"{vid}: PURL without a version: {purl}"
            )
        expired = entry.get("expired_at")
        assert isinstance(expired, dt.date), (
            f"{vid}: expired_at (YYYY-MM-DD) is required"
        )


def test_trivyignore_does_not_hide_pip_vendored_versions():
    for entry in _ignore_entries():
        hidden = PIP_VENDORED_PURLS & set(entry.get("purls") or [])
        assert not hidden, (
            f"{entry.get('id')} suppresses {sorted(hidden)}, which come from pip's "
            "vendored SBOM (pip/_vendor/bom.cdx.json). Remove pip from the image instead."
        )
