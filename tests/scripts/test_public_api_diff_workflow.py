"""Contract tests for .github/workflows/public-api-diff.yml.

All three jobs stayed green while measuring nothing: the Rust listing never
ran (no nightly toolchain, hidden by ``continue-on-error``), gorelease failed
on the ``replace``d phonemize module (hidden by ``|| true``), and the C#
PublicAPI baseline was empty with RS0016/RS0017 in NoWarn. These tests keep a
tool failure failing the job and keep the C# baseline enforced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "public-api-diff.yml"
PROPS = REPO_ROOT / "src" / "csharp" / "Directory.Build.props"
CORE = REPO_ROOT / "src" / "csharp" / "PiperPlus.Core"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict) -> list[str]:
    return [s["run"] for s in job["steps"] if "run" in s]


def test_no_continue_on_error_or_swallowed_failures(workflow):
    for name, job in workflow["jobs"].items():
        assert "continue-on-error" not in job, name
        for step in job["steps"]:
            assert "continue-on-error" not in step, (name, step.get("name"))
        for run in _runs(job):
            # `|| true` / `|| echo` after a tool call hides its failure.
            # The only allowed `|| true` guards grep -v, whose "no match"
            # exit is not a failure.
            for line in run.splitlines():
                if re.search(r"\|\|\s*(true|echo)\b", line):
                    assert "grep -v" in line, (name, line.strip())


def test_tools_are_pinned(workflow):
    rust = workflow["jobs"]["rust-public-api"]["env"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", rust["CARGO_PUBLIC_API_VERSION"])
    assert re.fullmatch(r"nightly-\d{4}-\d{2}-\d{2}", rust["RUSTDOC_NIGHTLY"])
    go = workflow["jobs"]["go-public-api"]["env"]
    assert re.fullmatch(r"v0\.0\.0-\d{14}-[0-9a-f]{12}", go["APIDIFF_VERSION"])
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "@latest" not in text
    assert "gorelease" not in "\n".join(_runs(workflow["jobs"]["go-public-api"]))


def test_rust_listing_uses_the_pinned_nightly_and_rejects_empty_output(workflow):
    run = "\n".join(_runs(workflow["jobs"]["rust-public-api"]))
    assert 'rustup toolchain install "$RUSTDOC_NIGHTLY"' in run
    assert run.count('cargo "+$RUSTDOC_NIGHTLY" public-api') == 2
    assert "test -s /tmp/api-current.txt" in run
    assert "test -s /tmp/api-base.txt" in run


def test_go_compares_every_module_on_its_own(workflow):
    job = workflow["jobs"]["go-public-api"]
    step = next(s for s in job["steps"] if s.get("name") == "Compare module APIs to the merge base")
    assert step["env"]["GOWORK"] == "off"
    modules = sorted(p.parent.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "src" / "go").rglob("go.mod"))
    for module_dir in modules:
        assert module_dir in step["run"], module_dir


def test_csharp_publicapi_analyzer_is_enforced_for_core():
    props = PROPS.read_text(encoding="utf-8")
    # The global NoWarn must not silence the PublicAPI rules ...
    global_nowarn = re.search(r"<NoWarn>\$\(NoWarn\);CS1573;[^<]*</NoWarn>", props)
    assert global_nowarn, "global NoWarn not found"
    for rule in ("RS0016", "RS0017", "RS0037"):
        assert rule not in global_nowarn.group(0), rule
    # ... they are silenced only where no PublicAPI file exists.
    assert "<PropertyGroup Condition=\"!Exists('$(MSBuildProjectDirectory)\\PublicAPI.Shipped.txt')\">" in props
    assert "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>" in props


def test_csharp_shipped_baseline_is_filled():
    shipped = (CORE / "PublicAPI.Shipped.txt").read_text(encoding="utf-8").splitlines()
    assert shipped[0] == "#nullable enable"
    entries = [line for line in shipped[1:] if line.strip()]
    # csharp-v0.5.1 shipped several hundred public symbols; an empty file
    # means the analyzer has nothing to compare against.
    assert len(entries) > 100
    assert any(line.startswith("PiperPlus.Core.") for line in entries)
