"""Tests for ONNX Runtime session utilities (ort_utils.py).

Verifies that create_session_options() produces settings aligned with
the C#/Rust engine implementations and that get_providers() returns
the correct execution providers for each device type.
"""

from unittest.mock import patch

import onnxruntime
import pytest

from piper_train.ort_utils import (
    _get_logical_core_count,
    create_session_options,
    get_providers,
)


@pytest.mark.unit
class TestCreateSessionOptions:
    """create_session_options() の設定値テスト."""

    def test_graph_optimization_level(self):
        opts = create_session_options()
        assert (
            opts.graph_optimization_level
            == onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )

    def test_execution_mode_sequential(self):
        opts = create_session_options()
        assert opts.execution_mode == onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    def test_inter_op_threads_is_one(self):
        opts = create_session_options()
        assert opts.inter_op_num_threads == 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=128)
    def test_intra_op_threads_capped_at_max(self, _mock):
        """128 コア環境: intra_op は上限 4 を超えない."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    def test_intra_op_threads_at_least_one(self):
        opts = create_session_options()
        assert opts.intra_op_num_threads >= 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=16)
    def test_intra_op_threads_16_cores(self, _mock):
        """16 コア環境: min(16 // 2, 4) = 4."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=8)
    def test_intra_op_threads_8_cores(self, _mock):
        """8 コア環境: min(8 // 2, 4) = 4 — 上限に到達."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=4)
    def test_intra_op_threads_4_cores(self, _mock):
        """4 コア環境: min(4 // 2, 4) = 2."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 2

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=3)
    def test_intra_op_threads_3_cores(self, _mock):
        """3 コア (奇数): min(3 // 2, 4) = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=2)
    def test_intra_op_threads_2_cores(self, _mock):
        """2 コア環境: min(2 // 2, 4) = min(1, 4) = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=1)
    def test_intra_op_threads_1_core(self, _mock):
        """Docker --cpus=1: 1 // 2 = 0 → 0 or 1 = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    def test_memory_arena_enabled(self):
        opts = create_session_options()
        assert opts.enable_cpu_mem_arena is True

    def test_memory_pattern_enabled(self):
        opts = create_session_options()
        assert opts.enable_mem_pattern is True

    def test_memory_reuse_enabled(self):
        opts = create_session_options()
        assert opts.enable_mem_reuse is True

    def test_returns_session_options_instance(self):
        opts = create_session_options()
        assert isinstance(opts, onnxruntime.SessionOptions)

    def test_dynamic_block_base(self):
        opts = create_session_options()
        assert opts.get_session_config_entry("session.dynamic_block_base") == "4"

    def test_returns_new_instance_each_call(self):
        """毎回新しい SessionOptions オブジェクトを返す."""
        opts_a = create_session_options()
        opts_b = create_session_options()
        assert opts_a is not opts_b


@pytest.mark.unit
class TestCreateSessionOptionsParams:
    """create_session_options() の引数テスト."""

    def test_intra_op_threads_override_1(self):
        """intra_op_threads=1 が反映される."""
        opts = create_session_options(intra_op_threads=1)
        assert opts.intra_op_num_threads == 1

    def test_intra_op_threads_override_2(self):
        """intra_op_threads=2 が反映される."""
        opts = create_session_options(intra_op_threads=2)
        assert opts.intra_op_num_threads == 2

    def test_inter_op_threads_override(self):
        """inter_op_threads=2 が反映される."""
        opts = create_session_options(inter_op_threads=2)
        assert opts.inter_op_num_threads == 2


@pytest.mark.unit
class TestPiperIntraThreadsEnv:
    """PIPER_INTRA_THREADS 環境変数オーバーライドのテスト."""

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "2"})
    def test_env_overrides_auto_detection(self):
        """環境変数が自動検出より優先される."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 2

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "3"})
    def test_env_overrides_explicit_arg(self):
        """環境変数が引数 intra_op_threads より優先される."""
        opts = create_session_options(intra_op_threads=1)
        assert opts.intra_op_num_threads == 3


@pytest.mark.unit
class TestGetLogicalCoreCount:
    """_get_logical_core_count() のテスト."""

    @patch("os.sched_getaffinity", create=True, return_value={0, 1, 2, 3})
    def test_uses_sched_getaffinity(self, _mock):
        """sched_getaffinity が利用可能ならその結果を返す."""
        assert _get_logical_core_count() == 4

    @patch("os.sched_getaffinity", create=True, side_effect=AttributeError)
    @patch("os.cpu_count", return_value=8)
    def test_fallback_to_cpu_count(self, _mock_cpu, _mock_affinity):
        """sched_getaffinity が AttributeError → os.cpu_count() にフォールバック."""
        assert _get_logical_core_count() == 8

    @patch("os.sched_getaffinity", create=True, side_effect=AttributeError)
    @patch("os.cpu_count", return_value=None)
    def test_fallback_to_default_when_cpu_count_none(self, _mock_cpu, _mock_affinity):
        """os.cpu_count() が None → デフォルト 2."""
        assert _get_logical_core_count() == 2


@pytest.mark.unit
class TestGetProviders:
    """get_providers() のデバイス別テスト."""

    def test_cpu_provider(self):
        providers = get_providers("cpu")
        assert providers == ["CPUExecutionProvider"]

    def test_gpu_provider(self):
        providers = get_providers("gpu")
        assert "CUDAExecutionProvider" in providers
        assert "CPUExecutionProvider" in providers
        assert providers.index("CUDAExecutionProvider") < providers.index(
            "CPUExecutionProvider"
        )

    def test_auto_provider(self):
        providers = get_providers("auto")
        assert "CUDAExecutionProvider" in providers
        assert "CPUExecutionProvider" in providers

    def test_default_is_cpu(self):
        providers = get_providers()
        assert providers == ["CPUExecutionProvider"]
