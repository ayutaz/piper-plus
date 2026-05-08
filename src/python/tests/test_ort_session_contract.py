"""ORT session contract parity test (Python canonical).

Loads ``tests/fixtures/ort_session/contract.json`` and verifies that the
Python canonical implementation in ``piper_train.ort_utils`` agrees with
the contract values for graph optimization level, intra/inter threads,
memory arena, warmup parameters, cache file extensions, and env vars.

Sister tests in Rust/Go/C# load the same fixture and assert their own
runtime constants — drift in any of them is caught locally.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import onnxruntime
import pytest

from piper_train.ort_utils import (
    DEFAULT_WARMUP_RUNS,
    MAX_INTRA_THREADS,
    WARMUP_PHONEME_LENGTH,
    create_session_options,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/ort_session/contract.json"


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.unit
class TestSessionConstants:
    def test_max_intra_threads_matches_contract(self, contract: dict) -> None:
        assert MAX_INTRA_THREADS == contract["session"]["max_intra_threads"]

    def test_warmup_phoneme_length_matches_contract(self, contract: dict) -> None:
        assert WARMUP_PHONEME_LENGTH == contract["warmup"]["phoneme_length"]

    def test_default_warmup_runs_matches_contract(self, contract: dict) -> None:
        assert DEFAULT_WARMUP_RUNS == contract["warmup"]["default_runs"]

    def test_session_options_graph_optimization_level(self, contract: dict) -> None:
        opts = create_session_options(intra_op_threads=2)
        # Contract says ORT_ENABLE_ALL.
        assert contract["session"]["graph_optimization_level"] == "ORT_ENABLE_ALL"
        assert (
            opts.graph_optimization_level
            == onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )

    def test_session_options_execution_mode_sequential(self, contract: dict) -> None:
        opts = create_session_options(intra_op_threads=2)
        assert contract["session"]["execution_mode"] == "SEQUENTIAL"
        assert opts.execution_mode == onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    def test_session_options_inter_op_threads(self, contract: dict) -> None:
        opts = create_session_options(intra_op_threads=2, inter_op_threads=1)
        assert opts.inter_op_num_threads == contract["session"]["inter_op_threads"]

    def test_session_options_intra_threads_capped_to_max(self, contract: dict) -> None:
        # Asking for 100 must be capped to MAX_INTRA_THREADS via env var.
        env_save = os.environ.get("PIPER_INTRA_THREADS")
        os.environ["PIPER_INTRA_THREADS"] = "100"
        try:
            opts = create_session_options()
            assert opts.intra_op_num_threads == contract["session"]["max_intra_threads"]
        finally:
            if env_save is None:
                del os.environ["PIPER_INTRA_THREADS"]
            else:
                os.environ["PIPER_INTRA_THREADS"] = env_save

    def test_session_options_memory_arena_and_pattern_enabled(self, contract: dict) -> None:
        opts = create_session_options(intra_op_threads=2)
        assert contract["session"]["enable_cpu_mem_arena"] is True
        assert contract["session"]["enable_memory_pattern"] is True
        assert opts.enable_cpu_mem_arena is True
        assert opts.enable_mem_pattern is True


@pytest.mark.unit
class TestCacheConventions:
    def test_optimized_extension(self, contract: dict) -> None:
        assert contract["cache"]["optimized_extension"] == "opt.onnx"

    def test_sentinel_extension(self, contract: dict) -> None:
        assert contract["cache"]["sentinel_extension"] == "opt.onnx.ok"

    def test_sentinel_content(self, contract: dict) -> None:
        assert contract["cache"]["sentinel_content"] == "ok"

    def test_device_label_cpu(self, contract: dict) -> None:
        assert contract["cache"]["device_label_cpu"] == "cpu"

    def test_device_label_cuda_format(self, contract: dict) -> None:
        # "cuda{device_id}" — substitution token format
        assert "{device_id}" in contract["cache"]["device_label_cuda_format"]
        assert contract["cache"]["device_label_cuda_format"].startswith("cuda")


@pytest.mark.unit
class TestEnvVars:
    def test_disable_warmup_name(self, contract: dict) -> None:
        assert contract["env_vars"]["disable_warmup"] == "PIPER_DISABLE_WARMUP"

    def test_disable_cache_name(self, contract: dict) -> None:
        assert contract["env_vars"]["disable_cache"] == "PIPER_DISABLE_CACHE"

    def test_intra_threads_name(self, contract: dict) -> None:
        assert contract["env_vars"]["intra_threads"] == "PIPER_INTRA_THREADS"


@pytest.mark.unit
class TestWarmupTokens:
    def test_bos_token(self, contract: dict) -> None:
        assert contract["warmup"]["bos_token"] == 1

    def test_eos_token(self, contract: dict) -> None:
        assert contract["warmup"]["eos_token"] == 2

    def test_dummy_phoneme(self, contract: dict) -> None:
        assert contract["warmup"]["dummy_phoneme"] == 8

    def test_warmup_scales(self, contract: dict) -> None:
        assert contract["warmup"]["noise_scale"] == 0.667
        assert contract["warmup"]["length_scale"] == 1.0
        assert contract["warmup"]["noise_w"] == 0.8


@pytest.mark.unit
class TestFixtureMeta:
    def test_schema_version(self, contract: dict) -> None:
        assert contract["schema_version"] == 1

    def test_fixture_exists(self) -> None:
        assert FIXTURE_PATH.exists()
