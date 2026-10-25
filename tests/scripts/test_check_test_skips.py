"""Tests for scripts/check_test_skips.py and its pytest plugin."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_test_skips.py"
PLUGIN_DIR = REPO_ROOT / "scripts" / "pytest_plugins"
TODAY = dt.date(2026, 10, 25)


def _module():
    spec = importlib.util.spec_from_file_location("check_test_skips", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m = _module()


def _entry(**overrides):
    entry = {"runtime": "go", "test": "TestA", "kind": "harmless", "reason": "r"}
    entry.update(overrides)
    return entry


# --- parsers ------------------------------------------------------------------

GO_OUTPUT = """\
=== RUN   TestA
    a_test.go:5: first
    a_test.go:5: reason a
--- SKIP: TestA (0.00s)
=== RUN   TestB
=== RUN   TestB/sub
    a_test.go:7: reason sub
--- PASS: TestB (0.00s)
    --- SKIP: TestB/sub (0.00s)
=== RUN   TestC
--- PASS: TestC (0.00s)
PASS
ok  \tgskip\t0.022s
"""


def test_go_reads_the_message_printed_before_the_skip_line():
    # Output of `go test -v` (Go 1.26): the message precedes `--- SKIP`.
    assert m.parse_go(GO_OUTPUT) == [m.Skip("TestA", "reason a"), m.Skip("TestB/sub", "reason sub")]


def test_cpp_reads_gtest_and_ctest_skips_but_not_the_summary():
    text = textwrap.dedent(
        """\
        3: [ RUN      ] OpenJTalkOptimizedTest.Basic
        3: [  SKIPPED ] OpenJTalkOptimizedTest.Basic (0 ms)
        3: [       OK ] Other.Test (1 ms)
        3: [  SKIPPED ] 1 test, listed below:
        3: [  SKIPPED ] OpenJTalkOptimizedTest.Basic
        7/9 Test #7: test_legacy ......................***Skipped   0.01 sec
        8/9 Test #8: test_ok ..........................   Passed    0.01 sec
        """
    )
    assert m.parse_cpp(text) == [m.Skip("OpenJTalkOptimizedTest.Basic", ""), m.Skip("test_legacy", "ctest")]


def test_csharp_reads_not_executed_results_with_the_skip_message():
    trx = """<?xml version="1.0" encoding="utf-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <Results>
    <UnitTestResult testName="Ns.A.Passes" outcome="Passed" />
    <UnitTestResult testName="Ns.A.Skips" outcome="NotExecuted">
      <Output><ErrorInfo><Message>fixture missing</Message></ErrorInfo></Output>
    </UnitTestResult>
  </Results>
</TestRun>
"""
    assert m.parse_csharp(trx) == [m.Skip("Ns.A.Skips", "fixture missing")]


def test_rust_reads_ignored_tests_with_and_without_a_reason():
    text = textwrap.dedent(
        """\
        test smoke::runs_cli ... ignored, needs a model
        test plain ... ignored
        test passes ... ok
        test src/lib.rs - Voice (line 12) ... ignored
        test result: ok. 1 passed; 0 failed; 3 ignored
        """
    )
    assert m.parse_rust(text) == [
        m.Skip("smoke::runs_cli", "needs a model"),
        m.Skip("plain", ""),
        m.Skip("src/lib.rs - Voice (line 12)", ""),
    ]


def test_python_reads_the_plugin_records():
    text = '{"test": "a.py::t", "reason": "r"}\n\n'
    assert m.parse_python(text) == [m.Skip("a.py::t", "r")]


def test_expand_fails_when_the_tests_left_no_output(tmp_path):
    with pytest.raises(SystemExit, match="did the tests run"):
        m.expand([str(tmp_path / "missing.log")])
    with pytest.raises(SystemExit, match="did the tests run"):
        m.expand([str(tmp_path / "**" / "*.trx")])
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "a.trx").write_text("", encoding="utf-8")
    assert m.expand([str(tmp_path / "**" / "*.trx")]) == [tmp_path / "x" / "a.trx"]


# --- allowlist ----------------------------------------------------------------


def test_the_repository_allowlist_is_valid():
    assert m.validate(m.load_entries(m.SPEC)) == []


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (_entry(runtime="java"), "runtime must be"),
        (_entry(test=""), "test is empty"),
        (_entry(reason=" "), "reason is empty"),
        (_entry(kind="ok"), "kind must be"),
        (_entry(kind="tracked"), "needs expires"),
        (_entry(expires="2027-01-01"), "harmless entry has no expires"),
        (_entry(kind="tracked", expires="soon"), "not YYYY-MM-DD"),
        (_entry(platforms=["linux", "bsd"]), "platform 'bsd'"),
        (_entry(expire="2027-01-01"), "unknown field"),
    ],
)
def test_validate_rejects_malformed_entries(entry, message):
    problems = m.validate([entry])
    assert any(message in p for p in problems), problems


def test_validate_rejects_duplicates():
    assert any("duplicate" in p for p in m.validate([_entry(), _entry()]))


def test_check_fails_on_a_skip_without_an_entry():
    problems = m.check("go", "linux", [m.Skip("TestB", "no fixture")], [_entry()], TODAY)
    assert problems == ["skipped without an allowlist entry: TestB (no fixture)"]


def test_check_matches_patterns_exact_ids_and_platforms():
    entries = [
        _entry(runtime="python", test="src/python/tests/test_korean.py::*"),
        _entry(runtime="python", test="a.py::t[x-1]"),
        _entry(runtime="python", test="b.py::t", platforms=["windows"]),
    ]
    skips = [m.Skip("src/python/tests/test_korean.py::T::t[1]", ""), m.Skip("a.py::t[x-1]", "")]
    assert m.check("python", "linux", skips, entries, TODAY) == []
    assert m.check("python", "linux", [m.Skip("b.py::t", "")], entries, TODAY) != []
    assert m.check("python", "windows", [m.Skip("b.py::t", "")], entries, TODAY) == []
    # An entry for another runtime does not apply.
    assert m.check("go", "linux", [m.Skip("a.py::t[x-1]", "")], entries, TODAY) != []


def test_check_fails_on_an_expired_tracked_entry_even_without_skips():
    entry = _entry(kind="tracked", expires="2026-10-24")
    problems = m.check("go", "linux", [], [entry], TODAY)
    assert len(problems) == 1 and "expired on 2026-10-24" in problems[0]
    assert m.check("go", "linux", [], [_entry(kind="tracked", expires="2026-10-25")], TODAY) == []


def test_main_check_exit_codes(tmp_path, capsys):
    spec = tmp_path / "allow.toml"
    spec.write_text('[[entry]]\nruntime = "go"\ntest = "TestA"\nkind = "harmless"\nreason = "r"\n', encoding="utf-8")
    log = tmp_path / "go.log"
    log.write_text(GO_OUTPUT, encoding="utf-8")
    args = ["--spec", str(spec), "check", "--runtime", "go", "--platform", "linux", "--today", "2026-10-25", str(log)]
    assert m.main(args) == 1
    assert "::error::skipped without an allowlist entry: TestB/sub (reason sub)" in capsys.readouterr().out
    spec.write_text(spec.read_text(encoding="utf-8") + '\n[[entry]]\nruntime = "go"\ntest = "TestB/*"\nkind = "harmless"\nreason = "r"\n', encoding="utf-8")
    assert m.main(args) == 0


def test_main_check_takes_runner_os_as_the_platform(tmp_path):
    # The workflows pass $RUNNER_OS unchanged: macOS runners ship bash 3.2,
    # which cannot lowercase with ${RUNNER_OS,,}.
    spec = tmp_path / "allow.toml"
    spec.write_text(
        '[[entry]]\nruntime = "go"\ntest = "Test*"\nkind = "harmless"\nreason = "r"\nplatforms = ["macos"]\n',
        encoding="utf-8",
    )
    log = tmp_path / "go.log"
    log.write_text(GO_OUTPUT, encoding="utf-8")
    for runner_os, code in (("macOS", 0), ("Linux", 1)):
        args = ["--spec", str(spec), "check", "--runtime", "go", "--platform", runner_os, str(log)]
        assert m.main(args) == code, runner_os


def test_main_reports_every_skip_when_stdout_cannot_encode_the_test_id(tmp_path):
    # Windows runners write stdout as cp1252. Parametrized test IDs carry
    # Hangul jamo, and printing one used to raise UnicodeEncodeError and cut
    # the report after the first such ID.
    spec = tmp_path / "allow.toml"
    spec.write_text('[[entry]]\nruntime = "go"\ntest = "TestZ"\nkind = "harmless"\nreason = "r"\n', encoding="utf-8")
    log = tmp_path / "go.log"
    log.write_text("--- SKIP: TestA/ᄡ (0.00s)\n--- SKIP: TestB (0.00s)\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--spec", str(spec), "check", "--runtime", "go", "--platform", "windows", str(log)],
        env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
        capture_output=True,
        check=False,
    )
    out = result.stdout.decode("cp1252")
    assert result.returncode == 1, out + result.stderr.decode("cp1252", "replace")
    assert b"Traceback" not in result.stderr
    assert "TestA/" in out
    assert "TestB" in out


# --- pytest plugin ------------------------------------------------------------


def test_plugin_records_skips_but_not_xfail_or_tests_outside_the_repository(tmp_path):
    project = tmp_path / "repo"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_sample.py").write_text(
        textwrap.dedent(
            """\
            import pytest

            def test_pass():
                pass

            @pytest.mark.skip(reason="marker reason")
            def test_marker():
                pass

            @pytest.mark.parametrize("x", [1])
            def test_inline(x):
                pytest.skip("inline reason")

            @pytest.mark.xfail(reason="expected")
            def test_xfail():
                assert False
            """
        ),
        encoding="utf-8",
    )
    (project / "tests" / "test_module_skip.py").write_text(
        'import pytest\npytest.importorskip("no_such_module_for_skip_test")\n',
        encoding="utf-8",
    )
    log = tmp_path / "skips.jsonl"
    env = {
        **os.environ,
        "PYTEST_PLUGINS": "piper_plus_skip_log",
        "PYTHONPATH": str(PLUGIN_DIR),
        "PIPER_PLUS_SKIP_LOG": str(log),
        "GITHUB_WORKSPACE": str(project),
    }
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "tests"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    records = sorted((r["test"], r["reason"]) for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()))
    assert records[0] == ("tests/test_module_skip.py", records[0][1])
    assert "no_such_module_for_skip_test" in records[0][1]
    assert records[1:] == [
        ("tests/test_sample.py::test_inline[1]", "inline reason"),
        ("tests/test_sample.py::test_marker", "marker reason"),
    ]

    # The same run with the repository elsewhere records nothing.
    log.unlink()
    env["GITHUB_WORKSPACE"] = str(tmp_path / "elsewhere")
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "tests"],
        cwd=project,
        env=env,
        capture_output=True,
        check=False,
    )
    assert log.read_text(encoding="utf-8") == ""
