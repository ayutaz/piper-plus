"""``--no-cudnn-benchmark``: 可変長学習で cuDNN のカーネル探索を止める。

``cudnn.benchmark=True`` は新しい入力形状のたびにカーネルを探索する。VITS は batch
ごとに系列長が変わるため、探索が学習の大半を占める (RTX 5090・S4 recipe・batch 24、
毎 batch 新しい長さの合成データで 1.81 s/step → 無効化で 0.61 s/step)。
既定は従来どおり有効。
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="torch required for piper_train.__main__")

from piper_train.__main__ import configure_cudnn_benchmark, create_parser  # noqa: E402

pytestmark = pytest.mark.unit

_BASE_ARGS = ["--dataset-dir", "/tmp/test", "--batch-size", "4"]


@pytest.fixture
def restore_benchmark():
    saved = torch.backends.cudnn.benchmark
    yield
    torch.backends.cudnn.benchmark = saved


def test_default_keeps_benchmark_on(restore_benchmark):
    args = create_parser().parse_args(_BASE_ARGS)
    assert args.no_cudnn_benchmark is False
    torch.backends.cudnn.benchmark = False
    configure_cudnn_benchmark(args)
    assert torch.backends.cudnn.benchmark is True


def test_flag_turns_benchmark_off(restore_benchmark):
    args = create_parser().parse_args([*_BASE_ARGS, "--no-cudnn-benchmark"])
    torch.backends.cudnn.benchmark = True
    configure_cudnn_benchmark(args)
    assert torch.backends.cudnn.benchmark is False
