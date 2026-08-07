"""Monotonic Alignment Search (MAS) with optional Triton-GPU acceleration.

Dispatches to the Triton-GPU implementation provided by
``super_monotonic_align`` (Park et al., 2024 — https://arxiv.org/abs/2409.07704)
when both the package is installed and the input tensors are on CUDA.
Otherwise falls back to the original Cython implementation with adaptive
chunked processing (Issue #197).

Super-MAS reports 19-72x speedup on GPU vs the Cython baseline. The output is
algorithmically equivalent — the upstream README does not guarantee
bit-identical floats — and the kernel additionally fixes a ``max_neg_val``
edge case present in the original Glow-TTS implementation.

Opt-in install (training-only, GPU-only):

    pip install piper-train[super-mas]

Disable at runtime via env (forces Cython for debugging / reproducibility):

    PIPER_PLUS_DISABLE_SUPER_MAS=1

Runtime parity validation: the first few Super-MAS dispatches are checked
against the Cython reference; on mismatch the process permanently falls back
to Cython (see ``_validate_super_mas_parity``).
"""

import logging
import os

import numpy as np
import torch


_LOGGER = logging.getLogger(__name__)


try:
    from .core import maximum_path_c  # Cython or numba fallback
except ImportError:
    from .core import maximum_path_c  # noqa: F811

# Memory threshold for adaptive chunking (t_t * t_s)
# When matrix size exceeds this, use batch_size=1
_LARGE_MATRIX_THRESHOLD = 500000  # ~700x700

# Super-MAS (Triton-GPU) optional accelerator
# Env override is read at import time so process-wide settings are honoured
# without affecting subsequent calls; tests that mock the dispatcher can
# patch ``_super_mas_fn`` directly.
_SUPER_MAS_DISABLED = os.environ.get("PIPER_PLUS_DISABLE_SUPER_MAS", "").lower() in (
    "1",
    "true",
    "yes",
)
_super_mas_fn = None
if not _SUPER_MAS_DISABLED:
    try:
        from super_monotonic_align import (
            maximum_path as _super_mas_fn,  # type: ignore[import-not-found]
        )
    except ImportError:
        _super_mas_fn = None

# --- Super-MAS runtime parity validation -----------------------------------
# 2026-08 v8 incident: on py3.12 + a specific triton build the Super-MAS
# kernel ran without any error yet returned corrupt alignments, silently
# collapsing duration supervision (loss_dur ≈ 0.006) and pinning KL at its
# safety cap for an entire 80-epoch run. Environment-dependent silent
# breakage cannot be caught by unit tests on a healthy environment, so the
# first few *real* dispatches are validated at runtime against the Cython
# reference; on mismatch the process permanently falls back to Cython.
#
# The comparison metric is IoU over the alignment's '1' cells. Exact cell
# equality is too strict (equal-score ties may legally break differently
# between implementations), while reference-coverage alone would let an
# all-ones garbage path pass. IoU catches both all-ones and near-random
# corruption while tolerating benign tie differences.
_PARITY_CHECK_CALLS = 3
_PARITY_MIN_IOU = 0.90
_parity_checks_done = 0


def _use_super_mas(neg_cent: torch.Tensor) -> bool:
    """Decide whether to dispatch to Super-MAS for this batch."""
    if _super_mas_fn is None:
        return False
    if not neg_cent.is_cuda:
        return False
    return torch.cuda.is_available()


def maximum_path(neg_cent, mask):
    """Compute MAS (Monotonic Alignment Search).

    Dispatches to the Triton-GPU implementation when CUDA tensors are passed
    and ``super_monotonic_align`` is installed; otherwise falls back to the
    Cython implementation with adaptive chunked processing.

    Args:
        neg_cent: [batch, t_t, t_s] tensor
        mask: [batch, t_t, t_s] tensor

    Returns:
        Path tensor [batch, t_t, t_s] on the same device and dtype as
        ``neg_cent``.
    """
    if _use_super_mas(neg_cent):
        path = _maximum_path_super_mas(neg_cent, mask)
        if _parity_checks_done < _PARITY_CHECK_CALLS:
            path = _validate_super_mas_parity(path, neg_cent, mask)
        return path

    return _maximum_path_cython(neg_cent, mask)


def _maximum_path_cython(neg_cent, mask):
    """Cython reference path with adaptive chunked processing (Issue #197)."""
    device = neg_cent.device
    dtype = neg_cent.dtype
    batch_size, t_t, t_s = neg_cent.shape
    matrix_size = t_t * t_s

    # 大きな行列の場合は1つずつ処理
    if matrix_size > _LARGE_MATRIX_THRESHOLD:
        max_chunk = 1
    else:
        max_chunk = 10

    # バッチをチャンクに分割
    if batch_size > max_chunk:
        results = []
        for i in range(0, batch_size, max_chunk):
            chunk_end = min(i + max_chunk, batch_size)
            chunk_result = _maximum_path_core(
                neg_cent[i:chunk_end], mask[i:chunk_end], device, dtype
            )
            results.append(chunk_result)
        return torch.cat(results, dim=0)

    return _maximum_path_core(neg_cent, mask, device, dtype)


def _validate_super_mas_parity(path, neg_cent, mask):
    """Validate a Super-MAS path against the Cython reference at runtime.

    Called for the first ``_PARITY_CHECK_CALLS`` dispatches only (counter is
    module-global, i.e. per-process / per-DDP-rank). On IoU below
    ``_PARITY_MIN_IOU`` the Super-MAS kernel is treated as silently broken in
    this environment: it is permanently disabled for the rest of the process
    and the trusted Cython path is returned instead, so not even the failing
    batch trains on a corrupt alignment.
    """
    global _parity_checks_done, _super_mas_fn
    _parity_checks_done += 1

    reference = _maximum_path_cython(neg_cent, mask)
    # bf16 cannot represent integer counts > 256 exactly — compute in fp32.
    path_f = path.detach().to(torch.float32)
    ref_f = reference.detach().to(torch.float32)
    intersection = float((path_f * ref_f).sum())
    union = float(path_f.sum()) + float(ref_f.sum()) - intersection
    iou = intersection / union if union > 0 else 1.0

    if iou < _PARITY_MIN_IOU:
        _LOGGER.error(
            "Super-MAS parity check FAILED (IoU=%.4f < %.2f) on call %d/%d — "
            "the Triton kernel is returning corrupt alignments in this "
            "environment (known failure mode: silent breakage that collapses "
            "duration loss and diverges KL). Permanently falling back to the "
            "Cython implementation for this process.",
            iou,
            _PARITY_MIN_IOU,
            _parity_checks_done,
            _PARITY_CHECK_CALLS,
        )
        _super_mas_fn = None
        return reference

    _LOGGER.info(
        "Super-MAS parity check %d/%d passed (IoU=%.4f)",
        _parity_checks_done,
        _PARITY_CHECK_CALLS,
        iou,
    )
    return path


def _maximum_path_super_mas(neg_cent, mask):
    """Super-MAS Triton-GPU dispatch path.

    The upstream kernel mutates ``value`` in place, so we clone it to keep
    ``neg_cent`` immutable (matches the Cython contract used elsewhere in
    the training loop). Inputs are cast to float32 / int32 as required and
    the output is cast back to the caller's dtype.
    """
    value = neg_cent.detach().to(dtype=torch.float32).contiguous().clone()
    attn_mask = mask.detach().to(dtype=torch.int32).contiguous()
    path = _super_mas_fn(value, attn_mask, dtype=torch.float32)
    return path.to(dtype=neg_cent.dtype)


def _maximum_path_core(neg_cent, mask, device, dtype):
    """Core Cython implementation without chunking."""
    neg_cent_np = neg_cent.data.cpu().numpy().astype(np.float32)
    path = np.zeros(neg_cent_np.shape, dtype=np.int32)
    t_t_max = mask.sum(1)[:, 0].data.cpu().numpy().astype(np.int32)
    t_s_max = mask.sum(2)[:, 0].data.cpu().numpy().astype(np.int32)
    maximum_path_c(path, neg_cent_np, t_t_max, t_s_max)
    return torch.from_numpy(path).to(device=device, dtype=dtype)
