"""Unit tests for scripts/check_doc_examples.py execute subcommand (T-010)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_doc_examples.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_doc_examples",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture(scope="module")
def executor_mod():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from doc_examples import executor

    return executor


# ----- executor unit tests -----


def test_executor_runs_bash_syntax_check(executor_mod):
    result = executor_mod.execute_block(
        block_hash="h",
        file="x.md",
        line_start=1,
        language="bash",
        body="echo hello\nls -la\n",
        timeout_sec=10,
        mode="syntax",
    )
    assert result.status == executor_mod.EXEC_PASS


def test_executor_detects_bash_syntax_error(executor_mod):
    result = executor_mod.execute_block(
        block_hash="h",
        file="x.md",
        line_start=1,
        language="bash",
        body="if true; then\necho missing fi\n",
        timeout_sec=10,
        mode="syntax",
    )
    assert result.status == executor_mod.EXEC_FAIL
    assert result.exit_code != 0


def test_executor_validates_python_syntax(executor_mod):
    result = executor_mod.execute_block(
        block_hash="h",
        file="x.md",
        line_start=1,
        language="python",
        body="print('ok')\nfor i in range(3):\n    print(i)\n",
        timeout_sec=10,
        mode="syntax",
    )
    assert result.status == executor_mod.EXEC_PASS


def test_executor_detects_python_syntax_error(executor_mod):
    result = executor_mod.execute_block(
        block_hash="h",
        file="x.md",
        line_start=1,
        language="python",
        body="def broken(:\n    pass\n",
        timeout_sec=10,
        mode="syntax",
    )
    assert result.status == executor_mod.EXEC_FAIL


def test_executor_routes_unsupported_runners(executor_mod):
    for lang in ("rust", "csharp", "go", "wasm"):
        result = executor_mod.execute_block(
            block_hash="h",
            file="x.md",
            line_start=1,
            language=lang,
            body="// stub",
            timeout_sec=10,
            mode="syntax",
        )
        assert result.status == executor_mod.EXEC_RUNNER_UNSUPPORTED, (
            f"runner for {lang} should not be registered in v1"
        )


def test_executor_injects_pipefail_in_real_bash(executor_mod):
    """In real mode, a multi-line bash with a failing mid-pipe must fail.

    Without ``set -euo pipefail`` injection, ``false; echo ok`` exits 0
    (the last command's status). The injection turns the early failure
    into a non-zero exit.
    """
    result = executor_mod.execute_block(
        block_hash="h",
        file="x.md",
        line_start=1,
        language="bash",
        body="false\necho ok\n",
        timeout_sec=10,
        mode="real",
    )
    assert result.status == executor_mod.EXEC_FAIL
    assert result.exit_code != 0


def test_executor_honours_author_pipefail_optout(executor_mod):
    """Author-supplied ``set +e`` opts out of the injection (head heuristic)."""
    result = executor_mod.execute_block(
        block_hash="h",
        file="x.md",
        line_start=1,
        language="bash",
        body="set +e\nfalse\necho ok\n",
        timeout_sec=10,
        mode="real",
    )
    # With set +e, the script returns the last command's status (0).
    assert result.status == executor_mod.EXEC_PASS


# ----- execute CLI integration -----


def _make_audit_fixture(
    tmp_path: Path,
    blocks: list[dict],
    executable_count: int | None = None,
) -> Path:
    audit_path = tmp_path / "audit.json"
    totals = {
        "executable": executable_count
        if executable_count is not None
        else sum(1 for b in blocks if b["category"] == "executable"),
        "needs_placeholder": 0,
        "skip_warranted": 0,
        "total": len(blocks),
    }
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-05-19T00:00:00Z",
                "totals": totals,
                "by_language": {},
                "blocks": blocks,
            }
        ),
        encoding="utf-8",
    )
    return audit_path


def test_cli_execute_runs_executable_blocks(mod, tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    sample = docs / "sample.md"
    sample.write_text(
        "```bash\necho ok\n```\n\n```python\nprint(1)\n```\n",
        encoding="utf-8",
    )
    from doc_examples.extractor import extract_from_file

    blocks = extract_from_file(sample, repo_root=tmp_path)
    records = [
        {
            "file": b.file,
            "line_start": b.line_start,
            "line_end": b.line_end,
            "language_raw": b.language,
            "language": b.language,
            "category": "executable",
            "hash_sha1": b.hash_sha1,
            "suggested_action": "",
            "placeholders_detected": [],
            "directives_detected": [],
            "env_dependencies": [],
        }
        for b in blocks
    ]
    audit = _make_audit_fixture(tmp_path, records, executable_count=2)
    report = tmp_path / "report.json"
    rc = mod.main(
        [
            "execute",
            "--audit-input",
            str(audit),
            "--repo-root",
            str(tmp_path),
            "--report",
            str(report),
        ]
    )
    assert rc == 0  # informational tier: always exit 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["observed_total"] == 2
    statuses = {r["status"] for r in payload["results"]}
    assert statuses == {"pass"}


def test_cli_execute_silent_zero_warning_when_dispatch_empty(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    audit = _make_audit_fixture(
        tmp_path,
        blocks=[],
        executable_count=5,  # audit claims 5 but we have 0 records
    )
    rc = mod.main(
        [
            "execute",
            "--audit-input",
            str(audit),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "Collected executable blocks (N=0)" in captured.err
    assert "::warning::" in captured.err


def test_cli_execute_strict_mode_returns_one_on_fail(mod, tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    sample = docs / "broken.md"
    sample.write_text(
        "```bash\nif true; then\necho missing-fi\n```\n",
        encoding="utf-8",
    )
    from doc_examples.extractor import extract_from_file

    blocks = extract_from_file(sample, repo_root=tmp_path)
    records = [
        {
            "file": b.file,
            "line_start": b.line_start,
            "line_end": b.line_end,
            "language_raw": b.language,
            "language": b.language,
            "category": "executable",
            "hash_sha1": b.hash_sha1,
            "suggested_action": "",
            "placeholders_detected": [],
            "directives_detected": [],
            "env_dependencies": [],
        }
        for b in blocks
    ]
    audit = _make_audit_fixture(tmp_path, records, executable_count=1)
    rc = mod.main(
        [
            "execute",
            "--audit-input",
            str(audit),
            "--repo-root",
            str(tmp_path),
            "--strict",
        ]
    )
    assert rc == 1


def test_cli_execute_detects_stale_audit(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    docs = tmp_path / "docs"
    docs.mkdir()
    sample = docs / "sample.md"
    sample.write_text(
        "```bash\necho v2\n```\n",
        encoding="utf-8",
    )
    # Audit records a hash that does NOT match the current sample body.
    records = [
        {
            "file": "docs/sample.md",
            "line_start": 1,
            "line_end": 3,
            "language_raw": "bash",
            "language": "bash",
            "category": "executable",
            "hash_sha1": "0" * 40,  # stale hash
            "suggested_action": "",
            "placeholders_detected": [],
            "directives_detected": [],
            "env_dependencies": [],
        }
    ]
    audit = _make_audit_fixture(tmp_path, records, executable_count=1)
    rc = mod.main(
        [
            "execute",
            "--audit-input",
            str(audit),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "::warning::Audit JSON stale" in captured.err


def test_cli_execute_missing_audit_returns_two(mod, tmp_path: Path):
    rc = mod.main(
        [
            "execute",
            "--audit-input",
            str(tmp_path / "nope.json"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 2


def test_cli_execute_writes_sticky_comment(mod, tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "x.md").write_text(
        "```bash\necho ok\n```\n",
        encoding="utf-8",
    )
    from doc_examples.extractor import extract_from_file

    [block] = extract_from_file(docs / "x.md", repo_root=tmp_path)
    records = [
        {
            "file": block.file,
            "line_start": block.line_start,
            "line_end": block.line_end,
            "language_raw": block.language,
            "language": block.language,
            "category": "executable",
            "hash_sha1": block.hash_sha1,
            "suggested_action": "",
            "placeholders_detected": [],
            "directives_detected": [],
            "env_dependencies": [],
        }
    ]
    audit = _make_audit_fixture(tmp_path, records, executable_count=1)
    sticky = tmp_path / "sticky.md"
    mod.main(
        [
            "execute",
            "--audit-input",
            str(audit),
            "--repo-root",
            str(tmp_path),
            "--sticky-comment",
            str(sticky),
        ]
    )
    text = sticky.read_text(encoding="utf-8")
    assert "doc-examples-gate report" in text
    assert "Expected from audit.totals.executable: **1**" in text
    assert "observed: **1**" in text
