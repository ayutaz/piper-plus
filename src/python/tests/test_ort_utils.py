"""Tests for ONNX Runtime session utilities (ort_utils.py).

Verifies that create_session_options() produces settings aligned with
the C#/Rust engine implementations and that get_providers() returns
the correct execution providers for each device type.
"""

from unittest.mock import patch

import onnxruntime
import pytest

from piper_train.ort_utils import (
    MAX_INTRA_THREADS,
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

    def test_intra_op_threads_capped_at_max(self):
        """intra_op_num_threads は MAX_INTRA_THREADS (4) を超えない."""
        opts = create_session_options()
        assert opts.intra_op_num_threads <= MAX_INTRA_THREADS

    def test_intra_op_threads_at_least_one(self):
        opts = create_session_options()
        assert opts.intra_op_num_threads >= 1

    @patch("os.cpu_count", return_value=16)
    def test_intra_op_threads_16_cores(self, _mock):
        """16 コア環境: min(16 // 2, 4) = 4."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    @patch("os.cpu_count", return_value=4)
    def test_intra_op_threads_4_cores(self, _mock):
        """4 コア環境: min(4 // 2, 4) = 2."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 2

    @patch("os.cpu_count", return_value=2)
    def test_intra_op_threads_2_cores(self, _mock):
        """2 コア環境: min(2 // 2, 4) = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    @patch("os.cpu_count", return_value=None)
    def test_intra_op_threads_unknown_cores(self, _mock):
        """os.cpu_count() が None: フォールバック 2 → min(1, 4) = 1."""
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
