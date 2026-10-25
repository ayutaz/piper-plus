"""Tests for monotonic_align module with chunked processing.

These tests verify that monotonic_align.maximum_path handles large matrices
and inputs with more text tokens than frames without crashing.

Issue: https://github.com/ayutaz/piper-plus/issues/197 (the training SIGSEGV
on an 829-frame x 1068-token sample). Its cause was not memory pressure: with
more tokens than frames the Cython backtrack read value[-1, ...] at y == 0,
memory before the buffer, which segfaults on Linux/macOS when the buffer is
mmap'd. core.pyx now guards that read; see TestMoreTokensThanFrames.

Note: These tests require torch and piper_train to be installed.
They are skipped in CI environments without GPU/training dependencies.
"""

import subprocess
import sys

import pytest

# Skip entire module if torch is not available (e.g., in CI without training deps)
torch = pytest.importorskip("torch", reason="torch required for monotonic_align tests")

# Also skip if monotonic_align is not available (Cython extension)
try:
    from piper_train.vits import monotonic_align
except ImportError:
    pytest.skip(
        "piper_train.vits.monotonic_align not available", allow_module_level=True
    )

# Module-level so every test here is selected by a CI `-m` expression
# (conftest.py rejects tests with no unit / integration / benchmark marker).
pytestmark = [pytest.mark.unit, pytest.mark.training]


class TestMonotonicAlignChunking:
    """Test adaptive chunking for large matrices."""

    def test_large_matrix_subprocess(self):
        """The #197 crash case (batch=20, 829 frames x 1068 tokens).

        Run in a subprocess so that a regression is reported as a failed
        test instead of a segfault that ends the whole pytest session.
        """
        code = """
import torch
from piper_train.vits import monotonic_align
neg_cent = torch.randn(20, 829, 1068)
attn_mask = torch.ones(20, 829, 1068)
result = monotonic_align.maximum_path(neg_cent, attn_mask)
assert result.shape == (20, 829, 1068)
print("SUCCESS")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "SUCCESS" in result.stdout

    def test_normal_matrix_batch20(self):
        """Test that normal-sized matrices still work efficiently."""
        neg_cent = torch.randn(20, 100, 100)
        attn_mask = torch.ones(20, 100, 100)

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.shape == (20, 100, 100)

    def test_medium_matrix_batch10(self):
        """Test medium-sized matrices with batch=10."""
        neg_cent = torch.randn(10, 300, 400)
        attn_mask = torch.ones(10, 300, 400)

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.shape == (10, 300, 400)

    def test_chunking_triggers(self):
        """Test that chunking triggers for large batch with medium matrices."""
        # Just below threshold (400x400 = 160,000 < 500,000)
        # Should use max_chunk=10, so batch=15 should trigger chunking
        neg_cent = torch.randn(15, 400, 400)
        attn_mask = torch.ones(15, 400, 400)

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.shape == (15, 400, 400)

    def test_result_dtype_preserved(self):
        """Test that result dtype matches input dtype."""
        neg_cent = torch.randn(2, 50, 50, dtype=torch.float32)
        attn_mask = torch.ones(2, 50, 50)

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.dtype == torch.float32

    def test_result_device_preserved(self):
        """Test that result device matches input device."""
        neg_cent = torch.randn(2, 50, 50)
        attn_mask = torch.ones(2, 50, 50)

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.device == neg_cent.device

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
    def test_gpu_large_matrix(self):
        """Test large matrices on GPU."""
        neg_cent = torch.randn(20, 829, 1068).cuda()
        attn_mask = torch.ones(20, 829, 1068).cuda()

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.shape == (20, 829, 1068)
        assert result.device.type == "cuda"

    def test_path_is_valid(self):
        """Test that the returned path is a valid monotonic alignment."""
        batch_size, t_t, t_s = 2, 10, 15
        neg_cent = torch.randn(batch_size, t_t, t_s)
        attn_mask = torch.ones(batch_size, t_t, t_s)

        result = monotonic_align.maximum_path(neg_cent, attn_mask)

        # Path should be binary (0 or 1)
        assert torch.all((result == 0) | (result == 1))

        # Each row should have exactly one 1 (monotonic alignment)
        for b in range(batch_size):
            path = result[b]
            row_sums = path.sum(dim=1)
            # Each row should have at most one 1
            assert torch.all(row_sums <= 1)


class TestMoreTokensThanFrames:
    """More text tokens than frames (t_s > t_t): no monotonic path covers them.

    The backtrack then never reaches token 0, and before the fix it compared
    value[-1, ...] at the first frame, reading memory before the buffer. With
    buffers large enough to be mmap'd this segfaulted on Linux and macOS
    (batch 10 x 300 x 400 did in CI); Windows read the memory and passed.
    """

    @pytest.mark.parametrize("shape", [(10, 300, 400), (1, 829, 1068)])
    def test_does_not_read_before_the_buffer(self, shape):
        code = f"""
import torch
from piper_train.vits import monotonic_align
b, t_t, t_s = {shape}
path = monotonic_align.maximum_path(torch.randn(b, t_t, t_s), torch.ones(b, t_t, t_s))
assert path.shape == (b, t_t, t_s)
# The backtrack marks exactly one token per frame.
assert int(path.sum()) == b * t_t, int(path.sum())
print("SUCCESS")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"exit {result.returncode} (-11 / 139 = segfault): {result.stderr[-2000:]}"
        )
        assert "SUCCESS" in result.stdout
