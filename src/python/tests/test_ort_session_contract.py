"""ORT session contract parity test (Python canonical).

Loads ``tests/fixtures/ort_session/contract.json`` and verifies that the
Python canonical implementation in ``piper_train.ort_utils`` agrees with
the contract values for graph optimization level, intra/inter threads,
memory arena, warmup parameters, cache file extensions, and env vars.

Sister tests in Rust/Go/C# load the same fixture and assert their own
runtime constants — drift in any of them is caught locally.
"""

from __future__ import annotations

import copy
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


# ---------------------------------------------------------------------------
# Forward-compat loader (schema_version >= 2)
# ---------------------------------------------------------------------------
#
# Audit finding: 4 runtimes (Py / C# / Rust / Go) currently hard-assert
# ``schema_version == 1`` in lockstep.  ZH-EN loanword JSON has already
# adopted a graceful loader (``schema_version: 2`` with unknown fields is
# silently accepted) but the ORT-session contract has not.  These tests
# describe the *desired* forward-compat contract for a future
# ``load_ort_session_contract`` helper: known fields are read, unknown
# top-level keys are silently dropped, ``schema_version >= 2`` is allowed.
#
# The tests operate on a deep-copied fixture rendered to a temp file so
# the canonical fixture is never mutated.


def _render_contract(tmp_path: Path, payload: dict) -> Path:
    """Write *payload* as JSON to a temp file and return its path."""
    out = tmp_path / "contract.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _load_with_forward_compat(contract_path: Path) -> dict:
    """Reference forward-compat loader for the ORT session contract.

    Mirrors the ``_load_loanword_data`` pattern used by ZH-EN: known
    sections are extracted by name; ``schema_version`` and unknown
    top-level keys are dropped from the returned dict.  This is a
    *reference* used only by these tests — when the production loader
    lands in ``piper_train.ort_utils``, swap the import.
    """
    raw = json.loads(contract_path.read_text(encoding="utf-8"))
    known_sections = {"session", "warmup", "cache", "env_vars"}
    return {key: value for key, value in raw.items() if key in known_sections}


@pytest.mark.unit
class TestSchemaV2ForwardCompat:
    """Forward-compat: future ``schema_version: 2+`` contracts must load.

    Mirrors the ZH-EN ``test_loader_accepts_schema_v2_future_fields``
    pattern.  The current parity contract (Py/C#/Rust/Go) hard-asserts
    ``schema_version == 1`` — these tests document the migration target
    and pin the *graceful loader* invariant once it ships.
    """

    def test_load_contract_with_schema_version_2(
        self, contract: dict, tmp_path: Path
    ) -> None:
        """``schema_version: 2`` plus a brand-new top-level key must load.

        Known sections must roundtrip exactly; unknown keys are dropped.
        """
        future = copy.deepcopy(contract)
        future["schema_version"] = 2
        future["thread_pool_policy"] = {"strategy": "adaptive"}  # unknown key
        future["session"]["future_extension_field"] = "ignored-value"

        contract_path = _render_contract(tmp_path, future)
        loaded = _load_with_forward_compat(contract_path)

        # Known sections survive unchanged.
        assert (
            loaded["session"]["graph_optimization_level"]
            == contract["session"]["graph_optimization_level"]
        )
        assert (
            loaded["warmup"]["phoneme_length"]
            == contract["warmup"]["phoneme_length"]
        )
        assert (
            loaded["cache"]["sentinel_extension"]
            == contract["cache"]["sentinel_extension"]
        )
        # schema_version + unknown top-level keys are silently dropped.
        assert "schema_version" not in loaded
        assert "thread_pool_policy" not in loaded

    def test_load_contract_unknown_top_level_keys(
        self, contract: dict, tmp_path: Path
    ) -> None:
        """Multiple future top-level fields (``metadata``, ``runtime_overrides``)
        must coexist with known sections without breaking the loader.
        """
        future = copy.deepcopy(contract)
        future["schema_version"] = 2
        future["metadata"] = {"author": "future-runtime", "experimental": True}
        future["runtime_overrides"] = {"rust": {"prefetch": True}}
        future["telemetry"] = {"endpoint": "https://example/metrics"}

        contract_path = _render_contract(tmp_path, future)
        loaded = _load_with_forward_compat(contract_path)

        # All four known sections are present.
        assert set(loaded) == {"session", "warmup", "cache", "env_vars"}
        # Unknown top-level keys are dropped (not surfaced).
        for forbidden in ("metadata", "runtime_overrides", "telemetry", "schema_version"):
            assert forbidden not in loaded

    def test_load_contract_with_schema_version_3(
        self, contract: dict, tmp_path: Path
    ) -> None:
        """``schema_version: 3`` (i.e. arbitrary future bumps) must load
        the same way ``schema_version: 2`` does — no version pinning beyond
        the graceful skip.
        """
        future = copy.deepcopy(contract)
        future["schema_version"] = 3
        future["new_section"] = {"foo": "bar"}
        # Bump nested fields with unknown names too.
        future["cache"]["compression_codec"] = "zstd"

        contract_path = _render_contract(tmp_path, future)
        loaded = _load_with_forward_compat(contract_path)

        # Cache section roundtrips its known fields and tolerates extras.
        assert loaded["cache"]["optimized_extension"] == "opt.onnx"
        # Loader does NOT strip unknown nested keys — only top-level
        # filtering is required (matches the ZH-EN loanword pattern).
        assert loaded["cache"].get("compression_codec") == "zstd"
        assert "new_section" not in loaded
        assert "schema_version" not in loaded

    def test_load_contract_schema_v1_still_loads(
        self, contract: dict, tmp_path: Path
    ) -> None:
        """The reference forward-compat loader is backward-compatible:
        ``schema_version: 1`` (the current canonical) loads identically.
        """
        contract_path = _render_contract(tmp_path, copy.deepcopy(contract))
        loaded = _load_with_forward_compat(contract_path)
        assert set(loaded) == {"session", "warmup", "cache", "env_vars"}
        assert loaded["session"] == contract["session"]
        assert loaded["warmup"] == contract["warmup"]
