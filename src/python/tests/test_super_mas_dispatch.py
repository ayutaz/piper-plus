"""Tests for the Super-MAS dispatcher in monotonic_align.

Verifies the dispatcher routes correctly between the Triton-GPU
``super_monotonic_align`` path (arXiv:2409.07704) and the Cython fallback
without needing an actual CUDA device or the upstream package installed.
The Cython fallback is also exercised end-to-end so the existing training
contract (Issue #197) is preserved.

The full GPU + Triton kernel path itself is intentionally not covered here —
that is a benchmark/integration test that requires both a CUDA device and
the optional dependency. The unit test scope is the dispatch logic.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap
from unittest import mock

import pytest


torch = pytest.importorskip("torch", reason="torch required for dispatch tests")

try:
    from piper_train.vits import monotonic_align
except ImportError:
    pytest.skip(
        "piper_train.vits.monotonic_align not available",
        allow_module_level=True,
    )


class TestDispatcherDecision:
    """Confirm `_use_super_mas` predicate routes correctly."""

    def test_cpu_tensor_always_falls_back(self):
        """CPU tensors must always go through the Cython path."""
        neg_cent = torch.randn(2, 16, 24)
        with mock.patch.object(monotonic_align, "_super_mas_fn", lambda *a, **k: None):
            assert monotonic_align._use_super_mas(neg_cent) is False

    def test_no_super_mas_package_falls_back(self):
        """When the optional package is not installed, _super_mas_fn is None."""
        neg_cent = torch.randn(2, 16, 24)
        with mock.patch.object(monotonic_align, "_super_mas_fn", None):
            assert monotonic_align._use_super_mas(neg_cent) is False

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available for GPU dispatch decision test",
    )
    def test_gpu_tensor_with_package_dispatches(self):
        """CUDA tensor + installed package => Super-MAS path selected."""
        neg_cent = torch.randn(2, 16, 24, device="cuda")
        with mock.patch.object(
            monotonic_align,
            "_super_mas_fn",
            lambda *a, **k: torch.zeros_like(a[0], dtype=torch.float32),
        ):
            assert monotonic_align._use_super_mas(neg_cent) is True


class TestCythonFallbackCorrectness:
    """End-to-end exercise of the dispatcher with Cython fallback only."""

    def test_dispatch_returns_cython_when_no_super_mas(self):
        """maximum_path produces a valid monotonic path via Cython."""
        batch_size, t_t, t_s = 2, 12, 18
        neg_cent = torch.randn(batch_size, t_t, t_s)
        attn_mask = torch.ones(batch_size, t_t, t_s)

        with mock.patch.object(monotonic_align, "_super_mas_fn", None):
            result = monotonic_align.maximum_path(neg_cent, attn_mask)

        assert result.shape == (batch_size, t_t, t_s)
        assert result.device == neg_cent.device
        # Binary path
        assert torch.all((result == 0) | (result == 1))
        # Monotonic: each row at most one 1
        for b in range(batch_size):
            row_sums = result[b].sum(dim=1)
            assert torch.all(row_sums <= 1)

    def test_disable_env_marker_class_attribute(self):
        """`_SUPER_MAS_DISABLED` is exposed for runtime introspection.

        Note: the value is read at import time, so this just verifies the
        attribute exists and is bool. Tests that need to flip it use mock.
        """
        assert hasattr(monotonic_align, "_SUPER_MAS_DISABLED")
        assert isinstance(monotonic_align._SUPER_MAS_DISABLED, bool)


class TestSuperMASPathContract:
    """Verify the Super-MAS dispatch helper itself with a mocked kernel.

    We mock the upstream kernel so the test runs on CPU without Triton or a
    GPU, but the wrapper logic (clone, dtype cast, device propagation) is
    exercised end-to-end.
    """

    def test_clone_preserves_input(self):
        """Wrapper must clone before calling upstream (upstream mutates input)."""
        neg_cent = torch.randn(1, 8, 10)
        snapshot = neg_cent.clone()

        def fake_kernel(value, attn_mask, dtype=torch.float32):
            # Simulate the upstream behaviour: mutate the input.
            value.fill_(0)
            return torch.ones(value.shape, dtype=dtype)

        with mock.patch.object(monotonic_align, "_super_mas_fn", fake_kernel):
            _ = monotonic_align._maximum_path_super_mas(
                neg_cent, torch.ones_like(neg_cent)
            )

        # Original tensor must remain unchanged.
        assert torch.allclose(neg_cent, snapshot)

    def test_dtype_propagated_back(self):
        """Output dtype must match input dtype (Cython contract parity)."""
        neg_cent = torch.randn(1, 4, 6, dtype=torch.float64)

        def fake_kernel(value, attn_mask, dtype=torch.float32):
            return torch.ones(value.shape, dtype=torch.float32)

        with mock.patch.object(monotonic_align, "_super_mas_fn", fake_kernel):
            out = monotonic_align._maximum_path_super_mas(
                neg_cent, torch.ones_like(neg_cent)
            )

        assert out.dtype == torch.float64

    def test_int32_mask_passed_to_kernel(self):
        """Wrapper must cast mask to int32 (Super-MAS contract)."""
        neg_cent = torch.randn(1, 4, 6)
        mask = torch.ones(1, 4, 6, dtype=torch.float32)
        captured: dict = {}

        def fake_kernel(value, attn_mask, dtype=torch.float32):
            captured["mask_dtype"] = attn_mask.dtype
            captured["value_dtype"] = value.dtype
            return torch.zeros(value.shape, dtype=dtype)

        with mock.patch.object(monotonic_align, "_super_mas_fn", fake_kernel):
            _ = monotonic_align._maximum_path_super_mas(neg_cent, mask)

        assert captured["mask_dtype"] == torch.int32
        assert captured["value_dtype"] == torch.float32


class TestPublicMaximumPathDispatch:
    """Confirm ``maximum_path()`` actually routes through the Super-MAS path
    when the predicate says so.

    The individual helpers are covered above, but the integration point — the
    ``if _use_super_mas(): return _maximum_path_super_mas(...)`` branch in the
    public ``maximum_path()`` — is its own contract. We exercise it by
    patching the predicate to return True and verifying the wrapper is the
    one that produced the result (rather than falling through to Cython).
    """

    def test_dispatcher_invokes_super_mas_branch_when_predicate_true(self):
        """When the predicate returns True, the wrapper is called once.

        We do not need a real CUDA tensor — the predicate is the gate, and
        we patch both it and the kernel. This isolates the wiring inside
        ``maximum_path()`` from CUDA / Triton availability.
        """
        neg_cent = torch.randn(1, 8, 12)
        mask = torch.ones(1, 8, 12)

        sentinel = torch.zeros(1, 8, 12, dtype=torch.float32)
        kernel_calls = []

        def fake_kernel(value, attn_mask, dtype=torch.float32):
            kernel_calls.append((value.shape, attn_mask.dtype))
            return sentinel

        with (
            mock.patch.object(monotonic_align, "_use_super_mas", return_value=True),
            mock.patch.object(monotonic_align, "_super_mas_fn", fake_kernel),
        ):
            out = monotonic_align.maximum_path(neg_cent, mask)

        # Kernel was reached exactly once via the dispatcher branch
        assert len(kernel_calls) == 1
        # Output dtype matches caller's neg_cent dtype (Cython contract parity)
        assert out.dtype == neg_cent.dtype
        # Shape preserved
        assert out.shape == neg_cent.shape

    def test_dispatcher_skips_super_mas_branch_when_predicate_false(self):
        """When the predicate returns False, the wrapper is never called."""
        neg_cent = torch.randn(1, 8, 12)
        mask = torch.ones(1, 8, 12)
        kernel_calls = []

        def fake_kernel(*args, **kwargs):
            kernel_calls.append(args)
            return torch.zeros_like(neg_cent)

        with (
            mock.patch.object(monotonic_align, "_use_super_mas", return_value=False),
            mock.patch.object(monotonic_align, "_super_mas_fn", fake_kernel),
        ):
            out = monotonic_align.maximum_path(neg_cent, mask)

        # Kernel was not reached — Cython branch handled it
        assert len(kernel_calls) == 0
        assert out.shape == neg_cent.shape


class TestEnvDisableImportTime:
    """Verify PIPER_DISABLE_SUPER_MAS=1 is honoured at import time.

    The toggle is module-level (read once on import), so we re-import in a
    fresh subprocess with the env var set. This is the only way to assert
    the contract — patching the live module would test the wrong thing.
    """

    def _run_import_check(self, env_value: str | None) -> dict:
        """Run a subprocess that imports the module and reports state.

        We inherit the *full* parent environment via ``os.environ.copy()`` so
        that platform-specific magic variables (Windows ``SystemRoot``, Linux
        ``LD_LIBRARY_PATH``, etc.) reach the child intact. A hand-built env
        was used in an earlier draft but it (a) risked overriding Windows'
        case-insensitive ``SystemRoot`` and (b) dropped the test session's
        ``sys.path`` injection set by ``tests/conftest.py``, leaving the
        subprocess unable to import ``piper_train`` outside an editable
        install. PYTHONPATH is then prepended explicitly so the import works
        regardless of how piper_train is installed.
        """
        code = textwrap.dedent("""
            import json
            from piper_train.vits import monotonic_align as m
            print(json.dumps({
                "disabled": m._SUPER_MAS_DISABLED,
                "fn_is_none": m._super_mas_fn is None,
            }))
        """)
        env = os.environ.copy()
        # Ensure src/python is on sys.path even if piper_train is not
        # editable-installed (conftest.py only runs inside pytest, not in a
        # fresh `python -c` subprocess).
        src_python = str(pathlib.Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = src_python + os.pathsep + env.get("PYTHONPATH", "")
        # Configure the toggle under test
        if env_value is None:
            env.pop("PIPER_DISABLE_SUPER_MAS", None)
        else:
            env["PIPER_DISABLE_SUPER_MAS"] = env_value

        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            check=False,
        )
        assert proc.returncode == 0, (
            f"subprocess failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
        import json

        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_env_unset_does_not_force_disable(self):
        """Without the env var, the disable flag is False."""
        state = self._run_import_check(env_value=None)
        assert state["disabled"] is False
        # _super_mas_fn may or may not be None (depends on whether the
        # optional package is installed) — we only assert the flag here.

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
    def test_env_truthy_disables_super_mas(self, value: str):
        """Truthy env values force ``_super_mas_fn = None`` at import."""
        state = self._run_import_check(env_value=value)
        assert state["disabled"] is True
        assert state["fn_is_none"] is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "anything-else"])
    def test_env_non_truthy_does_not_disable(self, value: str):
        """Non-truthy values leave the disable flag False."""
        state = self._run_import_check(env_value=value)
        assert state["disabled"] is False
