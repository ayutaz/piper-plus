"""The hook counts written in CLAUDE.md and .claude/README.md match the config.

Regression focus: 2026-11, both documents said 119 hooks while
.pre-commit-config.yaml had 120. Every PR that adds a hook has to remember
two numbers in two files, and nothing failed when it did not.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_doc_hook_count.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_doc_hook_count", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


CONFIG = """\
repos:
  - repo: local
    hooks:
      - id: ruff
      - id: pua-contract
      - id: trigger-coverage
"""


def _repo(root: Path, *, total: int = 3, contract: int = 1, readme: int = 3) -> Path:
    (root / ".claude").mkdir()
    (root / ".pre-commit-config.yaml").write_text(CONFIG, encoding="utf-8")
    (root / "CLAUDE.md").write_text(
        f"gate は集約 ({total} hook、 うち id に `contract` を含む gate {contract}、 formatter)。\n",
        encoding="utf-8",
    )
    (root / ".claude/README.md").write_text(
        f"集約されています (hook 数は {readme}、 2026-11-11 時点)。\n", encoding="utf-8"
    )
    return root


def test_matching_counts_pass(gate, tmp_path):
    assert gate.check(_repo(tmp_path)) == []


def test_stale_total_is_reported(gate, tmp_path):
    assert gate.check(_repo(tmp_path, total=2)) == [
        "CLAUDE.md: says 2 hooks, .pre-commit-config.yaml has 3"
    ]


def test_stale_contract_count_is_reported(gate, tmp_path):
    assert gate.check(_repo(tmp_path, contract=2)) == [
        "CLAUDE.md: says 2 contract gates, .pre-commit-config.yaml has 1"
    ]


def test_stale_readme_is_reported(gate, tmp_path):
    assert gate.check(_repo(tmp_path, readme=4)) == [
        ".claude/README.md: says 4 hooks, .pre-commit-config.yaml has 3"
    ]


def test_missing_phrase_is_reported(gate, tmp_path):
    root = _repo(tmp_path)
    (root / "CLAUDE.md").write_text("hooks are in the config.\n", encoding="utf-8")
    errors = gate.check(root)
    assert len(errors) == 1
    assert errors[0].startswith("CLAUDE.md: the hook count was not found")


def test_main_returns_1_and_prints_error(gate, tmp_path, capsys):
    root = _repo(tmp_path, total=2)
    assert gate.main(["--root", str(root)]) == 1
    assert "ERROR: CLAUDE.md: says 2 hooks" in capsys.readouterr().err


def test_real_repository_matches(gate):
    assert gate.check(REPO_ROOT) == []
