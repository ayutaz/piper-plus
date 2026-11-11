"""Every runtime strips control characters before phonemizing, the same way.

Regression focus: #934 (2026-11) added C1 stripping to the Python G2P and
said the result matched Rust's ``validate_input``. It did not: the Python
helper was called by ja / en / sv only, and the Rust ``validate_input`` had
no caller at all. No other runtime stripped anything. A contract that lists
each runtime's entry points, one fixture every runtime's test reads, and
this gate keep the rule from drifting again.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_input_sanitize_contract.py"

FIXTURE = "tests/fixtures/g2p/input_sanitize_cases.json"
MIRROR = "src/rust/g2p/tests/fixtures/input_sanitize_cases.json"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_input_sanitize_contract", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def _fixture(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "strip_cases": [
            {"name": "nul", "input": "a\u0000b", "expected": "ab"},
            {"name": "keeps_newline", "input": "a\nb", "expected": "a\nb"},
        ],
        "word_cases": [
            {"language": "es", "clean": "hola", "dirty": "ho\u0000la"},
        ],
        "pipeline_cases": [
            {"name": "ssml", "clean": "<speak>hola</speak>", "dirty": "<speak>ho\u0000la</speak>"},
        ],
    }
    data.update(overrides)
    return data


def _contract(status: str = "enforced", languages: str = '["es"]') -> str:
    return textwrap.dedent(
        f"""\
        schema_version = 1
        [rule]
        strip_category = "Cc"
        keep = ["\\n", "\\t", "\\r"]
        [fixture]
        canonical = "{FIXTURE}"
        mirrors = ["{MIRROR}"]
        languages = {languages}
        [[runtime]]
        name = "toy"
        status = "{status}"
        consumer_tests = ["src/toy/test_contract.py"]
        entry_points = [{{file = "src/toy/spanish.py", calls = "_sanitize_input"}}]
        """
    )


def _repo(
    root: Path,
    *,
    fixture: dict | None = None,
    mirror_bytes: bytes | None = None,
    contract: str | None = None,
    consumer: str | None = 'FIXTURE = "input_sanitize_cases.json"\n',
    entry: str = "def phonemize(text):\n    text = self._sanitize_input(text)\n",
    hook_files: str | None = r"^(docs/spec/input-sanitize-contract\.toml|tests/fixtures/g2p/input_sanitize_cases\.json|src/rust/g2p/tests/fixtures/input_sanitize_cases\.json|src/toy/.*)$",
) -> Path:
    data = json.dumps(fixture or _fixture(), ensure_ascii=False, indent=2).encode()
    (root / "tests/fixtures/g2p").mkdir(parents=True)
    (root / FIXTURE).write_bytes(data)
    (root / MIRROR).parent.mkdir(parents=True)
    (root / MIRROR).write_bytes(data if mirror_bytes is None else mirror_bytes)
    (root / "docs/spec").mkdir(parents=True)
    (root / "docs/spec/input-sanitize-contract.toml").write_text(
        contract or _contract(), encoding="utf-8"
    )
    (root / "src/toy").mkdir(parents=True)
    if consumer is not None:
        (root / "src/toy/test_contract.py").write_text(consumer, encoding="utf-8")
    (root / "src/toy/spanish.py").write_text(entry, encoding="utf-8")
    if hook_files is not None:
        (root / ".pre-commit-config.yaml").write_text(
            textwrap.dedent(
                f"""\
                repos:
                  - repo: local
                    hooks:
                      - id: input-sanitize-contract
                        name: x
                        entry: x
                        language: system
                        files: {hook_files}
                """
            ),
            encoding="utf-8",
        )
    return root


def test_valid_repo_passes(gate, tmp_path):
    assert gate.check(_repo(tmp_path)) == []


def test_mirror_drift_is_reported(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, mirror_bytes=b"{}"))
    assert len(errors) == 1
    assert MIRROR in errors[0]


def test_enforced_without_consumer_test_is_reported(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, consumer=None))
    assert len(errors) == 1
    assert "src/toy/test_contract.py" in errors[0]


def test_consumer_test_not_reading_fixture_is_reported(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, consumer="def test_x():\n    pass\n"))
    assert len(errors) == 1
    assert "input_sanitize_cases" in errors[0]


def test_entry_point_without_call_is_reported(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, entry="def phonemize(text):\n    return text\n"))
    assert len(errors) == 1
    assert "src/toy/spanish.py" in errors[0]
    assert "_sanitize_input" in errors[0]


def test_pending_is_listed_not_failed(gate, tmp_path, capsys):
    root = _repo(
        tmp_path,
        contract=_contract(status="pending"),
        consumer=None,
        entry="def phonemize(text):\n    return text\n",
    )
    assert gate.check(root) == []
    assert gate.main(["--root", str(root)]) == 0
    assert "PENDING: toy" in capsys.readouterr().out


def test_unknown_status_is_reported(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, contract=_contract(status="skip")))
    assert len(errors) == 1
    assert "skip" in errors[0]


def test_missing_language_in_word_cases_is_reported(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, contract=_contract(languages='["es", "xx"]')))
    assert len(errors) == 1
    assert "xx" in errors[0]


def test_fixture_case_breaking_rule_is_reported(gate, tmp_path):
    bad = _fixture(
        strip_cases=[{"name": "keeps_tab_wrongly", "input": "a\tb", "expected": "ab"}]
    )
    errors = gate.check(_repo(tmp_path, fixture=bad))
    assert len(errors) == 1
    assert "keeps_tab_wrongly" in errors[0]


def test_dirty_that_does_not_strip_to_clean_is_reported(gate, tmp_path):
    bad = _fixture(word_cases=[{"language": "es", "clean": "hola", "dirty": "ho\u0000lx"}])
    errors = gate.check(_repo(tmp_path, fixture=bad))
    assert len(errors) == 1
    assert "es" in errors[0]


def test_contract_path_outside_hook_files_is_reported(gate, tmp_path):
    # A gate only guards what its trigger shows it: an entry point the hook
    # does not watch can lose its call without the hook ever running.
    errors = gate.check(
        _repo(tmp_path, hook_files=r"^(docs/spec/input-sanitize-contract\.toml)$")
    )
    assert any("src/toy/spanish.py" in e and "files:" in e for e in errors)


def test_main_returns_1_and_prints_error(gate, tmp_path, capsys):
    root = _repo(tmp_path, consumer=None)
    assert gate.main(["--root", str(root)]) == 1
    assert "ERROR:" in capsys.readouterr().err


def test_real_repository_has_no_violations(gate):
    assert gate.check(REPO_ROOT) == []
