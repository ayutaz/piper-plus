"""Tests for scripts/check_orphan_test_files.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_orphan_test_files.py"

_spec = importlib.util.spec_from_file_location("check_orphan_test_files", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
sys.modules["check_orphan_test_files"] = gate
_spec.loader.exec_module(gate)

NODE_TEST = 'import { test } from "node:test";\n'


def _workflow(repo: Path, name: str, run: str) -> None:
    path = repo / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"          {line}" for line in run.splitlines())
    path.write_text(
        "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        f"    steps:\n      - run: |\n{body}\n",
        encoding="utf-8",
    )


def _package(repo: Path, pkg: str, scripts: dict[str, str], tests: dict[str, str]) -> None:
    root = repo / pkg
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    test_dir = root / gate.NODE_PACKAGES[pkg]
    test_dir.mkdir(parents=True, exist_ok=True)
    for name, text in tests.items():
        (test_dir / name).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    scripts_dir = tmp_path / "tests" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "test_a.py").write_text("", encoding="utf-8")
    (scripts_dir / "test_b.py").write_text("", encoding="utf-8")
    _package(tmp_path, "src/wasm/g2p", {"test": "node --test test/test-g.js"}, {"test-g.js": NODE_TEST})
    _package(
        tmp_path,
        "src/wasm/openjtalk-web",
        {"test:all": "node --test test/js/test-w.js"},
        {"test-w.js": NODE_TEST, "helper.js": "export const x = 1;\n"},
    )
    return tmp_path


def test_directory_run_covers_every_python_file(repo: Path) -> None:
    _workflow(repo, "s.yml", "pytest tests/scripts -q\nnpm test\nnpm run test:all")
    assert gate.main([str(repo)]) == 0


def test_unlisted_python_file_is_reported(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _workflow(repo, "s.yml", "pytest tests/scripts/test_a.py\nnpm test\nnpm run test:all")
    assert gate.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "tests/scripts/test_b.py" in err
    assert "test_a.py" not in err


def test_file_after_directory_is_not_a_directory_run(repo: Path) -> None:
    assert not gate.runs_whole_dir("pytest tests/scripts/test_a.py", "tests/scripts")
    assert gate.runs_whole_dir("python -m pytest tests/scripts -o addopts=", "tests/scripts")
    assert gate.runs_whole_dir("pytest tests/scripts/", "tests/scripts")


def test_commented_command_does_not_count(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A YAML comment and a shell comment both name the directory; neither runs.
    path = repo / ".github" / "workflows" / "s.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "on: pull_request\n# pytest tests/scripts\njobs:\n  a:\n    runs-on: x\n"
        "    steps:\n      - run: |\n          # pytest tests/scripts\n"
        "          npm test\n          npm run test:all\n",
        encoding="utf-8",
    )
    assert gate.main([str(repo)]) == 1
    assert "tests/scripts/test_a.py" in capsys.readouterr().err


def test_node_file_in_unrun_script_is_reported(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # test:all names test-w.js, but no workflow runs test:all.
    _workflow(repo, "s.yml", "pytest tests/scripts\nnpm test")
    assert gate.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "src/wasm/openjtalk-web/test/js/test-w.js" in err
    assert "helper.js" not in err  # not a node:test file


def test_script_reached_through_npm_run_counts(repo: Path) -> None:
    pkg = repo / "src/wasm/openjtalk-web/package.json"
    pkg.write_text(
        json.dumps({"scripts": {"ci": "npm run test:all", "test:all": "node --test test/js/test-w.js"}}),
        encoding="utf-8",
    )
    _workflow(repo, "s.yml", "pytest tests/scripts\nnpm test\nnpm run ci")
    assert gate.main([str(repo)]) == 0


def test_node_file_named_by_workflow_counts(repo: Path) -> None:
    _workflow(repo, "s.yml", "pytest tests/scripts\nnpm test\nnode --test \\\n  test/js/test-w.js")
    assert gate.main([str(repo)]) == 0


def test_empty_directory_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for f in (repo / "tests" / "scripts").glob("*.py"):
        f.unlink()
    _workflow(repo, "s.yml", "pytest tests/scripts\nnpm test\nnpm run test:all")
    assert gate.main([str(repo)]) == 1
    assert "pass vacuously" in capsys.readouterr().err


def test_repository_passes() -> None:
    assert gate.main([str(REPO_ROOT)]) == 0
