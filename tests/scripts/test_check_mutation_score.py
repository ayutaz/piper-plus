"""Mutation testing must measure something and fail below its break score.

Regression focus: until 2026-10 every mutation-testing job was
continue-on-error and none had ever measured anything (mutmut unpinned with
a failing Cython build step, cargo-mutants finding 0 mutants through wrong
--file paths, Stryker rejecting its config). These tests pin the spec, the
workflow and the score gate so a run that tests nothing cannot pass.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import sys
import tomllib
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_mutation_score.py"
SPEC = REPO_ROOT / "docs" / "spec" / "mutation-testing.toml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mutation-testing.yml"
STRYKER_CONFIG = REPO_ROOT / "src" / "csharp" / "stryker-config.json"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("check_mutation_score", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def targets():
    return tomllib.loads(SPEC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


# --- spec ---------------------------------------------------------------------


def test_every_runtime_has_targets(targets):
    for runtime in ("python", "rust", "csharp"):
        assert targets[runtime], runtime


def test_python_targets_and_tests_exist(targets):
    for t in targets["python"]:
        assert (REPO_ROOT / t["target"]).is_file(), t["target"]
        assert t["tests"], t["module"]
        for test in t["tests"]:
            assert (REPO_ROOT / test).is_file(), test


def test_rust_files_exist(targets):
    for t in targets["rust"]:
        assert (REPO_ROOT / "src" / "rust" / t["file"]).is_file(), t["file"]
        for name in re.findall(r"--test (\S+)", t["cargo_test_args"]):
            crate_dir = REPO_ROOT / "src" / "rust" / t["file"].split("/")[0]
            assert (crate_dir / "tests" / f"{name}.rs").is_file(), name


def test_csharp_config_and_mutated_files_exist(targets):
    for t in targets["csharp"]:
        config = json.loads((REPO_ROOT / t["config"]).read_text(encoding="utf-8"))["stryker-config"]
        project_dir = (REPO_ROOT / t["config"]).parent / Path(config["project"]).parent
        for path in config["mutate"]:
            assert (project_dir / path).is_file(), path


def test_module_names_are_unique(targets):
    for runtime in ("python", "rust", "csharp"):
        names = [t["module"] for t in targets[runtime]]
        assert len(names) == len(set(names)), runtime


def test_break_sits_just_below_the_measured_score(targets):
    """`break` comes from a measurement: not above it, and at most 5 points below."""
    for runtime in ("python", "rust", "csharp"):
        for t in targets[runtime]:
            m = re.fullmatch(r"(\d+)/(\d+) = (\d+\.\d)%", t["measured"])
            assert m, (runtime, t["module"], t["measured"])
            detected, total, pct = int(m[1]), int(m[2]), float(m[3])
            assert round(100 * detected / total, 1) == pct, (runtime, t["module"])
            assert pct - 5 <= t["break"] <= pct, (runtime, t["module"], t["break"], pct)


def test_stryker_break_matches_the_spec(targets):
    config = json.loads(STRYKER_CONFIG.read_text(encoding="utf-8"))["stryker-config"]
    assert config["thresholds"]["break"] == targets["csharp"][0]["break"]


def test_stryker_uses_the_microsoft_testing_platform_runner():
    """The test projects are xunit v3 executables. Under the default vstest
    runner Stryker could not activate mutants in them and reported 4.2%
    (1 killed, 461 survived); with mtp the same files score 90.2%."""
    config = json.loads(STRYKER_CONFIG.read_text(encoding="utf-8"))["stryker-config"]
    assert config["test-runner"] == "mtp"


def test_stryker_config_has_no_unknown_keys():
    """Stryker 5 rejects keys it does not know, so `_comment` keys stop the run."""
    config = json.loads(STRYKER_CONFIG.read_text(encoding="utf-8"))["stryker-config"]
    assert not [k for k in config if k.startswith("_")]


# --- workflow -----------------------------------------------------------------


def _run(job) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_no_job_or_step_hides_failure(workflow):
    for job_id, job in workflow["jobs"].items():
        assert "continue-on-error" not in job, job_id
        for step in job["steps"]:
            if "continue-on-error" in step:
                assert step.get("uses", "").startswith("actions/cache@"), (job_id, step.get("name"))


def test_matrices_come_from_the_spec(workflow):
    jobs = workflow["jobs"]
    assert "check_mutation_score.py matrix" in _run(jobs["plan"])
    for runtime in ("python", "rust", "csharp"):
        assert jobs[runtime]["strategy"]["matrix"] == f"${{{{ fromJSON(needs.plan.outputs.{runtime}) }}}}"
        assert f"check_mutation_score.py score {runtime}" in _run(jobs[runtime])


def test_tool_versions_are_pinned(workflow):
    jobs = workflow["jobs"]
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    locked = re.search(r'name = "mutmut"\nversion = "([^"]+)"', lock)[1]
    assert f"'mutmut=={locked}'" in _run(jobs["python"])
    assert re.search(r"cargo install --locked cargo-mutants@\d+\.\d+\.\d+", _run(jobs["rust"]))
    assert re.search(r"dotnet-stryker --version \d+\.\d+\.\d+", _run(jobs["csharp"]))


def test_stryker_is_given_its_config_file(workflow):
    run = _run(workflow["jobs"]["csharp"])
    assert "dotnet stryker --config-file" in run
    assert not re.search(r"dotnet stryker -c\b", run)


def test_matrix_output_is_valid_json(gate, targets):
    for runtime in ("python", "rust", "csharp"):
        data = json.loads(json.dumps({"include": gate.load_targets()[runtime]}))
        assert [t["module"] for t in data["include"]] == [t["module"] for t in targets[runtime]]


# --- score gate ---------------------------------------------------------------


SPEC_TEXT = """
[[python]]
module = "m"
break = 50

[[rust]]
module = "r"
break = 50

[[csharp]]
module = "c"
break = 50
"""


@pytest.fixture
def spec(tmp_path):
    p = tmp_path / "spec.toml"
    p.write_text(SPEC_TEXT, encoding="utf-8")
    return p


def _mutmut_cache(path: Path, statuses: dict[str, int]) -> Path:
    con = sqlite3.connect(path)
    con.execute("create table Mutant (id integer primary key, status text)")
    for status, n in statuses.items():
        con.executemany("insert into Mutant (status) values (?)", [(status,)] * n)
    con.commit()
    con.close()
    return path


def test_mutmut_counts_timeouts_as_detected(gate, spec, tmp_path):
    cache = _mutmut_cache(tmp_path / "c", {"ok_killed": 4, "bad_timeout": 1, "bad_survived": 4, "ok_suspicious": 1})
    assert gate.check_score("python", "m", cache, spec) == []


def test_mutmut_below_break_fails(gate, spec, tmp_path):
    cache = _mutmut_cache(tmp_path / "c", {"ok_killed": 4, "bad_survived": 6})
    problems = gate.check_score("python", "m", cache, spec)
    assert len(problems) == 1 and "below break 50" in problems[0]


def test_mutmut_untested_mutants_fail(gate, spec, tmp_path):
    cache = _mutmut_cache(tmp_path / "c", {"ok_killed": 10, "untested": 1})
    assert any("never tested" in p for p in gate.check_score("python", "m", cache, spec))


def test_mutmut_empty_cache_fails(gate, spec, tmp_path):
    cache = _mutmut_cache(tmp_path / "c", {})
    assert any("no mutants" in p for p in gate.check_score("python", "m", cache, spec))


def _outcomes(path: Path, **counts) -> Path:
    data = {"total_mutants": 0, "caught": 0, "missed": 0, "timeout": 0, "unviable": 0} | counts
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_cargo_mutants_leaves_unviable_out(gate, spec, tmp_path):
    out = _outcomes(tmp_path / "o.json", total_mutants=12, caught=4, timeout=1, missed=5, unviable=2)
    assert gate.check_score("rust", "r", out, spec) == []


def test_cargo_mutants_incomplete_run_fails(gate, spec, tmp_path):
    out = _outcomes(tmp_path / "o.json", total_mutants=20, caught=9, missed=1)
    assert any("only 10 of 20" in p for p in gate.check_score("rust", "r", out, spec))


def test_cargo_mutants_zero_mutants_fails(gate, spec, tmp_path):
    out = _outcomes(tmp_path / "o.json")
    assert any("no mutants" in p for p in gate.check_score("rust", "r", out, spec))


def _report(path: Path, statuses: list[str]) -> Path:
    data = {"files": {"A.cs": {"mutants": [{"status": s} for s in statuses]}}}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_stryker_counts_no_coverage_as_undetected(gate, spec, tmp_path):
    report = _report(tmp_path / "r.json", ["Killed"] * 5 + ["Survived"] * 4 + ["NoCoverage"] * 2 + ["CompileError"] * 9)
    problems = gate.check_score("csharp", "c", report, spec)
    assert len(problems) == 1 and "45.5%" in problems[0]


def test_stryker_unfinished_mutants_fail(gate, spec, tmp_path):
    report = _report(tmp_path / "r.json", ["Killed"] * 9 + ["Pending"])
    assert any("Pending" in p for p in gate.check_score("csharp", "c", report, spec))


def test_unknown_module_is_an_error(gate, spec, tmp_path):
    with pytest.raises(SystemExit):
        gate.check_score("python", "nope", tmp_path / "x", spec)


def test_main_exit_codes(gate, spec, tmp_path):
    good = _mutmut_cache(tmp_path / "good", {"ok_killed": 9, "bad_survived": 1})
    bad = _mutmut_cache(tmp_path / "bad", {"ok_killed": 1, "bad_survived": 9})
    assert gate.main(["--spec", str(spec), "score", "python", "m", str(good)]) == 0
    assert gate.main(["--spec", str(spec), "score", "python", "m", str(bad)]) == 1
