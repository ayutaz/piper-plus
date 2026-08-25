"""Unit tests for scripts/check_label_references.py.

The regression these cover: CI config named labels that nobody had created.
`.github/dependabot.yml` asked for `dependencies` / `automated` on all 11
ecosystems, `security-issue-routing.yml` ran `gh issue edit --add-label
"needs-triage,roadmap"` under `set -e`, and `actions/stale` was told to exempt
`help-wanted` while the repository label is `help wanted`. Nothing checked any
of it, so all five recent Dependabot PRs shipped with zero labels.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_label_references.py"

LABELS_YML = """\
- name: alpha
  color: "AABBCC"
  description: first

- name: help wanted
  color: "008672"
  description: space in the name is significant
"""

DEPENDABOT_YML = """\
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    labels:
      - "alpha"
      - "undeclared-one"
"""

STALE_WORKFLOW = """\
name: stale
jobs:
  stale:
    steps:
      - uses: actions/stale@v9.1.0
        with:
          stale-issue-label: alpha
          exempt-issue-labels: 'help wanted,undeclared-two'
"""

# OCI image labels must never be collected — they are not GitHub labels.
DOCKER_WORKFLOW = """\
name: docker
jobs:
  build:
    steps:
      - uses: docker/build-push-action@v6
        with:
          labels: ${{ steps.meta.outputs.labels }}
"""

GH_CLI_WORKFLOW = """\
name: routing
jobs:
  route:
    steps:
      - run: |
          gh issue edit "${ISSUE_NUMBER}" --add-label "alpha,undeclared-three"
"""

FAST_LANE = 'PROMOTE_LABEL = "alpha"\n'


@pytest.fixture(scope="module")
def mod():
    # Ensure platform_utils is importable from scripts/
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_label_references", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build(root: Path, **overrides) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    files = {
        ".github/labels.yml": LABELS_YML,
        ".github/dependabot.yml": DEPENDABOT_YML,
        ".github/workflows/stale.yml": STALE_WORKFLOW,
        ".github/workflows/docker-build.yml": DOCKER_WORKFLOW,
        ".github/workflows/routing.yml": GH_CLI_WORKFLOW,
        "scripts/first_pr_fast_lane.py": FAST_LANE,
    }
    files.update(overrides)
    for rel, content in files.items():
        if content is None:
            continue
        (root / rel).write_text(content, encoding="utf-8")


def _point_at(mod, root: Path):
    """Repoint every module-level path constant at `root`."""
    saved = {
        name: getattr(mod, name)
        for name in (
            "REPO_ROOT",
            "LABELS_YML",
            "DEPENDABOT_YML",
            "WORKFLOWS_DIR",
            "FAST_LANE_SCRIPT",
        )
    }
    mod.REPO_ROOT = root
    mod.LABELS_YML = root / ".github" / "labels.yml"
    mod.DEPENDABOT_YML = root / ".github" / "dependabot.yml"
    mod.WORKFLOWS_DIR = root / ".github" / "workflows"
    mod.FAST_LANE_SCRIPT = root / "scripts" / "first_pr_fast_lane.py"
    return saved


def _run(mod, root: Path, argv: list[str] | None = None) -> int:
    saved = _point_at(mod, root)
    try:
        return mod.main(argv or [])
    finally:
        for name, value in saved.items():
            setattr(mod, name, value)


def test_undeclared_labels_fail_with_call_sites(mod, tmp_path, capsys):
    _build(tmp_path)
    assert _run(mod, tmp_path) == 1
    err = capsys.readouterr().err
    assert "'undeclared-one'" in err
    assert "'undeclared-two'" in err
    assert "'undeclared-three'" in err
    # Call sites are reported so the fix is a one-line edit, not a hunt.
    assert ".github/dependabot.yml:" in err
    assert ".github/workflows/stale.yml:" in err
    assert ".github/workflows/routing.yml:" in err


def test_all_declared_passes(mod, tmp_path, capsys):
    declared = LABELS_YML + "".join(
        f'\n- name: {name}\n  color: "112233"\n  description: d\n'
        for name in ("undeclared-one", "undeclared-two", "undeclared-three")
    )
    _build(tmp_path, **{".github/labels.yml": declared})
    assert _run(mod, tmp_path) == 0
    assert "OK every referenced label is declared" in capsys.readouterr().out


def test_oci_image_labels_are_not_collected(mod, tmp_path):
    """`labels: ${{ steps.meta.outputs.labels }}` is Docker metadata."""
    _point_at(mod, tmp_path)
    try:
        _build(tmp_path)
        refs = {label for label, _src, _line in mod.collect_references()}
    finally:
        _point_at(mod, REPO_ROOT)
    assert not any("steps.meta" in r or "${{" in r for r in refs)


def test_label_name_with_space_is_preserved(mod, tmp_path):
    """`help wanted` must not be split or normalised to `help-wanted`."""
    _point_at(mod, tmp_path)
    try:
        _build(tmp_path)
        refs = {label for label, _src, _line in mod.collect_references()}
    finally:
        _point_at(mod, REPO_ROOT)
    assert "help wanted" in refs
    assert "help-wanted" not in refs


def test_zero_references_is_a_failure(mod, tmp_path, capsys):
    """An extraction rule that stops matching must be loud, not green."""
    _build(
        tmp_path,
        **{
            ".github/dependabot.yml": "version: 2\nupdates: []\n",
            ".github/workflows/stale.yml": "name: stale\n",
            ".github/workflows/docker-build.yml": DOCKER_WORKFLOW,
            ".github/workflows/routing.yml": "name: routing\n",
            "scripts/first_pr_fast_lane.py": "# no promote label\n",
        },
    )
    assert _run(mod, tmp_path) == 1
    assert "scan found 0 label references" in capsys.readouterr().err


def test_empty_catalogue_is_a_failure(mod, tmp_path, capsys):
    _build(tmp_path, **{".github/labels.yml": "# nothing declared\n"})
    assert _run(mod, tmp_path) == 1
    assert "no labels declared" in capsys.readouterr().err


def test_emit_create_commands_uses_force(mod, tmp_path, capsys):
    _build(tmp_path)
    assert _run(mod, tmp_path, ["--emit-create-commands"]) == 0
    out = capsys.readouterr().out
    assert "gh label create 'alpha' --color AABBCC --force" in out
    # Quoting must survive the space in the label name.
    assert "gh label create 'help wanted' --color 008672 --force" in out
    # The catalogue never drives deletions: every emitted command creates.
    commands = [ln for ln in out.splitlines() if not ln.startswith("#")]
    assert commands
    assert all(ln.startswith("gh label create ") for ln in commands)


def test_real_repo_passes(mod, capsys):
    """The checked-in config must satisfy its own gate."""
    assert mod.main([]) == 0
    assert "OK every referenced label is declared" in capsys.readouterr().out
