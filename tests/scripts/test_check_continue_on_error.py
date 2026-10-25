"""Every continue-on-error must be allowlisted, with a reason and, if it hides a check, a deadline.

Regression focus: in 2026-10 the workflows had 62 continue-on-error keys
and 37 of them hid check results; the "strict after 2-3 weeks" promises
were about five months overdue. This test runs the gate on the real
repository, so an unlisted key or an expired entry fails scripts-tests on
every PR.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_continue_on_error.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_continue_on_error", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


TODAY = dt.date(2026, 10, 25)

WORKFLOW = textwrap.dedent(
    """\
    on: push
    jobs:
      build:
        runs-on: ubuntu-24.04
        continue-on-error: true
        steps:
          - name: Cache
            uses: actions/cache@v4.3.0
            continue-on-error: true
          - name: Lint
            run: make lint
            continue-on-error: ${{ github.event_name == 'pull_request' }}
          - name: Test
            run: make test
            continue-on-error: false
    """
)

ENTRIES = """
[[entry]]
workflow = "w.yml"
job = "build"
kind = "tracked"
expires = "2026-12-31"
reason = "backlog"

[[entry]]
workflow = "w.yml"
job = "build"
step = "Cache"
kind = "harmless"
reason = "cache restore"

[[entry]]
workflow = "w.yml"
job = "build"
step = "Lint"
kind = "tracked"
expires = "2026-12-31"
reason = "lint backlog"
"""


def _repo(tmp_path, entries=ENTRIES, workflow=WORKFLOW):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "w.yml").write_text(workflow, encoding="utf-8")
    (tmp_path / "docs" / "spec").mkdir(parents=True)
    (tmp_path / gate_allowlist()).write_text(entries, encoding="utf-8")
    return tmp_path


def gate_allowlist():
    return Path("docs/spec/continue-on-error-allowlist.toml")


def test_real_repository_passes(gate):
    assert gate.check(REPO_ROOT, dt.date.today()) == []


def test_every_tracked_entry_in_the_real_allowlist_has_a_deadline(gate):
    import tomllib

    entries = tomllib.loads((REPO_ROOT / gate_allowlist()).read_text(encoding="utf-8"))["entry"]
    tracked = [e for e in entries if e["kind"] == "tracked"]
    assert tracked
    for entry in tracked:
        dt.date.fromisoformat(entry["expires"])


def test_complete_allowlist_passes(gate, tmp_path):
    assert gate.check(_repo(tmp_path), TODAY) == []


def test_explicit_false_needs_no_entry(gate, tmp_path):
    errors = gate.check(_repo(tmp_path), TODAY)
    assert not any("Test" in e for e in errors)


def test_unlisted_key_fails(gate, tmp_path):
    entries = ENTRIES.split("[[entry]]")
    without_cache = "[[entry]]".join(e for e in entries if 'step = "Cache"' not in e)
    errors = gate.check(_repo(tmp_path, without_cache), TODAY)
    assert len(errors) == 1 and "Cache" in errors[0] and "not in" in errors[0]


def test_expression_value_counts_as_a_key(gate, tmp_path):
    entries = ENTRIES.split("[[entry]]")
    without_lint = "[[entry]]".join(e for e in entries if 'step = "Lint"' not in e)
    errors = gate.check(_repo(tmp_path, without_lint), TODAY)
    assert len(errors) == 1 and "Lint" in errors[0]


def test_stale_entry_fails(gate, tmp_path):
    stale = ENTRIES + '\n[[entry]]\nworkflow = "w.yml"\njob = "build"\nstep = "Gone"\nkind = "harmless"\nreason = "x"\n'
    errors = gate.check(_repo(tmp_path, stale), TODAY)
    assert len(errors) == 1 and "no such continue-on-error" in errors[0]


def test_expired_entry_fails(gate, tmp_path):
    errors = gate.check(_repo(tmp_path), dt.date(2027, 1, 1))
    assert len(errors) == 2 and all("expired on 2026-12-31" in e for e in errors)


def test_tracked_without_expiry_fails(gate, tmp_path):
    errors = gate.check(_repo(tmp_path, ENTRIES.replace('expires = "2026-12-31"\n', "", 1)), TODAY)
    assert len(errors) == 1 and "need expires" in errors[0]


def test_job_level_harmless_fails(gate, tmp_path):
    entries = ENTRIES.replace('kind = "tracked"\nexpires = "2026-12-31"\nreason = "backlog"', 'kind = "harmless"\nreason = "backlog"')
    errors = gate.check(_repo(tmp_path, entries), TODAY)
    assert len(errors) == 1 and "job-level" in errors[0]


def test_empty_reason_and_unknown_kind_fail(gate, tmp_path):
    entries = ENTRIES.replace('reason = "cache restore"', 'reason = " "').replace('kind = "harmless"', 'kind = "ignore"')
    errors = gate.check(_repo(tmp_path, entries), TODAY)
    assert {"reason is empty" in e for e in errors} == {True, False}
    assert any("kind must be one of" in e for e in errors)


def test_unknown_field_fails(gate, tmp_path):
    entries = ENTRIES.replace('expires = "2026-12-31"\nreason = "backlog"', 'expire = "2026-12-31"\nreason = "backlog"')
    errors = gate.check(_repo(tmp_path, entries), TODAY)
    assert any("unknown field(s) ['expire']" in e for e in errors)
    assert any("need expires" in e for e in errors)


def test_duplicate_entry_fails(gate, tmp_path):
    cache = [e for e in ENTRIES.split("[[entry]]") if 'step = "Cache"' in e][0]
    errors = gate.check(_repo(tmp_path, ENTRIES + "[[entry]]" + cache), TODAY)
    assert len(errors) == 1 and "duplicate" in errors[0]


def test_main_exit_codes(gate, tmp_path):
    root = _repo(tmp_path)
    assert gate.main(["--root", str(root), "--today", "2026-10-25"]) == 0
    assert gate.main(["--root", str(root), "--today", "2027-01-01"]) == 1
