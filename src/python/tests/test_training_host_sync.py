"""学習 step の host 同期を増やさないための検査。

``self.log`` は Python の数値を ``torch.tensor(value, device=self.device)`` で
GPU テンソルにする。これは pageable memory からの host→device コピーで、それまで
に積んだ GPU の処理を全部待つ (D の optimizer step 直後の ``optimizer_updates_d``
で毎 batch GPU が空になっていた。RTX 5090 の py-spy 実測で学習 thread の約 2 割)。
``_log_with_batch_info`` は数値を CPU テンソルにしてから渡し、記録される値は
Lightning が作る場合と同じ (既定 dtype の 0 次元テンソル) に保つ。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch", reason="lightning module needs the train extra (torch).")

from piper_train.vits.lightning import VitsModel  # noqa: E402

pytestmark = pytest.mark.unit


class _Logger:
    """``self.log`` の代役: 受け取った引数を記録する。"""

    def __init__(self, world_size=1):
        self.trainer = SimpleNamespace(world_size=world_size)
        self.calls = []

    def log(self, key, value, **kwargs):
        self.calls.append((key, value, kwargs))


@pytest.mark.parametrize("value", [3, 0.25, 1.0, True, 2**40])
def test_python_number_is_logged_as_cpu_tensor_with_the_same_value(value):
    stub = _Logger()
    VitsModel._log_with_batch_info(stub, "k", value, batch_size=4)
    [(key, logged, kwargs)] = stub.calls
    assert key == "k"
    assert isinstance(logged, torch.Tensor)
    assert logged.device.type == "cpu"
    assert logged.dim() == 0
    # Lightning の ``__to_tensor`` と同じ変換 (既定 dtype) で作った値と一致する
    expected = torch.tensor(value, dtype=torch.get_default_dtype())
    assert logged.dtype == expected.dtype
    assert torch.equal(logged, expected)
    assert kwargs == {"batch_size": 4, "sync_dist": False}


def test_tensor_is_passed_through_unchanged():
    stub = _Logger(world_size=2)
    value = torch.tensor(0.5)
    VitsModel._log_with_batch_info(stub, "k", value, batch_size=4)
    [(_, logged, kwargs)] = stub.calls
    assert logged is value
    assert kwargs == {"batch_size": 4, "sync_dist": True}


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_logging_a_number_does_not_synchronize_cuda():
    stub = _Logger()
    torch.cuda.synchronize()
    busy = torch.randn(2048, 2048, device="cuda")
    torch.cuda.set_sync_debug_mode("error")
    try:
        busy = busy @ busy  # 非同期に積まれた GPU 処理がある状態で記録する
        VitsModel._log_with_batch_info(stub, "optimizer_updates_d", 7, batch_size=4)
    finally:
        torch.cuda.set_sync_debug_mode(0)
    torch.cuda.synchronize()
    assert stub.calls[0][1].item() == 7.0
