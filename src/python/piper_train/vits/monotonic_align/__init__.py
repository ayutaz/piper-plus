import numpy as np
import torch

try:
    from .core import maximum_path_c  # Cython or numba fallback
except ImportError:
    from .core import maximum_path_c  # noqa: F811

# Memory threshold for adaptive chunking (t_t * t_s)
# When matrix size exceeds this, use batch_size=1
_LARGE_MATRIX_THRESHOLD = 500000  # ~700x700


def maximum_path(neg_cent, mask):
    """Cython optimized version with adaptive chunked processing.

    Large batches or large matrices are automatically split into smaller
    chunks to avoid memory/stack overflow in the Cython implementation.

    Args:
        neg_cent: [batch, t_t, t_s] tensor
        mask: [batch, t_t, t_s] tensor

    Returns:
        Path tensor [batch, t_t, t_s]
    """
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
                neg_cent[i:chunk_end],
                mask[i:chunk_end],
                device,
                dtype
            )
            results.append(chunk_result)
        return torch.cat(results, dim=0)

    return _maximum_path_core(neg_cent, mask, device, dtype)


def _maximum_path_core(neg_cent, mask, device, dtype):
    """Core implementation without chunking."""
    neg_cent_np = neg_cent.data.cpu().numpy().astype(np.float32)
    path = np.zeros(neg_cent_np.shape, dtype=np.int32)
    t_t_max = mask.sum(1)[:, 0].data.cpu().numpy().astype(np.int32)
    t_s_max = mask.sum(2)[:, 0].data.cpu().numpy().astype(np.int32)
    maximum_path_c(path, neg_cent_np, t_t_max, t_s_max)
    return torch.from_numpy(path).to(device=device, dtype=dtype)
