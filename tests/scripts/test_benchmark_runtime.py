"""Tests for scripts/benchmark_runtime.py and the multi-runtime-rtf workflow.

The wasm cell pointed at ``bin/piper-plus.js``, which does not exist, and the
benchmark step ended in ``|| echo "::warning::..."``: every wasm run failed
(6 of 6 measured) and every one was green. The Node bin
(``bin/piper-cli.js``) has no G2P and reads phoneme_ids JSONL only, so the
harness phonemizes the text for that runtime and pipes the ids.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "benchmark_runtime.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "multi-runtime-rtf.yml"
MODEL = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
CONFIG = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("benchmark_runtime", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_runtime"] = module
    spec.loader.exec_module(module)
    return module


bench = _load_module()


def test_wasm_cell_pipes_phoneme_ids_on_stdin(tmp_path):
    payload = json.dumps({"phoneme_ids": [1, 8, 2], "language_id": 1})
    argv, stdin = bench._build_cmd(
        ["node", "bin/piper-cli.js"],
        "wasm",
        "model.onnx",
        "model.onnx.json",
        tmp_path / "out.wav",
        payload,
    )
    assert argv == [
        "node",
        "bin/piper-cli.js",
        "--model",
        "model.onnx",
        "--config",
        "model.onnx.json",
        "--output-file",
        str(tmp_path / "out.wav"),
        "--json-input",
    ]
    assert stdin == payload


def test_text_runtimes_still_receive_text(tmp_path):
    argv, stdin = bench._build_cmd(
        ["piper-plus-cli"], "rust", "m.onnx", "m.json", tmp_path / "o.wav", "Hi."
    )
    assert argv[-2:] == ["--text", "Hi."]
    assert stdin is None


def test_jsonl_runtime_requires_config():
    with pytest.raises(SystemExit, match="--config"):
        bench._phoneme_jsonl(str(MODEL), None, "Hello.")


def test_phoneme_jsonl_reads_the_text_as_english():
    pytest.importorskip("piper_plus")
    line = json.loads(bench._phoneme_jsonl(str(MODEL), str(CONFIG), "Hello there."))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert line["language_id"] == config["language_id_map"]["en"]
    ids = line["phoneme_ids"]
    bos, eos = config["phoneme_id_map"]["^"][0], config["phoneme_id_map"]["$"][0]
    assert ids[0] == bos and ids[-1] == eos
    assert len(ids) > 10


def test_phoneme_jsonl_joins_every_sentence():
    """The Node bin writes each JSONL line to --output-file, so the last line
    would overwrite the others: one line carries every sentence."""
    pytest.importorskip("piper_plus")
    one = json.loads(bench._phoneme_jsonl(str(MODEL), str(CONFIG), "Hello there."))
    two = json.loads(
        bench._phoneme_jsonl(str(MODEL), str(CONFIG), "Hello there. Hello there.")
    )
    assert len(two["phoneme_ids"]) == 2 * len(one["phoneme_ids"])


def test_result_records_whether_g2p_is_timed():
    assert bench.RUNTIME_PROFILES["wasm"]["g2p_in_timing"] is False
    for runtime in ("python", "rust", "go", "csharp", "cpp"):
        assert bench.RUNTIME_PROFILES[runtime]["g2p_in_timing"] is True


# ---------------------------------------------------------------------------
# Workflow contract
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _cli_commands(job: dict) -> dict[str, str]:
    step = next(s for s in job["steps"] if s.get("id") == "cli")
    return dict(re.findall(r"^\s*(\w+)\)\s*\n\s*.*?echo \"cmd=([^\"]+)\"", step["run"], re.M | re.S))


def test_every_cell_command_points_at_a_file_that_exists(workflow):
    commands = _cli_commands(workflow["jobs"]["benchmark"])
    assert set(commands) == set(bench.RUNTIME_PROFILES)
    wasm = shlex.split(commands["wasm"])
    assert wasm[0] == "node"
    assert (REPO_ROOT / wasm[1]).is_file(), wasm[1]


def test_a_failed_cell_fails_the_job(workflow):
    """Regressions stay warn-only until the baseline is calibrated, but a
    cell that cannot run at all is a broken harness and must be red."""
    job = workflow["jobs"]["benchmark"]
    assert "continue-on-error" not in job
    for step in job["steps"]:
        assert "continue-on-error" not in step, step.get("name")
    # One step per text length; each must fail on its own.
    runs = {
        s["name"]: s["run"]
        for s in job["steps"]
        if s.get("name", "").startswith("Run benchmark")
    }
    assert sorted(runs) == [
        "Run benchmark (long)",
        "Run benchmark (medium)",
        "Run benchmark (short)",
    ]
    for name, run in runs.items():
        text = name.split("(")[1].rstrip(")")
        assert f"--text-key {text} " in run, name
        assert "|| echo" not in run, name
        assert "|| true" not in run, name
