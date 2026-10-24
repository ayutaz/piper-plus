"""Prevent ONNX regressions from becoming unexecuted or advisory PR checks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_contract_job_runs_on_all_dev_prs_with_both_runtimes():
    ci = workflow("ci.yml")
    assert "dev" in ci["on"]["pull_request"]["branches"]
    assert not ci["on"]["pull_request"].get("paths")
    job = ci["jobs"]["wasm-onnx-contract"]
    assert "if" not in job
    assert job.get("continue-on-error", "false") == "false"
    assert job["strategy"]["fail-fast"] == "false"
    assert set(job["strategy"]["matrix"]["ort"]) == {"1.22.0", "1.30.0"}
    commands = "\n".join(s.get("run", "") for s in job["steps"])
    assert "npm run test:onnx-inputs" in commands
    assert "test_wasm_onnx_ci_contract.py" in commands
    assert all(s.get("continue-on-error", "false") == "false" for s in job["steps"])


@pytest.mark.parametrize(
    "conclusion", ["success", "failure", "cancelled", "skipped", "timed_out"]
)
def test_required_gate_rejects_every_non_success_contract_result(conclusion):
    gate = workflow("ci.yml")["jobs"]["ci-required"]
    assert "wasm-onnx-contract" in gate["needs"]
    step = next(s for s in gate["steps"] if "check_ci_required.py" in s.get("run", ""))
    assert step["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    assert step.get("continue-on-error", "false") == "false"
    always_run = step["run"].split("--always-run ", 1)[1].split()[0]
    assert "wasm-onnx-contract" in always_run.split(",")
    needs = {name: {"result": "success"} for name in gate["needs"]}
    needs["wasm-onnx-contract"] = {"result": conclusion}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_ci_required.py"), "--always-run", always_run],
        env={**os.environ, "NEEDS": json.dumps(needs)},
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) == (conclusion == "success")


def test_public_model_browser_test_is_aggregated_and_runs_on_demo_changes():
    ci = workflow("ci.yml")
    assert "npm-package-tests" in ci["jobs"]["ci-required"]["needs"]
    steps = ci["jobs"]["npm-package-tests"]["steps"]
    browser = next(s for s in steps if "npm run test:browser" in s.get("run", ""))
    assert browser.get("continue-on-error", "false") == "false"
    filters = next(
        s["with"]["filters"]
        for s in ci["jobs"]["changes"]["steps"]
        if "with" in s and "filters" in s["with"]
    )
    assert "deploy-webassembly-demo.yml" in filters


def test_regressions_are_registered_in_package_and_publish_validation():
    package = json.loads(
        (ROOT / "src/wasm/openjtalk-web/package.json").read_text(encoding="utf-8")
    )
    for filename in ["test-onnx-input-contract.js", "test-piper-plus-onnx-inputs.js"]:
        assert filename in package["scripts"]["test:onnx-inputs"]
    assert "test-onnx-input-contract.js" in package["scripts"]["test:npm-package:all"]
    for filename in ["test-webassembly.yml", "npm-publish.yml"]:
        text = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
        assert "npm run test:onnx-inputs" in text


def test_deploy_verifies_real_synthesis_after_asset_checks():
    steps = workflow("deploy-webassembly-demo.yml")["jobs"]["deploy"]["steps"]
    probe = next(s for s in steps if "npm run probe:demo" in s.get("run", ""))
    assert "steps.deployment.outputs.page_url" in probe["env"]["PIPER_PLUS_DEMO_URL"]
    assert probe.get("continue-on-error", "false") == "false"
